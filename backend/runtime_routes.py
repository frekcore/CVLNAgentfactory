import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from database import db
from auth_utils import get_current_actor, log_authz
from activity_journal import journal
from event_bus import publish
from gate_routes import gate_check

router = APIRouter(prefix="/runtime", tags=["agent-runtime"])

RUNTIME_STATES = ["actif", "sommeil", "attente_validation", "erreur", "suspendu", "termine"]
TRANSITIONS = {
    "sommeil": ["actif", "erreur", "suspendu"],
    "actif": ["sommeil", "attente_validation", "erreur", "suspendu", "termine"],
    "attente_validation": ["actif", "suspendu", "erreur"],
    "erreur": ["actif", "suspendu"],
    "suspendu": ["actif", "termine"],
    "termine": [],
}
JOURNAL_TYPE_BY_STATE = {"erreur": "erreur", "termine": "cloture"}


class StatePayload(BaseModel):
    state: str
    note: str = ""
    last_action: str = ""
    next_action: str = ""
    validation_id: Optional[str] = None


class CheckpointPayload(BaseModel):
    last_action: str = Field(min_length=3)
    next_action: str = ""
    active_objective: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)
    context: dict = Field(default_factory=dict)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def agent_runtime(agent: dict) -> dict:
    rt = agent.get("runtime")
    if rt:
        return rt
    return {"state": "sommeil", "since": None, "initialized": False, "note": "runtime non initialisé"}


def check_actor_can_operate(actor: dict, agent_id: str):
    if actor["type"] == "human" and actor["role"] == "reader":
        raise HTTPException(status_code=403, detail="Readers cannot operate the runtime")
    if actor["type"] == "service" and actor["id"] not in (agent_id, "AGT-000"):
        raise HTTPException(status_code=403,
                            detail="A service identity only operates its own runtime (or AGT-000 as architect)")


async def create_checkpoint(agent_id: str, state: str, actor: dict, last_action: str,
                            next_action: str, active_objective=None, dependencies=None, context=None) -> dict:
    if active_objective is None:
        obj = await db.objectives.find_one({"owner": agent_id, "status": "active"},
                                           {"_id": 0, "id": 1, "code": 1, "title": 1, "next_action": 1},
                                           sort=[("priority", 1)])
        active_objective = obj["code"] if obj else None
        if not next_action and obj:
            next_action = obj.get("next_action", "")
    cp = {"id": str(uuid.uuid4()), "agent_id": agent_id, "state": state,
          "last_action": last_action, "next_action": next_action,
          "active_objective": active_objective, "dependencies": dependencies or [],
          "context": context or {}, "created_by": f'{actor["type"]}:{actor["id"]}',
          "timestamp": now_iso()}
    await db.agent_checkpoints.insert_one({**cp})
    await publish("agent.checkpoint_created", actor["id"], {"agent_id": agent_id, "checkpoint_id": cp["id"]})
    return cp


@router.get("/status")
async def runtime_status(actor: dict = Depends(get_current_actor)):
    agents = await db.agents.find({}, {"_id": 0, "id": 1, "name": 1, "pole": 1, "entity": 1,
                                       "status": 1, "runtime": 1}).to_list(2000)
    out, by_state = [], {s: 0 for s in RUNTIME_STATES}
    for a in agents:
        rt = agent_runtime(a)
        by_state[rt["state"]] = by_state.get(rt["state"], 0) + 1
        out.append({**{k: a.get(k) for k in ("id", "name", "pole", "entity", "status")}, "runtime": rt})
    return {"by_state": by_state, "agents": out}


@router.get("/agents/{agent_id}")
async def get_agent_runtime(agent_id: str, actor: dict = Depends(get_current_actor)):
    agent = await db.agents.find_one({"id": agent_id}, {"_id": 0, "id": 1, "name": 1, "runtime": 1})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    cp = await db.agent_checkpoints.find_one({"agent_id": agent_id}, {"_id": 0}, sort=[("timestamp", -1)])
    return {"agent_id": agent_id, "name": agent["name"], "runtime": agent_runtime(agent),
            "allowed_transitions": TRANSITIONS[agent_runtime(agent)["state"]],
            "last_checkpoint": cp}


@router.get("/agents/{agent_id}/checkpoints")
async def list_checkpoints(agent_id: str, limit: int = 20, actor: dict = Depends(get_current_actor)):
    return await db.agent_checkpoints.find({"agent_id": agent_id}, {"_id": 0}) \
        .sort("timestamp", -1).to_list(min(limit, 100))


