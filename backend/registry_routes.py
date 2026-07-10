import uuid
import difflib
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from database import db
from adl_schema import parse_adl_yaml, adl_to_yaml, allowed_transitions, semver_tuple, LifecycleStatus
from auth_utils import get_current_actor, require_registry_writer, log_authz
from event_bus import publish

router = APIRouter(prefix="/registry", tags=["registry"])

ECOSYSTEM_TARGET = 284


class ADLPayload(BaseModel):
    adl_yaml: str


class LifecyclePayload(BaseModel):
    target_status: str
    note: str = ""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


async def find_duplicates(agent_id: str, name: str, mission: str):
    dups = []
    async for a in db.agents.find({}, {"_id": 0, "id": 1, "name": 1, "mission": 1}):
        if a["id"] == agent_id:
            continue
        reasons = []
        if a["name"].strip().lower() == name.strip().lower():
            reasons.append("identical name")
        sim = similarity(a.get("mission", ""), mission)
        if sim >= 0.75:
            reasons.append(f"similar mission ({int(sim*100)}%)")
        if reasons:
            dups.append({"id": a["id"], "name": a["name"], "reasons": reasons})
    return dups


@router.get("/stats")
async def registry_stats(actor: dict = Depends(get_current_actor)):
    agents = await db.agents.find({}, {"_id": 0, "status": 1, "pole": 1, "entity": 1}).to_list(2000)
    by_status, by_pole, by_entity = {}, {}, {}
    for a in agents:
        by_status[a["status"]] = by_status.get(a["status"], 0) + 1
        by_pole[a["pole"]] = by_pole.get(a["pole"], 0) + 1
        by_entity[a["entity"]] = by_entity.get(a["entity"], 0) + 1
    return {"total": len(agents), "target": ECOSYSTEM_TARGET,
            "by_status": by_status, "by_pole": by_pole, "by_entity": by_entity}


