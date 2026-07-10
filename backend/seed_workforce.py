import uuid
import secrets
import logging
from datetime import datetime, timezone
from database import db
from auth_utils import hash_service_token
from adl_schema import adl_to_yaml
from doctrine import DOCTRINE_VERSION

logger = logging.getLogger(__name__)

ENTITIES = [
    ("CVLN Holding", "holding", "Société mère du groupe CVLN", ["Gouvernance", "Stratégie groupe"]),
    ("CVLN Brain", "brain", "Couche connaissance et raisonnement stratégique", ["Knowledge", "Doctrine", "Mémoire stratégique"]),
    ("Kiltikonet", "tech", "Entité CVLN indépendante", []),
    ("Laurent.ia", "ia", "Système IA applicatif indépendant — communication par contrats API uniquement", []),
    ("FREK", "creative", "Entité CVLN indépendante", []),
    ("KORA", "tech", "Entité CVLN indépendante", []),
    ("LabelOS", "musique", "Entité CVLN indépendante", []),
    ("Factory Maker Studio", "musique", "Studio musique — catalogue, artistes, sorties, performances", ["Production musicale", "Distribution"]),
    ("Good Mood", "media", "Entité CVLN indépendante", []),
    ("CVL Academy", "education", "Entité CVLN indépendante", []),
]

PILOTS = [
    ("Digital CEO Agent", "Direction Numérique", "Direction", "CVLN Holding",
     "Piloter la coordination globale des agents métiers, consolider les priorités du groupe numérique et préparer les arbitrages stratégiques pour Laurent.",
     ["Consolider les priorités inter-entités", "Préparer les arbitrages stratégiques", "Suivre l'avancement global"],
     ["Priorités traitées", "Arbitrages préparés", "Taux d'exécution du plan"],
     ["reporting", "planning"], 2),
    ("Digital CFO Agent", "Finance", "Finance", "CVLN Holding",
     "Mesurer la valeur économique produite par les agents : rentabilité, coûts, ROI et prévisions du groupe numérique CVLN.",
     ["Suivre coûts et revenus par agent et entité", "Calculer le ROI", "Produire des prévisions"],
     ["ROI global", "Coût par agent", "Précision des prévisions"],
     ["finance-ledger", "analytics"], 2),
    ("Knowledge Manager Agent", "Connaissance", "CVLN Brain", "CVLN Brain",
     "Organiser l'ingestion, la classification et la validation des connaissances CVLN et alimenter la mémoire des agents concernés.",
     ["Structurer les connaissances entrantes", "Maintenir la classification", "Alimenter les mémoires agents"],
     ["Items ingérés", "Taux de validation", "Couverture des agents"],
     ["knowledge-pipeline"], 2),
    ("Operations Agent", "Opérations", "Opérations", "Agent Factory",
     "Suivre les tâches opérationnelles des agents, détecter les blocages et garantir l'exécution quotidienne du plan de travail.",
     ["Suivre les tâches ouvertes", "Détecter les blocages", "Fluidifier l'exécution"],
     ["Tâches clôturées", "Blocages résolus", "Délai moyen d'exécution"],
     ["task-manager"], 2),
    ("Marketing Strategy Agent", "Marketing", "Marketing", "CVLN Holding",
     "Définir et suivre la stratégie marketing des entités CVLN : campagnes, croissance et génération de leads.",
     ["Produire les plans de campagne", "Suivre la croissance", "Générer des leads qualifiés"],
     ["Campagnes produites", "Croissance", "Leads générés"],
     ["analytics", "content-tools"], 2),
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def seed_workforce():
    if await db.entities.count_documents({}) == 0:
        for name, etype, desc, activities in ENTITIES:
            await db.entities.insert_one({
                "id": str(uuid.uuid4()), "name": name, "type": etype, "description": desc,
                "activities": activities, "data_domains": [], "apis": [], "objectives": [],
                "agent_ids": [], "created_at": now_iso(), "updated_at": now_iso()})
        logger.info("Seeded %d CVLN entities", len(ENTITIES))

    existing = await db.agents.count_documents({"pilot": True})
    if existing > 0:
        return
    from generator_routes import build_adl_from_definition, next_agent_id, BusinessDefinition
    from event_bus import publish
    for name, category, pole, entity, mission, objectives, kpis, tools, level in PILOTS:
        if await db.agents.find_one({"name": name}):
            continue
        agent_id = await next_agent_id()
        d = BusinessDefinition(name=name, category=category, pole=pole, entity=entity, mission=mission,
                               objectives=objectives, skills=[], tools=tools,
                               autonomy_level="semi-autonomous", kpis=kpis)
        adl = build_adl_from_definition(d, agent_id)
        adl_yaml = adl_to_yaml(adl)
        ts = now_iso()
        await db.agents.insert_one({
            "id": agent_id, "name": name, "pole": pole, "entity": entity, "version": "1.0.0",
            "status": "Beta", "mission": mission, "vision": "", "objectives": objectives, "kpis": kpis,
            "adl": adl, "adl_yaml": adl_yaml, "generated": True, "pilot": True,
            "autonomy": {"level": level, "label": "recommendation",
                         "fr": "Recommandation — l'agent propose des décisions"},
            "created_at": ts, "updated_at": ts})
        history = [("version", "Draft", "Pilote — génération automatique (test avant industrialisation)"),
                   ("lifecycle", "Prototype", "Progression pilote"), ("lifecycle", "Alpha", "Progression pilote"),
                   ("lifecycle", "Beta", "Pilote en observation — Production sous validation humaine")]
        for htype, status, note in history:
            await db.versions.insert_one({
                "id": str(uuid.uuid4()), "agent_id": agent_id, "type": htype, "version": "1.0.0",
                "status": status, "adl": adl if htype == "version" else None,
                "adl_yaml": adl_yaml if htype == "version" else None,
                "actor": "system:pilot-seed", "note": note, "timestamp": now_iso()})
        token = "svc_" + secrets.token_urlsafe(32)
        await db.identities.insert_one({
            "id": str(uuid.uuid4()), "agent_id": agent_id, "name": name,
            "token_hash": hash_service_token(token),
            "scopes": ["events:publish", "memory:write:self"], "active": True, "created_at": ts})
        await db.memory_entries.insert_one({
            "id": str(uuid.uuid4()), "agent_id": agent_id, "entity": entity, "scope": "persistent",
            "key": "bootstrap", "value": {"generated_by": "AGT-000", "pilot": True,
                                          "doctrine_version": DOCTRINE_VERSION},
            "owner": agent_id, "created_at": ts, "updated_at": ts})
        await db.entities.update_one({"name": entity}, {"$addToSet": {"agent_ids": agent_id}})
        await publish("agent.created", "AGT-000", {"agent_id": agent_id, "name": name, "pilot": True})
    logger.info("Seeded 5 pilot operational agents")
