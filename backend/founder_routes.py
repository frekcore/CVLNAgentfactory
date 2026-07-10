from fastapi import APIRouter, Depends
from database import db
from auth_utils import require_admin
from doctrine import DOCTRINE_VERSION

router = APIRouter(prefix="/founder", tags=["founder-control-center"])


@router.get("/overview")
async def founder_overview(actor: dict = Depends(require_admin)):
    agents = await db.agents.find({}, {"_id": 0, "id": 1, "name": 1, "status": 1, "pole": 1, "entity": 1,
                                       "autonomy": 1}).to_list(2000)
    by_status = {}
    for a in agents:
        by_status[a["status"]] = by_status.get(a["status"], 0) + 1

    proposals = await db.evolution_proposals.find({"status": "proposed"}, {"_id": 0}).sort("created_at", -1).to_list(50)
    beta_agents = [a for a in agents if a["status"] == "Beta"]

    last_closing = await db.daily_reports.find_one({"status": "closed"}, {"_id": 0, "date": 1,
                                                   "average_confidence": 1, "executive_report": 1,
                                                   "general_state": 1, "next_day_plan": 1}, sort=[("date", -1)])
    interventions = []
    if last_closing:
        interventions = last_closing.get("next_day_plan", {}).get("critical_missions", [])

    entries = await db.finance_entries.find({}, {"_id": 0, "type": 1, "amount": 1}).to_list(10000)
    total_cost = round(sum(e["amount"] for e in entries if e["type"] == "cost"), 2)
    total_revenue = round(sum(e["amount"] for e in entries if e["type"] == "revenue"), 2)

    alerts = await db.events.find({"topic": "monitoring.alert"}, {"_id": 0}).sort("timestamp", -1).to_list(10)
    denied = await db.audit_logs.count_documents({"allowed": False})
    entities_count = await db.entities.count_documents({})
    knowledge_total = await db.knowledge_items.count_documents({})
    knowledge_pending = await db.knowledge_items.count_documents({"status": "ingested"})
    open_tasks = await db.agent_tasks.count_documents({"status": {"$in": ["open", "in_progress"]}})
    blocked_tasks = await db.agent_tasks.count_documents({"status": "blocked"})

    return {
        "governance_model": "Laurent décide · AGT-000 supervise · Core Services organisent · Agents exécutent",
        "doctrine_version": DOCTRINE_VERSION,
        "ecosystem": {"total_agents": len(agents), "target": 284, "by_status": by_status,
                      "entities": entities_count},
        "pending_validations": {
            "evolution_proposals": proposals,
            "beta_awaiting_production": [{"id": a["id"], "name": a["name"]} for a in beta_agents],
            "human_interventions": interventions,
            "knowledge_to_validate": knowledge_pending,
        },
        "finance": {"total_cost": total_cost, "total_revenue": total_revenue,
                    "net": round(total_revenue - total_cost, 2), "currency": "EUR"},
        "operations": {"open_tasks": open_tasks, "blocked_tasks": blocked_tasks},
        "security": {"denied_authorizations_total": denied},
        "alerts": alerts,
        "last_closing": last_closing,
        "knowledge": {"total": knowledge_total, "pending_validation": knowledge_pending},
    }
