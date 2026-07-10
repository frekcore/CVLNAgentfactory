import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from database import db
from auth_utils import get_current_actor, require_registry_writer, log_authz
from event_bus import publish

router = APIRouter(prefix="/workforce", tags=["workforce"])

AUTONOMY_LEVELS = {
    1: {"label": "observation", "fr": "Observation — l'agent analyse et rapporte"},
    2: {"label": "recommendation", "fr": "Recommandation — l'agent propose des décisions"},
    3: {"label": "controlled-execution", "fr": "Exécution contrôlée — actions autorisées uniquement"},
    4: {"label": "operational-autonomy", "fr": "Autonomie opérationnelle — agit seul dans son périmètre"},
}

TASK_STATUSES = ["open", "in_progress", "done", "blocked"]
TASK_PRIORITIES = ["P0", "P1", "P2"]


class TaskPayload(BaseModel):
    agent_id: str
    title: str = Field(min_length=3)
    description: str = ""
    priority: str = "P1"
    entity: str = ""


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None


class AutonomyPayload(BaseModel):
    level: int = Field(ge=1, le=4)
    note: str = ""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def agent_autonomy(agent: dict) -> dict:
    a = agent.get("autonomy")
    if a:
        return a
    legacy = agent.get("adl", {}).get("brain", {}).get("identity", {}).get("autonomy_level", "supervised")
    level = {"supervised": 1, "semi-autonomous": 2, "autonomous": 3}.get(legacy, 1)
    return {"level": level, **AUTONOMY_LEVELS[level]}


@router.get("/autonomy-levels")
async def autonomy_levels():
    return AUTONOMY_LEVELS


@router.post("/agents/{agent_id}/autonomy")
async def set_autonomy(agent_id: str, payload: AutonomyPayload, actor: dict = Depends(require_registry_writer)):
    agent = await db.agents.find_one({"id": agent_id}, {"_id": 0, "id": 1, "autonomy": 1})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if payload.level >= 3 and not (actor["type"] == "human" and actor["role"] == "admin"):
        await log_authz(actor, "autonomy_change", f"agent:{agent_id}", False,
                        "levels 3-4 (execution) require human admin validation")
        raise HTTPException(status_code=403, detail="Autonomy levels 3-4 require human admin validation")
    autonomy = {"level": payload.level, **AUTONOMY_LEVELS[payload.level]}
    await db.agents.update_one({"id": agent_id}, {"$set": {"autonomy": autonomy, "updated_at": now_iso()}})
    await log_authz(actor, "autonomy_change", f"agent:{agent_id}", True,
                    f"level {payload.level} ({autonomy['label']}) — {payload.note}")
    await publish("agent.autonomy_changed", actor["id"], {"agent_id": agent_id, "level": payload.level})
    return {"result": "ok", "agent_id": agent_id, "autonomy": autonomy}


# ---------- Tasks ----------
@router.get("/tasks")
async def list_tasks(agent_id: Optional[str] = None, status: Optional[str] = None,
                     actor: dict = Depends(get_current_actor)):
    query = {}
    if agent_id:
        query["agent_id"] = agent_id
    if status:
        query["status"] = status
    return await db.agent_tasks.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)


@router.post("/tasks")
async def create_task(payload: TaskPayload, actor: dict = Depends(get_current_actor)):
    if actor["type"] == "human" and actor["role"] == "reader":
        raise HTTPException(status_code=403, detail="Readers cannot create tasks")
    if payload.priority not in TASK_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"priority must be one of {TASK_PRIORITIES}")
    if not await db.agents.find_one({"id": payload.agent_id}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=404, detail="Agent not found")
    task = {"id": str(uuid.uuid4()), **payload.model_dump(), "status": "open",
            "created_by": f'{actor["type"]}:{actor["id"]}', "created_at": now_iso(), "updated_at": now_iso()}
    await db.agent_tasks.insert_one({**task})
    await publish("agent.task_assigned", actor["id"], {"agent_id": payload.agent_id, "title": payload.title,
                                                       "priority": payload.priority})
    return task


@router.patch("/tasks/{task_id}")
async def update_task(task_id: str, payload: TaskUpdate, actor: dict = Depends(get_current_actor)):
    task = await db.agent_tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if actor["type"] == "service" and actor["id"] != task["agent_id"]:
        raise HTTPException(status_code=403, detail="A service identity can only update its own tasks")
    if actor["type"] == "human" and actor["role"] == "reader":
        raise HTTPException(status_code=403, detail="Readers cannot update tasks")
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "status" in update and update["status"] not in TASK_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {TASK_STATUSES}")
    update["updated_at"] = now_iso()
    await db.agent_tasks.update_one({"id": task_id}, {"$set": update})
    if update.get("status") == "done":
        await publish("agent.task_completed", actor["id"], {"agent_id": task["agent_id"], "title": task["title"]})
    return {"result": "ok"}


# ---------- Agent Workspace ----------
@router.get("/workspace/{agent_id}")
async def agent_workspace(agent_id: str, actor: dict = Depends(get_current_actor)):
    agent = await db.agents.find_one({"id": agent_id}, {"_id": 0, "adl_yaml": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    tasks = await db.agent_tasks.find({"agent_id": agent_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    reports = await db.daily_agent_reports.find({"agent_id": agent_id}, {"_id": 0}).sort("date", -1).to_list(7)
    memory_by_scope = {}
    async for m in db.memory_entries.find({"agent_id": agent_id}, {"_id": 0, "scope": 1}):
        memory_by_scope[m["scope"]] = memory_by_scope.get(m["scope"], 0) + 1
    snapshots = await db.memory_snapshots.count_documents({"agent_id": agent_id})
    knowledge = await db.knowledge_items.find({"target_agents": agent_id},
                                              {"_id": 0, "id": 1, "title": 1, "category": 1, "status": 1}).to_list(50)
    entities = await db.entities.find({"agent_ids": agent_id}, {"_id": 0, "id": 1, "name": 1, "type": 1}).to_list(20)
    open_tasks = [t for t in tasks if t["status"] in ("open", "in_progress")]

    briefing = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "objectives": agent.get("objectives", []),
        "priority_tasks": sorted(open_tasks, key=lambda t: t["priority"])[:5],
        "memory_context": (reports[0].get("next_actions", []) if reports else []),
        "last_confidence": reports[0]["confidence"] if reports else None,
    }
    return {
        "agent": {"id": agent["id"], "name": agent["name"], "pole": agent["pole"], "entity": agent["entity"],
                  "version": agent["version"], "status": agent["status"], "mission": agent["mission"],
                  "kpis": agent.get("kpis", []), "objectives": agent.get("objectives", []),
                  "tools": agent.get("adl", {}).get("tools", []),
                  "permissions": agent.get("adl", {}).get("permissions", {}),
                  "autonomy": agent_autonomy(agent)},
        "briefing": briefing,
        "tasks": tasks,
        "daily_reports": reports,
        "memory": {"entries_by_scope": memory_by_scope, "snapshots": snapshots},
        "knowledge": knowledge,
        "entities": entities,
    }
