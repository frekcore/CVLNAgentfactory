"""Idempotent bootstrap for FREK AI Workforce.

The bootstrap registers 38 agents as PROTOTYPE + dry_run. It never creates
service tokens, never activates production, and never overwrites an existing
agent definition. Conflicts fail closed and are journaled by the caller.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft7Validator

from database import db
from frek_workforce_catalog import FREK_WORKFORCE
from frek_workforce_adl import build_adl

logger = logging.getLogger(__name__)

_SCHEMA = json.loads((Path(__file__).parent / "schemas" / "adl_v2_schema.json").read_text())
VALIDATOR = Draft7Validator(_SCHEMA)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_adl(doc: dict) -> list[str]:
    return [
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in VALIDATOR.iter_errors(doc)
    ]


async def seed_frek_workforce() -> dict:
    """Register missing FREK workforce definitions without granting live execution."""
    result = {"expected": 38, "created": 0, "existing": 0, "conflicts": [], "invalid": []}
    ts = now_iso()

    for role in FREK_WORKFORCE:
        adl = build_adl(role, ts)
        errors = validate_adl(adl)
        if errors:
            result["invalid"].append({"agent_id": role.id, "errors": errors[:10]})
            continue

        existing_by_id = await db.agents.find_one({"id": role.id}, {"_id": 0, "id": 1, "name": 1})
        existing_by_name = await db.agents.find_one({"name": role.name, "entity": role.entity}, {"_id": 0, "id": 1, "name": 1})
        if existing_by_id:
            if existing_by_id.get("name") != role.name:
                result["conflicts"].append({"agent_id": role.id, "reason": "id_already_owned", "existing": existing_by_id})
            else:
                result["existing"] += 1
            continue
        if existing_by_name:
            result["conflicts"].append({"agent_id": role.id, "reason": "role_already_registered_with_other_id", "existing": existing_by_name})
            continue

        agent = {
            "id": role.id,
            "name": role.name,
            "pole": role.pole,
            "entity": role.entity,
            "version": "0.1.0",
            "status": "Prototype",
            "mission": role.mission,
            "vision": adl["agent"]["vision"],
            "objectives": [o["description"] for o in adl["agent"]["objectives"]],
            "kpis": [k["metric"] for k in adl["agent"]["kpis"]],
            "adl_v2": adl,
            "generated": True,
            "pilot": False,
            "workforce": "FREK",
            "capability_id": role.capability,
            "orchestrator": "MetaCVLN",
            "controller": "CVLN Agent Factory",
            "runtime": {
                "state": "sommeil",
                "mode": "dry_run",
                "initialized": False,
                "since": ts,
                "note": "FREK workforce bootstrap — activation on demand only",
                "last_transition_by": "system:frek-workforce-seed",
            },
            "autonomy": {"level": 1, "label": "dry_run", "fr": "Prototype — exécution réelle non autorisée"},
            "created_at": ts,
            "updated_at": ts,
        }
        await db.agents.insert_one(agent)
        await db.versions.insert_one({
            "id": f"{role.id}-bootstrap-0.1.0",
            "agent_id": role.id,
            "type": "version",
            "version": "0.1.0",
            "status": "Prototype",
            "adl": adl,
            "actor": "system:frek-workforce-seed",
            "note": "FREK AI employee registered in PROTOTYPE/dry_run; no production authority.",
            "timestamp": ts,
        })
        result["created"] += 1

    result["ok"] = not result["invalid"] and not result["conflicts"] and result["created"] + result["existing"] == 38
    logger.info("FREK workforce seed: %s", result)
    return result