@router.post("/agents/{agent_id}/checkpoint")
async def save_checkpoint(agent_id: str, payload: CheckpointPayload, actor: dict = Depends(get_current_actor)):
    check_actor_can_operate(actor, agent_id)
    agent = await db.agents.find_one({"id": agent_id}, {"_id": 0, "id": 1, "runtime": 1})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    cp = await create_checkpoint(agent_id, agent_runtime(agent)["state"], actor,
                                 payload.last_action, payload.next_action,
                                 payload.active_objective, payload.dependencies, payload.context)
    await journal("observation", actor, f"Checkpoint sauvegardé pour {agent_id} : {payload.last_action}",
                  source="agent-runtime", agent_id=agent_id,
                  evidence={"checkpoint_id": cp["id"]}, result="checkpoint")
    return cp


@router.post("/agents/{agent_id}/state")
async def change_state(agent_id: str, payload: StatePayload, actor: dict = Depends(get_current_actor)):
    check_actor_can_operate(actor, agent_id)
    if payload.state not in RUNTIME_STATES:
        raise HTTPException(status_code=400, detail=f"state must be one of {RUNTIME_STATES}")
    agent = await db.agents.find_one({"id": agent_id}, {"_id": 0, "id": 1, "name": 1, "runtime": 1})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    current = agent_runtime(agent)["state"]
    if payload.state not in TRANSITIONS[current]:
        await journal("action_bloquee", actor,
                      f"Transition runtime interdite pour {agent_id} : {current} → {payload.state}",
                      source="agent-runtime", agent_id=agent_id, result="refused")
        raise HTTPException(status_code=409,
                            detail=f"Transition {current} → {payload.state} interdite (autorisées : {TRANSITIONS[current]})")

    # Critical transitions go through the Permission Gate
    critical_action = None
    if payload.state == "termine":
        critical_action = "agent_termination"
    elif current == "suspendu" and payload.state == "actif":
        critical_action = "agent_reactivation"
    if critical_action:
        decision = await gate_check(actor, critical_action,
                                    f"Transition runtime {agent_id} : {current} → {payload.state}. {payload.note}",
                                    agent_id=agent_id, validation_id=payload.validation_id,
                                    source="agent-runtime")
        if not decision["allowed"]:
            raise HTTPException(status_code=423, detail={
                "message": decision["reason"],
                "validation_request_id": decision.get("validation_request_id")})

    ts = now_iso()
    checkpoint_id = None
    if current == "actif" and payload.state in ("sommeil", "suspendu", "termine", "erreur"):
        cp = await create_checkpoint(agent_id, payload.state, actor,
                                     payload.last_action or f"mise en {payload.state}",
                                     payload.next_action)
        checkpoint_id = cp["id"]

    runtime = {"state": payload.state, "since": ts, "initialized": True,
               "previous_state": current, "note": payload.note,
               "last_transition_by": f'{actor["type"]}:{actor["id"]}',
               "last_checkpoint_id": checkpoint_id or agent.get("runtime", {}).get("last_checkpoint_id")}
    await db.agents.update_one({"id": agent_id}, {"$set": {"runtime": runtime, "updated_at": ts}})
    jtype = JOURNAL_TYPE_BY_STATE.get(payload.state, "action_executee")
    await journal(jtype, actor, f"Runtime {agent_id} : {current} → {payload.state}. {payload.note}",
                  source="agent-runtime", agent_id=agent_id,
                  evidence={"from": current, "to": payload.state, "checkpoint_id": checkpoint_id},
                  result=payload.state)
    await log_authz(actor, "runtime_transition", f"agent:{agent_id}", True, f"{current} → {payload.state}")
    await publish("agent.runtime_state_changed", actor["id"],
                  {"agent_id": agent_id, "from": current, "to": payload.state})
    return {"result": "ok", "agent_id": agent_id, "runtime": runtime, "checkpoint_id": checkpoint_id}


