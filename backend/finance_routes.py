import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from database import db
from auth_utils import get_current_actor
from event_bus import publish

router = APIRouter(prefix="/finance", tags=["finance"])

ENTRY_TYPES = ["cost", "revenue"]
CATEGORIES = ["api", "infrastructure", "software", "service", "production", "data", "other"]


class FinanceEntry(BaseModel):
    type: str
    category: str = "other"
    agent_id: Optional[str] = None
    entity: Optional[str] = None
    amount: float = Field(gt=0)
    currency: str = "EUR"
    description: str = ""
    date: Optional[str] = None


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------- Financial Compliance Gatekeeper (F-003) ----------
# Plafonds : <=10 000€ auto-approuvé · 10 000-100 000€ validation Wudy/admin · >100 000€ deux validateurs distincts
AUTO_LIMIT, SINGLE_LIMIT = 10000, 100000


class ExpenseRequest(BaseModel):
    amount: float = Field(gt=0)
    description: str = Field(min_length=5)
    entity: str = ""
    agent_id: Optional[str] = None
    category: str = "other"


@router.get("/expense-requests")
async def list_expense_requests(status: Optional[str] = None, actor: dict = Depends(get_current_actor)):
    query = {"status": status} if status else {}
    return await db.expense_requests.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.post("/expense-request")
async def request_expense(payload: ExpenseRequest, actor: dict = Depends(get_current_actor)):
    from activity_journal import journal
    from notifier import notify
    if actor["type"] == "human" and actor["role"] == "reader":
        raise HTTPException(status_code=403, detail="Readers cannot request expenses")
    ts = now_iso()
    required = 0 if payload.amount <= AUTO_LIMIT else (1 if payload.amount <= SINGLE_LIMIT else 2)
    req = {"id": str(uuid.uuid4()), **payload.model_dump(),
           "required_approvals": required, "approvals": [],
           "status": "auto_approved" if required == 0 else "pending",
           "requested_by": f'{actor["type"]}:{actor["id"]}', "created_at": ts, "updated_at": ts}
    await db.expense_requests.insert_one({**req})
    if required == 0:
        await db.finance_entries.insert_one({
            "id": str(uuid.uuid4()), "type": "cost", "category": payload.category,
            "agent_id": payload.agent_id, "entity": payload.entity, "amount": payload.amount,
            "currency": "EUR", "description": f"[auto<={AUTO_LIMIT}€] {payload.description}",
            "date": ts[:10], "created_by": req["requested_by"], "created_at": ts})
        await journal("action_executee", actor,
                      f"Dépense auto-approuvée (Gatekeeper, ≤{AUTO_LIMIT}€) : {payload.amount}€ — {payload.description[:80]}",
                      source="financial-gatekeeper", agent_id=payload.agent_id,
                      evidence={"expense_id": req["id"]}, result="auto_approved")
    else:
        await journal("proposition", actor,
                      f"Dépense {payload.amount}€ en attente ({required} validation(s) requise(s)) : {payload.description[:80]}",
                      source="financial-gatekeeper", agent_id=payload.agent_id,
                      evidence={"expense_id": req["id"]}, result="pending")
        await notify(2, "Dépense — validation requise",
                     f"{payload.amount}€ ({payload.entity or 'groupe'}) : {payload.description[:120]} — "
                     f"{required} validation(s) requise(s) (plafonds Gatekeeper).", source="financial-gatekeeper")
    return req


