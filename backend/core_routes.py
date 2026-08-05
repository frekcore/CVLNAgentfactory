import uuid
import time
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from database import db, client
from auth_utils import get_current_actor, require_admin, log_authz
from event_bus import publish, VALID_TOPICS_PREFIXES
from notifier import notify

router = APIRouter(tags=["core"])
START_TIME = time.time()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------- Event Bus ----------
class PublishPayload(BaseModel):
    topic: str
    payload: dict = {}
    destination: str = "broadcast"


@router.get("/events")
async def list_events(topic: Optional[str] = None, source: Optional[str] = None,
                      limit: int = 100, actor: dict = Depends(get_current_actor)):
    query = {}
    if topic:
        query["topic"] = {"$regex": topic, "$options": "i"}
    if source:
        query["source"] = {"$regex": source, "$options": "i"}
    events = await db.events.find(query, {"_id": 0}).sort("timestamp", -1).to_list(min(limit, 500))
    return events


@router.post("/events/publish")
async def publish_event(payload: PublishPayload, actor: dict = Depends(get_current_actor)):
    if actor["type"] != "service" and actor["role"] != "admin":
        await log_authz(actor, "event_publish", f"topic:{payload.topic}", False,
                        "only service identities or admin can publish — no inter-pole communication outside Event Bus")
        raise HTTPException(status_code=403, detail="Only service identities or admin can publish on the Event Bus")
    if not payload.topic.startswith(VALID_TOPICS_PREFIXES):
        raise HTTPException(status_code=400, detail=f"Topic must start with one of {VALID_TOPICS_PREFIXES}")
    event = await publish(payload.topic, actor["id"], payload.payload, payload.destination)
    return event


# ---------- Memory Service ----------
MEMORY_SCOPES = ("session", "persistent", "operational", "strategic", "doctrinal", "learning")
MEMORY_LAYERS_V2 = {
    "doctrinal": "Mémoire doctrinale — règles permanentes, gouvernance, interdictions",
    "strategic": "Mémoire stratégique — vision, objectifs long terme, décisions majeures",
    "operational": "Mémoire opérationnelle — tâches, missions, états",
    "learning": "Mémoire d'apprentissage — retours d'expérience, corrections, optimisations",
}


class MemoryWrite(BaseModel):
    agent_id: str
    entity: str
    scope: str = "session"
    key: str
    value: dict | str | list | int | float | bool
    source: str = ""
    confidence: Optional[int] = None
    provenance: str = ""


async def log_memory_access(actor, agent_id, operation, key=""):
    await db.memory_access_logs.insert_one({
        "id": str(uuid.uuid4()), "actor_type": actor["type"], "actor_id": actor["id"],
        "agent_id": agent_id, "operation": operation, "key": key, "timestamp": now_iso()})


@router.get("/memory/logs")
async def memory_logs(limit: int = 100, actor: dict = Depends(get_current_actor)):
    logs = await db.memory_access_logs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(min(limit, 500))
    return logs


@router.get("/memory-layers/summary")
async def memory_layers_summary(actor: dict = Depends(get_current_actor)):
    """Memory Layer v2 — vue par les 4 couches (compat ascendante : session/persistent en legacy)."""
    pipeline = [{"$group": {"_id": "$scope", "count": {"$sum": 1},
                            "validated": {"$sum": {"$cond": [{"$eq": ["$validation.status", "validated"]}, 1, 0]}},
                            "avg_confidence": {"$avg": "$confidence"}}}]
    by_scope = {r["_id"]: r async for r in db.memory_entries.aggregate(pipeline)}
    layers = []
    for scope, label in MEMORY_LAYERS_V2.items():
        r = by_scope.get(scope, {})
        layers.append({"layer": scope, "label": label, "entries": r.get("count", 0),
                       "validated": r.get("validated", 0),
                       "avg_confidence": round(r["avg_confidence"], 1) if r.get("avg_confidence") else None})
    legacy = {s: by_scope.get(s, {}).get("count", 0) for s in ("session", "persistent")}
    return {"layers": layers, "legacy_scopes": legacy,
            "total_entries": sum(r.get("count", 0) for r in by_scope.values())}


@router.post("/memory/entries/{entry_id}/validate")
async def validate_memory_entry(entry_id: str, actor: dict = Depends(require_admin)):
    entry = await db.memory_entries.find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    ts = now_iso()
    await db.memory_entries.update_one(
        {"id": entry_id},
        {"$set": {"validation": {"status": "validated", "validated_by": f'human:{actor["id"]}',
                                 "validated_at": ts}, "updated_at": ts}})
    await log_memory_access(actor, entry["agent_id"], "validate", entry["key"])
    from activity_journal import journal
    await journal("decision_humaine", actor,
                  f"Entrée mémoire validée : {entry['key']} ({entry['scope']}, agent {entry['agent_id']})",
                  source="memory-layer", agent_id=entry["agent_id"],
                  evidence={"entry_id": entry_id}, result="validated")
    return {"result": "validated", "entry_id": entry_id}


