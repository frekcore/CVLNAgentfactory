"""Mission OS (PHASE B) — Entity Registry (entités existantes uniquement), Strategic Objectives (placeholders),
Alignment Engine souverain (score 0-1 : poids × pertinence lexicale × probabilité historique).
Dashboard lecture seule. Aucune injection de [MISSION CONTEXT] dans le flux réel (condition Laurent)."""
import uuid
import math
import re
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from database import db
from auth_utils import get_current_actor, require_admin
from activity_journal import journal

router = APIRouter(prefix="/mission-os", tags=["mission-os"])

STOP = {"le", "la", "les", "de", "des", "du", "un", "une", "et", "en", "pour", "sur", "avec", "dans",
        "est", "sont", "the", "a", "of", "to", "and", "in", "ce", "cette", "que", "qui", "par", "au", "aux", "d", "l"}


def tokenize(text: str) -> set:
    return {w for w in re.findall(r"[a-zà-ÿ0-9]{2,}", (text or "").lower()) if w not in STOP}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


class ObjectivePayload(BaseModel):
    entity_id: str
    title: str = Field(min_length=5)
    description: str = ""
    weight: float = Field(0.5, ge=0, le=1)
    horizon: str = "2026-Q4"
    key_results: List[dict] = Field(default_factory=list)  # placeholders acceptés
    status: str = "active"


class LinkPayload(BaseModel):
    agent_id: str
    objective_id: str
    role: str = "contributor"


class AlignmentPayload(BaseModel):
    agent_id: str
    task_description: str = Field(min_length=5)
    entity_id: Optional[str] = None
    apply: bool = False  # False = évaluation pure (aucune escalade réelle) — flux réel non activé


@router.get("/entities")
async def list_entities(actor: dict = Depends(get_current_actor)):
    """Entity Registry — lecture des entités EXISTANTES uniquement (aucune création ici)."""
    entities = await db.entities.find({}, {"_id": 0}).to_list(100)
    for e in entities:
        e["strategic_objectives"] = await db.strategic_objectives.count_documents({"entity_id": e["id"]})
    return entities


@router.get("/objectives")
async def list_objectives(entity_id: Optional[str] = None, actor: dict = Depends(get_current_actor)):
    q = {"entity_id": entity_id} if entity_id else {}
    return await db.strategic_objectives.find(q, {"_id": 0}).sort("weight", -1).to_list(200)


@router.post("/objectives")
async def create_objective(payload: ObjectivePayload, actor: dict = Depends(require_admin)):
    if not await db.entities.find_one({"id": payload.entity_id}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=404, detail="Entité inconnue — aucune création d'entité sans validation Laurent")
    count = await db.strategic_objectives.count_documents({})
    obj = {"id": str(uuid.uuid4()), "code": f"SO-{count + 1:03d}", **payload.model_dump(),
           "placeholder": len(payload.key_results) == 0,
           "created_by": f'human:{actor["id"]}', "created_at": now_iso(), "updated_at": now_iso()}
    await db.strategic_objectives.insert_one({**obj})
    await journal("action_executee", actor, f"Objectif stratégique {obj['code']} créé : {payload.title} (poids {payload.weight})",
                  source="mission-os", evidence={"objective_id": obj["id"], "entity_id": payload.entity_id},
                  result="created")
    return obj


@router.post("/links")
async def link_agent(payload: LinkPayload, actor: dict = Depends(require_admin)):
    if not await db.agents.find_one({"id": payload.agent_id}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=404, detail="Agent inconnu")
    if not await db.strategic_objectives.find_one({"id": payload.objective_id}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=404, detail="Objectif inconnu")
    link = {"id": str(uuid.uuid4()), **payload.model_dump(), "created_at": now_iso()}
    await db.agent_objective_links.update_one(
        {"agent_id": payload.agent_id, "objective_id": payload.objective_id},
        {"$setOnInsert": link}, upsert=True)
    return link


@router.get("/links/{agent_id}")
async def agent_links(agent_id: str, actor: dict = Depends(get_current_actor)):
    return await db.agent_objective_links.find({"agent_id": agent_id}, {"_id": 0}).to_list(50)


async def completion_likelihood(agent_id: str) -> float:
    """Probabilité de succès basée sur l'historique réel de l'agent (journal v2)."""
    ok = await db.activity_journal.count_documents({"agent_id": agent_id, "type": "action_executee"})
    err = await db.activity_journal.count_documents({"agent_id": agent_id, "type": "erreur"})
    if ok + err == 0:
        return 0.7  # défaut sans historique
    return round(max(0.1, min(1.0, ok / (ok + err))), 3)


