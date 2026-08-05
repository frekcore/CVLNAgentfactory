import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
from database import db
from auth_utils import get_current_actor, require_admin, log_authz
from activity_journal import journal, JOURNAL_TYPES
from event_bus import publish
from notifier import notify

router = APIRouter(prefix="/gate", tags=["permission-gate-v2"])

GATE_LEVELS = {
    1: {"label": "observe", "fr": "Observer"},
    2: {"label": "analyze", "fr": "Analyser"},
    3: {"label": "propose", "fr": "Proposer"},
    4: {"label": "prepare", "fr": "Préparer"},
    5: {"label": "execute_after_validation", "fr": "Exécuter après validation humaine"},
    6: {"label": "forbidden", "fr": "Interdit"},
}

# Actions ALWAYS requiring Laurent's human validation — non-overridable by rules
CRITICAL_ACTIONS = ["expense", "external_publication", "governance_change",
                    "data_deletion", "permission_change", "critical_production_activation"]

DEFAULT_ACTION_LEVELS = {
    "observe": 1, "analyze": 2, "propose": 3, "prepare": 4, "execute": 5,
    **{a: 5 for a in CRITICAL_ACTIONS},
}

LEVEL_JOURNAL_TYPE = {1: "observation", 2: "analyse", 3: "proposition", 4: "proposition"}


class RulePayload(BaseModel):
    scope: str = Field(pattern="^(agent|mission|action_type)$")
    target_id: Optional[str] = None  # agent_id or mission_id (None for global action_type rules)
    action_type: str
    level: int = Field(ge=1, le=6)
    note: str = ""


class CheckPayload(BaseModel):
    action_type: str
    summary: str = Field(min_length=5)
    agent_id: Optional[str] = None
    mission_id: Optional[str] = None
    validation_id: Optional[str] = None
    confidence: Optional[int] = Field(None, ge=0, le=100)
    evidence: Optional[dict] = None


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def resolve_level(action_type: str, agent_id: str | None, mission_id: str | None) -> tuple[int, str]:
    """Rule resolution order: agent rule > mission rule > global action_type rule > default."""
    if agent_id:
        r = await db.permission_rules.find_one(
            {"scope": "agent", "target_id": agent_id, "action_type": action_type, "active": True}, {"_id": 0})
        if r:
            return r["level"], f"règle agent {agent_id}"
    if mission_id:
        r = await db.permission_rules.find_one(
            {"scope": "mission", "target_id": mission_id, "action_type": action_type, "active": True}, {"_id": 0})
        if r:
            return r["level"], f"règle mission {mission_id}"
    r = await db.permission_rules.find_one(
        {"scope": "action_type", "action_type": action_type, "active": True}, {"_id": 0})
    if r:
        return r["level"], "règle globale action_type"
    return DEFAULT_ACTION_LEVELS.get(action_type, 5), "niveau par défaut"


