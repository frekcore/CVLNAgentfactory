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
