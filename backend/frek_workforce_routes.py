"""Read-only discovery surface for FREK AI Workforce capabilities.

MetaCVLN may discover and route to these capabilities. Agent Factory retains
lifecycle/runtime control and executor resolution.
"""
from fastapi import APIRouter, Depends, HTTPException

from auth_utils import get_current_actor
from database import db
from frek_workforce_catalog import FREK_WORKFORCE
from frek_workforce_contracts import capability_binding

router = APIRouter(prefix="/frek-workforce", tags=["frek-workforce"])

ROLE_BY_CAPABILITY = {role.capability: role for role in FREK_WORKFORCE}


async def _runtime_snapshot(agent_id: str) -> tuple[str, str]:
    agent = await db.agents.find_one(
        {"id": agent_id},
        {"_id": 0, "status": 1, "runtime.state": 1},
    )
    if not agent:
        return "missing", "disabled"
    return agent.get("status", "Prototype"), (agent.get("runtime") or {}).get("state", "sommeil")


@router.get("/capabilities")
async def list_frek_capabilities(actor: dict = Depends(get_current_actor)):
    items = []
    for role in FREK_WORKFORCE:
        status, runtime_state = await _runtime_snapshot(role.id)
        items.append(capability_binding(role, status=status, runtime_state=runtime_state))
    return {
        "schema": "cvln.agent-factory.capability-catalog/1.0",
        "source": "CVLN Agent Factory",
        "orchestrator": "MetaCVLN",
        "count": len(items),
        "capabilities": items,
    }


@router.get("/capabilities/{capability_id}")
async def get_frek_capability(capability_id: str, actor: dict = Depends(get_current_actor)):
    role = ROLE_BY_CAPABILITY.get(capability_id)
    if not role:
        raise HTTPException(status_code=404, detail="Unknown FREK capability")
    status, runtime_state = await _runtime_snapshot(role.id)
    return capability_binding(role, status=status, runtime_state=runtime_state)
