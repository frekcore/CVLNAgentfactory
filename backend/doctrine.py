import uuid
from datetime import datetime, timezone
from database import db

DOCTRINE_VERSION = "1.0"

DOCTRINE_SECTIONS = [
    {"key": "architecture", "title_fr": "Règles d'architecture", "title_en": "Architecture rules", "rules": [
        {"id": "DOC-ARC-01", "fr": "Tout agent doit être défini par un fichier ADL validé par schéma.", "en": "Every agent must be defined by a schema-validated ADL file."},
        {"id": "DOC-ARC-02", "fr": "Le Registry est la source unique de vérité : aucun agent n'existe hors Registry.", "en": "The Registry is the single source of truth: no agent exists outside the Registry."},
        {"id": "DOC-ARC-03", "fr": "L'espace mémoire d'un agent est isolé : son owner doit être l'agent lui-même.", "en": "An agent's memory space is isolated: its owner must be the agent itself."},
        {"id": "DOC-ARC-04", "fr": "Aucune dépendance fournisseur (GPT/Claude) codée en dur : la couche d'exécution est provider-agnostic.", "en": "No hardcoded provider dependency (GPT/Claude): the execution layer is provider-agnostic."},
    ]},
    {"key": "security", "title_fr": "Règles de sécurité", "title_en": "Security rules", "rules": [
        {"id": "DOC-SEC-01", "fr": "Seul AGT-000 (ou un admin agissant en son nom) écrit dans le Registry.", "en": "Only AGT-000 (or an admin acting on its behalf) writes to the Registry."},
        {"id": "DOC-SEC-02", "fr": "Principe du moindre privilège : un agent ne déclare que les permissions strictement nécessaires.", "en": "Least privilege: an agent declares only strictly necessary permissions."},
        {"id": "DOC-SEC-03", "fr": "Les secrets ne circulent jamais en clair dans les logs ou les fiches ADL.", "en": "Secrets never travel in clear text in logs or ADL files."},
        {"id": "DOC-SEC-04", "fr": "Tout agent doit être rattaché à au moins une entité CVLN.", "en": "Every agent must be attached to at least one CVLN entity."},
    ]},
    {"key": "communication", "title_fr": "Règles de communication", "title_en": "Communication rules", "rules": [
        {"id": "DOC-COM-01", "fr": "Aucune communication inter-pôle hors Event Bus. Règle non négociable.", "en": "No inter-pole communication outside the Event Bus. Non-negotiable rule."},
        {"id": "DOC-COM-02", "fr": "Les topics d'événements sont normés : agent.*, factory.*, monitoring.*, memory.*, identity.*.", "en": "Event topics are normalized: agent.*, factory.*, monitoring.*, memory.*, identity.*."},
        {"id": "DOC-COM-03", "fr": "Les systèmes externes (Laurent.ia, KORA, FREK…) restent indépendants et communiquent uniquement via contrats d'API.", "en": "External systems (Laurent.ia, KORA, FREK…) remain independent and communicate only via API contracts."},
    ]},
    {"key": "autonomy", "title_fr": "Règles d'autonomie", "title_en": "Autonomy rules", "rules": [
        {"id": "DOC-AUT-01", "fr": "Chaque agent déclare un niveau d'autonomie : supervised, semi-autonomous ou autonomous.", "en": "Every agent declares an autonomy level: supervised, semi-autonomous or autonomous."},
        {"id": "DOC-AUT-02", "fr": "Le passage Beta → Production exige une validation humaine (admin).", "en": "Beta → Production transition requires human (admin) validation."},
        {"id": "DOC-AUT-03", "fr": "Le Monitoring alerte mais n'agit jamais : lecture seule stricte.", "en": "Monitoring alerts but never acts: strict read-only."},
    ]},
    {"key": "governance", "title_fr": "Règles de gouvernance", "title_en": "Governance rules", "rules": [
        {"id": "DOC-GOV-01", "fr": "Chaque changement de version ou de statut est historisé de façon immuable.", "en": "Every version or status change is immutably historized."},
        {"id": "DOC-GOV-02", "fr": "Chaque décision d'autorisation (acceptée ou refusée) est journalisée.", "en": "Every authorization decision (granted or denied) is logged."},
        {"id": "DOC-GOV-03", "fr": "Tout agent doit déclarer au moins un test de conformité.", "en": "Every agent must declare at least one compliance test."},
        {"id": "DOC-GOV-04", "fr": "Les superviseurs humains valident les évolutions importantes.", "en": "Human supervisors validate major evolutions."},
    ]},
    {"key": "strategy", "title_fr": "Principes stratégiques CVLN", "title_en": "CVLN strategic principles", "rules": [
        {"id": "DOC-STR-01", "fr": "La Factory est le moteur du groupe : elle prépare la naissance d'un groupe numérique autonome sous gouvernance humaine.", "en": "The Factory is the group's engine: it prepares the birth of an autonomous digital group under human governance."},
        {"id": "DOC-STR-02", "fr": "L'architecture reste multi-tenant-ready pour une commercialisation future.", "en": "The architecture remains multi-tenant-ready for future commercialization."},
        {"id": "DOC-STR-03", "fr": "Le savoir CVLN est structuré, versionné et exploitable par machine.", "en": "CVLN knowledge is structured, versioned and machine-exploitable."},
    ]},
]

