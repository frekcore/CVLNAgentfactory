import os
import uuid
import logging
import httpx
from datetime import datetime, timezone
from database import db

logger = logging.getLogger(__name__)

LEVELS = {
    1: {"key": "critical", "prefix": "🔴 CVLN Alert — Action requise", "push": True},
    2: {"key": "decision", "prefix": "🟠 CVLN Decision — Votre validation est requise", "push": True},
    3: {"key": "report", "prefix": "🔵 CVLN Report", "push": True},
    4: {"key": "info", "prefix": "⚪ CVLN Info", "push": False},
}


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN']}/{method}"


async def get_founder_chat_id() -> int | None:
    setting = await db.settings.find_one({"key": "founder_chat_id"})
    return setting["value"] if setting else None


async def discover_chat_id() -> dict:
    """One-time discovery: founder must have sent /start to the bot."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(_api("getUpdates"))
        data = r.json()
    if not data.get("ok"):
        return {"found": False, "error": data.get("description", "telegram error")}
    for upd in reversed(data.get("result", [])):
        msg = upd.get("message") or upd.get("my_chat_member", {})
        chat = msg.get("chat") if isinstance(msg, dict) else None
        if chat and chat.get("type") == "private":
            chat_id = chat["id"]
            await db.settings.update_one({"key": "founder_chat_id"},
                                         {"$set": {"value": chat_id,
                                                   "chat_name": f'{chat.get("first_name", "")} {chat.get("last_name", "")}'.strip(),
                                                   "updated_at": datetime.now(timezone.utc).isoformat()}},
                                         upsert=True)
            return {"found": True, "chat_id": chat_id, "name": chat.get("first_name", "")}
    return {"found": False, "error": "Aucun message reçu — envoie /start au bot @cvln puis réessaie."}


async def send_telegram(chat_id: int, text: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(_api("sendMessage"),
                              json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
        data = r.json()
    return {"sent": bool(data.get("ok")), "error": None if data.get("ok") else data.get("description")}


async def notify(level: int, title: str, message: str, source: str = "system", meta: dict | None = None):
    """Founder Notification Service — persists every notification, pushes levels 1-3 to Telegram."""
    cfg = LEVELS.get(level, LEVELS[4])
    record = {
        "id": str(uuid.uuid4()), "level": level, "level_key": cfg["key"],
        "title": title, "message": message, "source": source, "meta": meta or {},
        "pushed": False, "push_error": None, "read": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if cfg["push"] and os.environ.get("TELEGRAM_TOKEN"):
        chat_id = await get_founder_chat_id()
        if chat_id is None:
            disc = await discover_chat_id()
            chat_id = disc.get("chat_id")
        if chat_id:
            text = f"<b>{cfg['prefix']}</b>\n\n<b>{title}</b>\n{message}"
            try:
                result = await send_telegram(chat_id, text)
                record["pushed"] = result["sent"]
                record["push_error"] = result["error"]
            except Exception as e:
                record["push_error"] = str(e)[:200]
        else:
            record["push_error"] = "founder chat_id not discovered yet (send /start to the bot)"
    await db.notifications.insert_one({**record})
    return record
