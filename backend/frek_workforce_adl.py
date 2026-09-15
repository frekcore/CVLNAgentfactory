"""ADL v2 generator for the 38-agent FREK workforce.

No database write occurs here. The catalog can be validated/seeded by Agent Factory under an explicit gate.
"""
from datetime import datetime, timezone
from frek_workforce_catalog import FREK_WORKFORCE, FrekRole

SCHEMA_URI = "https://cvln.group/schemas/adl/2.0"
REGISTERED_BY = "AGT-000"


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_adl(role: FrekRole, now: str | None = None) -> dict:
    now = now or _iso()
    gate_condition = (
        "Human approval required for governance, production deployment, external publication, "
        "financial commitment, destructive action, credential/key mutation, permission expansion or certification."
    )
    return {
        "adl_version": "2.0",
        "schema_uri": SCHEMA_URI,
        "agent": {
            "id": role.id,
            "name": role.name,
            "pole": role.pole,
            "entity": role.entity,
            "version": "0.1.0",
            "status": "PROTOTYPE",
            "mission": role.mission,
            "vision": "Operate as a bounded FREK specialist under CVLN Agent Factory control and MetaCVLN orchestration, preserving human authority.",
            "objectives": [{
                "id": "OBJ-001",
                "description": f"Deliver governed capability {role.capability} within the assigned authority boundary.",
                "kpi": "policy_compliant_runs_ratio",
                "target": 1.0,
                "deadline": "2027-12-31T23:59:59+00:00",
            }],
            "kpis": [
                {"metric": "policy_compliant_runs_ratio", "target": 1.0, "frequency": "daily"},
                {"metric": "unapproved_privilege_escalations", "target": 0.0, "frequency": "daily"},
            ],
        },
        "brain": {
            "registry": {"registered_at": now, "last_updated": now, "registered_by": REGISTERED_BY},
            "memory": {
                "scope": "persistent",
                "owner": role.id,
                "vector_store_id": f"vs-sovereign-{role.id.lower()}",
                "consolidation_policy": {"enabled": True, "interval": "24h", "summary_model": "sovereign-internal"},
            },
            "identity": {
                "auth_method": "mTLS",
                "permissions": {
                    "read": list(role.read_scope),
                    "write": list(role.write_scope),
                    "entities": [role.entity],
                },
                "secrets_scope": f"cvln/agents/{role.id}",
            },
            "events": {
                "subscribe": [f"mission.assigned.{role.id.lower()}", "agent.control.pause", "agent.control.revoke"],
                "publish": ["agent.run.started", "agent.run.completed", "agent.run.blocked", "agent.evidence.created"],
                "priority": "normal",
            },
            "monitoring": {
                "metrics_export": "prometheus",
                "alert_thresholds": {"error_rate": 0.05, "latency_p99": "5000ms", "memory_usage": "85%"},
            },
        },
        "capabilities": {
            "tools": [],
            "knowledge": [],
            "permissions": {
                "tools": [],
                "knowledge": [],
            },
            "tests": [
                {"id": "TST-BOUNDARY", "name": "Authority boundary", "type": "security", "script": "deny_out_of_scope_write", "expected_result": "denied"},
                {"id": "TST-ESCALATION", "name": "Sensitive action escalation", "type": "security", "script": gate_condition, "expected_result": "human_gate_required"},
                {"id": "TST-DRYRUN", "name": "Prototype is non-production", "type": "integration", "script": "assert_runtime_mode_dry_run", "expected_result": "dry_run"},
            ],
        },
        "cvln_governance": {
            "orchestrator": "MetaCVLN",
            "controller": "CVLN Agent Factory",
            "runtime_mode": "dry_run",
            "activation": "on_demand",
            "self_permission_expansion": False,
            "human_gate_required": role.human_gate,
            "capability_id": role.capability,
            "authority_model": "least_privilege",
        },
    }


def build_catalog(now: str | None = None) -> list[dict]:
    now = now or _iso()
    return [build_adl(role, now) for role in FREK_WORKFORCE]
