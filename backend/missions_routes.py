import re
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from database import db
from auth_utils import get_current_actor, require_registry_writer, require_admin, log_authz
from event_bus import publish
from notifier import notify

router = APIRouter(prefix="/missions", tags=["mission-engine"])

WORKFLOW = ["specification", "design", "development", "testing", "security_review",
            "deployment", "monitoring"]
STATUSES = ["assigned", "in_progress", "delivered", "validated", "rejected"]
STOPWORDS = {"le", "la", "les", "de", "des", "du", "un", "une", "pour", "sur", "avec", "et", "en",
             "cette", "ce", "mes", "mon", "moi", "crée", "cree", "creer", "prépare", "prepare",
             "analyse", "analyser", "construis", "fais", "the", "a", "for", "les", "aux"}


class OrchestratePayload(BaseModel):
    request_text: str = Field(min_length=5)
    entity: Optional[str] = None


class MissionPayload(BaseModel):
    title: str = Field(min_length=5)
    objective: str = Field(min_length=10)
    entity: str
    agent_ids: List[str] = Field(min_length=1)
    deadline: Optional[str] = None
    autonomy_level: int = Field(2, ge=1, le=4)
    expected_results: List[str] = Field(default_factory=list)
    mission_type: str = "analysis"  # analysis | strategy | application | process
    origin_request: str = ""


class DeliverPayload(BaseModel):
    summary: str = Field(min_length=10)
    deliverables: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def tokenize(text: str):
    return [w for w in re.findall(r"[a-zà-ÿ]{3,}", text.lower()) if w not in STOPWORDS]


@router.post("/orchestrate")
async def orchestrate(payload: OrchestratePayload, actor: dict = Depends(get_current_actor)):
    """Agent Orchestrator : intention → sélection des agents compétents → brouillon de mission."""
    words = set(tokenize(payload.request_text))
    agents = await db.agents.find({"status": {"$nin": ["Archive"]}},
                                  {"_id": 0, "id": 1, "name": 1, "pole": 1, "entity": 1,
                                   "mission": 1, "objectives": 1, "adl.knowledge": 1}).to_list(2000)
    scored = []
    for a in agents:
        corpus = " ".join([a["name"], a["pole"], a.get("mission", ""), " ".join(a.get("objectives", [])),
                           " ".join(k.get("source", "") for k in a.get("adl", {}).get("knowledge", []))])
        overlap = words & set(tokenize(corpus))
        if payload.entity and payload.entity.lower() in a["entity"].lower():
            overlap.add("_entity_match")
        if overlap:
            scored.append({"agent_id": a["id"], "name": a["name"], "pole": a["pole"],
                           "entity": a["entity"], "score": len(overlap),
                           "matched_on": sorted(w for w in overlap if not w.startswith("_"))[:6]})
    scored.sort(key=lambda x: -x["score"])
    mission_type = "application" if any(w in words for w in ("application", "app", "outil", "logiciel", "plateforme")) \
        else "strategy" if any(w in words for w in ("stratégie", "strategie", "plan", "marketing")) \
        else "process" if any(w in words for w in ("processus", "process", "workflow", "procédure")) \
        else "analysis"
    await publish("factory.orchestration", actor["id"],
                  {"request": payload.request_text[:200], "recommended": [s["agent_id"] for s in scored[:5]],
                   "mission_type": mission_type})
    return {"intent": {"mission_type": mission_type, "keywords": sorted(words)[:12]},
            "recommended_agents": scored[:5],
            "draft_mission": {
                "title": payload.request_text[:80],
                "objective": payload.request_text,
                "entity": payload.entity or (scored[0]["entity"] if scored else "CVLN Holding"),
                "agent_ids": [s["agent_id"] for s in scored[:2]],
                "mission_type": mission_type,
                "autonomy_level": 2,
                "expected_results": ["analyse", "recommandations", "plan d'action", "rapport"]}}


@router.post("")
async def create_mission(payload: MissionPayload, actor: dict = Depends(require_registry_writer)):
    valid = [a["id"] async for a in db.agents.find({"id": {"$in": payload.agent_ids}}, {"_id": 0, "id": 1})]
    if not valid:
        raise HTTPException(status_code=404, detail="No valid agents")
    ts = now_iso()
    mission = {"id": str(uuid.uuid4()), **payload.model_dump(), "agent_ids": valid,
               "status": "assigned", "workflow_stage": WORKFLOW[0],
               "workflow_history": [{"stage": WORKFLOW[0], "timestamp": ts, "actor": f'{actor["type"]}:{actor["id"]}'}],
               "delivery": None, "created_by": f'{actor["type"]}:{actor["id"]}',
               "created_at": ts, "updated_at": ts}
    await db.missions.insert_one({**mission})
    for aid in valid:
        await db.agent_tasks.insert_one({
            "id": str(uuid.uuid4()), "agent_id": aid, "entity": payload.entity,
            "title": f"[Mission] {payload.title}", "description": payload.objective,
            "priority": "P0", "status": "open", "mission_id": mission["id"],
            "created_by": f'{actor["type"]}:{actor["id"]}', "created_at": ts, "updated_at": ts})
    await log_authz(actor, "mission_create", f"mission:{mission['id']}", True, payload.title)
    await publish("agent.mission_assigned", actor["id"],
                  {"mission_id": mission["id"], "title": payload.title, "agents": valid})
    await notify(4, "Nouvelle mission assignée",
                 f"« {payload.title} » → {', '.join(valid)} ({payload.entity})", source="mission-engine")
    return mission


@router.get("")
async def list_missions(status: Optional[str] = None, agent_id: Optional[str] = None,
                        actor: dict = Depends(get_current_actor)):
    query = {}
    if status:
        query["status"] = status
    if agent_id:
        query["agent_ids"] = agent_id
    return await db.missions.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/{mission_id}/advance")
