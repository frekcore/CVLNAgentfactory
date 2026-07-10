import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from database import db
from auth_utils import require_admin, get_current_actor
from notifier import notify, discover_chat_id, get_founder_chat_id, LEVELS

router = APIRouter(prefix="/notifications", tags=["founder-notifications"])


class TestPayload(BaseModel):
    message: str = "Votre organisation numérique est opérationnelle. Ceci est une notification réelle CVLN Command."


@router.get("")
async def list_notifications(level: Optional[int] = None, limit: int = 100,
                             actor: dict = Depends(require_admin)):
    query = {"level": level} if level else {}
    return await db.notifications.find(query, {"_id": 0}).sort("timestamp", -1).to_list(min(limit, 500))


@router.get("/settings")
async def notification_settings(actor: dict = Depends(require_admin)):
    chat_id = await get_founder_chat_id()
    return {"telegram_configured": bool(os.environ.get("TELEGRAM_TOKEN")),
            "founder_chat_connected": chat_id is not None,
            "levels": {k: v["prefix"] for k, v in LEVELS.items()}}


@router.post("/discover-chat")
async def discover(actor: dict = Depends(require_admin)):
    result = await discover_chat_id()
    if not result["found"]:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/test")
async def send_test(payload: TestPayload, actor: dict = Depends(require_admin)):
    record = await notify(3, "Test CVLN Command", payload.message, source="founder-console")
    return {"result": "sent" if record["pushed"] else "persisted_only",
            "pushed": record["pushed"],
            "push_error": record["push_error"]}


@router.post("/{notification_id}/read")
async def mark_read(notification_id: str, actor: dict = Depends(require_admin)):
    await db.notifications.update_one({"id": notification_id}, {"$set": {"read": True}})
    return {"result": "ok"}
