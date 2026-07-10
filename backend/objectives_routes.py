import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from database import db
from auth_utils import get_current_actor, require_admin
from activity_journal import journal
from event_bus import publish

router = APIRouter(prefix="/objectives", tags=["objective-registry"])

STATUSES = ["active", "paused", "waiting_validation", "done", "archived"]
PRIORITIES = ["P0", "P1", "P2"]


class ObjectivePayload(BaseModel):
    title: str = Field(min_length=5)
    description: str = ""
    priority: str = "P1"
    owner: str  # agent_id (ex: AGT-011) ou human:<id>
    mission_id: Optional[str] = None
    next_action: str = Field(min_length=3)
    dependencies: List[str] = Field(default_factory=list)
    requires_human_validation: bool = False


class ObjectiveUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    next_action: Optional[str] = None
    mission_id: Optional[str] = None
    dependencies: Optional[List[str]] = None
    requires_human_validation: Optional[bool] = None
    note: str = ""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


@router.get("")
async def list_objectives(status: Optional[str] = None, owner: Optional[str] = None,
                          actor: dict = Depends(get_current_actor)):
    query = {}
    if status:
        query["status"] = status
    if owner:
        query["owner"] = owner
    return await db.objectives.find(query, {"_id": 0}).sort([("priority", 1), ("created_at", -1)]).to_list(500)


@router.get("/pursue")
async def what_to_pursue(actor: dict = Depends(get_current_actor)):
    """« Qu'est-ce que je dois continuer à faire même lorsque Laurent n'est pas connecté ? »
    Consommé par le Runtime autonome (PHASE 4)."""
    active = await db.objectives.find({"status": "active"}, {"_id": 0}) \
        .sort([("priority", 1), ("last_activity", 1)]).to_list(200)
    done_ids = {o["id"] async for o in db.objectives.find({"status": "done"}, {"_id": 0, "id": 1})}
    pursuable, blocked = [], []
    for o in active:
        unmet = [d for d in o.get("dependencies", []) if d not in done_ids]
        if unmet:
            blocked.append({**o, "unmet_dependencies": unmet})
        else:
            pursuable.append(o)
    waiting = await db.objectives.find({"status": "waiting_validation"}, {"_id": 0}).to_list(100)
    return {"pursuable": pursuable, "blocked_by_dependencies": blocked,
            "waiting_human_validation": waiting,
            "answer": f"{len(pursuable)} objectif(s) actif(s) à poursuivre, "
                      f"{len(blocked)} bloqué(s) par dépendances, "
                      f"{len(waiting)} en attente de validation de Laurent."}


@router.post("")
async def create_objective(payload: ObjectivePayload, actor: dict = Depends(get_current_actor)):
    if actor["type"] == "human" and actor["role"] == "reader":
        raise HTTPException(status_code=403, detail="Readers cannot create objectives")
    if payload.priority not in PRIORITIES:
        raise HTTPException(status_code=400, detail=f"priority must be one of {PRIORITIES}")
    if payload.owner.startswith("AGT-") and not await db.agents.find_one({"id": payload.owner}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=404, detail=f"Agent owner {payload.owner} not found")
    if payload.mission_id and not await db.missions.find_one({"id": payload.mission_id}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=404, detail="Mission not found")
    ts = now_iso()
    count = await db.objectives.count_documents({})
    obj = {"id": str(uuid.uuid4()), "code": f"OBJ-{count + 1:03d}", **payload.model_dump(),
           "status": "waiting_validation" if payload.requires_human_validation else "active",
           "last_activity": ts, "history": [],
           "created_by": f'{actor["type"]}:{actor["id"]}', "created_at": ts, "updated_at": ts}
    await db.objectives.insert_one({**obj})
    await journal("proposition" if obj["status"] == "waiting_validation" else "action_executee",
                  actor, f"Objectif {obj['code']} créé : {payload.title} (owner {payload.owner})",
                  source="objective-registry", mission_id=payload.mission_id,
                  agent_id=payload.owner if payload.owner.startswith("AGT-") else None,
                  evidence={"objective_id": obj["id"], "code": obj["code"]}, result=obj["status"])
    await publish("factory.objective_created", actor["id"],
                  {"objective_id": obj["id"], "code": obj["code"], "title": payload.title})
    return obj


@router.patch("/{objective_id}")
async def update_objective(objective_id: str, payload: ObjectiveUpdate,
                           actor: dict = Depends(get_current_actor)):
    if actor["type"] == "human" and actor["role"] == "reader":
        raise HTTPException(status_code=403, detail="Readers cannot update objectives")
    obj = await db.objectives.find_one({"id": objective_id}, {"_id": 0})
    if not obj:
        raise HTTPException(status_code=404, detail="Objective not found")
    update = {k: v for k, v in payload.model_dump().items() if v is not None and k != "note"}
    if "status" in update:
        if update["status"] not in STATUSES:
            raise HTTPException(status_code=400, detail=f"status must be one of {STATUSES}")
        if update["status"] in ("done", "archived") and obj.get("requires_human_validation") \
                and not (actor["type"] == "human" and actor["role"] == "admin"):
            raise HTTPException(status_code=403,
                                detail="Cet objectif exige la validation humaine de Laurent pour être clos ou archivé")
    if "priority" in update and update["priority"] not in PRIORITIES:
        raise HTTPException(status_code=400, detail=f"priority must be one of {PRIORITIES}")
    ts = now_iso()
    actor_label = f'{actor["type"]}:{actor["id"]}'
    await db.objectives.update_one(
        {"id": objective_id},
        {"$set": {**update, "last_activity": ts, "updated_at": ts},
         "$push": {"history": {"actor": actor_label, "timestamp": ts,
                               "changes": update, "note": payload.note}}})
    updated = await db.objectives.find_one({"id": objective_id}, {"_id": 0})
    jtype = "decision_humaine" if (actor["type"] == "human" and "status" in update) else "action_executee"
    await journal(jtype, actor,
                  f"Objectif {obj['code']} mis à jour : {', '.join(f'{k}={v}' for k, v in update.items())}",
                  source="objective-registry", mission_id=updated.get("mission_id"),
                  agent_id=updated["owner"] if updated["owner"].startswith("AGT-") else None,
                  evidence={"objective_id": objective_id, "note": payload.note}, result=updated["status"])
    return updated
