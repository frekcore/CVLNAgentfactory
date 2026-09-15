"""Pure contract projection for MetaCVLN discovery.

Agent Factory remains the controller/executor registry. MetaCVLN consumes these
capability contracts for orchestration; it does not own the 38 agent definitions.
"""
from typing import Optional

from frek_workforce_catalog import FREK_WORKFORCE, FrekRole

ENTITY_IDS = {
    "FREKCORE": "frekcore",
    "FREKANSLA": "frekansla",
    "FREKRAW": "frekraw",
    "FREK Luciole": "frek:luciole",
}


def capability_health(status: Optional[str], runtime_state: Optional[str]) -> str:
    """Map Agent Factory lifecycle/runtime to MetaCVLN green/amber/red health."""
    normalized = (status or "").strip().lower()
    runtime = (runtime_state or "").strip().lower()
    if normalized in {"archive", "archived", "deprecated"} or runtime in {"revoked", "error", "disabled"}:
        return "red"
    if normalized in {"production", "maintenance"} and runtime not in {"paused", "suspendu"}:
        return "green"
    # Prototype/dry-run/sleeping agents are discoverable but intentionally not live.
    return "amber"


def capability_contract(role: FrekRole, *, status: Optional[str] = None,
                        runtime_state: Optional[str] = None) -> dict:
    """Return an object conforming to MetaCVLN Capability contract v1.0."""
    return {
        "contract": "capability",
        "version": "1.0",
        "id": role.capability,
        "name": role.capability,
        "entity_id": ENTITY_IDS[role.entity],
        "input_schema": {
            "type": "object",
            "properties": {
                "mission": {"type": "string"},
                "context": {"type": "object"},
                "trace_id": {"type": "string"},
            },
            "required": ["mission", "trace_id"],
            "additionalProperties": True,
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "evidence": {"type": "object"},
                "result": {},
            },
            "required": ["status"],
            "additionalProperties": True,
        },
        "allowed_actors": ["meta-cvln-os", "AGT-000", "admin"],
        "prohibited_actors": ["anonymous"],
        "requires_approval_by": "human:admin" if role.human_gate else None,
        "escalation_to": "human:admin" if role.human_gate else "AGT-000",
        "p95_latency_ms": None,
        "cost_eur": None,
        "idempotent": False,
        "rollback_supported": False,
        "health": capability_health(status, runtime_state),
    }


def capability_binding(role: FrekRole, *, status: Optional[str] = None,
                       runtime_state: Optional[str] = None) -> dict:
    """Discovery envelope: contract + Agent Factory executor binding."""
    return {
        "capability": capability_contract(role, status=status, runtime_state=runtime_state),
        "executor": {
            "agent_id": role.id,
            "controller": "CVLN Agent Factory",
            "activation": "on_demand",
            "runtime_mode": "dry_run",
            "lifecycle_status": status or "Prototype",
            "runtime_state": runtime_state or "sommeil",
        },
    }


def static_catalog() -> list[dict]:
    return [capability_binding(role) for role in FREK_WORKFORCE]
