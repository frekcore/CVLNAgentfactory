import uuid
from datetime import datetime, timezone
from database import db

VALID_TOPICS_PREFIXES = ("agent.", "factory.", "monitoring.", "memory.", "identity.")


async def publish(topic: str, source: str, payload: dict, destination: str = "broadcast"):
    event = {
        "id": str(uuid.uuid4()),
        "topic": topic,
        "source": source,
        "destination": destination,
        "payload": payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await db.events.insert_one({**event})
    return event