@router.get("/agents")
async def list_agents(pole: Optional[str] = None, entity: Optional[str] = None,
                      status: Optional[str] = None, search: Optional[str] = None,
                      actor: dict = Depends(get_current_actor)):
    query = {}
    if pole:
        query["pole"] = pole
    if entity:
        query["entity"] = entity
    if status:
        query["status"] = status
    if search:
        query["$or"] = [{"name": {"$regex": search, "$options": "i"}},
                        {"id": {"$regex": search, "$options": "i"}},
                        {"mission": {"$regex": search, "$options": "i"}}]
    agents = await db.agents.find(query, {"_id": 0, "adl": 0, "adl_yaml": 0}).sort("id", 1).to_list(2000)
    return agents


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str, actor: dict = Depends(get_current_actor)):
    agent = await db.agents.find_one({"id": agent_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent["allowed_transitions"] = allowed_transitions(agent["status"])
    return agent


@router.get("/agents/{agent_id}/versions")
async def get_versions(agent_id: str, actor: dict = Depends(get_current_actor)):
    versions = await db.versions.find({"agent_id": agent_id}, {"_id": 0, "adl": 0}).sort("timestamp", -1).to_list(500)
    return versions


@router.get("/agents/{agent_id}/export")
async def export_adl(agent_id: str, actor: dict = Depends(get_current_actor)):
    agent = await db.agents.find_one({"id": agent_id}, {"_id": 0, "adl_yaml": 1, "id": 1, "name": 1})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"id": agent["id"], "name": agent["name"], "adl_yaml": agent["adl_yaml"]}


@router.get("/agents/{agent_id}/diff")
async def diff_versions(agent_id: str, from_version: str, to_version: str,
                        actor: dict = Depends(get_current_actor)):
    v_from = await db.versions.find_one({"agent_id": agent_id, "version": from_version, "type": "version"}, {"_id": 0})
    v_to = await db.versions.find_one({"agent_id": agent_id, "version": to_version, "type": "version"}, {"_id": 0})
    if not v_from or not v_to:
        raise HTTPException(status_code=404, detail="Version not found")
    diff = list(difflib.unified_diff(
        v_from["adl_yaml"].splitlines(), v_to["adl_yaml"].splitlines(),
        fromfile=f"{agent_id}@{from_version}", tofile=f"{agent_id}@{to_version}", lineterm=""))
    return {"from_version": from_version, "to_version": to_version, "diff": diff}


@router.post("/compile")
async def compile_agent(payload: ADLPayload, actor: dict = Depends(require_registry_writer)):
    doc, errors = parse_adl_yaml(payload.adl_yaml)
    if errors:
        await publish("factory.compile", actor["id"], {"result": "validation_failed", "errors": errors[:5]})
        raise HTTPException(status_code=422, detail={"type": "validation", "errors": errors})

    meta = doc.agent
    dups = await find_duplicates(meta.id, meta.name, meta.mission)
    existing = await db.agents.find_one({"id": meta.id}, {"_id": 0})

    if dups and not existing:
        await publish("factory.compile", actor["id"], {"result": "duplicate_detected", "agent_id": meta.id, "duplicates": dups})
        raise HTTPException(status_code=409, detail={"type": "duplicate", "duplicates": dups})

    adl_dict = doc.model_dump()
    canonical_yaml = adl_to_yaml(adl_dict)
    ts = now_iso()

    if existing:
        if semver_tuple(meta.version) <= semver_tuple(existing["version"]):
            raise HTTPException(status_code=409, detail={
                "type": "version",
                "message": f"Version {meta.version} must be greater than current {existing['version']}"})
        update = {"name": meta.name, "pole": meta.pole, "entity": meta.entity,
                  "version": meta.version, "mission": meta.mission, "vision": meta.vision,
                  "objectives": meta.objectives, "kpis": meta.kpis,
                  "adl": adl_dict, "adl_yaml": canonical_yaml, "updated_at": ts}
        await db.agents.update_one({"id": meta.id}, {"$set": update})
        await db.versions.insert_one({
            "id": str(uuid.uuid4()), "agent_id": meta.id, "type": "version",
            "version": meta.version, "status": existing["status"], "adl": adl_dict,
            "adl_yaml": canonical_yaml, "actor": f'{actor["type"]}:{actor["id"]}',
            "note": "Compile — new version", "timestamp": ts})
        await log_authz(actor, "registry_write", f"agent:{meta.id}", True, f"compiled version {meta.version}")
        await publish("agent.updated", actor["id"], {"agent_id": meta.id, "version": meta.version})
        await publish("factory.compile", actor["id"], {"result": "success", "agent_id": meta.id, "mode": "update"})
        return {"result": "updated", "agent_id": meta.id, "version": meta.version, "status": existing["status"]}

    agent_doc = {"id": meta.id, "name": meta.name, "pole": meta.pole, "entity": meta.entity,
                 "version": meta.version, "status": LifecycleStatus.DRAFT.value,
                 "mission": meta.mission, "vision": meta.vision,
                 "objectives": meta.objectives, "kpis": meta.kpis,
                 "adl": adl_dict, "adl_yaml": canonical_yaml,
                 "created_at": ts, "updated_at": ts}
    await db.agents.insert_one({**agent_doc})
    await db.versions.insert_one({
        "id": str(uuid.uuid4()), "agent_id": meta.id, "type": "version",
        "version": meta.version, "status": LifecycleStatus.DRAFT.value, "adl": adl_dict,
        "adl_yaml": canonical_yaml, "actor": f'{actor["type"]}:{actor["id"]}',
        "note": "Compile — creation (Draft)", "timestamp": ts})
    await log_authz(actor, "registry_write", f"agent:{meta.id}", True, "compiled new agent (Draft)")
    await publish("agent.created", actor["id"], {"agent_id": meta.id, "name": meta.name, "version": meta.version})
    await publish("factory.compile", actor["id"], {"result": "success", "agent_id": meta.id, "mode": "create"})
    return {"result": "created", "agent_id": meta.id, "version": meta.version, "status": "Draft"}


@router.post("/agents/{agent_id}/lifecycle")
async def transition_lifecycle(agent_id: str, payload: LifecyclePayload,
                               actor: dict = Depends(require_registry_writer)):
    agent = await db.agents.find_one({"id": agent_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    allowed = allowed_transitions(agent["status"])
    if payload.target_status not in allowed:
        raise HTTPException(status_code=400, detail=f"Transition {agent['status']} → {payload.target_status} not allowed. Allowed: {allowed}")
    if agent["status"] == "Beta" and payload.target_status == "Production":
        if not (actor["type"] == "human" and actor["role"] == "admin"):
            await log_authz(actor, "lifecycle_transition", f"agent:{agent_id}", False,
                            "Beta → Production requires human admin validation")
            raise HTTPException(status_code=403, detail="Beta → Production requires human admin validation")
    ts = now_iso()
    await db.agents.update_one({"id": agent_id}, {"$set": {"status": payload.target_status, "updated_at": ts}})
    await db.versions.insert_one({
        "id": str(uuid.uuid4()), "agent_id": agent_id, "type": "lifecycle",
        "version": agent["version"], "status": payload.target_status,
        "from_status": agent["status"],
        "actor": f'{actor["type"]}:{actor["id"]}', "note": payload.note or f"{agent['status']} → {payload.target_status}",
        "timestamp": ts})
    await log_authz(actor, "lifecycle_transition", f"agent:{agent_id}", True,
                    f"{agent['status']} → {payload.target_status}")
    topic = "agent.archived" if payload.target_status == "Archive" else "agent.updated"
    await publish(topic, actor["id"], {"agent_id": agent_id, "from": agent["status"], "to": payload.target_status})
    return {"result": "ok", "agent_id": agent_id, "status": payload.target_status}
