import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from database import db
from auth_utils import get_current_actor, require_admin, log_authz
from activity_journal import journal
from event_bus import publish
from doctrine import DOCTRINE_SECTIONS

router = APIRouter(prefix="/doctrine/registry", tags=["doctrine-registry-v2"])

STATUSES = ["proposition", "validee", "active", "archivee"]
STATUS_FLOW = {"proposition": ["validee", "archivee"], "validee": ["active", "archivee"],
               "active": ["archivee"], "archivee": []}


class DoctrinePayload(BaseModel):
    title: str = Field(min_length=5)
    principle: str = Field(min_length=10)
    rules: List[str] = Field(default_factory=list)
    category: str = "governance"
    agents_concerned: List[str] = Field(default_factory=list)
    missions_concerned: List[str] = Field(default_factory=list)


class DoctrineUpdate(BaseModel):
    title: Optional[str] = None
    principle: Optional[str] = None
    rules: Optional[List[str]] = None
    agents_concerned: Optional[List[str]] = None
    missions_concerned: Optional[List[str]] = None
    note: str = ""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def snapshot_version(doc: dict, actor_label: str, note: str):
    await db.doctrine_versions.insert_one({
        "id": str(uuid.uuid4()), "doctrine_id": doc["id"], "version": doc["version"],
        "status": doc["status"], "content": {k: doc[k] for k in
                                             ("title", "principle", "rules", "category",
                                              "agents_concerned", "missions_concerned")},
        "actor": actor_label, "note": note, "timestamp": now_iso()})


@router.get("")
async def list_doctrines(status: Optional[str] = None, actor: dict = Depends(get_current_actor)):
    query = {"status": status} if status else {}
    return await db.doctrine_registry.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.get("/{doctrine_id}/history")
async def doctrine_history(doctrine_id: str, actor: dict = Depends(get_current_actor)):
    doc = await db.doctrine_registry.find_one({"id": doctrine_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Doctrine not found")
    versions = await db.doctrine_versions.find({"doctrine_id": doctrine_id}, {"_id": 0}) \
        .sort("timestamp", -1).to_list(100)
    return {"doctrine": doc, "versions": versions}


@router.post("")
async def propose_doctrine(payload: DoctrinePayload, actor: dict = Depends(get_current_actor)):
    if actor["type"] == "human" and actor["role"] == "reader":
        raise HTTPException(status_code=403, detail="Readers cannot propose doctrines")
    ts = now_iso()
    count = await db.doctrine_registry.count_documents({})
    actor_label = f'{actor["type"]}:{actor["id"]}'
    doc = {"id": f"DR-{count + 1:03d}", **payload.model_dump(), "version": 1,
           "status": "proposition", "author": actor_label,
           "validated_by": None, "validated_at": None,
           "history": [{"event": "proposed", "actor": actor_label, "timestamp": ts, "note": ""}],
           "created_at": ts, "updated_at": ts}
    await db.doctrine_registry.insert_one({**doc})
    await snapshot_version(doc, actor_label, "proposition initiale")
    await journal("proposition", actor, f"Doctrine proposée : {payload.title}",
                  source="doctrine-registry", evidence={"doctrine_id": doc["id"]}, result="proposition")
    await publish("factory.doctrine_proposed", actor["id"], {"doctrine_id": doc["id"], "title": payload.title})
    doc.pop("_id", None)
    return doc


@router.patch("/{doctrine_id}")
async def update_doctrine(doctrine_id: str, payload: DoctrineUpdate, actor: dict = Depends(get_current_actor)):
    if actor["type"] == "human" and actor["role"] == "reader":
        raise HTTPException(status_code=403, detail="Readers cannot update doctrines")
    doc = await db.doctrine_registry.find_one({"id": doctrine_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Doctrine not found")
    if doc["status"] == "archivee":
        raise HTTPException(status_code=409, detail="Archived doctrine is immutable")
    update = {k: v for k, v in payload.model_dump().items() if v is not None and k != "note"}
    if not update:
        raise HTTPException(status_code=400, detail="Nothing to update")
    ts = now_iso()
    actor_label = f'{actor["type"]}:{actor["id"]}'
    new_version = doc["version"] + 1
    await db.doctrine_registry.update_one(
        {"id": doctrine_id},
        {"$set": {**update, "version": new_version, "updated_at": ts},
         "$push": {"history": {"event": "updated", "actor": actor_label, "timestamp": ts,
                               "note": payload.note, "version": new_version}}})
    updated = await db.doctrine_registry.find_one({"id": doctrine_id}, {"_id": 0})
    await snapshot_version(updated, actor_label, payload.note or "mise à jour")
    await journal("proposition", actor, f"Doctrine mise à jour (v{new_version}) : {updated['title']}",
                  source="doctrine-registry", evidence={"doctrine_id": doctrine_id, "note": payload.note},
                  result="updated")
    return updated


@router.post("/{doctrine_id}/status")
async def change_status(doctrine_id: str, status: str, note: str = "",
                        actor: dict = Depends(require_admin)):
    """Governance transitions require the human validator (Laurent/admin)."""
    if status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {STATUSES}")
    doc = await db.doctrine_registry.find_one({"id": doctrine_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Doctrine not found")
    if status not in STATUS_FLOW[doc["status"]]:
        raise HTTPException(status_code=409,
                            detail=f"Transition {doc['status']} → {status} interdite (flux: {STATUS_FLOW[doc['status']]})")
    ts = now_iso()
    actor_label = f'human:{actor["id"]}'
    update = {"status": status, "updated_at": ts}
    if status == "validee":
        update["validated_by"] = actor_label
        update["validated_at"] = ts
    await db.doctrine_registry.update_one(
        {"id": doctrine_id},
        {"$set": update,
         "$push": {"history": {"event": f"status:{status}", "actor": actor_label,
                               "timestamp": ts, "note": note}}})
    updated = await db.doctrine_registry.find_one({"id": doctrine_id}, {"_id": 0})
    await snapshot_version(updated, actor_label, f"statut → {status}. {note}")
    await journal("decision_humaine", actor,
                  f"Doctrine « {doc['title']} » : {doc['status']} → {status}",
                  source="doctrine-registry", evidence={"doctrine_id": doctrine_id, "note": note}, result=status)
    await log_authz(actor, "doctrine_status_change", doctrine_id, True, f"{doc['status']} → {status}")
    await publish("factory.doctrine_status_changed", actor["id"],
                  {"doctrine_id": doctrine_id, "status": status})
    return updated


async def seed_doctrine_registry():
    """Idempotent non-destructive import of legacy v1.0 rules as governed v2 records."""
    if await db.doctrine_registry.count_documents({"author": "legacy-import:doctrine-v1.0"}) > 0:
        return
    ts = now_iso()
    for section in DOCTRINE_SECTIONS:
        for rule in section["rules"]:
            doc = {"id": rule["id"], "title": f'{section["title_fr"]} — {rule["id"]}',
                   "principle": rule["fr"], "rules": [rule["fr"]], "category": section["key"],
                   "agents_concerned": [], "missions_concerned": [],
                   "version": 1, "status": "active",
                   "author": "legacy-import:doctrine-v1.0",
                   "validated_by": "human:laurent (import doctrine v1.0)", "validated_at": ts,
                   "history": [{"event": "imported_from_v1", "actor": "system:seed", "timestamp": ts,
                                "note": "Import non destructif de la doctrine v1.0"}],
                   "created_at": ts, "updated_at": ts}
            await db.doctrine_registry.insert_one(doc)
