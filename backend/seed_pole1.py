"""Script one-shot : création des 20 agents manquants du Pôle 1 (AGT-016→035) depuis l'inventaire maître.
Réplique le pipeline Générateur avec IDs imposés. Idempotent. Arrêt en Beta (décision Laurent)."""
import asyncio
import uuid
import secrets
from datetime import datetime, timezone
import openpyxl
from database import db
from generator_routes import BusinessDefinition, build_adl_from_definition
from doctrine import check_doctrine_compliance, DOCTRINE_VERSION
from adl_schema import adl_to_yaml
from auth_utils import hash_service_token
from event_bus import publish
from activity_journal import journal

ACTOR = {"type": "service", "id": "AGT-000", "name": "CVLN Agent Architect"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def create_agent(agent_id: str, name: str, pole: str, entity: str):
    if await db.agents.find_one({"id": agent_id}, {"_id": 0, "id": 1}):
        print(f"{agent_id} existe déjà — skip")
        return
    d = BusinessDefinition(
        name=name, category="AI Services", pole=pole, entity=entity,
        mission=f"Fournir le service « {name} » pour {entity} au sein du Pôle 1 AI Services du groupe CVLN.",
        objectives=[f"Opérer {name} avec qualité constante", "Respecter la doctrine CVLN"],
        skills=[name], tools=[], autonomy_level="supervised",
        kpis=["taux de satisfaction interne", "délais de traitement"])
    adl = build_adl_from_definition(d, agent_id)
    adl_yaml = adl_to_yaml(adl)
    violations = [c for c in check_doctrine_compliance(adl) if not c["passed"]]
    if violations:
        print(f"{agent_id} VIOLATIONS doctrine: {violations}")
        return
    ts = now_iso()
    token = "svc_" + secrets.token_urlsafe(32)
    await db.identities.insert_one({"id": str(uuid.uuid4()), "agent_id": agent_id, "name": name,
                                    "token_hash": hash_service_token(token),
                                    "scopes": ["events:publish", "memory:write:self"], "active": True,
                                    "created_at": ts})
    await db.memory_entries.insert_one({"id": str(uuid.uuid4()), "agent_id": agent_id, "entity": entity,
                                        "scope": "persistent", "key": "bootstrap",
                                        "value": {"generated_by": "AGT-000", "doctrine_version": DOCTRINE_VERSION,
                                                  "origin": "import inventaire maître Pôle 1"},
                                        "owner": agent_id, "created_at": ts, "updated_at": ts})
    await db.agents.insert_one({"id": agent_id, "name": name, "pole": pole, "entity": entity,
                                "version": "1.0.0", "status": "Draft", "mission": d.mission, "vision": "",
                                "objectives": d.objectives, "kpis": d.kpis, "adl": adl, "adl_yaml": adl_yaml,
                                "generated": True, "created_at": ts, "updated_at": ts})
    await db.versions.insert_one({"id": str(uuid.uuid4()), "agent_id": agent_id, "type": "version",
                                  "version": "1.0.0", "status": "Draft", "adl": adl, "adl_yaml": adl_yaml,
                                  "actor": "service:AGT-000",
                                  "note": "Import inventaire maître — Pôle 1 AI Services", "timestamp": ts})
    current = "Draft"
    for status in ("Prototype", "Beta"):
        lts = now_iso()
        await db.agents.update_one({"id": agent_id}, {"$set": {"status": status, "updated_at": lts}})
        await db.versions.insert_one({"id": str(uuid.uuid4()), "agent_id": agent_id, "type": "lifecycle",
                                      "version": "1.0.0", "status": status, "from_status": current,
                                      "actor": "service:AGT-000",
                                      "note": "Import inventaire — progression pipeline (arrêt Beta, validation Production réservée à Laurent)",
                                      "timestamp": lts})
        current = status
    await publish("agent.created", "AGT-000", {"agent_id": agent_id, "name": name, "generated": True})
    print(f"{agent_id} — {name} → Beta")


async def main():
    wb = openpyxl.load_workbook("/app/memory/artifacts/INVENTAIRE.xlsx")
    ws = wb["Inventaire"]
    rows = [r for r in ws.iter_rows(min_row=2, values_only=True)
            if r[0] and r[0] >= "AGT-016" and r[0] <= "AGT-035"]
    print(f"{len(rows)} agents Pôle 1 à créer")
    for aid, name, pole, entity, _ in rows:
        await create_agent(aid, name, pole, entity)
    await journal("action_executee", ACTOR,
                  f"Import inventaire maître : {len(rows)} agents Pôle 1 AI Services (AGT-016→035) créés jusqu'à Beta",
                  source="generator", result="imported")

    # Réveil des runtimes des agents en Production uniquement (décision Laurent)
    ts = now_iso()
    woken = 0
    async for a in db.agents.find({"status": "Production"}, {"_id": 0, "id": 1, "runtime": 1}):
        state = (a.get("runtime") or {}).get("state", "sommeil")
        if state != "actif":
            await db.agents.update_one({"id": a["id"]},
                                       {"$set": {"runtime": {"state": "actif", "since": ts, "initialized": True,
                                                             "previous_state": state,
                                                             "note": "activation des agents Production (décision Laurent)",
                                                             "last_transition_by": "service:AGT-000"},
                                                 "updated_at": ts}})
            woken += 1
    await journal("action_executee", ACTOR,
                  f"Réveil des runtimes : {woken} agent(s) Production passés en actif (décision Laurent — les Draft/Beta restent en sommeil)",
                  source="agent-runtime", result="awake")
    print(f"{woken} agents Production réveillés")

asyncio.run(main())
