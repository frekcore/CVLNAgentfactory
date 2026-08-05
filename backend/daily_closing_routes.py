import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from database import db
from auth_utils import get_current_actor, require_registry_writer, log_authz
from event_bus import publish
from notifier import notify

router = APIRouter(prefix="/daily", tags=["daily-closing"])

SYSTEM_VERSION = "1.1.0"
MEMORY_TIERS = ["session", "operational", "strategic"]


class AgentDailyReport(BaseModel):
    agent_id: str
    date: Optional[str] = None
    mission: str = ""
    tasks_done: List[str] = Field(default_factory=list)
    results: List[str] = Field(default_factory=list)
    data_produced: List[str] = Field(default_factory=list)
    decisions: List[str] = Field(default_factory=list)
    difficulties: List[str] = Field(default_factory=list)
    alerts: List[str] = Field(default_factory=list)
    next_actions: List[str] = Field(default_factory=list)
    confidence: int = Field(80, ge=0, le=100)
    human_intervention_needed: bool = False
    human_intervention_reason: str = ""


class ClosePayload(BaseModel):
    date: Optional[str] = None
    note: str = ""


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def flatten(reports, field, prefix=True):
    out = []
    for r in reports:
        for item in r.get(field, []):
            out.append(f"[{r['agent_id']}] {item}" if prefix else item)
    return out


# ---------- Agent daily reports ----------
@router.post("/reports")
async def submit_report(payload: AgentDailyReport, actor: dict = Depends(get_current_actor)):
    if actor["type"] == "service" and actor["id"] != payload.agent_id:
        await log_authz(actor, "daily_report_submit", f"agent:{payload.agent_id}", False,
                        "a service identity can only submit its own daily report")
        raise HTTPException(status_code=403, detail="A service identity can only submit its own daily report")
    if actor["type"] == "human" and actor["role"] == "reader":
        raise HTTPException(status_code=403, detail="Readers cannot submit daily reports")
    agent = await db.agents.find_one({"id": payload.agent_id}, {"_id": 0, "id": 1})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found in Registry")
    date = payload.date or today()
    closed = await db.daily_reports.find_one({"date": date, "status": "closed"})
    if closed:
        raise HTTPException(status_code=409, detail=f"Day {date} is already closed")
    doc = payload.model_dump()
    doc.update({"date": date, "submitted_by": f'{actor["type"]}:{actor["id"]}', "timestamp": now_iso()})
    await db.daily_agent_reports.update_one(
        {"agent_id": payload.agent_id, "date": date},
        {"$set": doc, "$setOnInsert": {"id": str(uuid.uuid4())}}, upsert=True)
    await publish("agent.daily.completed", actor["id"],
                  {"agent_id": payload.agent_id, "date": date, "confidence": payload.confidence,
                   "human_intervention_needed": payload.human_intervention_needed})
    return {"result": "ok", "agent_id": payload.agent_id, "date": date}


@router.get("/reports")
async def list_reports(date: Optional[str] = None, agent_id: Optional[str] = None,
                       actor: dict = Depends(get_current_actor)):
    query = {"date": date or today()}
    if agent_id:
        query["agent_id"] = agent_id
    return await db.daily_agent_reports.find(query, {"_id": 0}).sort("agent_id", 1).to_list(1000)