@router.get("/memory/{agent_id}")
async def read_memory(agent_id: str, actor: dict = Depends(get_current_actor)):
    if actor["type"] == "service" and actor["id"] != agent_id:
        await log_authz(actor, "memory_read", f"agent:{agent_id}", False, "memory is isolated per agent")
        raise HTTPException(status_code=403, detail="Memory space is isolated per agent")
    entries = await db.memory_entries.find({"agent_id": agent_id}, {"_id": 0}).sort("updated_at", -1).to_list(500)
    await log_memory_access(actor, agent_id, "read")
    return entries


@router.post("/memory")
async def write_memory(payload: MemoryWrite, actor: dict = Depends(get_current_actor)):
    if actor["type"] == "service" and actor["id"] != payload.agent_id:
        await log_authz(actor, "memory_write", f"agent:{payload.agent_id}", False, "memory is isolated per agent")
        raise HTTPException(status_code=403, detail="Memory space is isolated per agent")
    if actor["type"] == "human" and actor["role"] == "reader":
        await log_authz(actor, "memory_write", f"agent:{payload.agent_id}", False, "readers cannot write memory")
        raise HTTPException(status_code=403, detail="Readers cannot write to memory")
    if payload.scope not in MEMORY_SCOPES:
        raise HTTPException(status_code=400, detail=f"scope must be one of {MEMORY_SCOPES}")
    if payload.confidence is not None and not (0 <= payload.confidence <= 100):
        raise HTTPException(status_code=400, detail="confidence must be between 0 and 100")
    ts = now_iso()
    await db.memory_entries.update_one(
        {"agent_id": payload.agent_id, "key": payload.key, "scope": payload.scope},
        {"$set": {"value": payload.value, "entity": payload.entity, "updated_at": ts,
                  "source": payload.source, "confidence": payload.confidence,
                  "provenance": payload.provenance},
         "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": ts, "owner": actor["id"],
                          "validation": {"status": "none", "validated_by": None, "validated_at": None}}},
        upsert=True)
    await log_memory_access(actor, payload.agent_id, "write", payload.key)
    await publish("memory.written", actor["id"], {"agent_id": payload.agent_id, "key": payload.key, "scope": payload.scope})
    return {"result": "ok"}


# ---------- Audit ----------
@router.get("/audit")
async def audit_logs(allowed: Optional[bool] = None, action: Optional[str] = None,
                     limit: int = 100, actor: dict = Depends(get_current_actor)):
    if actor["type"] == "human" and actor["role"] == "reader":
        raise HTTPException(status_code=403, detail="Audit log requires operator or admin role")
    query = {}
    if allowed is not None:
        query["allowed"] = allowed
    if action:
        query["action"] = {"$regex": action, "$options": "i"}
    logs = await db.audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).to_list(min(limit, 500))
    return logs


# ---------- Monitoring ----------
@router.get("/monitoring/health")
async def health(actor: dict = Depends(get_current_actor)):
    services = []
    try:
        await client.admin.command("ping")
        db_ok = True
    except Exception:
        db_ok = False
    agents_count = await db.agents.count_documents({}) if db_ok else 0
    events_count = await db.events.count_documents({}) if db_ok else 0
    services.append({"name": "Registry", "status": "healthy" if db_ok else "down", "detail": f"{agents_count} agents"})
    services.append({"name": "Identity", "status": "healthy" if db_ok else "down",
                     "detail": f"{await db.users.count_documents({})} users, {await db.identities.count_documents({})} service identities"})
    services.append({"name": "Event Bus", "status": "healthy" if db_ok else "down", "detail": f"{events_count} events"})
    services.append({"name": "Memory", "status": "healthy" if db_ok else "down",
                     "detail": f"{await db.memory_entries.count_documents({})} entries"})
    services.append({"name": "Monitoring", "status": "healthy", "detail": f"uptime {int(time.time() - START_TIME)}s"})
    # F-008 : le Monitoring PUBLIE des événements d'action (il n'exécute pas — séparation stricte)
    agents_in_error = [a["id"] async for a in db.agents.find({"runtime.state": "erreur"}, {"_id": 0, "id": 1})]
    throttle_since = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    for aid in agents_in_error:
        recent = await db.events.find_one({"topic": "monitoring.action", "payload.agent_id": aid,
                                           "timestamp": {"$gte": throttle_since}}, {"_id": 0, "id": 1})
        if recent:
            continue
        await publish("monitoring.action", "monitoring",
                      {"action": "AGENT_RESTART", "agent_id": aid,
                       "reason": "agent en état erreur détecté — réparation via POST /monitoring/heal"})
    if not db_ok:
        await publish("monitoring.alert", "monitoring", {"severity": "critical", "message": "MongoDB unreachable"})
        await notify(1, "Service critique en panne", "MongoDB injoignable — Registry, Memory et Event Bus impactés.", source="monitoring")
    return {"services": services, "database": "up" if db_ok else "down",
            "agents_in_error": agents_in_error, "uptime_seconds": int(time.time() - START_TIME)}


