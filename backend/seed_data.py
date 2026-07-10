import os
import uuid
import logging
from datetime import datetime, timezone
from database import db
from auth_utils import hash_password, verify_password, hash_service_token
from adl_schema import adl_to_yaml

logger = logging.getLogger(__name__)

FOUNDERS = [
    ("AGT-000", "CVLN Agent Architect", "Core / Orchestration", "CVLN Holding",
     "Concevoir, construire, maintenir, versionner et faire évoluer tous les agents IA du groupe CVLN. Il pilote la Factory et valide les cycles de vie.",
     "Être le gardien de la cohérence et de la gouvernance de l'écosystème d'agents CVLN.",
     ["Piloter la Factory", "Valider les cycles de vie", "Garantir la conformité ADL"],
     ["100% des agents conformes ADL", "0 doublon dans le Registry"]),
    ("AGT-001", "AI Agent & Chatbot Development", "Infrastructure IA", "CVLN Holding / Agent Factory",
     "Concevoir et maintenir l'infrastructure technique permettant de générer, structurer et déployer les agents conformes au modèle CVLN.",
     "Une chaîne de production d'agents industrialisée et fiable.",
     ["Standardiser la génération d'agents", "Maintenir les templates ADL"],
     ["Temps de création d'un agent < 1h", "Taux de compilation réussie > 95%"]),
    ("AGT-002", "Knowledge Representation", "Infrastructure IA", "CVLN Brain",
     "Organiser les connaissances CVLN : ontologies, graphes de connaissances, schémas de données et structures permettant aux agents d'exploiter un savoir cohérent.",
     "Un savoir CVLN unifié, structuré et exploitable par machine.",
     ["Construire l'ontologie CVLN", "Maintenir les graphes de connaissances"],
     ["Couverture ontologique des entités", "Fraîcheur des graphes"]),
    ("AGT-003", "AI API Integration", "Infrastructure IA", "Agent Factory",
     "Créer et maintenir les connecteurs entre les systèmes CVLN et les services externes, avec une gestion standardisée des APIs.",
     "Des intégrations externes fiables et standardisées.",
     ["Standardiser les connecteurs API", "Gérer les quotas et clés"],
     ["Disponibilité connecteurs > 99%", "Temps d'intégration nouveau service"]),
    ("AGT-004", "MLOps", "Infrastructure IA", "Agent Factory / Runtime",
     "Assurer le passage de la Factory au Runtime : déploiement, versioning, mise à jour, rollback et maintien opérationnel des agents.",
     "Un pipeline Factory → Runtime sans friction.",
     ["Automatiser les déploiements", "Gérer versioning et rollback"],
     ["Temps de déploiement", "Taux de rollback réussi"]),
    ("AGT-005", "AI Model Development", "Infrastructure IA", "CVLN Brain",
     "Développer, évaluer et faire évoluer les modèles utilisés par les agents et les futures capacités IA propriétaires.",
     "Des capacités IA propriétaires souveraines.",
     ["Évaluer les modèles", "Développer les capacités propriétaires"],
     ["Scores d'évaluation modèles", "Coût par inférence"]),
    ("AGT-006", "Data Engineering", "Infrastructure IA", "CVLN Brain",
     "Construire les pipelines de données entre les entités CVLN, assurer la qualité, la transformation et la circulation des données.",
     "Des données fiables circulant entre toutes les entités CVLN.",
     ["Construire les pipelines inter-entités", "Garantir la qualité des données"],
     ["Fraîcheur des données", "Taux d'erreur pipeline"]),
    ("AGT-007", "Database Administration", "Infrastructure", "CVLN Holding",
     "Administrer les bases de données (notamment MongoDB Atlas), garantir performance, sauvegarde, intégrité et sécurité des données.",
     "Une couche de persistance robuste et sécurisée.",
     ["Administrer MongoDB Atlas", "Garantir sauvegardes et intégrité"],
     ["Uptime base de données", "RPO/RTO respectés"]),
    ("AGT-008", "Cloud Engineering", "Infrastructure", "CVLN Holding",
     "Gérer les environnements cloud, la capacité, les coûts, la disponibilité et la sécurité de l'infrastructure technique.",
     "Une infrastructure cloud maîtrisée en coût et en disponibilité.",
     ["Optimiser les coûts cloud", "Garantir la disponibilité"],
     ["Coût mensuel cloud", "Disponibilité infra > 99.9%"]),
    ("AGT-009", "DevOps Engineering", "Infrastructure IA", "Agent Factory / Runtime",
     "Automatiser CI/CD, tests, déploiements et standardiser les pipelines techniques des agents.",
     "Des pipelines techniques entièrement automatisés.",
     ["Automatiser CI/CD", "Standardiser les pipelines"],
     ["Fréquence de déploiement", "Taux de succès CI"]),
    ("AGT-010", "Information Security", "Gouvernance transverse", "CVLN Holding",
     "Protéger les agents, données et applications, gérer conformité, sécurité, audits et règles d'accès.",
     "Un écosystème sécurisé et conforme par conception.",
     ["Gérer les règles d'accès", "Conduire les audits de sécurité"],
     ["Incidents de sécurité", "Conformité des accès"]),
]