# ---------- Closing pipeline (Agent 000 / admin) ----------
@router.post("/close")
async def close_day(payload: ClosePayload, actor: dict = Depends(require_registry_writer)):
    date = payload.date or today()
    if await db.daily_reports.find_one({"date": date, "status": "closed"}):
        raise HTTPException(status_code=409, detail=f"Day {date} is already closed")

    await publish("daily.closing.started", actor["id"], {"date": date})
    steps = []

    # 1. Collecte des rapports
    agents = await db.agents.find({"status": {"$ne": "Archive"}},
                                  {"_id": 0, "id": 1, "name": 1, "version": 1, "status": 1, "mission": 1}).to_list(2000)
    reports = await db.daily_agent_reports.find({"date": date}, {"_id": 0}).to_list(2000)
    reported_ids = {r["agent_id"] for r in reports}
    missing = [a["id"] for a in agents if a["id"] not in reported_ids]
    steps.append({"step": "collect_reports", "status": "ok",
                  "detail": f"{len(reports)} rapport(s) reçu(s), {len(missing)} agent(s) sans rapport"})

    # 2. Contrôle final AGT-000 : anomalies, blocages, incohérences, erreurs critiques
    low_confidence = [r["agent_id"] for r in reports if r["confidence"] < 50]
    interventions = [{"agent_id": r["agent_id"], "reason": r["human_intervention_reason"]}
                     for r in reports if r["human_intervention_needed"]]
    all_alerts = flatten(reports, "alerts")
    since = f"{date}T00:00:00"
    until = f"{date}T23:59:59"
    denied = await db.audit_logs.count_documents({"allowed": False, "timestamp": {"$gte": since, "$lte": until}})
    mem_active = {m["agent_id"] async for m in db.memory_entries.find({}, {"_id": 0, "agent_id": 1})}
    inconsistencies = [r["agent_id"] for r in reports
                       if (r["tasks_done"] or r["data_produced"]) and r["agent_id"] not in mem_active]
    steps.append({"step": "agent000_control", "status": "warning" if (all_alerts or interventions or low_confidence) else "ok",
                  "detail": f"{len(all_alerts)} alerte(s), {len(interventions)} intervention(s) humaine(s) requise(s), "
                            f"{len(low_confidence)} confiance faible, {denied} refus d'autorisation, "
                            f"{len(inconsistencies)} incohérence(s) mémoire"})

    # 3. Snapshots mémoire (3 niveaux, versionnés, aucune suppression)
    snapshot_count = 0
    for r in reports:
        tiers = {
            "session": {"tasks_done": r["tasks_done"], "results": r["results"], "data_produced": r["data_produced"]},
            "operational": {k: r[k] for k in ("mission", "tasks_done", "results", "data_produced", "decisions",
                                              "difficulties", "alerts", "next_actions", "confidence")},
            "strategic": {"decisions": r["decisions"], "learnings": r["results"],
                          "next_actions": r["next_actions"], "patterns": r["difficulties"]},
        }
        for tier, content in tiers.items():
            version = await db.memory_snapshots.count_documents({"agent_id": r["agent_id"], "tier": tier}) + 1
            await db.memory_snapshots.insert_one({
                "id": str(uuid.uuid4()), "agent_id": r["agent_id"], "date": date, "tier": tier,
                "version": version, "content": content, "created_at": now_iso()})
            snapshot_count += 1
    await publish("memory.snapshot.created", actor["id"], {"date": date, "snapshots": snapshot_count, "tiers": MEMORY_TIERS})
    steps.append({"step": "memory_snapshots", "status": "ok",
                  "detail": f"{snapshot_count} snapshot(s) mémoire versionné(s) ({len(reports)} agents × 3 niveaux)"})

    # 4. États quotidiens Registry
    report_by_agent = {r["agent_id"]: r for r in reports}
    for a in agents:
        r = report_by_agent.get(a["id"])
        await db.agent_daily_states.update_one(
            {"agent_id": a["id"], "date": date},
            {"$set": {"version": a["version"], "status": a["status"],
                      "activity": (r["tasks_done"][0] if r and r["tasks_done"] else (r["mission"] if r else "Aucun rapport")),
                      "performance": r["confidence"] if r else None,
                      "evolution_recommendation": (r["next_actions"][0] if r and r["next_actions"] else ""),
                      "reported": bool(r), "timestamp": now_iso()},
             "$setOnInsert": {"id": str(uuid.uuid4())}}, upsert=True)
    steps.append({"step": "registry_daily_states", "status": "ok", "detail": f"{len(agents)} état(s) quotidien(s) enregistré(s)"})

    # 5. Daily Report global CVLN
    avg_conf = round(sum(r["confidence"] for r in reports) / len(reports), 1) if reports else None
    important_events = await db.events.find(
        {"timestamp": {"$gte": since, "$lte": until},
         "topic": {"$in": ["agent.created", "agent.archived", "factory.generate", "monitoring.alert"]}},
        {"_id": 0, "topic": 1, "source": 1, "payload": 1}).to_list(50)
    global_report = {
        "id": str(uuid.uuid4()), "date": date, "system_version": SYSTEM_VERSION, "status": "closed",
        "general_state": {
            "active_agents": len([a for a in agents if a["status"] in ("Production", "Maintenance")]),
            "total_agents": len(agents), "reports_received": len(reports),
            "agents_in_error": sorted(set(low_confidence + [i["agent_id"] for i in interventions])),
            "agents_waiting": missing, "important_events": important_events},
        "production": {
            "projects_advanced": flatten(reports, "tasks_done"),
            "deliverables": flatten(reports, "data_produced"),
            "strategic_decisions": flatten(reports, "decisions")},
        "intelligence": {
            "new_knowledge": flatten(reports, "results"),
            "new_rules": [d for d in flatten(reports, "decisions") if d],
            "patterns_detected": flatten(reports, "difficulties")},
        "risks": {
            "technical_issues": flatten(reports, "difficulties"),
            "security": {"denied_authorizations": denied, "alerts": all_alerts},
            "inconsistencies": inconsistencies, "costs": []},
        "next_day_plan": {
            "priorities": flatten(reports, "next_actions"),
            "open_tasks": [f"{aid} : rapport quotidien manquant" for aid in missing],
            "critical_missions": [f"{i['agent_id']} : {i['reason'] or 'intervention humaine requise'}" for i in interventions]},
        "governance": await governance_snapshot(),
        "average_confidence": avg_conf,
        "closed_by": f'{actor["type"]}:{actor["id"]}', "note": payload.note, "created_at": now_iso(),
    }

    # 6. CVLN Daily Executive Report (pour Laurent)
    global_report["executive_report"] = {
        "title": f"CVLN Daily Executive Report — {date}",
        "for": "Laurent (fondateur — supervision, validation stratégique, arbitrage, contrôle souverain)",
        "prepared_by": "AGT-000 — CVLN Agent Architect",
        "headline": f"{len(reports)}/{len(agents)} agents ont clôturé. Confiance moyenne : {avg_conf if avg_conf is not None else '—'}%. "
                    f"{len(interventions)} arbitrage(s) humain(s) requis. {len(all_alerts)} alerte(s).",
        "decisions_requiring_validation": global_report["next_day_plan"]["critical_missions"],
        "strategic_highlights": global_report["production"]["strategic_decisions"][:10],
        "risks_summary": {"alerts": len(all_alerts), "denied_authorizations": denied,
                          "missing_reports": len(missing), "memory_inconsistencies": len(inconsistencies)},
        "tomorrow_top_priorities": global_report["next_day_plan"]["priorities"][:10],
    }
    steps.append({"step": "executive_report", "status": "ok", "detail": "CVLN Daily Executive Report généré pour Laurent"})

    await db.daily_reports.insert_one({**global_report})
    await log_authz(actor, "daily_closing", f"date:{date}", True, f"{len(reports)} rapports, {snapshot_count} snapshots")
    await publish("daily.report.generated", actor["id"], {"date": date, "average_confidence": avg_conf,
                                                          "reports": len(reports), "missing": len(missing)})
    await publish("system.ready.next.day", actor["id"], {"date": date, "priorities": len(global_report["next_day_plan"]["priorities"])})
    steps.append({"step": "system_ready_next_day", "status": "ok", "detail": "Cycle suivant préparé — system.ready.next.day publié"})

    await notify(3, f"Daily Executive Report — {date}",
                 global_report["executive_report"]["headline"], source="daily-closing",
                 meta={"date": date})
    if interventions:
        await notify(2, "Interventions humaines requises",
                     " · ".join(global_report["next_day_plan"]["critical_missions"][:5]),
                     source="daily-closing", meta={"date": date})

    global_report["steps"] = steps
    return global_report