@router.post("/agents/{agent_id}/wake")
async def wake_agent(agent_id: str, actor: dict = Depends(get_current_actor)):
    """Réveil : sommeil → actif avec restauration complète du contexte.
    Toute information absente est SIGNALÉE (missing_information), jamais inventée."""
    check_actor_can_operate(actor, agent_id)
    agent = await db.agents.find_one({"id": agent_id}, {"_id": 0, "adl_yaml": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    current = agent_runtime(agent)["state"]
    if current not in ("sommeil", "erreur", "attente_validation"):
        raise HTTPException(status_code=409, detail=f"Réveil impossible depuis l'état '{current}'")

    ts = now_iso()
    missing = []

    checkpoint = await db.agent_checkpoints.find_one({"agent_id": agent_id}, {"_id": 0}, sort=[("timestamp", -1)])
    if not checkpoint:
        missing.append("aucun checkpoint — l'agent repart de son contexte opérationnel courant")

    objectives = await db.objectives.find({"owner": agent_id, "status": {"$in": ["active", "waiting_validation"]}},
                                          {"_id": 0}).sort("priority", 1).to_list(50)
    if not objectives:
        missing.append("aucun objectif actif dans l'Objective Registry")

    doctrines = await db.doctrine_registry.find({"status": "active", "agents_concerned": agent_id},
                                                {"_id": 0, "id": 1, "title": 1, "principle": 1}).to_list(100)
    global_doctrines_count = await db.doctrine_registry.count_documents(
        {"status": "active", "agents_concerned": []})
    if not doctrines and global_doctrines_count == 0:
        missing.append("aucune doctrine active applicable")

    history = await db.activity_journal.find({"agent_id": agent_id}, {"_id": 0}) \
        .sort("timestamp", -1).to_list(10)
    open_tasks = await db.agent_tasks.find({"agent_id": agent_id, "status": {"$in": ["open", "in_progress"]}},
                                           {"_id": 0}).sort("priority", 1).to_list(20)
    missions = await db.missions.find({"agent_ids": agent_id, "status": {"$in": ["assigned", "in_progress"]}},
                                      {"_id": 0, "id": 1, "title": 1, "status": 1, "workflow_stage": 1}).to_list(20)
    pending_validations = await db.validation_requests.find({"agent_id": agent_id, "status": "pending"},
                                                            {"_id": 0}).to_list(20)
    gate_rules = await db.permission_rules.find({"scope": "agent", "target_id": agent_id, "active": True},
                                                {"_id": 0}).to_list(50)
    memory_counts = {}
    async for m in db.memory_entries.find({"agent_id": agent_id}, {"_id": 0, "scope": 1}):
        memory_counts[m["scope"]] = memory_counts.get(m["scope"], 0) + 1
    if not memory_counts:
        missing.append("aucune entrée mémoire")

    runtime = {"state": "actif", "since": ts, "initialized": True, "previous_state": current,
               "note": "réveil avec restauration de contexte",
               "last_transition_by": f'{actor["type"]}:{actor["id"]}',
               "last_checkpoint_id": checkpoint["id"] if checkpoint else None}
    await db.agents.update_one({"id": agent_id}, {"$set": {"runtime": runtime, "updated_at": ts}})
    await journal("action_executee", actor,
                  f"Réveil de {agent_id} ({current} → actif) — contexte restauré"
                  + (f" ({len(missing)} information(s) manquante(s) signalée(s))" if missing else " complet"),
                  source="agent-runtime", agent_id=agent_id,
                  evidence={"checkpoint_id": checkpoint["id"] if checkpoint else None,
                            "missing_information": missing}, result="awake")
    await publish("agent.woken", actor["id"], {"agent_id": agent_id, "missing": len(missing)})

    return {
        "result": "awake", "agent_id": agent_id, "runtime": runtime,
        "restored_context": {
            "identity": {k: agent.get(k) for k in ("id", "name", "pole", "entity", "version", "mission")},
            "role": {"objectives_adl": agent.get("objectives", []), "vision": agent.get("vision", ""),
                     "kpis": agent.get("kpis", [])},
            "doctrine": {"specific": doctrines, "global_active_rules": global_doctrines_count},
            "active_objectives": objectives,
            "history": history,
            "permissions": {"adl": agent.get("adl", {}).get("permissions", {}),
                            "autonomy": agent.get("autonomy"), "gate_rules": gate_rules},
            "pending_validations": pending_validations,
            "last_checkpoint": checkpoint,
            "operational_context": {"open_tasks": open_tasks, "missions_in_progress": missions,
                                    "memory_entries_by_scope": memory_counts},
        },
        "missing_information": missing,
    }


async def runtime_recovery():
    """Recovery au démarrage : reconcilie les agents actifs avec leur dernier checkpoint."""
    active_agents = await db.agents.find({"runtime.state": "actif"}, {"_id": 0, "id": 1}).to_list(2000)
    without_cp = []
    for a in active_agents:
        cp = await db.agent_checkpoints.find_one({"agent_id": a["id"]}, {"_id": 0, "id": 1})
        if not cp:
            without_cp.append(a["id"])
    report = {"id": str(uuid.uuid4()), "active_agents": len(active_agents),
              "agents_without_checkpoint": without_cp, "coherent": len(without_cp) == 0,
              "timestamp": now_iso()}
    await db.runtime_recoveries.insert_one({**report})
    await journal("observation", {"type": "system", "id": "runtime", "name": "Runtime Recovery"},
                  f"Reprise système : {len(active_agents)} agent(s) actif(s) restauré(s)"
                  + (f", {len(without_cp)} sans checkpoint (signalé)" if without_cp else ", cohérence vérifiée"),
                  source="agent-runtime", evidence=report, result="recovered")
    await publish("agent.runtime_recovered", "system",
                  {"active_agents": len(active_agents), "without_checkpoint": without_cp})
    return report


@router.get("/recovery-status")
async def recovery_status(actor: dict = Depends(get_current_actor)):
    last = await db.runtime_recoveries.find_one({}, {"_id": 0}, sort=[("timestamp", -1)])
    return {"last_recovery": last}
