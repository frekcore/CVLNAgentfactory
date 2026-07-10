import os
import json
import gzip
import uuid
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from database import db
from auth_utils import require_admin, log_authz
from event_bus import publish

router = APIRouter(prefix="/continuity", tags=["continuity-layer"])

BACKUP_DIR = Path("/app/backups")
COLLECTIONS = ["agents", "versions", "entities", "doctrine", "knowledge_items", "memory_entries",
               "memory_snapshots", "missions", "agent_tasks", "evolution_proposals", "daily_reports",
               "daily_agent_reports", "finance_entries", "catalog_entries", "users", "identities",
               "cognitive_conversations", "cognitive_messages", "settings"]


@router.post("/backup")
async def create_backup(actor: dict = Depends(require_admin)):
    BACKUP_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dump = {"created_at": datetime.now(timezone.utc).isoformat(), "collections": {}}
    total = 0
    for coll in COLLECTIONS:
        docs = await db[coll].find({}, {"_id": 0, "password_hash": 0, "token_hash": 0}).to_list(50000)
        dump["collections"][coll] = docs
        total += len(docs)
    path = BACKUP_DIR / f"cvln_backup_{ts}.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(dump, f, ensure_ascii=False, default=str)
    record = {"id": str(uuid.uuid4()), "file": path.name, "documents": total,
              "size_kb": round(path.stat().st_size / 1024, 1),
              "collections": len(COLLECTIONS), "created_by": actor["id"],
              "created_at": dump["created_at"]}
    await db.backups.insert_one({**record})
    await log_authz(actor, "continuity_backup", path.name, True, f"{total} documents")
    await publish("system.backup_created", actor["id"], {"file": path.name, "documents": total})
    return record


@router.get("/backups")
async def list_backups(actor: dict = Depends(require_admin)):
    return await db.backups.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