async def advance_stage(mission_id: str, actor: dict = Depends(get_current_actor)):
    if actor["type"] == "human" and actor["role"] == "reader":
        raise HTTPException(status_code=403, detail="Readers cannot advance missions")
    mission = await db.missions.find_one({"id": mission_id}, {"_id": 0})
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    idx = WORKFLOW.index(mission["workflow_stage"])
    if idx + 1 >= len(WORKFLOW):
        raise HTTPException(status_code=409, detail="Workflow complete — use /deliver")
    nxt = WORKFLOW[idx + 1]
    ts = now_iso()
    await db.missions.update_one({"id": mission_id},
                                 {"$set": {"workflow_stage": nxt, "status": "in_progress", "updated_at": ts},
                                  "$push": {"workflow_history": {"stage": nxt, "timestamp": ts,
                                                                 "actor": f'{actor["type"]}:{actor["id"]}'}}})
    await publish("agent.mission_progress", actor["id"], {"mission_id": mission_id, "stage": nxt})
    return {"result": "ok", "workflow_stage": nxt}


@router.post("/{mission_id}/deliver")
async def deliver_mission(mission_id: str, payload: DeliverPayload, actor: dict = Depends(get_current_actor)):
    if actor["type"] == "human" and actor["role"] == "reader":
        raise HTTPException(status_code=403, detail="Readers cannot deliver missions")
    mission = await db.missions.find_one({"id": mission_id}, {"_id": 0})
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission["status"] in ("delivered", "validated"):
        raise HTTPException(status_code=409, detail=f"Mission already {mission['status']}")
    ts = now_iso()
    await db.missions.update_one({"id": mission_id},
                                 {"$set": {"status": "delivered", "updated_at": ts,
                                           "delivery": {**payload.model_dump(),
                                                        "delivered_by": f'{actor["type"]}:{actor["id"]}',
                                                        "delivered_at": ts}}})
    await publish("agent.mission_delivered", actor["id"], {"mission_id": mission_id, "title": mission["title"]})
    await notify(2, "Mission livrée — validation requise",
                 f"« {mission['title']} » ({mission['entity']}) livrée par {', '.join(mission['agent_ids'])}. "
                 f"Résumé : {payload.summary[:150]}", source="mission-engine",
                 meta={"mission_id": mission_id})
    return {"result": "delivered"}


@router.post("/{mission_id}/validate")
async def validate_mission(mission_id: str, decision: str = "validated", actor: dict = Depends(require_admin)):
    if decision not in ("validated", "rejected"):
        raise HTTPException(status_code=400, detail="decision must be validated or rejected")
    mission = await db.missions.find_one({"id": mission_id}, {"_id": 0})
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission["status"] != "delivered":
        raise HTTPException(status_code=409, detail="Mission must be delivered first")
    ts = now_iso()
    await db.missions.update_one({"id": mission_id},
                                 {"$set": {"status": decision, "validated_by": f'human:{actor["id"]}',
                                           "validated_at": ts, "updated_at": ts}})
    if decision == "validated":
        await db.agent_tasks.update_many({"mission_id": mission_id}, {"$set": {"status": "done", "updated_at": ts}})
    await log_authz(actor, "mission_validate", f"mission:{mission_id}", True, decision)
    await publish("agent.mission_validated", actor["id"], {"mission_id": mission_id, "decision": decision})
    return {"result": decision}


# ---------- Agent Performance System ----------
@router.get("/performance")
async def performance_scores(actor: dict = Depends(get_current_actor)):
    agents = await db.agents.find({"status": {"$ne": "Archive"}},
                                  {"_id": 0, "id": 1, "name": 1, "pole": 1, "entity": 1, "status": 1}).to_list(2000)
    tasks_done, missions_by_agent, conf, finance = {}, {}, {}, {}
    async for t in db.agent_tasks.find({"status": "done"}, {"_id": 0, "agent_id": 1}):
        tasks_done[t["agent_id"]] = tasks_done.get(t["agent_id"], 0) + 1
    async for m in db.missions.find({"status": "validated"}, {"_id": 0, "agent_ids": 1}):
        for aid in m["agent_ids"]:
            missions_by_agent[aid] = missions_by_agent.get(aid, 0) + 1
    async for r in db.daily_agent_reports.find({}, {"_id": 0, "agent_id": 1, "confidence": 1}):
        conf.setdefault(r["agent_id"], []).append(r["confidence"])
    async for e in db.finance_entries.find({"agent_id": {"$ne": None}}, {"_id": 0, "agent_id": 1, "type": 1, "amount": 1}):
        f = finance.setdefault(e["agent_id"], {"cost": 0, "revenue": 0})
        f[e["type"]] += e["amount"]
    out = []
    for a in agents:
        td = tasks_done.get(a["id"], 0)
        mv = missions_by_agent.get(a["id"], 0)
        avg_conf = round(sum(conf[a["id"]]) / len(conf[a["id"]]), 1) if a["id"] in conf else None
        f = finance.get(a["id"], {"cost": 0, "revenue": 0})
        net = round(f["revenue"] - f["cost"], 2)
        score = min(100, round(td * 8 + mv * 25 + (avg_conf or 0) * 0.35 + max(0, min(20, net / 50))))
        out.append({"agent_id": a["id"], "name": a["name"], "pole": a["pole"], "entity": a["entity"],
                    "status": a["status"], "tasks_done": td, "missions_validated": mv,
                    "avg_confidence": avg_conf, "net_value": net, "performance_score": score})
    out.sort(key=lambda x: -x["performance_score"])
    return out
