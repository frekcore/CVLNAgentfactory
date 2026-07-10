import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from database import db
from auth_utils import get_current_actor, require_registry_writer, log_authz
from event_bus import publish

router = APIRouter(prefix="/entities", tags=["entity-registry"])

ENTITY_TYPES = ["holding", "brain", "musique", "ia", "media", "education", "tech", "creative", "other"]


class EntityPayload(BaseModel):
    name: str = Field(min_length=2)
    type: str = "other"
    description: str = ""
    activities: List[str] = Field(default_factory=list)
    data_domains: List[str] = Field(default_factory=list)
    apis: List[str] = Field(default_factory=list)
    objectives: List[str] = Field(default_factory=list)


class LinkAgentsPayload(BaseModel):
    agent_ids: List[str]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


@router.get("")
async def list_entities(actor: dict = Depends(get_current_actor)):
    entities = await db.entities.find({}, {"_id": 0}).sort("name", 1).to_list(200)
    for e in entities:
        e["agent_count"] = len(e.get("agent_ids", []))
    return entities


@router.get("/{entity_id}")
async def get_entity(entity_id: str, actor: dict = Depends(get_current_actor)):
    entity = await db.entities.find_one({"id": entity_id}, {"_id": 0})
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    agents = await db.agents.find({"id": {"$in": entity.get("agent_ids", [])}},
                                  {"_id": 0, "id": 1, "name": 1, "status": 1, "pole": 1}).to_list(500)
    entity["agents"] = agents
    return entity


@router.post("")
async def create_entity(payload: EntityPayload, actor: dict = Depends(require_registry_writer)):
    if await db.entities.find_one({"name": payload.name}):
        raise HTTPException(status_code=409, detail="Entity already exists")
    entity = {"id": str(uuid.uuid4()), **payload.model_dump(), "agent_ids": [],
              "created_at": now_iso(), "updated_at": now_iso()}
    await db.entities.insert_one({**entity})
    await log_authz(actor, "entity_create", f"entity:{payload.name}", True, "")
    await publish("factory.entity_created", actor["id"], {"name": payload.name, "type": payload.type})
    return entity


@router.patch("/{entity_id}")
async def update_entity(entity_id: str, payload: EntityPayload, actor: dict = Depends(require_registry_writer)):
    result = await db.entities.update_one({"id": entity_id},
                                          {"$set": {**payload.model_dump(), "updated_at": now_iso()}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"result": "ok"}


@router.post("/{entity_id}/agents")
async def link_agents(entity_id: str, payload: LinkAgentsPayload, actor: dict = Depends(require_registry_writer)):
    entity = await db.entities.find_one({"id": entity_id})
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    valid = [a["id"] async for a in db.agents.find({"id": {"$in": payload.agent_ids}}, {"_id": 0, "id": 1})]
    await db.entities.update_one({"id": entity_id},
                                 {"$addToSet": {"agent_ids": {"$each": valid}}, "$set": {"updated_at": now_iso()}})
    await publish("factory.agents_assigned", actor["id"], {"entity": entity["name"], "agents": valid})
    return {"result": "ok", "linked": valid}


@router.delete("/{entity_id}/agents/{agent_id}")
async def unlink_agent(entity_id: str, agent_id: str, actor: dict = Depends(require_registry_writer)):
    await db.entities.update_one({"id": entity_id}, {"$pull": {"agent_ids": agent_id}})
    return {"result": "ok"}