AUTONOMY_LEVELS = ("supervised", "semi-autonomous", "autonomous")


def check_doctrine_compliance(adl: dict) -> list:
    """Deterministic doctrine checks against an ADL dict. Returns list of rule results."""
    agent = adl.get("agent", {})
    brain = adl.get("brain", {})
    perms = adl.get("permissions", {})
    results = []

    def add(rule_id, category, passed, detail):
        results.append({"rule_id": rule_id, "category": category, "passed": passed, "detail": detail})

    add("DOC-ARC-03", "architecture",
        brain.get("memory", {}).get("owner", "") == agent.get("id", ""),
        f"memory.owner='{brain.get('memory', {}).get('owner', '')}' vs agent.id='{agent.get('id', '')}'")

    add("DOC-SEC-01", "security",
        "registry" not in perms.get("write", []) or agent.get("id") == "AGT-000",
        "permissions.write must not include 'registry' (reserved to AGT-000)")

    add("DOC-SEC-04", "security",
        len(perms.get("entities", [])) > 0,
        f"entities declared: {perms.get('entities', [])}")

    valid_prefixes = ("agent.", "factory.", "monitoring.", "memory.", "identity.")
    topics = brain.get("events", {}).get("subscribe", []) + brain.get("events", {}).get("publish", [])
    bad_topics = [t for t in topics if not t.startswith(valid_prefixes)]
    add("DOC-COM-02", "communication", len(bad_topics) == 0,
        f"non-normalized topics: {bad_topics}" if bad_topics else "all topics normalized")

    direct_tools = [t.get("name") for t in adl.get("tools", []) if t.get("type") == "direct-agent-connection"]
    add("DOC-COM-01", "communication", len(direct_tools) == 0,
        f"direct agent connections forbidden: {direct_tools}" if direct_tools else "no direct inter-agent connection")

    autonomy = brain.get("identity", {}).get("autonomy_level", "supervised")
    add("DOC-AUT-01", "autonomy", autonomy in AUTONOMY_LEVELS,
        f"autonomy_level='{autonomy}'")

    add("DOC-GOV-03", "governance", len(adl.get("tests", [])) > 0,
        f"{len(adl.get('tests', []))} test(s) declared")

    return results


async def seed_doctrine():
    existing = await db.doctrine.find_one({"version": DOCTRINE_VERSION})
    if existing is None:
        await db.doctrine.insert_one({
            "id": str(uuid.uuid4()), "version": DOCTRINE_VERSION,
            "sections": DOCTRINE_SECTIONS,
            "created_at": datetime.now(timezone.utc).isoformat()})
