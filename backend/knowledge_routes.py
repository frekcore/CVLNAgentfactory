import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from database import db
from auth_utils import get_current_actor, require_admin, log_authz
from event_bus import publish

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

SOURCE_TYPES = ["obsidian", "document", "note", "chatgpt", "claude", "markdown", "pdf", "other"]
CATEGORIES = ["doctrine", "strategy", "process", "business", "history", "research", "founding_decisions"]

CATEGORY_KEYWORDS = {
    "doctrine": ["doctrine", "règle", "principe", "gouvernance", "rule"],
    "strategy": ["stratégie", "strategy", "vision", "objectif", "roadmap", "plan"],
    "process": ["processus", "procédure", "workflow", "étape", "process", "pipeline"],
    "business": ["client", "marché", "produit", "vente", "métier", "business", "revenue"],
    "history": ["historique", "archive", "journal", "history"],
    "research": ["recherche", "analyse", "étude", "research", "benchmark"],
    "founding_decisions": ["décision", "fondateur", "arbitrage", "founding"],
}


class IngestPayload(BaseModel):
    title: str = Field(min_length=3)
    source_type: str = "document"
    category: Optional[str] = None
    content: str = Field(min_length=10)
    target_agents: List[str] = Field(default_factory=list)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def classify(text: str) -> str:
    scores = {}
    low = text.lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        scores[cat] = sum(low.count(kw) for kw in kws)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "business"


@router.get("/categories")
async def categories():
    return {"source_types": SOURCE_TYPES, "categories": CATEGORIES}


@router.post("/ingest")
async def ingest(payload: IngestPayload, actor: dict = Depends(get_current_actor)):
    if actor["type"] == "human" and actor["role"] == "reader":
        raise HTTPException(status_code=403, detail="Readers cannot ingest knowledge")
    if payload.source_type not in SOURCE_TYPES:
        raise HTTPException(status_code=400, detail=f"source_type must be one of {SOURCE_TYPES}")
    category = payload.category or classify(f"{payload.title} {payload.content}")
    if category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"category must be one of {CATEGORIES}")
    valid_agents = [a["id"] async for a in db.agents.find({"id": {"$in": payload.target_agents}}, {"_id": 0, "id": 1})]
    version = await db.knowledge_items.count_documents({"title": payload.title}) + 1
    ts = now_iso()
    item = {"id": str(uuid.uuid4()), "title": payload.title, "source_type": payload.source_type,
            "category": category, "auto_classified": payload.category is None,
            "content": payload.content, "target_agents": valid_agents,
            "status": "ingested", "version": version,
            "created_by": f'{actor["type"]}:{actor["id"]}', "created_at": ts}
    await db.knowledge_items.insert_one({**item})

    # L6 — dual write transition : réplique v2 dans knowledge_sources (legacy jamais supprimé)
    from knowledge_sources_routes import dual_write_from_legacy
    v2_source_id = await dual_write_from_legacy(item)
    await db.knowledge_items.update_one({"id": item["id"]}, {"$set": {"v2_source_id": v2_source_id}})
    item["v2_source_id"] = v2_source_id

    # Pipeline: Ingestion → AGT-002 → CVLN Brain → mémoire des agents concernés
    for agent_id in valid_agents:
        await db.memory_entries.update_one(
            {"agent_id": agent_id, "key": f"knowledge:{item['id']}", "scope": "strategic"},
            {"$set": {"value": {"title": payload.title, "category": category, "knowledge_id": item["id"]},
                      "entity": "CVLN Brain", "updated_at": ts},
             "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": ts, "owner": "AGT-002"}},
            upsert=True)
    await publish("memory.knowledge_ingested", actor["id"],
                  {"knowledge_id": item["id"], "title": payload.title, "category": category,
                   "pipeline": ["source", "knowledge-ingestion", "AGT-002", "cvln-brain", "agent-memory"],
                   "target_agents": valid_agents})
    return item


@router.get("/items")
async def list_items(category: Optional[str] = None, status: Optional[str] = None,
                     search: Optional[str] = None, actor: dict = Depends(get_current_actor)):
    query = {}
    if category:
        query["category"] = category
    if status:
        query["status"] = status
    if search:
        query["$or"] = [{"title": {"$regex": search, "$options": "i"}},
                        {"content": {"$regex": search, "$options": "i"}}]
    return await db.knowledge_items.find(query, {"_id": 0, "content": 0}).sort("created_at", -1).to_list(500)


@router.get("/items/{item_id}")
async def get_item(item_id: str, actor: dict = Depends(get_current_actor)):
    item = await db.knowledge_items.find_one({"id": item_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    return item


@router.post("/items/{item_id}/validate")
async def validate_item(item_id: str, actor: dict = Depends(require_admin)):
    result = await db.knowledge_items.update_one(
        {"id": item_id}, {"$set": {"status": "validated", "validated_by": actor["id"], "validated_at": now_iso()}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    await log_authz(actor, "knowledge_validate", f"knowledge:{item_id}", True, "")
    await publish("memory.knowledge_validated", actor["id"], {"knowledge_id": item_id})
    return {"result": "validated"}


@router.get("/brain/stats")
async def brain_stats(actor: dict = Depends(get_current_actor)):
    by_category, by_status = {}, {}
    async for k in db.knowledge_items.find({}, {"_id": 0, "category": 1, "status": 1}):
        by_category[k["category"]] = by_category.get(k["category"], 0) + 1
        by_status[k["status"]] = by_status.get(k["status"], 0) + 1
    return {"total": sum(by_status.values()), "by_category": by_category, "by_status": by_status}