async def gate_check(actor: dict, action_type: str, summary: str,
                     agent_id: str | None = None, mission_id: str | None = None,
                     validation_id: str | None = None, confidence: int | None = None,
                     evidence: dict | None = None, source: str = "permission-gate") -> dict:
    """Core Permission Gate v2 decision. Reusable by the Autonomous Runtime (PHASE 4)."""
    level, rule_source = await resolve_level(action_type, agent_id, mission_id)
    is_critical = action_type in CRITICAL_ACTIONS
    if is_critical and level < 5:
        level, rule_source = 5, "action critique — validation Laurent non contournable"
    ctx = {"action_type": action_type, "level": level, "rule_source": rule_source,
           "agent_id": agent_id, "mission_id": mission_id}

    if level == 6:
        await journal("action_bloquee", actor, f"[NIVEAU 6 INTERDIT] {summary}", source=source,
                      mission_id=mission_id, agent_id=agent_id, confidence=confidence,
                      evidence={**(evidence or {}), **ctx}, result="refused")
        await log_authz(actor, f"gate:{action_type}", agent_id or mission_id or "system", False,
                        f"niveau 6 interdit ({rule_source})")
        return {"allowed": False, "level": 6, "decision": "forbidden", "rule_source": rule_source,
                "reason": "Action interdite (niveau 6) — aucune exécution possible."}

    if level <= 4:
        await journal(LEVEL_JOURNAL_TYPE[level], actor, summary, source=source,
                      mission_id=mission_id, agent_id=agent_id, confidence=confidence,
                      evidence={**(evidence or {}), **ctx}, result="allowed")
        return {"allowed": True, "level": level, "decision": GATE_LEVELS[level]["label"],
                "rule_source": rule_source, "reason": f"Autorisé au niveau {level} ({GATE_LEVELS[level]['fr']})."}

    # Level 5 — execution requires human validation
    if actor.get("type") == "human" and actor.get("role") == "admin":
        await journal("decision_humaine", actor, f"Validation implicite (admin exécute) : {summary}",
                      source=source, mission_id=mission_id, agent_id=agent_id,
                      evidence={**(evidence or {}), **ctx}, result="approved")
        await journal("action_executee", actor, summary, source=source,
                      mission_id=mission_id, agent_id=agent_id, confidence=confidence,
                      evidence={**(evidence or {}), **ctx}, result="executed")
        return {"allowed": True, "level": 5, "decision": "execute_after_validation",
                "rule_source": rule_source, "reason": "Exécution autorisée — acteur humain admin (validation implicite)."}

    if validation_id:
        vr = await db.validation_requests.find_one({"id": validation_id}, {"_id": 0})
        if vr and vr["status"] == "approved" and vr["action_type"] == action_type:
            await journal("action_executee", actor, summary, source=source,
                          mission_id=mission_id, agent_id=agent_id, confidence=confidence,
                          evidence={**(evidence or {}), **ctx, "validation_id": validation_id}, result="executed")
            return {"allowed": True, "level": 5, "decision": "execute_after_validation",
                    "rule_source": rule_source, "validation_id": validation_id,
                    "reason": "Exécution autorisée — validation humaine approuvée."}
        # LIAISON 2 : une dépense approuvée dans la file Gatekeeper vaut validation
        er = await db.expense_requests.find_one({"id": validation_id}, {"_id": 0})
        if er and er["status"] in ("approved", "auto_approved") and action_type == "expense":
            await journal("action_executee", actor, summary, source=source,
                          mission_id=mission_id, agent_id=agent_id, confidence=confidence,
                          evidence={**(evidence or {}), **ctx, "expense_request_id": validation_id}, result="executed")
            return {"allowed": True, "level": 5, "decision": "execute_after_validation",
                    "rule_source": rule_source, "validation_id": validation_id,
                    "reason": "Exécution autorisée — dépense validée par le Financial Gatekeeper."}

    # Automatic escalation to human validation
    # LIAISON 2 (Vague 1) : les dépenses passent par la file UNIQUE du Financial Gatekeeper
    if action_type == "expense":
        amount = float((evidence or {}).get("amount") or 0)
        req = {"id": str(uuid.uuid4()), "amount": amount or 0.01, "description": summary[:300],
               "entity": (evidence or {}).get("entity", ""), "agent_id": agent_id, "category": "gate",
               "required_approvals": 1 if amount <= 100000 else 2, "approvals": [],
               "status": "pending", "requested_by": f'{actor.get("type","?")}:{actor.get("id","?")}',
               "created_at": now_iso(), "updated_at": now_iso()}
        await db.expense_requests.insert_one({**req})
        await journal("action_bloquee", actor, f"[GATEKEEPER] Dépense escaladée (file unique) : {summary}",
                      source="financial-gatekeeper", mission_id=mission_id, agent_id=agent_id,
                      evidence={**(evidence or {}), **ctx, "expense_request_id": req["id"]}, result="escalated")
        await notify(2, "Dépense — validation requise",
                     f"{summary[:150]} — validation via Financial Gatekeeper.", source="financial-gatekeeper")
        return {"allowed": False, "level": 5, "decision": "pending_human_validation",
                "rule_source": rule_source, "queue": "financial-gatekeeper",
                "validation_request_id": req["id"],
                "reason": "Dépense bloquée — validation via la file unique du Financial Gatekeeper (plafonds Art. 13)."}
    vr = {"id": str(uuid.uuid4()), "action_type": action_type, "summary": summary,
          "agent_id": agent_id, "mission_id": mission_id, "critical": is_critical,
          "requested_by": f'{actor.get("type","?")}:{actor.get("id","?")}',
          "status": "pending", "decided_by": None, "decided_at": None, "decision_note": None,
          "created_at": now_iso()}
    await db.validation_requests.insert_one({**vr})
    await journal("action_bloquee", actor, f"[ESCALADE → validation Laurent] {summary}", source=source,
                  mission_id=mission_id, agent_id=agent_id, confidence=confidence,
                  evidence={**(evidence or {}), **ctx, "validation_request_id": vr["id"]}, result="escalated")
    await log_authz(actor, f"gate:{action_type}", agent_id or mission_id or "system", False,
                    f"niveau 5 — escalade validation humaine ({vr['id']})")
    await publish("factory.validation_requested", actor.get("id", "system"),
                  {"validation_request_id": vr["id"], "action_type": action_type, "summary": summary[:200]})
    await notify(2, "Permission Gate — validation requise",
                 f"Action « {action_type} » demandée par {vr['requested_by']} : {summary[:180]}",
                 source="permission-gate", meta={"validation_request_id": vr["id"]})
    return {"allowed": False, "level": 5, "decision": "pending_human_validation",
            "rule_source": rule_source, "validation_request_id": vr["id"],
            "reason": "Exécution bloquée — validation humaine de Laurent requise (escalade automatique créée)."}