@router.get("/closings")
async def list_closings(actor: dict = Depends(get_current_actor)):
    return await db.daily_reports.find({}, {"_id": 0, "id": 1, "date": 1, "system_version": 1, "status": 1,
                                            "average_confidence": 1, "closed_by": 1, "created_at": 1,
                                            "general_state.reports_received": 1, "general_state.total_agents": 1}
                                       ).sort("date", -1).to_list(365)


@router.get("/closings/{date}")
async def get_closing(date: str, actor: dict = Depends(get_current_actor)):
    report = await db.daily_reports.find_one({"date": date}, {"_id": 0})
    if not report:
        raise HTTPException(status_code=404, detail="No closing for this date")
    return report


@router.get("/states")
async def daily_states(date: Optional[str] = None, agent_id: Optional[str] = None,
                       actor: dict = Depends(get_current_actor)):
    query = {}
    if date:
        query["date"] = date
    if agent_id:
        query["agent_id"] = agent_id
    return await db.agent_daily_states.find(query, {"_id": 0}).sort([("date", -1), ("agent_id", 1)]).to_list(2000)


@router.get("/snapshots")
async def memory_snapshots(agent_id: Optional[str] = None, tier: Optional[str] = None,
                           date: Optional[str] = None, actor: dict = Depends(get_current_actor)):
    query = {}
    if agent_id:
        query["agent_id"] = agent_id
    if tier:
        query["tier"] = tier
    if date:
        query["date"] = date
    return await db.memory_snapshots.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)


