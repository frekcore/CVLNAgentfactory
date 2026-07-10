import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from database import db
from auth_utils import get_current_actor, require_registry_writer, require_admin, log_authz
from event_bus import publish
from notifier import notify

router = APIRouter(prefix="/evolution", tags=["improvement-loop"])

PROPOSAL_TYPES = ["improve_agent", "create_agent", "modify_workflow", "optimize_procedure"]


class ProposalPayload(BaseModel):
    type: str
    title: str = Field(min_length=5)
    description: str = Field(min_length=10)
    target_agent_id: Optional[str] = None
    source: str = "manual"


class DecisionPayload(BaseModel):
    decision: str  # validated | rejected
    note: str = ""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


@router.get("/proposals")
async def list_proposals(status: Optional[str] = None, actor: dict = Depends(get_current_actor)):
    query = {"status": status} if status else {}
    return await db.evolution_proposals.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/proposals")
async def create_proposal(payload: ProposalPayload, actor: dict = Depends(require_registry_writer)):
    if payload.type not in PROPOSAL_TYPES:
        raise HTTPException(status_code=400, detail=f"type must be one of {PROPOSAL_TYPES}")
    proposal = {"id": str(uuid.uuid4()), **payload.model_dump(), "status": "proposed",
                "proposed_by": f'{actor["type"]}:{actor["id"]}',
                "decision_by": None, "decision_note": "", "created_at": now_iso(), "decided_at": None}
    await db.evolution_proposals.insert_one({**proposal})
    await publish("factory.evolution_proposed", actor["id"],
                  {"proposal_id": proposal["id"], "type": payload.type, "title": payload.title})
    await notify(2, "Proposition d'évolution à valider",
                 f"[{payload.type}] {payload.title} — proposé par {proposal['proposed_by']}",
                 source="improvement-loop", meta={"proposal_id": proposal["id"]})
    return proposal


@router.post("/proposals/{proposal_id}/decide")
async def decide_proposal(proposal_id: str, payload: DecisionPayload, actor: dict = Depends(require_admin)):
    """Toute modification stratégique nécessite validation humaine (admin)."""
    if payload.decision not in ("validated", "rejected"):
        raise HTTPException(status_code=400, detail="decision must be 'validated' or 'rejected'")
    proposal = await db.evolution_proposals.find_one({"id": proposal_id}, {"_id": 0})
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal["status"] != "proposed":
        raise HTTPException(status_code=409, detail=f"Proposal already {proposal['status']}")
    await db.evolution_proposals.update_one(
        {"id": proposal_id},
        {"$set": {"status": payload.decision, "decision_by": f'human:{actor["id"]}',
                  "decision_note": payload.note, "decided_at": now_iso()}})
    await log_authz(actor, "evolution_decision", f"proposal:{proposal_id}", True,
                    f"{payload.decision} — {proposal['title']}")
    await publish("factory.evolution_decided", actor["id"],
                  {"proposal_id": proposal_id, "decision": payload.decision, "title": proposal["title"]})
    return {"result": payload.decision, "proposal_id": proposal_id}