# ---------- Routes ----------
@router.get("/levels")
async def levels(actor: dict = Depends(get_current_actor)):
    return {"levels": GATE_LEVELS, "critical_actions": CRITICAL_ACTIONS,
            "default_action_levels": DEFAULT_ACTION_LEVELS}


@router.post("/check")
async def check(payload: CheckPayload, actor: dict = Depends(get_current_actor)):
    return await gate_check(actor, payload.action_type, payload.summary,
                            agent_id=payload.agent_id, mission_id=payload.mission_id,
                            validation_id=payload.validation_id, confidence=payload.confidence,
                            evidence=payload.evidence)


@router.get("/rules")
async def list_rules(actor: dict = Depends(get_current_actor)):
    return await db.permission_rules.find({"active": True}, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/rules")
async def create_rule(payload: RulePayload, actor: dict = Depends(require_admin)):
    if payload.scope in ("agent", "mission") and not payload.target_id:
        raise HTTPException(status_code=400, detail="target_id required for agent/mission scope")
    if payload.action_type in CRITICAL_ACTIONS and payload.level < 5:
        raise HTTPException(status_code=400,
                            detail=f"'{payload.action_type}' est une action critique — niveau minimum 5 (validation Laurent non contournable)")
    rule = {"id": str(uuid.uuid4()), **payload.model_dump(), "active": True,
            "created_by": f'human:{actor["id"]}', "created_at": now_iso()}
    await db.permission_rules.insert_one({**rule})
    await journal("decision_humaine", actor,
                  f"Règle Permission Gate créée : {payload.scope}/{payload.target_id or 'global'} · {payload.action_type} → niveau {payload.level}",
                  source="permission-gate", evidence={"rule_id": rule["id"], "note": payload.note}, result="rule_created")
    await log_authz(actor, "gate_rule_create", rule["id"], True, payload.note)
    return rule


@router.delete("/rules/{rule_id}")
async def deactivate_rule(rule_id: str, actor: dict = Depends(require_admin)):
    r = await db.permission_rules.update_one({"id": rule_id}, {"$set": {"active": False, "deactivated_at": now_iso()}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Rule not found")
    await journal("decision_humaine", actor, f"Règle Permission Gate désactivée : {rule_id}",
                  source="permission-gate", evidence={"rule_id": rule_id}, result="rule_deactivated")
    return {"result": "deactivated"}


@router.get("/refusals")
async def refusals(limit: int = 100, actor: dict = Depends(get_current_actor)):
    return await db.activity_journal.find({"type": "action_bloquee"}, {"_id": 0}) \
        .sort("timestamp", -1).to_list(min(limit, 500))


@router.get("/validation-requests")
async def list_validation_requests(status: Optional[str] = None, actor: dict = Depends(get_current_actor)):
    query = {"status": status} if status else {}
    return await db.validation_requests.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.post("/validation-requests/{request_id}/decide")
async def decide_validation(request_id: str, decision: str, note: str = "",
                            actor: dict = Depends(require_admin)):
    if decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="decision must be approved or rejected")
    vr = await db.validation_requests.find_one({"id": request_id}, {"_id": 0})
    if not vr:
        raise HTTPException(status_code=404, detail="Validation request not found")
    if vr["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Already {vr['status']}")
    ts = now_iso()
    await db.validation_requests.update_one({"id": request_id},
                                            {"$set": {"status": decision, "decided_by": f'human:{actor["id"]}',
                                                      "decided_at": ts, "decision_note": note}})
    await journal("decision_humaine", actor,
                  f"Validation {('APPROUVÉE' if decision == 'approved' else 'REJETÉE')} : {vr['summary'][:150]}",
                  source="permission-gate", mission_id=vr.get("mission_id"), agent_id=vr.get("agent_id"),
                  evidence={"validation_request_id": request_id, "note": note}, result=decision)
    await log_authz(actor, "gate_validation_decide", request_id, True, decision)
    await publish("factory.validation_decided", actor["id"],
                  {"validation_request_id": request_id, "decision": decision})
    return {"result": decision, "validation_request_id": request_id}


# ---------- Activity Journal v2 ----------
journal_router = APIRouter(prefix="/journal", tags=["activity-journal-v2"])


@journal_router.get("/types")
async def journal_types(actor: dict = Depends(get_current_actor)):
    return JOURNAL_TYPES


@journal_router.get("")
async def list_journal(type: Optional[str] = None, agent_id: Optional[str] = None,
                       mission_id: Optional[str] = None, limit: int = 100,
                       actor: dict = Depends(get_current_actor)):
    query = {}
    if type:
        query["type"] = type
    if agent_id:
        query["agent_id"] = agent_id
    if mission_id:
        query["mission_id"] = mission_id
    return await db.activity_journal.find(query, {"_id": 0}).sort("timestamp", -1).to_list(min(limit, 500))


@journal_router.get("/unified")
async def unified_journal(limit: int = 100, actor: dict = Depends(get_current_actor)):
    """Read-level fusion: activity_journal v2 + legacy audit_logs + events, mapped to v2 types.
    No migration — legacy history preserved, backward compatible."""
    n = min(limit, 300)
    v2 = await db.activity_journal.find({}, {"_id": 0}).sort("timestamp", -1).to_list(n)
    entries = [{**e, "origin": "journal_v2"} for e in v2]
    async for a in db.audit_logs.find({}, {"_id": 0}).sort("timestamp", -1).limit(n):
        entries.append({"id": a["id"], "type": "action_executee" if a["allowed"] else "action_bloquee",
                        "timestamp": a["timestamp"], "actor_type": a["actor_type"], "actor_id": a["actor_id"],
                        "actor_name": a.get("actor_name", ""), "source": "audit_legacy",
                        "mission_id": None, "agent_id": None, "confidence": None,
                        "evidence": {"action": a["action"], "resource": a["resource"], "reason": a.get("reason", "")},
                        "result": "allowed" if a["allowed"] else "denied",
                        "summary": f'{a["action"]} → {a["resource"]}', "origin": "audit_logs"})
    async for ev in db.events.find({}, {"_id": 0}).sort("timestamp", -1).limit(n):
        entries.append({"id": ev["id"], "type": "observation", "timestamp": ev["timestamp"],
                        "actor_type": "system", "actor_id": ev["source"], "actor_name": ev["source"],
                        "source": "event_bus", "mission_id": None, "agent_id": None, "confidence": None,
                        "evidence": ev.get("payload", {}), "result": None,
                        "summary": ev["topic"], "origin": "events"})
    entries.sort(key=lambda x: x["timestamp"], reverse=True)
    return entries[:n]