@router.post("/expense-requests/{request_id}/approve")
async def approve_expense(request_id: str, decision: str = "approved", actor: dict = Depends(get_current_actor)):
    from activity_journal import journal
    if not (actor["type"] == "human" and actor["role"] == "admin"):
        raise HTTPException(status_code=403, detail="Seul un validateur humain (Wudy/admin) approuve les dépenses")
    if decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="decision must be approved or rejected")
    req = await db.expense_requests.find_one({"id": request_id}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Expense request not found")
    if req["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Request is {req['status']}")
    validator = f'human:{actor["id"]}'
    if validator in req["approvals"]:
        raise HTTPException(status_code=409, detail="Déjà validé par ce validateur — un second pair distinct est requis")
    ts = now_iso()
    if decision == "rejected":
        await db.expense_requests.update_one({"id": request_id},
                                             {"$set": {"status": "rejected", "updated_at": ts},
                                              "$push": {"approvals": validator}})
        await journal("decision_humaine", actor, f"Dépense REJETÉE : {req['amount']}€ — {req['description'][:80]}",
                      source="financial-gatekeeper", evidence={"expense_id": request_id}, result="rejected")
        return {"result": "rejected"}
    approvals = req["approvals"] + [validator]
    done = len(approvals) >= req["required_approvals"]
    await db.expense_requests.update_one({"id": request_id},
                                         {"$set": {"status": "approved" if done else "pending", "updated_at": ts},
                                          "$push": {"approvals": validator}})
    await journal("decision_humaine", actor,
                  f"Validation dépense {len(approvals)}/{req['required_approvals']} : {req['amount']}€"
                  + (" — APPROUVÉE" if done else " — en attente du second validateur"),
                  source="financial-gatekeeper", evidence={"expense_id": request_id},
                  result="approved" if done else "pending")
    if done:
        await db.finance_entries.insert_one({
            "id": str(uuid.uuid4()), "type": "cost", "category": req["category"],
            "agent_id": req["agent_id"], "entity": req["entity"], "amount": req["amount"],
            "currency": "EUR", "description": f"[validé Gatekeeper] {req['description']}",
            "date": ts[:10], "created_by": req["requested_by"], "created_at": ts})
    return {"result": "approved" if done else "pending", "approvals": approvals,
            "required": req["required_approvals"]}


@router.post("/entries")
async def add_entry(payload: FinanceEntry, actor: dict = Depends(get_current_actor)):
    if actor["type"] == "human" and actor["role"] == "reader":
        raise HTTPException(status_code=403, detail="Readers cannot record finance entries")
    if payload.type not in ENTRY_TYPES:
        raise HTTPException(status_code=400, detail=f"type must be one of {ENTRY_TYPES}")
    if payload.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"category must be one of {CATEGORIES}")
    entry = {"id": str(uuid.uuid4()), **payload.model_dump(),
             "date": payload.date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
             "created_by": f'{actor["type"]}:{actor["id"]}', "created_at": now_iso()}
    await db.finance_entries.insert_one({**entry})
    await publish("monitoring.finance_entry", actor["id"],
                  {"type": payload.type, "amount": payload.amount, "agent_id": payload.agent_id})
    return entry


@router.get("/entries")
async def list_entries(type: Optional[str] = None, agent_id: Optional[str] = None,
                       entity: Optional[str] = None, limit: int = 200,
                       actor: dict = Depends(get_current_actor)):
    query = {}
    if type:
        query["type"] = type
    if agent_id:
        query["agent_id"] = agent_id
    if entity:
        query["entity"] = entity
    return await db.finance_entries.find(query, {"_id": 0}).sort("date", -1).to_list(min(limit, 1000))


@router.get("/summary")
async def finance_summary(actor: dict = Depends(get_current_actor)):
    entries = await db.finance_entries.find({}, {"_id": 0}).to_list(10000)
    total_cost = sum(e["amount"] for e in entries if e["type"] == "cost")
    total_revenue = sum(e["amount"] for e in entries if e["type"] == "revenue")
    net = round(total_revenue - total_cost, 2)
    roi = round((total_revenue - total_cost) / total_cost * 100, 1) if total_cost > 0 else None

    def bucket(key):
        out = {}
        for e in entries:
            k = e.get(key)
            if not k:
                continue
            b = out.setdefault(k, {"cost": 0, "revenue": 0})
            b[e["type"]] += e["amount"]
        for k, b in out.items():
            b["cost"] = round(b["cost"], 2)
            b["revenue"] = round(b["revenue"], 2)
            b["net"] = round(b["revenue"] - b["cost"], 2)
            b["roi"] = round((b["revenue"] - b["cost"]) / b["cost"] * 100, 1) if b["cost"] > 0 else None
        return out

    by_category = {}
    for e in entries:
        if e["type"] == "cost":
            by_category[e["category"]] = round(by_category.get(e["category"], 0) + e["amount"], 2)

    dates = sorted({e["date"] for e in entries})
    span_days = max(1, (datetime.fromisoformat(dates[-1]) - datetime.fromisoformat(dates[0])).days + 1) if dates else 1
    forecast_30d = round(net / span_days * 30, 2) if entries else 0

    return {"total_cost": round(total_cost, 2), "total_revenue": round(total_revenue, 2),
            "net": net, "roi_percent": roi, "entries_count": len(entries),
            "by_agent": bucket("agent_id"), "by_entity": bucket("entity"),
            "cost_by_category": by_category, "forecast_net_30d": forecast_30d, "currency": "EUR"}
