import time
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from database import db
from auth_utils import get_current_actor, log_authz
from event_bus import publish
from cognitive_engine import classify_message, build_context, internal_response, llm_response, ACTION_LABELS
from knowledge_sources_routes import vector_store, dual_write_from_legacy

router = APIRouter(prefix="/cognitive", tags=["cognitive-interface"])

MIN_KNOWLEDGE_RELEVANCE = 0.3


class ChatPayload(BaseModel):
    message: str = Field(min_length=2)
    conversation_id: Optional[str] = None
    disable_knowledge_search: bool = False


def now_iso():
    return datetime.now(timezone.utc).isoformat()


@router.post("/chat")
async def cognitive_chat(payload: ChatPayload, actor: dict = Depends(get_current_actor)):
    conv_id = payload.conversation_id or str(uuid.uuid4())
    classification = classify_message(payload.message)
    ctx = await build_context()
    history = await db.cognitive_messages.find({"conversation_id": conv_id}, {"_id": 0}).sort("timestamp", 1).to_list(50)

    # L4 — recherche souveraine top-3 avant chaque réponse (moteur lexical interne, aucun appel fournisseur)
    relevant, retrieval_ms = [], 0.0
    if not payload.disable_knowledge_search:
        t0 = time.perf_counter()
        hits = await vector_store.search(payload.message, None, 3)
        retrieval_ms = round((time.perf_counter() - t0) * 1000, 1)
        relevant = [h for h in hits if h["score"] >= MIN_KNOWLEDGE_RELEVANCE]
        if relevant:
            src_ids = list({h["source_id"] for h in relevant})
            titles = {s["id"]: s["title"] async for s in db.knowledge_sources.find(
                {"id": {"$in": src_ids}}, {"_id": 0, "id": 1, "title": 1})}
            for h in relevant:
                h["source_title"] = titles.get(h["source_id"], "")
    knowledge_block = " | ".join(f'[{h["source_title"]}] {h["text"][:250]}' for h in relevant) or None
    sovereign_knowledge = {
        "used": bool(relevant), "retrieval_ms": retrieval_ms,
        "sources": [{"source_id": h["source_id"], "title": h["source_title"], "score": h["score"]} for h in relevant],
        "note": None if relevant else "Réponse non fondée sur la mémoire souveraine (aucune source suffisamment pertinente)"}

    reply = await llm_response(payload.message, classification, ctx,
                               [{"role": m["role"], "content": m["content"]} for m in history], conv_id,
                               knowledge_block=knowledge_block)
    engine = "llm-accelerator" if reply else "internal-sovereign"
    if not reply:
        reply = internal_response(payload.message, classification, ctx, knowledge_hits=relevant)

    ts = now_iso()
    user_msg = {"id": str(uuid.uuid4()), "conversation_id": conv_id, "role": "user",
                "content": payload.message, "classification": classification,
                "proposed_action": ACTION_LABELS[classification], "action_executed": False,
                "actor_id": actor["id"], "timestamp": ts}
    assistant_msg = {"id": str(uuid.uuid4()), "conversation_id": conv_id, "role": "assistant",
                     "content": reply, "engine": engine, "sovereign_knowledge": sovereign_knowledge,
                     "timestamp": now_iso()}
    await db.cognitive_messages.insert_one({**user_msg})
    await db.cognitive_messages.insert_one({**assistant_msg})
    await db.cognitive_conversations.update_one(
        {"id": conv_id},
        {"$set": {"last_message": payload.message[:80], "updated_at": ts, "actor_id": actor["id"]},
         "$setOnInsert": {"id": conv_id, "created_at": ts}}, upsert=True)
    return {"conversation_id": conv_id, "classification": classification,
            "proposed_action": ACTION_LABELS[classification], "engine": engine,
            "user_message_id": user_msg["id"], "reply": reply,
            "sovereign_knowledge": sovereign_knowledge}


