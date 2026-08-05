"""S0.2 — KnowledgeSource structuré (ADR-003) + Vector Store souverain (index lexical MongoDB, interface IVectorStore).
La mémoire métier des agents devient persistante et interrogeable. Migration Qdrant possible via l'interface."""
import re
import uuid
import math
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from database import db
from auth_utils import get_current_actor
from activity_journal import journal
from event_bus import publish

router = APIRouter(prefix="/knowledge/sources", tags=["knowledge-sources"])

STOP = {"le", "la", "les", "de", "des", "du", "un", "une", "et", "en", "pour", "sur", "avec", "dans",
        "est", "sont", "the", "a", "of", "to", "and", "in", "ce", "cette", "que", "qui", "par", "au", "aux"}


class KnowledgeSourcePayload(BaseModel):
    type: str = "document"  # document | database | archive | skill | doctrine
    source_uri: str = ""
    title: str = Field(min_length=3)
    content: str = Field(min_length=20)
    version: str = "1.0"
    agent_ids: List[str] = Field(default_factory=list)  # vide = Knowledge Commons (partagé)
    metadata: dict = Field(default_factory=dict)


class SearchPayload(BaseModel):
    query: str = Field(min_length=2)
    agent_id: Optional[str] = None
    top_k: int = Field(5, ge=1, le=20)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def tokenize(text: str) -> list:
    return [w for w in re.findall(r"[a-zà-ÿ0-9]{2,}", text.lower()) if w not in STOP]


def chunk_text(text: str, size: int = 600, overlap: int = 100) -> list:
    chunks, i = [], 0
    while i < len(text):
        chunks.append(text[i:i + size])
        i += size - overlap
    return chunks


class SovereignLexicalStore:
    """IVectorStore souverain v1 — index lexical MongoDB (TF pondéré). Interface stable pour migration Qdrant (ADR-005)."""

    async def ingest(self, source_id: str, text: str, agent_ids: list) -> int:
        chunks = chunk_text(text)
        ts = now_iso()
        for idx, c in enumerate(chunks):
            terms = tokenize(c)
            await db.knowledge_chunks.insert_one({
                "id": f"vec-{source_id}-{idx:03d}", "source_id": source_id, "chunk_index": idx,
                "text": c, "terms": list(set(terms)), "term_count": len(terms),
                "agent_ids": agent_ids, "created_at": ts})
        return len(chunks)

    async def search(self, query: str, agent_id: str | None, top_k: int) -> list:
        q_terms = set(tokenize(query))
        if not q_terms:
            return []
        flt = {"terms": {"$in": list(q_terms)}}
        if agent_id:
            flt["$or"] = [{"agent_ids": agent_id}, {"agent_ids": []}]
        scored = []
        async for c in db.knowledge_chunks.find(flt, {"_id": 0}).limit(500):
            overlap = q_terms & set(c["terms"])
            score = len(overlap) / math.sqrt(max(len(c["terms"]), 1)) * math.sqrt(len(overlap))
            scored.append({"vector_id": c["id"], "source_id": c["source_id"], "score": round(score, 4),
                           "matched_terms": sorted(overlap)[:8], "text": c["text"][:400]})
        scored.sort(key=lambda x: -x["score"])
        return scored[:top_k]

    async def delete_source(self, source_id: str) -> int:
        r = await db.knowledge_chunks.delete_many({"source_id": source_id})
        return r.deleted_count


vector_store = SovereignLexicalStore()


@router.get("")
async def list_sources(agent_id: Optional[str] = None, actor: dict = Depends(get_current_actor)):
    query = {}
    if agent_id:
        query["$or"] = [{"agent_ids": agent_id}, {"agent_ids": []}]
    return await db.knowledge_sources.find(query, {"_id": 0, "content": 0}).sort("last_updated", -1).to_list(500)


@router.post("")
async def create_source(payload: KnowledgeSourcePayload, actor: dict = Depends(get_current_actor)):
    if actor["type"] == "human" and actor["role"] == "reader":
        raise HTTPException(status_code=403, detail="Readers cannot ingest knowledge")
    count = await db.knowledge_sources.count_documents({})
    ks_id = f"ks-{count + 1:04d}-{uuid.uuid4().hex[:6]}"
    ts = now_iso()
    n_chunks = await vector_store.ingest(ks_id, payload.content, payload.agent_ids)
    source = {"id": ks_id, "type": payload.type, "source_uri": payload.source_uri,
              "title": payload.title, "version": payload.version,
              "embedding_model": "sovereign-lexical-v1",
              "vector_id_prefix": f"vec-{ks_id}", "chunks": n_chunks,
              "agent_ids": payload.agent_ids, "shared_commons": len(payload.agent_ids) == 0,
              "metadata": payload.metadata, "content": payload.content,
              "created_by": f'{actor["type"]}:{actor["id"]}',
              "created_at": ts, "last_updated": ts}
    await db.knowledge_sources.insert_one({**source})
    await journal("action_executee", actor,
                  f"KnowledgeSource {ks_id} ingérée : « {payload.title} » ({n_chunks} chunks, "
                  f"{'Knowledge Commons partagé' if not payload.agent_ids else ', '.join(payload.agent_ids)})",
                  source="knowledge-sources", evidence={"source_id": ks_id, "chunks": n_chunks}, result="ingested")
    await publish("memory.knowledge_ingested", actor["id"], {"source_id": ks_id, "chunks": n_chunks})
    source.pop("content", None)
    source.pop("_id", None)
    return source


@router.post("/search")
async def search_knowledge(payload: SearchPayload, actor: dict = Depends(get_current_actor)):
    results = await vector_store.search(payload.query, payload.agent_id, payload.top_k)
    src_ids = list({r["source_id"] for r in results})
    titles = {s["id"]: s["title"] async for s in
              db.knowledge_sources.find({"id": {"$in": src_ids}}, {"_id": 0, "id": 1, "title": 1})}
    for r in results:
        r["source_title"] = titles.get(r["source_id"], "")
    return {"query": payload.query, "engine": "sovereign-lexical-v1 (interface IVectorStore — migration Qdrant prête)",
            "results": results}
