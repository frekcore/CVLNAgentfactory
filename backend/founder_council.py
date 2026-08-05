"""Founder Council (F-001 / ADR-001) — FALLBACK uniquement, jamais délégation systématique.
AGT-000 reste le point d'entrée nominal. Si AGT-000 est indisponible, un quorum de 3 fondateurs
(AGT-001→AGT-010) peut co-signer une action Registry à usage unique."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from database import db
from auth_utils import get_current_actor, require_admin, log_authz
from activity_journal import journal
from event_bus import publish
from notifier import notify

router = APIRouter(prefix="/council", tags=["founder-council"])

FOUNDERS = [f"AGT-{i:03d}" for i in range(1, 11)]
QUORUM = 3


class ProposalPayload(BaseModel):
    action: str = Field(min_length=5)  # ex: registry_write, agent_creation
    justification: str = Field(min_length=10)
    payload_summary: str = ""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def agt000_available() -> bool:
    a = await db.agents.find_one({"id": "AGT-000"}, {"_id": 0, "runtime.state": 1, "status": 1})
    if not a:
        return False
    state = (a.get("runtime") or {}).get("state", "sommeil")
    return a.get("status") not in ("Archive",) and state not in ("erreur", "suspendu", "termine")


@router.get("/status")
async def council_status(actor: dict = Depends(get_current_actor)):
    return {"agt000_available": await agt000_available(), "founders": FOUNDERS, "quorum": QUORUM,
            "principle": "Fallback uniquement — AGT-000 reste le point d'entrée nominal (décision Laurent)"}


@router.get("/proposals")
async def list_proposals(status: Optional[str] = None, actor: dict = Depends(get_current_actor)):
    query = {"status": status} if status else {}
    return await db.council_proposals.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)


@router.post("/proposals")
async def create_proposal(payload: ProposalPayload, actor: dict = Depends(get_current_actor)):
    if actor["type"] == "human" and actor["role"] == "reader":
        raise HTTPException(status_code=403, detail="Readers cannot open council proposals")
    if await agt000_available():
        raise HTTPException(status_code=409,
                            detail="AGT-000 est disponible — le Founder Council est un fallback, pas une délégation. "
                                   "Passez par la voie nominale (AGT-000 ou admin).")
    prop = {"id": str(uuid.uuid4()), **payload.model_dump(), "signatures": [],
            "status": "pending", "used": False, "used_at": None,
            "created_by": f'{actor["type"]}:{actor["id"]}', "created_at": now_iso()}
    await db.council_proposals.insert_one({**prop})
    await journal("proposition", actor, f"Founder Council saisi (AGT-000 indisponible) : {payload.action} — {payload.justification[:120]}",
                  source="founder-council", evidence={"proposal_id": prop["id"]}, result="pending")
    await notify(2, "Founder Council activé", f"AGT-000 indisponible. Proposition « {payload.action} » ouverte "
                                              f"— quorum {QUORUM} fondateurs requis.", source="founder-council")
    return prop


@router.post("/proposals/{proposal_id}/sign")
async def sign_proposal(proposal_id: str, actor: dict = Depends(get_current_actor)):
    if not (actor["type"] == "service" and actor["id"] in FOUNDERS) and \
       not (actor["type"] == "human" and actor["role"] == "admin"):
        raise HTTPException(status_code=403, detail=f"Seuls les fondateurs ({FOUNDERS[0]}→{FOUNDERS[-1]}) ou un admin signent")
    prop = await db.council_proposals.find_one({"id": proposal_id}, {"_id": 0})
    if not prop:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if prop["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Proposal is {prop['status']}")
    signer = actor["id"] if actor["type"] == "service" else f'admin:{actor["id"]}'
    if signer in prop["signatures"]:
        raise HTTPException(status_code=409, detail="Déjà signé par cette identité")
    signatures = prop["signatures"] + [signer]
    status = "approved" if len(signatures) >= QUORUM else "pending"
    await db.council_proposals.update_one({"id": proposal_id},
                                          {"$set": {"signatures": signatures, "status": status,
                                                    "approved_at": now_iso() if status == "approved" else None}})
    await journal("decision_humaine" if actor["type"] == "human" else "proposition", actor,
                  f"Signature Council {len(signatures)}/{QUORUM} sur « {prop['action']} »"
                  + (" — QUORUM ATTEINT" if status == "approved" else ""),
                  source="founder-council", evidence={"proposal_id": proposal_id}, result=status)
    if status == "approved":
        await publish("factory.council_quorum", actor["id"], {"proposal_id": proposal_id, "action": prop["action"]})
    return {"result": status, "signatures": signatures, "quorum": QUORUM}


async def check_council_approval(approval_id: str) -> bool:
    """Autorisation Registry à usage unique via quorum du Council (utilisé par require_registry_writer)."""
    prop = await db.council_proposals.find_one({"id": approval_id}, {"_id": 0})
    if not prop or prop["status"] != "approved" or prop["used"]:
        return False
    await db.council_proposals.update_one({"id": approval_id},
                                          {"$set": {"used": True, "used_at": now_iso()}})
    await journal("action_executee", {"type": "system", "id": "founder-council", "name": "Founder Council"},
                  f"Approbation Council consommée (usage unique) : {prop['action']}",
                  source="founder-council", evidence={"proposal_id": approval_id}, result="consumed")
    return True
