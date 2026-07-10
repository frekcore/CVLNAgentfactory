import os
import re
import logging
from database import db

logger = logging.getLogger(__name__)

# Classification souveraine (moteur interne CVLN — fonctionne sans aucun LLM)
CLASSIFICATION_RULES = [
    ("rule", ["règle", "regle", "doctrine", "toujours", "jamais", "interdit", "obligatoire", "principe"]),
    ("decision", ["je décide", "je decide", "décision", "decision", "je valide", "j'arbitre", "je choisis", "on part sur"]),
    ("instruction", ["crée", "cree", "construis", "génère", "genere", "lance", "prépare", "prepare", "mets en place", "implémente", "implemente", "fais"]),
    ("task", ["tâche", "tache", "todo", "à faire", "a faire", "deadline", "assigner", "assigne"]),
    ("hypothesis", ["hypothèse", "hypothese", "peut-être", "peut etre", "si on", "imaginons", "et si", "supposons"]),
    ("idea", ["idée", "idee", "opportunité", "opportunite", "on pourrait", "vision", "projet futur", "innovation"]),
]


def classify_message(text: str) -> str:
    low = text.lower()
    scores = {}
    for cat, kws in CLASSIFICATION_RULES:
        s = sum(1 for kw in kws if kw in low)
        if s:
            scores[cat] = s
    return max(scores, key=scores.get) if scores else "information"


async def build_context() -> dict:
    agents_total = await db.agents.count_documents({"status": {"$ne": "Archive"}})
    beta = await db.agents.count_documents({"status": "Beta"})
    open_tasks = await db.agent_tasks.count_documents({"status": {"$in": ["open", "in_progress"]}})
    missions_active = await db.missions.count_documents({"status": {"$in": ["assigned", "in_progress"]}})
    missions_delivered = await db.missions.count_documents({"status": "delivered"})
    proposals = await db.evolution_proposals.count_documents({"status": "proposed"})
    last_closing = await db.daily_reports.find_one({"status": "closed"}, {"_id": 0, "date": 1, "average_confidence": 1}, sort=[("date", -1)])
    return {"agents_total": agents_total, "agents_beta": beta, "open_tasks": open_tasks,
            "missions_active": missions_active, "missions_delivered_awaiting_validation": missions_delivered,
            "proposals_pending": proposals,
            "last_closing": last_closing["date"] if last_closing else None,
            "last_confidence": last_closing.get("average_confidence") if last_closing else None}


ACTION_LABELS = {
    "task": "Créer une tâche assignée à l'agent le plus compétent",
    "instruction": "Créer une mission orchestrée",
    "decision": "Enregistrer dans la mémoire stratégique CVLN",
    "rule": "Proposer une évolution de la Doctrine (validation humaine requise)",
    "idea": "Capitaliser comme connaissance (Knowledge Sovereignty)",
    "hypothesis": "Capitaliser comme hypothèse de recherche",
    "information": "Mémoriser (mémoire opérationnelle)",
}


def internal_response(text: str, classification: str, ctx: dict) -> str:
    """Réponse du moteur cognitif interne souverain — aucun appel externe."""
    lines = [
        f"[Moteur cognitif interne CVLN — souverain]",
        f"J'ai analysé ton message et je le classe comme : {classification.upper()}.",
        f"Action proposée : {ACTION_LABELS[classification]}.",
        "",
        f"État actuel du groupe : {ctx['agents_total']} agents ({ctx['agents_beta']} en Beta), "
        f"{ctx['open_tasks']} tâche(s) ouverte(s), {ctx['missions_active']} mission(s) active(s), "
        f"{ctx['proposals_pending']} proposition(s) en attente de ta validation.",
    ]
    if ctx.get("last_closing"):
        lines.append(f"Dernière clôture : {ctx['last_closing']} (confiance {ctx.get('last_confidence', '—')}%).")
    lines.append("Confirme l'action proposée pour que je l'exécute dans l'écosystème.")
    return "\n".join(lines)


async def llm_response(text: str, classification: str, ctx: dict, history: list, session_id: str) -> str | None:
    """Accélérateur LLM interchangeable (Emergent universal key). Retourne None si indisponible → fallback interne."""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        key = os.environ.get("EMERGENT_LLM_KEY")
        if not key:
            return None
        system = (
            "Tu es CVLN Cognitive Interface, le deuxième cerveau opérationnel du groupe CVLN, au service de Laurent (fondateur). "
            "Tu réponds en français, de façon concise, structurée et orientée action. Tu respectes la Doctrine CVLN : "
            "gouvernance humaine sur les décisions critiques, souveraineté des données, humilité opérationnelle "
            "('je peux apprendre, mais je dois toujours vérifier'). "
            f"Classification interne du message : {classification}. Action système proposée : {ACTION_LABELS[classification]}. "
            f"Contexte réel du groupe : {ctx}. "
            "Termine toujours par une recommandation claire et, si pertinent, invite à confirmer l'action proposée."
        )
        chat = LlmChat(api_key=key, session_id=session_id, system_message=system).with_model(
            "openai", os.environ.get("COGNITIVE_MODEL", "gpt-5.5"))
        convo = "\n".join(f'{m["role"]}: {m["content"][:300]}' for m in history[-6:])
        prompt = (f"Historique récent:\n{convo}\n\nMessage: {text}" if convo else text)
        response = await chat.send_message(UserMessage(text=prompt))
        return str(response)
    except Exception as e:
        logger.warning(f"LLM accelerator unavailable, sovereign fallback: {e}")
        return None
