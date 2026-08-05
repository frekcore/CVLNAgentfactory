"""Event Bus CVLN (ADR-006) — Mongo persistant + mode dégradé (spool local JSONL) + Dead Letter Queue.
Interface publish() stable pour migration NATS JetStream future."""
import json
import uuid
import logging
from pathlib import Path
from datetime import datetime, timezone
from database import db

logger = logging.getLogger(__name__)
VALID_TOPICS_PREFIXES = ("agent.", "factory.", "monitoring.", "memory.", "identity.", "daily.", "system.")
SPOOL_PATH = Path("/app/backups/event_spool.jsonl")


async def publish(topic: str, source: str, payload: dict, destination: str = "broadcast"):
    event = {
        "id": str(uuid.uuid4()),
        "topic": topic,
        "source": source,
        "destination": destination,
        "payload": payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.events.insert_one({**event})
    except Exception as e:
        # Mode dégradé : file locale pour synchronisation différée (aucun événement perdu)
        try:
            SPOOL_PATH.parent.mkdir(exist_ok=True)
            with SPOOL_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps({**event, "spool_reason": str(e)[:100]}, ensure_ascii=False, default=str) + "\n")
            logger.error(f"Event Bus dégradé — événement spoolé localement: {topic}")
        except Exception as e2:
            logger.critical(f"Event Bus ET spool indisponibles: {e2}")
    return event


async def dead_letter(event: dict, reason: str):
    """DLQ : événements non traitables, conservés pour analyse/replay."""
    await db.events_dlq.insert_one({**event, "dlq_reason": reason,
                                    "dlq_at": datetime.now(timezone.utc).isoformat()})


async def replay_spool() -> dict:
    """Rejoue la file locale vers Mongo après rétablissement. Les lignes invalides partent en DLQ."""
    if not SPOOL_PATH.exists():
        return {"replayed": 0, "dlq": 0}
    replayed, dlq = 0, 0
    lines = SPOOL_PATH.read_text(encoding="utf-8").splitlines()
    for line in lines:
        try:
            ev = json.loads(line)
            ev.pop("spool_reason", None)
            await db.events.insert_one({**ev})
            replayed += 1
        except Exception as e:
            try:
                await dead_letter({"raw": line[:500]}, f"replay failed: {str(e)[:100]}")
                dlq += 1
            except Exception:
                pass
    SPOOL_PATH.unlink(missing_ok=True)
    return {"replayed": replayed, "dlq": dlq}
