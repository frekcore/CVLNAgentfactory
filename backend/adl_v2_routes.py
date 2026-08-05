"""S0.1 — ADL v2.0 : validateur JSON Schema strict + migration preview v1→v2 (agent par agent, jamais en masse)."""
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import yaml
from jsonschema import Draft7Validator
from database import db
from auth_utils import get_current_actor

router = APIRouter(prefix="/adl/v2", tags=["adl-v2"])

SCHEMA = json.loads((Path(__file__).parent / "schemas" / "adl_v2_schema.json").read_text())
VALIDATOR = Draft7Validator(SCHEMA)

STATUS_MAP = {"Draft": "DRAFT", "Prototype": "PROTOTYPE", "Beta": "STAGING",
              "Production": "PRODUCTION", "Maintenance": "PRODUCTION", "Archive": "ARCHIVE"}


class ValidatePayload(BaseModel):
    adl: Optional[dict] = None
    adl_yaml: Optional[str] = None


@router.get("/schema")
async def get_schema(actor: dict = Depends(get_current_actor)):
    return SCHEMA


@router.post("/validate")
async def validate_v2(payload: ValidatePayload, actor: dict = Depends(get_current_actor)):
    doc = payload.adl
    if doc is None and payload.adl_yaml:
        try:
            doc = yaml.safe_load(payload.adl_yaml)
        except yaml.YAMLError as e:
            return {"valid": False, "errors": [f"YAML invalide : {str(e)[:200]}"]}
    if not isinstance(doc, dict):
        raise HTTPException(status_code=400, detail="Provide adl (dict) or adl_yaml")
    errors = [f"{'/'.join(str(p) for p in e.absolute_path) or '<racine>'} : {e.message}"
              for e in VALIDATOR.iter_errors(doc)]
    return {"valid": len(errors) == 0, "schema_version": "2.0", "errors": errors[:50]}


def migrate_v1_to_v2(agent: dict) -> dict:
    """Conversion déterministe ADL v1 → v2 (structure capabilities, knowledge structuré). Preview uniquement."""
    adl = agent.get("adl", {})
    a1, brain = adl.get("agent", {}), adl.get("brain", {})
    now = datetime.now(timezone.utc).isoformat()
    return {
        "adl_version": "2.0",
        "schema_uri": "https://cvln.group/schemas/adl/2.0",
        "agent": {
            "id": a1.get("id", agent["id"]), "name": a1.get("name", agent["name"]),
            "pole": a1.get("pole", agent.get("pole", "")), "entity": a1.get("entity", agent.get("entity", "")),
            "version": a1.get("version", "1.0.0"),
            "status": STATUS_MAP.get(agent.get("status", "Draft"), "DRAFT"),
            "mission": a1.get("mission", ""), "vision": a1.get("vision", ""),
            "objectives": [{"id": f"OBJ-{i+1:03d}", "description": o, "kpi": "", "target": None, "deadline": None}
                           for i, o in enumerate(a1.get("objectives", []))],
            "kpis": [{"metric": k, "target": None, "frequency": "weekly"} for k in a1.get("kpis", [])],
        },
        "brain": {
            "registry": {"registered_by": brain.get("registry", {}).get("category") and "AGT-000" or "AGT-000",
                         "registered_at": agent.get("created_at", now), "last_updated": agent.get("updated_at", now)},
            "memory": {**brain.get("memory", {}),
                       "vector_store_id": f"vs-sovereign-{agent['id'].lower()}",
                       "consolidation_policy": {"enabled": True, "interval": "24h",
                                                "summary_model": "sovereign-internal"}},
            "identity": {**brain.get("identity", {}), "permissions": adl.get("permissions", {}),
                         "secrets_scope": f"cvln/agents/{agent['id']}"},
            "events": {**brain.get("events", {}), "priority": "normal"},
            "monitoring": {**brain.get("monitoring", {}),
                           "alert_thresholds": {"error_rate": 0.05, "latency_p99": "2000ms"}},
        },
        "capabilities": {
            "tools": [{"id": f"tool-{i+1:03d}", **t} for i, t in enumerate(adl.get("tools", []))],
            "knowledge": [{"id": f"ks-{i+1:03d}", "type": k.get("type", "document"),
                           "source_uri": k.get("source", ""), "version": "1.0",
                           "embedding_model": "sovereign-lexical-v1",
                           "vector_id": f"vec-{agent['id'].lower()}-{i+1:03d}",
                           "metadata": {"description": k.get("description", ""), "confidentiality": "internal"},
                           "last_updated": now}
                          for i, k in enumerate(adl.get("knowledge", []))],
            "tests": adl.get("tests", []),
        },
    }


@router.post("/migrate-preview/{agent_id}")
async def migrate_preview(agent_id: str, actor: dict = Depends(get_current_actor)):
    """Preview de migration v1→v2 pour UN agent. Aucune écriture (décision Laurent : pas de migration en masse)."""
    agent = await db.agents.find_one({"id": agent_id}, {"_id": 0, "adl_yaml": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    v2 = migrate_v1_to_v2(agent)
    errors = [f"{'/'.join(str(p) for p in e.absolute_path) or '<racine>'} : {e.message}"
              for e in VALIDATOR.iter_errors(v2)]
    return {"agent_id": agent_id, "adl_v2_preview": v2, "schema_valid": len(errors) == 0,
            "schema_errors": errors[:30],
            "note": "Preview uniquement — aucune écriture. Migration agent par agent après validation Laurent."}