def build_founder_adl(fid, name, pole, entity, mission, vision, objectives, kpis):
    return {
        "adl_version": "1.0",
        "agent": {"id": fid, "name": name, "pole": pole, "entity": entity,
                  "version": "1.0.0", "mission": mission, "vision": vision,
                  "objectives": objectives, "kpis": kpis},
        "brain": {
            "registry": {"registered": True},
            "memory": {"scope": "persistent", "owner": fid},
            "identity": {"role": "founder", "service_identity": fid == "AGT-000"},
            "events": {"subscribe": ["agent.*"] if fid == "AGT-000" else [],
                       "publish": ["factory.compile", "agent.created"] if fid == "AGT-000" else []},
            "monitoring": {"health_check": True},
        },
        "tools": [],
        "knowledge": [{"source": "CVLN Doctrine", "type": "document", "description": "Doctrine fondatrice CVLN"}],
        "permissions": {"read": ["registry"], "write": ["registry"] if fid == "AGT-000" else [], "entities": [entity]},
        "tests": [{"name": "identity_check", "assertion": f"agent.id == '{fid}'"}],
    }


async def seed_all():
    now = datetime.now(timezone.utc).isoformat()

    admin_email = os.environ.get("ADMIN_EMAIL", "laurent@cvln.fr")
    admin_password = os.environ.get("ADMIN_PASSWORD", "CVLNfactory2026!")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "id": str(uuid.uuid4()), "email": admin_email,
            "password_hash": hash_password(admin_password),
            "name": "Laurent", "role": "admin", "created_at": now,
        })
        logger.info(f"Seeded admin user {admin_email}")
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})

    svc_token = os.environ.get("AGENT000_SERVICE_TOKEN")
    if svc_token:
        existing_identity = await db.identities.find_one({"agent_id": "AGT-000"})
        token_hash = hash_service_token(svc_token)
        if existing_identity is None:
            await db.identities.insert_one({
                "id": str(uuid.uuid4()), "agent_id": "AGT-000", "name": "CVLN Agent Architect",
                "token_hash": token_hash, "scopes": ["registry:write", "events:publish", "memory:write"],
                "active": True, "created_at": now,
            })
            logger.info("Seeded AGT-000 service identity")
        elif existing_identity.get("token_hash") != token_hash:
            await db.identities.update_one({"agent_id": "AGT-000"}, {"$set": {"token_hash": token_hash}})

    count = await db.agents.count_documents({})
    if count == 0:
        for f in FOUNDERS:
            adl = build_founder_adl(*f)
            agent_doc = {
                "id": adl["agent"]["id"], "name": adl["agent"]["name"],
                "pole": adl["agent"]["pole"], "entity": adl["agent"]["entity"],
                "version": "1.0.0", "status": "Production",
                "mission": adl["agent"]["mission"], "vision": adl["agent"]["vision"],
                "objectives": adl["agent"]["objectives"], "kpis": adl["agent"]["kpis"],
                "adl": adl, "adl_yaml": adl_to_yaml(adl),
                "created_at": now, "updated_at": now,
            }
            await db.agents.insert_one({**agent_doc})
            await db.versions.insert_one({
                "id": str(uuid.uuid4()), "agent_id": adl["agent"]["id"], "type": "version",
                "version": "1.0.0", "status": "Production", "adl": adl,
                "adl_yaml": agent_doc["adl_yaml"],
                "actor": "system:seed", "note": "Seed initial — agent fondateur",
                "timestamp": now,
            })
        logger.info("Seeded 11 founder agents (AGT-000 → AGT-010)")

    await db.users.create_index("email", unique=True)
    await db.agents.create_index("id", unique=True)
    await db.events.create_index("timestamp")
    await db.audit_logs.create_index("timestamp")
