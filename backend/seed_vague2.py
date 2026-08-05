"""VAGUE 2 — corrections d'omission blueprint : TCV, SAYD (entités draft) + CC2027 rattaché à Kiltikonet.
Règle : une entité = une seule source de vérité → CC2027 (marché culturel de Kiltikonet) devient un
objectif stratégique de Kiltikonet, pas une entité doublon. Idempotent. Placeholders : poids 0, horizon 2028."""
import asyncio
import os
import uuid
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from motor.motor_asyncio import AsyncIOMotorClient


def now_iso():
    return datetime.now(timezone.utc).isoformat()


NEW_ENTITIES = [
    {"name": "TCV", "type": "media",
     "description": "Chaîne TV CVLN — correction d'omission blueprint (placeholder stratégique, draft)"},
    {"name": "SAYD", "type": "media",
     "description": "Série documentaire « c'est nous l'avenir » — correction d'omission blueprint (placeholder stratégique, draft)"},
]


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    print("=== Inventaire entités existantes ===")
    existing = {e["name"]: e async for e in db.entities.find({}, {"_id": 0, "id": 1, "name": 1})}
    for n in sorted(existing):
        print(" -", n)

    ts = now_iso()
    created = []
    for spec in NEW_ENTITIES:
        if spec["name"] in existing:
            print(f"[skip] entité {spec['name']} existe déjà — pas de doublon")
            continue
        ent = {"id": str(uuid.uuid4()), "name": spec["name"], "type": spec["type"],
               "description": spec["description"], "activities": [], "data_domains": [],
               "apis": [], "objectives": [], "agent_ids": [], "status": "draft",
               "origin": "correction_omission_blueprint_vague2",
               "created_at": ts, "updated_at": ts}
        await db.entities.insert_one(ent)
        existing[spec["name"]] = ent
        created.append(spec["name"])
        print(f"[créé] entité {spec['name']} (draft, 0 agent, 0 budget)")

    so_specs = [
        {"title": "CC2027 — Marché culturel de Kiltikonet", "entity": "Kiltikonet",
         "description": "Correction d'omission blueprint — CC2027 rattaché à Kiltikonet "
                        "(une entité = une seule source de vérité). Placeholder stratégique."},
        {"title": "TCV — Lancement de la chaîne TV CVLN", "entity": "TCV",
         "description": "Placeholder stratégique — correction d'omission blueprint."},
        {"title": "SAYD — Série documentaire « c'est nous l'avenir »", "entity": "SAYD",
         "description": "Placeholder stratégique — correction d'omission blueprint."},
    ]
    for spec in so_specs:
        ent = existing.get(spec["entity"])
        if not ent:
            print(f"[erreur] entité {spec['entity']} introuvable")
            continue
        if await db.strategic_objectives.find_one({"title": spec["title"]}):
            print(f"[skip] objectif « {spec['title']} » existe déjà")
            continue
        count = await db.strategic_objectives.count_documents({})
        obj = {"id": str(uuid.uuid4()), "code": f"SO-{count + 1:03d}", "entity_id": ent["id"],
               "title": spec["title"], "description": spec["description"],
               "weight": 0.0, "horizon": "2028", "key_results": [], "status": "draft",
               "placeholder": True, "created_by": "system:vague2-seed",
               "created_at": now_iso(), "updated_at": now_iso()}
        await db.strategic_objectives.insert_one(obj)
        print(f"[créé] {obj['code']} : {spec['title']} (poids 0, horizon 2028, draft, entité {spec['entity']})")

    await db.activity_journal.insert_one({
        "id": str(uuid.uuid4()), "type": "action_executee", "timestamp": now_iso(),
        "actor_type": "system", "actor_id": "vague2-seed", "actor_name": "Seed Vague 2",
        "source": "vague2", "mission_id": None, "agent_id": None, "confidence": None,
        "evidence": {"entities_created": created,
                     "rule": "une entité = une seule source de vérité — CC2027 rattaché à Kiltikonet"},
        "result": "seeded",
        "summary": "Vague 2 — corrections d'omission : TCV + SAYD (entités draft), CC2027 = objectif "
                   "stratégique de Kiltikonet (poids 0, horizon 2028, aucun agent, aucun budget)"})
    print("=== Terminé ===")


asyncio.run(main())
