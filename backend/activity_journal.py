import uuid
from datetime import datetime, timezone
from database import db

JOURNAL_TYPES = ["observation", "analyse", "proposition", "decision_humaine",
                 "action_executee", "action_bloquee", "erreur", "cloture"]


async def journal(entry_type: str, actor: dict, summary: str, source: str = "system",
                  mission_id: str | None = None, agent_id: str | None = None,
                  confidence: int | None = None, evidence: dict | str | None = None,
                  result: str | None = None) -> dict:
    """Activity Journal v2 — unified governance trail (CVLN-GOV-PHASE1-001)."""
    entry = {
        "id": str(uuid.uuid4()),
        "type": entry_type if entry_type in JOURNAL_TYPES else "observation",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor_type": actor.get("type", "system"),
        "actor_id": actor.get("id", "system"),
        "actor_name": actor.get("name", actor.get("email", "")),
        "source": source,
        "mission_id": mission_id,
        "agent_id": agent_id,
        "confidence": confidence,
        "evidence": evidence,
        "result": result,
        "summary": summary,
    }
    await db.activity_journal.insert_one({**entry})
    return entry