@router.post("/confirm/{message_id}")
async def confirm_action(message_id: str, actor: dict = Depends(get_current_actor)):
    if actor["type"] == "human" and actor["role"] == "reader":
        raise HTTPException(status_code=403, detail="Readers cannot execute cognitive actions")
    msg = await db.cognitive_messages.find_one({"id": message_id, "role": "user"}, {"_id": 0})
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if msg.get("action_executed"):
        raise HTTPException(status_code=409, detail="Action already executed")
    c, text, ts = msg["classification"], msg["content"], now_iso()
    result = {}

    if c in ("task", "instruction"):
        from missions_routes import tokenize
        words = set(tokenize(text))
        best, best_score = "AGT-000", 0
        async for a in db.agents.find({"status": {"$ne": "Archive"}}, {"_id": 0, "id": 1, "name": 1, "mission": 1, "pole": 1}):
            score = len(words & set(tokenize(f'{a["name"]} {a["pole"]} {a.get("mission", "")}')))
            if score > best_score:
                best, best_score = a["id"], score
        task = {"id": str(uuid.uuid4()), "agent_id": best, "entity": "CVLN Holding",
                "title": text[:80], "description": text, "priority": "P1", "status": "open",
                "source": "cognitive-interface", "created_by": f'{actor["type"]}:{actor["id"]}',
                "created_at": ts, "updated_at": ts}
        await db.agent_tasks.insert_one({**task})
        await publish("agent.task_assigned", "cognitive-interface", {"agent_id": best, "title": task["title"]})
        result = {"type": "task_created", "agent_id": best, "task_id": task["id"]}
    elif c == "decision":
        await db.memory_entries.insert_one({
            "id": str(uuid.uuid4()), "agent_id": "AGT-000", "entity": "CVLN Brain", "scope": "strategic",
            "key": f"decision:{message_id}", "value": {"decision": text, "decided_by": actor["id"]},
            "owner": actor["id"], "created_at": ts, "updated_at": ts})
        await publish("memory.strategic_decision", "cognitive-interface", {"decision": text[:120]})
        result = {"type": "strategic_memory_created"}
    elif c == "rule":
        prop = {"id": str(uuid.uuid4()), "type": "modify_workflow", "title": f"Règle doctrine proposée : {text[:60]}",
                "description": text, "target_agent_id": None, "source": "cognitive-interface",
                "status": "proposed", "proposed_by": f'{actor["type"]}:{actor["id"]}',
                "decision_by": None, "decision_note": "", "created_at": ts, "decided_at": None}
        await db.evolution_proposals.insert_one({**prop})
        await publish("factory.evolution_proposed", "cognitive-interface", {"proposal_id": prop["id"]})
        result = {"type": "doctrine_proposal_created", "proposal_id": prop["id"], "note": "Validation humaine requise"}
    else:
        category = "research" if c == "hypothesis" else "strategy" if c == "idea" else "business"
        item = {"id": str(uuid.uuid4()), "title": text[:70], "source_type": "note", "category": category,
                "auto_classified": True, "content": text, "target_agents": [], "status": "ingested",
                "version": 1, "created_by": f'{actor["type"]}:{actor["id"]}', "created_at": ts}
        await db.knowledge_items.insert_one({**item})
        # L6 — dual write transition : réplique v2 (legacy jamais supprimé)
        v2_id = await dual_write_from_legacy(item)
        await db.knowledge_items.update_one({"id": item["id"]}, {"$set": {"v2_source_id": v2_id}})
        result = {"type": "knowledge_created", "knowledge_id": item["id"], "category": category, "v2_source_id": v2_id}

    await db.cognitive_messages.update_one({"id": message_id}, {"$set": {"action_executed": True, "action_result": result}})
    await log_authz(actor, "cognitive_action", f"message:{message_id}", True, result["type"])
    return {"result": "executed", **result}


@router.get("/conversations")
async def list_conversations(actor: dict = Depends(get_current_actor)):
    return await db.cognitive_conversations.find({"actor_id": actor["id"]}, {"_id": 0}).sort("updated_at", -1).to_list(50)


@router.get("/conversations/{conv_id}/messages")
async def conversation_messages(conv_id: str, actor: dict = Depends(get_current_actor)):
    return await db.cognitive_messages.find({"conversation_id": conv_id}, {"_id": 0}).sort("timestamp", 1).to_list(200)


@router.get("/temporal")
async def temporal_intelligence(period: str = "day", actor: dict = Depends(get_current_actor)):
    hours = {"hour": 1, "day": 24, "week": 168, "month": 720, "year": 8760}.get(period, 24)
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    events = await db.events.count_documents({"timestamp": {"$gte": since}})
    tasks_done = await db.agent_tasks.count_documents({"status": "done", "updated_at": {"$gte": since}})
    missions_validated = await db.missions.count_documents({"status": "validated", "updated_at": {"$gte": since}})
    denied = await db.audit_logs.count_documents({"allowed": False, "timestamp": {"$gte": since}})
    finance = {"cost": 0, "revenue": 0}
    async for e in db.finance_entries.find({"created_at": {"$gte": since}}, {"_id": 0, "type": 1, "amount": 1}):
        finance[e["type"]] += e["amount"]
    top_topics = {}
    async for e in db.events.find({"timestamp": {"$gte": since}}, {"_id": 0, "topic": 1}):
        top_topics[e["topic"]] = top_topics.get(e["topic"], 0) + 1
    return {"period": period, "since": since, "events": events, "tasks_done": tasks_done,
            "missions_validated": missions_validated, "denied_authorizations": denied,
            "finance": {**finance, "net": round(finance["revenue"] - finance["cost"], 2)},
            "top_activity": dict(sorted(top_topics.items(), key=lambda x: -x[1])[:8])}
