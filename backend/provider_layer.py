"""Provider Adapter Layer (F-006 / ADR-002) — interface IAIProvider unifiée + ModelRouter à stratégies.
Aucun appel direct provider hors de cette couche. Le moteur souverain interne est TOUJOURS le fallback final."""
import os
import time
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from database import db
from auth_utils import get_current_actor, require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/providers", tags=["provider-adapter-layer"])

CATALOG = {
    "anthropic": {"model": "claude-sonnet-4-6", "cost_per_1k_tokens": 0.009, "quality_rank": 1},
    "openai": {"model": "gpt-5.4", "cost_per_1k_tokens": 0.008, "quality_rank": 2},
    "gemini": {"model": "gemini-3.1-pro-preview", "cost_per_1k_tokens": 0.005, "quality_rank": 3},
    "sovereign": {"model": "cvln-internal-deterministic", "cost_per_1k_tokens": 0.0, "quality_rank": 99},
}
STRATEGIES = {
    "quality": ["anthropic", "openai", "gemini", "sovereign"],
    "cost": ["gemini", "openai", "anthropic", "sovereign"],
    "sovereign_only": ["sovereign"],
}


class IAIProvider:
    name = "abstract"

    async def generate(self, system: str, prompt: str, session_id: str) -> str:
        raise NotImplementedError

    async def health_check(self) -> bool:
        return True

    def get_cost_estimate(self, tokens: int) -> float:
        return round(CATALOG[self.name]["cost_per_1k_tokens"] * tokens / 1000, 6)


class EmergentProvider(IAIProvider):
    """Adaptateur via la clé universelle Emergent (interchangeable, non critique)."""

    def __init__(self, name: str):
        self.name = name

    async def generate(self, system: str, prompt: str, session_id: str) -> str:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        key = os.environ.get("EMERGENT_LLM_KEY")
        if not key:
            raise RuntimeError("EMERGENT_LLM_KEY absent")
        chat = LlmChat(api_key=key, session_id=session_id, system_message=system) \
            .with_model(self.name, CATALOG[self.name]["model"])
        return str(await chat.send_message(UserMessage(text=prompt)))

    async def health_check(self) -> bool:
        return bool(os.environ.get("EMERGENT_LLM_KEY"))


class SovereignProvider(IAIProvider):
    """Moteur interne déterministe — garantit que CVLN répond même sans aucun fournisseur externe."""
    name = "sovereign"

    async def generate(self, system: str, prompt: str, session_id: str) -> str:
        from cognitive_engine import classify_message, build_context, internal_response
        ctx = await build_context()
        return internal_response(prompt, classify_message(prompt), ctx)


ADAPTERS: dict[str, IAIProvider] = {
    "anthropic": EmergentProvider("anthropic"),
    "openai": EmergentProvider("openai"),
    "gemini": EmergentProvider("gemini"),
    "sovereign": SovereignProvider(),
}


async def get_strategy() -> str:
    s = await db.settings.find_one({"key": "provider_strategy"})
    return s["value"] if s else "quality"


async def routed_generate(system: str, prompt: str, session_id: str) -> dict:
    """ModelRouter : essaie les providers selon la stratégie, journalise chaque appel, fallback souverain garanti."""
    strategy = await get_strategy()
    order = STRATEGIES.get(strategy, STRATEGIES["quality"])
    last_error = None
    for name in order:
        adapter = ADAPTERS[name]
        start = time.time()
        try:
            text = await adapter.generate(system, prompt, session_id)
            latency = round((time.time() - start) * 1000)
            await db.provider_calls.insert_one({
                "id": str(uuid.uuid4()), "provider": name, "model": CATALOG[name]["model"],
                "strategy": strategy, "ok": True, "latency_ms": latency,
                "cost_estimate": adapter.get_cost_estimate(len(prompt) // 4 + len(text) // 4),
                "timestamp": datetime.now(timezone.utc).isoformat()})
            return {"text": text, "provider": name, "model": CATALOG[name]["model"],
                    "strategy": strategy, "latency_ms": latency}
        except Exception as e:
            last_error = str(e)[:200]
            await db.provider_calls.insert_one({
                "id": str(uuid.uuid4()), "provider": name, "model": CATALOG[name]["model"],
                "strategy": strategy, "ok": False, "error": last_error,
                "latency_ms": round((time.time() - start) * 1000),
                "timestamp": datetime.now(timezone.utc).isoformat()})
            logger.warning(f"Provider {name} failed → next in chain: {last_error}")
    raise RuntimeError(f"Tous les providers ont échoué (impossible : sovereign est infaillible) — {last_error}")


class StrategyPayload(BaseModel):
    strategy: str


class TestPayload(BaseModel):
    prompt: str = Field(min_length=3)


@router.get("")
async def list_providers(actor: dict = Depends(get_current_actor)):
    out = []
    for name, meta in CATALOG.items():
        out.append({"provider": name, **meta, "healthy": await ADAPTERS[name].health_check()})
    from datetime import timedelta
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    calls_24h = await db.provider_calls.count_documents({"timestamp": {"$gte": since}})
    return {"providers": out, "strategy": await get_strategy(), "strategies": list(STRATEGIES.keys()),
            "calls_24h": calls_24h,
            "principle": "Aucun appel direct provider hors de cette couche (ADR-002). Fallback souverain garanti."}


@router.post("/strategy")
async def set_strategy(payload: StrategyPayload, actor: dict = Depends(require_admin)):
    if payload.strategy not in STRATEGIES:
        raise HTTPException(status_code=400, detail=f"strategy must be one of {list(STRATEGIES.keys())}")
    await db.settings.update_one({"key": "provider_strategy"},
                                 {"$set": {"value": payload.strategy,
                                           "updated_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    return {"strategy": payload.strategy}


@router.post("/test")
async def test_route(payload: TestPayload, actor: dict = Depends(require_admin)):
    result = await routed_generate("Tu es CVLN. Réponds en une phrase.", payload.prompt, f"provider-test-{uuid.uuid4()}")
    result["text"] = result["text"][:500]
    return result


@router.get("/calls")
async def list_calls(limit: int = 50, actor: dict = Depends(get_current_actor)):
    return await db.provider_calls.find({}, {"_id": 0}).sort("timestamp", -1).to_list(min(limit, 200))