# ---------- L7 — Gouvernance (lecture seule, aucune action automatique) ----------
async def governance_snapshot() -> dict:
    pending_validations = await db.validation_requests.find({"status": "pending"}, {"_id": 0}).sort("created_at", -1).to_list(100)
    pending_expenses = await db.expense_requests.find({"status": "pending"}, {"_id": 0}).sort("created_at", -1).to_list(100)
    pending_amendments = await db.doctrine_registry.find(
        {"status": "proposition"}, {"_id": 0, "id": 1, "title": 1, "status": 1, "created_at": 1}
    ).sort("created_at", -1).to_list(100)
    since = f"{today()}T00:00:00"
    scores = []
    async for c in db.autonomous_cycles.find({"started_at": {"$gte": since}}, {"_id": 0, "analyses": 1}):
        for a in (c.get("analyses") or []):
            al = a.get("alignment")
            if al and al.get("score") is not None:
                scores.append(al["score"])
    return {
        "read_only": True,
        "note": "Lecture seule — aucune action automatique sur les validations en attente",
        "pending_gate_validations": {"count": len(pending_validations), "items": pending_validations[:10]},
        "pending_expense_requests": {"count": len(pending_expenses), "items": pending_expenses[:10]},
        "pending_amendments": {"count": len(pending_amendments), "items": pending_amendments[:10]},
        "alignment_today": {"evaluations": len(scores),
                            "average_score": round(sum(scores) / len(scores), 4) if scores else None,
                            "low_alignment_count": sum(1 for s in scores if s < 0.3)},
    }


# ---------- Morning Briefing ----------
@router.get("/briefing")
async def morning_briefing(actor: dict = Depends(get_current_actor)):
    last = await db.daily_reports.find_one({"status": "closed"}, {"_id": 0}, sort=[("date", -1)])
    current_date = today()
    stats_agents = await db.agents.count_documents({"status": {"$ne": "Archive"}})
    if not last:
        return {"date": current_date, "message": "Voici l'état du groupe numérique au démarrage de cette journée.",
                "first_day": True, "last_closing": None, "priorities": [], "urgencies": [],
                "opportunities": [], "recommendations": ["Aucune clôture précédente — soumettre les rapports quotidiens puis clôturer la journée."],
                "open_missions": [], "unresolved_errors": [], "active_agents": stats_agents}
    states = await db.agent_daily_states.find({"date": last["date"], "evolution_recommendation": {"$ne": ""}},
                                              {"_id": 0, "agent_id": 1, "evolution_recommendation": 1}).to_list(200)
    recommendations = []
    if last["general_state"]["agents_waiting"]:
        recommendations.append(f"Relancer les agents sans rapport : {', '.join(last['general_state']['agents_waiting'][:10])}")
    if last["risks"]["security"]["denied_authorizations"] > 0:
        recommendations.append(f"Analyser {last['risks']['security']['denied_authorizations']} refus d'autorisation de la veille (journal Audit)")
    if last.get("average_confidence") is not None and last["average_confidence"] < 70:
        recommendations.append(f"Confiance moyenne faible ({last['average_confidence']}%) — revue des agents en difficulté")
    return {
        "date": current_date, "first_day": False,
        "message": "Voici l'état du groupe numérique au démarrage de cette journée.",
        "last_closing": {"date": last["date"], "average_confidence": last.get("average_confidence"),
                         "reports_received": last["general_state"]["reports_received"],
                         "total_agents": last["general_state"]["total_agents"]},
        "priorities": last["next_day_plan"]["priorities"],
        "urgencies": last["next_day_plan"]["critical_missions"],
        "opportunities": [f"[{s['agent_id']}] {s['evolution_recommendation']}" for s in states],
        "recommendations": recommendations,
        "open_missions": last["next_day_plan"]["open_tasks"],
        "unresolved_errors": last["general_state"]["agents_in_error"],
        "active_agents": stats_agents,
        "governance": await governance_snapshot(),
    }
