import re
import uuid
import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from database import db
from adl_schema import ADLDocument, adl_to_yaml, LIFECYCLE_ORDER
from auth_utils import get_current_actor, require_registry_writer, log_authz, hash_service_token
from doctrine import check_doctrine_compliance, DOCTRINE_VERSION, AUTONOMY_LEVELS
from registry_routes import find_duplicates
from event_bus import publish

router = APIRouter(prefix="/generator", tags=["generator"])


class BusinessDefinition(BaseModel):
    name: str = Field(min_length=3)
    category: str
    pole: str
    entity: str
    mission: str = Field(min_length=10)
    objectives: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    autonomy_level: str = "supervised"
    kpis: List[str] = Field(default_factory=list)


class GeneratePayload(BaseModel):
    catalog_id: Optional[str] = None
    definition: Optional[BusinessDefinition] = None
    target_status: str = "Beta"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def next_agent_id() -> str:
    ids = await db.agents.find({}, {"_id": 0, "id": 1}).to_list(2000)
    nums = [int(m.group(1)) for a in ids if (m := re.match(r'^AGT-(\d{3})$', a["id"]))]
    n = max(nums) + 1 if nums else 0
    if n > 999:
        raise HTTPException(status_code=409, detail="Agent ID space exhausted (AGT-999)")
    return f"AGT-{n:03d}"


def build_adl_from_definition(d: BusinessDefinition, agent_id: str) -> dict:
    adl = ADLDocument(**{
        "adl_version": "1.0",
        "agent": {"id": agent_id, "name": d.name, "pole": d.pole, "entity": d.entity,
                  "version": "1.0.0", "mission": d.mission, "vision": "",
                  "objectives": d.objectives, "kpis": d.kpis},
        "brain": {
            "registry": {"registered": True, "doctrine_version": DOCTRINE_VERSION, "category": d.category},
            "memory": {"scope": "persistent", "owner": agent_id},
            "identity": {"autonomy_level": d.autonomy_level, "generated_by": "AGT-000"},
            "events": {"subscribe": ["agent.updated"], "publish": ["agent.heartbeat"]},
            "monitoring": {"health_check": True},
        },
        "tools": [{"name": t, "type": "api", "description": f"Outil requis : {t}", "config": {}} for t in d.tools],
        "knowledge": [{"source": "Doctrine CVLN", "type": "doctrine", "description": f"Doctrine CVLN v{DOCTRINE_VERSION} héritée automatiquement"}]
                     + [{"source": s, "type": "skill", "description": ""} for s in d.skills],
        "permissions": {"read": ["registry", "memory:self"], "write": ["memory:self"], "entities": [d.entity]},
        "tests": [
            {"name": "identity_check", "assertion": f"agent.id == '{agent_id}'"},
            {"name": "doctrine_inheritance", "assertion": f"brain.registry.doctrine_version == '{DOCTRINE_VERSION}'"},
        ],
    })
    return adl.model_dump()


# ---------- Master catalog ----------
@router.get("/catalog")
async def list_catalog(actor: dict = Depends(get_current_actor)):
    entries = await db.catalog_entries.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return entries


@router.post("/catalog")
async def add_catalog_entry(definition: BusinessDefinition, actor: dict = Depends(require_registry_writer)):
    if definition.autonomy_level not in AUTONOMY_LEVELS:
        raise HTTPException(status_code=400, detail=f"autonomy_level must be one of {AUTONOMY_LEVELS}")
    entry = {"id": str(uuid.uuid4()), **definition.model_dump(),
             "generated_agent_id": None, "created_at": now_iso()}
    await db.catalog_entries.insert_one({**entry})
    return entry


@router.delete("/catalog/{catalog_id}")
async def delete_catalog_entry(catalog_id: str, actor: dict = Depends(require_registry_writer)):
    entry = await db.catalog_entries.find_one({"id": catalog_id})
    if not entry:
        raise HTTPException(status_code=404, detail="Catalog entry not found")
    if entry.get("generated_agent_id"):
        raise HTTPException(status_code=409, detail="Entry already generated — cannot delete")
    await db.catalog_entries.delete_one({"id": catalog_id})
    return {"result": "ok"}