@router.post("/monitoring/heal")
async def auto_heal(actor: dict = Depends(get_current_actor)):
    """F-008 Auto-healing : répare les agents en erreur (erreur → actif) depuis leur dernier checkpoint."""
    from activity_journal import journal
    if actor["type"] == "human" and actor["role"] == "reader":
        raise HTTPException(status_code=403, detail="Readers cannot heal")
    if actor["type"] == "service" and actor["id"] != "AGT-000":
        raise HTTPException(status_code=403, detail="Only AGT-000 or humans heal agents")
    healed = []
    ts = now_iso()
    async for a in db.agents.find({"runtime.state": "erreur"}, {"_id": 0, "id": 1, "runtime": 1}):
        cp = await db.agent_checkpoints.find_one({"agent_id": a["id"]}, {"_id": 0, "id": 1}, sort=[("timestamp", -1)])
        await db.agents.update_one({"id": a["id"]},
                                   {"$set": {"runtime": {"state": "actif", "since": ts, "initialized": True,
                                                         "previous_state": "erreur",
                                                         "note": "auto-healing (F-008) — restauration depuis checkpoint",
                                                         "last_transition_by": f'{actor["type"]}:{actor["id"]}',
                                                         "last_checkpoint_id": cp["id"] if cp else None},
                                             "updated_at": ts}})
        healed.append(a["id"])
        await publish("monitoring.action", actor["id"], {"action": "AGENT_RESTARTED", "agent_id": a["id"]})
    if healed:
        await journal("action_executee", actor,
                      f"Auto-healing : {len(healed)} agent(s) réparé(s) ({', '.join(healed)}) — erreur → actif",
                      source="monitoring", evidence={"healed": healed}, result="healed")
    return {"healed": healed, "count": len(healed)}


@router.get("/events/dlq")
async def list_dlq(limit: int = 50, actor: dict = Depends(get_current_actor)):
    return await db.events_dlq.find({}, {"_id": 0}).sort("dlq_at", -1).to_list(min(limit, 200))


@router.post("/events/replay-spool")
async def replay_event_spool(actor: dict = Depends(require_admin)):
    """ADR-006 : rejoue la file locale de secours vers l'Event Bus après rétablissement."""
    from event_bus import replay_spool
    result = await replay_spool()
    from activity_journal import journal
    await journal("action_executee", actor,
                  f"Replay du spool Event Bus : {result['replayed']} rejoué(s), {result['dlq']} en DLQ",
                  source="event-bus", evidence=result, result="replayed")
    return result


@router.get("/monitoring/dashboard")
async def monitoring_dashboard(actor: dict = Depends(get_current_actor)):
    agents = await db.agents.find({}, {"_id": 0, "id": 1, "name": 1, "status": 1, "pole": 1, "entity": 1}).to_list(2000)
    active = [a for a in agents if a["status"] in ("Production", "Maintenance")]
    by_pole, by_entity = {}, {}
    for a in active:
        by_pole[a["pole"]] = by_pole.get(a["pole"], 0) + 1
        by_entity[a["entity"]] = by_entity.get(a["entity"], 0) + 1
    recent_events = await db.events.find({}, {"_id": 0}).sort("timestamp", -1).to_list(15)
    alerts = await db.events.find({"topic": "monitoring.alert"}, {"_id": 0}).sort("timestamp", -1).to_list(20)
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    events_24h = await db.events.count_documents({"timestamp": {"$gte": since}})
    denied_24h = await db.audit_logs.count_documents({"allowed": False, "timestamp": {"$gte": since}})
    return {"active_agents": len(active), "total_agents": len(agents),
            "active_by_pole": by_pole, "active_by_entity": by_entity,
            "recent_events": recent_events, "alerts": alerts,
            "events_24h": events_24h, "denied_authz_24h": denied_24h}


# ---------- Laurent.ia reserved endpoint ----------
@router.api_route("/laurent-ia", methods=["GET", "POST"])
async def laurent_ia_placeholder():
    raise HTTPException(status_code=501, detail={
        "message": "Reserved entry point for Laurent.ia (separate system). Interface contract to be defined in V2.",
        "status": "reserved"})