async def compute_alignment(agent_id: str, task_description: str, entity_id: str | None) -> dict:
    """Alignment Score = Σ (objective_weight × task_relevance × completion_likelihood), borné à 1."""
    task_terms = tokenize(task_description)
    linked_ids = [l["objective_id"] async for l in db.agent_objective_links.find({"agent_id": agent_id}, {"_id": 0})]
    q = {"status": "active"}
    ors = []
    if linked_ids:
        ors.append({"id": {"$in": linked_ids}})
    if entity_id:
        ors.append({"entity_id": entity_id})
    if ors:
        q["$or"] = ors
    objectives = await db.strategic_objectives.find(q, {"_id": 0}).to_list(100)
    likelihood = await completion_likelihood(agent_id)
    breakdown, score = [], 0.0
    for o in objectives:
        obj_terms = tokenize(o["title"] + " " + o.get("description", "") + " " +
                             " ".join(str(kr.get("kr", "")) for kr in o.get("key_results", [])))
        overlap = task_terms & obj_terms
        relevance = round(len(overlap) / math.sqrt(max(len(task_terms), 1) * max(len(obj_terms), 1)), 3) if overlap else 0.0
        contrib = round(o["weight"] * relevance * likelihood, 4)
        score += contrib
        if relevance > 0:
            breakdown.append({"objective": o["code"], "title": o["title"], "weight": o["weight"],
                              "relevance": relevance, "likelihood": likelihood, "contribution": contrib,
                              "matched_terms": sorted(overlap)[:6]})
    score = round(min(score * 3.0, 1.0), 3)  # facteur d'échelle lexical (calibré sur jeu fictif)
    decision = "EXECUTION_AUTORISEE" if score > 0.6 else ("AVERTISSEMENT_CONFIRMATION_REQUISE" if score >= 0.3 else "ESCALADE_HORS_MISSION")
    reasoning = (f"Score {score} sur {len(objectives)} objectif(s) actif(s) "
                 f"({'liés à l’agent + entité' if linked_ids and entity_id else 'liés à l’agent' if linked_ids else 'de l’entité' if entity_id else 'globaux'}), "
                 f"probabilité historique {likelihood}. "
                 + (f"Contributions principales : {', '.join(b['objective'] for b in breakdown[:3])}." if breakdown
                    else "Aucun recouvrement lexical avec les objectifs stratégiques — tâche hors mission."))
    return {"agent_id": agent_id, "score": score, "decision": decision, "reasoning": reasoning,
            "likelihood": likelihood, "objectives_evaluated": len(objectives),
            "breakdown": sorted(breakdown, key=lambda b: -b["contribution"])[:5]}


@router.post("/alignment")
async def alignment(payload: AlignmentPayload, actor: dict = Depends(get_current_actor)):
    result = await compute_alignment(payload.agent_id, payload.task_description, payload.entity_id)
    result["mode"] = "evaluation_only" if not payload.apply else "applied"
    if payload.apply and result["decision"] == "ESCALADE_HORS_MISSION":
        from gate_routes import gate_check
        decision = await gate_check({"type": "system", "id": "mission-os", "name": "Mission OS"},
                                    "propose", f"[ART-006] Tâche hors mission (score {result['score']}) : "
                                               f"{payload.task_description[:120]}",
                                    agent_id=payload.agent_id, source="mission-os")
        result["escalade"] = decision
    await journal("analyse", actor, f"Alignment {payload.agent_id} : score {result['score']} → {result['decision']}",
                  source="mission-os", agent_id=payload.agent_id,
                  evidence={"task": payload.task_description[:150], "score": result["score"],
                            "reasoning": result["reasoning"][:200]}, result=result["decision"])
    return result


@router.get("/dashboard/{entity_id}")
async def entity_dashboard(entity_id: str, actor: dict = Depends(get_current_actor)):
    """Lecture seule (condition Laurent)."""
    entity = await db.entities.find_one({"id": entity_id}, {"_id": 0})
    if not entity:
        raise HTTPException(status_code=404, detail="Entité inconnue")
    objectives = await db.strategic_objectives.find({"entity_id": entity_id}, {"_id": 0}).sort("weight", -1).to_list(50)
    obj_ids = [o["id"] for o in objectives]
    links = await db.agent_objective_links.find({"objective_id": {"$in": obj_ids}}, {"_id": 0}).to_list(200)
    evals = await db.activity_journal.find({"source": "mission-os", "type": "analyse"}, {"_id": 0}) \
        .sort("timestamp", -1).to_list(10)
    return {"entity": entity, "objectives": objectives, "agent_links": links,
            "recent_alignments": evals, "read_only": True}