# ---------- Generator pipeline ----------
@router.post("/generate")
async def generate_agent(payload: GeneratePayload, actor: dict = Depends(require_registry_writer)):
    steps = []

    def step(name, status, detail=""):
        steps.append({"step": name, "status": status, "detail": detail})

    # 1. Analyse de la définition métier
    catalog_entry = None
    if payload.catalog_id:
        catalog_entry = await db.catalog_entries.find_one({"id": payload.catalog_id}, {"_id": 0})
        if not catalog_entry:
            raise HTTPException(status_code=404, detail="Catalog entry not found")
        if catalog_entry.get("generated_agent_id"):
            raise HTTPException(status_code=409, detail=f"Already generated as {catalog_entry['generated_agent_id']}")
        definition = BusinessDefinition(**{k: catalog_entry[k] for k in BusinessDefinition.model_fields})
    elif payload.definition:
        definition = payload.definition
    else:
        raise HTTPException(status_code=400, detail="Provide catalog_id or definition")
    if definition.autonomy_level not in AUTONOMY_LEVELS:
        raise HTTPException(status_code=400, detail=f"autonomy_level must be one of {AUTONOMY_LEVELS}")
    step("business_analysis", "ok", f"Définition '{definition.name}' analysée ({definition.category} / {definition.pole})")

    # 4-5. Doublon + attribution ID (avant génération pour échouer tôt)
    dups = await find_duplicates("", definition.name, definition.mission)
    if dups:
        step("duplicate_check", "failed", str(dups))
        await publish("factory.generate", actor["id"], {"result": "duplicate_detected", "name": definition.name, "duplicates": dups})
        raise HTTPException(status_code=409, detail={"type": "duplicate", "duplicates": dups, "steps": steps})
    step("duplicate_check", "ok", "Aucun doublon dans le Registry")

    agent_id = await next_agent_id()
    step("id_assignment", "ok", f"ID attribué : {agent_id}")

    # 2. Génération ADL
    adl = build_adl_from_definition(definition, agent_id)
    adl_yaml = adl_to_yaml(adl)
    step("adl_generation", "ok", f"ADL v1.0.0 générée ({len(adl_yaml)} caractères)")

    # 3. Conformité Doctrine
    compliance = check_doctrine_compliance(adl)
    failed_rules = [c for c in compliance if not c["passed"]]
    if failed_rules:
        step("doctrine_compliance", "failed", str(failed_rules))
        raise HTTPException(status_code=422, detail={"type": "doctrine", "violations": failed_rules, "steps": steps})
    step("doctrine_compliance", "ok", f"{len(compliance)} règles doctrine vérifiées, 0 violation")

    ts = now_iso()

    # 6. Identité de service
    token = "svc_" + secrets.token_urlsafe(32)
    await db.identities.insert_one({
        "id": str(uuid.uuid4()), "agent_id": agent_id, "name": definition.name,
        "token_hash": hash_service_token(token),
        "scopes": ["events:publish", "memory:write:self"], "active": True, "created_at": ts})
    step("identity_creation", "ok", "Identité de service créée (token scoped)")

    # 7. Permissions
    step("permissions", "ok", f"Permissions ADL : read={adl['permissions']['read']}, entities={adl['permissions']['entities']}")

    # 8. Espace mémoire
    await db.memory_entries.insert_one({
        "id": str(uuid.uuid4()), "agent_id": agent_id, "entity": definition.entity,
        "scope": "persistent", "key": "bootstrap",
        "value": {"generated_by": "AGT-000", "doctrine_version": DOCTRINE_VERSION},
        "owner": agent_id, "created_at": ts, "updated_at": ts})
    step("memory_space", "ok", f"Espace mémoire persistant initialisé (entité {definition.entity})")

    # 9. Événements
    step("events_setup", "ok", f"Topics : subscribe={adl['brain']['events']['subscribe']}, publish={adl['brain']['events']['publish']}")

    # 10. Enregistrement Registry
    agent_doc = {"id": agent_id, "name": definition.name, "pole": definition.pole,
                 "entity": definition.entity, "version": "1.0.0", "status": "Draft",
                 "mission": definition.mission, "vision": "",
                 "objectives": definition.objectives, "kpis": definition.kpis,
                 "adl": adl, "adl_yaml": adl_yaml, "generated": True,
                 "created_at": ts, "updated_at": ts}
    await db.agents.insert_one({**agent_doc})
    await db.versions.insert_one({
        "id": str(uuid.uuid4()), "agent_id": agent_id, "type": "version",
        "version": "1.0.0", "status": "Draft", "adl": adl, "adl_yaml": adl_yaml,
        "actor": f'{actor["type"]}:{actor["id"]}', "note": "Agent Generator Engine — création automatique",
        "timestamp": ts})
    await log_authz(actor, "registry_write", f"agent:{agent_id}", True, "generated via Agent Generator Engine")
    await publish("agent.created", actor["id"], {"agent_id": agent_id, "name": definition.name, "generated": True})
    step("registry_registration", "ok", "Enregistré dans le Registry en statut Draft")

    # 11. Progression cycle de vie
    order = [s.value for s in LIFECYCLE_ORDER]
    target = payload.target_status if payload.target_status in order else "Beta"
    if target == "Production" and not (actor["type"] == "human" and actor["role"] == "admin"):
        target = "Beta"
        step("lifecycle_note", "warning", "Beta → Production exige une validation humaine (admin) — arrêt en Beta")
    current = "Draft"
    for status in order[1:order.index(target) + 1]:
        lts = now_iso()
        await db.agents.update_one({"id": agent_id}, {"$set": {"status": status, "updated_at": lts}})
        await db.versions.insert_one({
            "id": str(uuid.uuid4()), "agent_id": agent_id, "type": "lifecycle",
            "version": "1.0.0", "status": status, "from_status": current,
            "actor": f'{actor["type"]}:{actor["id"]}',
            "note": "Progression automatique — Agent Generator Engine" + (" (validation humaine)" if status == "Production" else ""),
            "timestamp": lts})
        await publish("agent.updated", actor["id"], {"agent_id": agent_id, "from": current, "to": status})
        current = status
    step("lifecycle_progression", "ok", f"Draft → {current}")

    if catalog_entry:
        await db.catalog_entries.update_one({"id": payload.catalog_id}, {"$set": {"generated_agent_id": agent_id}})

    await publish("factory.generate", actor["id"], {"result": "success", "agent_id": agent_id, "status": current})
    return {"result": "generated", "agent_id": agent_id, "name": definition.name,
            "status": current, "service_token": token,
            "token_warning": "Store this token now — it will not be shown again.",
            "doctrine_version": DOCTRINE_VERSION, "compliance": compliance, "steps": steps}
