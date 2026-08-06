import hashlib
import json
import logging
import time

import httpx

from ..core.enums import Tier
from ..core.models import SessionContext
from ..backends.protocols import BackendRegistryProtocol

logger = logging.getLogger(__name__)

_CLASSIFIER_PROMPT = """You are a routing classifier. Given a chat request, decide which model tier to use.
Reply with exactly one JSON object: {"tier": "small"} or {"tier": "big"}.
Use "big" only if the task clearly requires complex multi-step reasoning, long-context synthesis, or advanced coding.
Use "small" for everything else."""


def _fingerprint(messages: list[dict]) -> str:
    key = json.dumps([{"role": m.get("role"), "content": (m.get("content") or "")[:200]} for m in messages[-3:]])
    return hashlib.sha1(key.encode()).hexdigest()[:16]


class ClassifierRouter:
    """Calls the small-tier model to classify routing tier.

    Results are cached by (agent_id, task fingerprint) to avoid redundant calls
    for multi-turn sessions where the routing decision is stable.
    """

    def __init__(
        self,
        registry: BackendRegistryProtocol,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self._registry = registry
        self._cache_ttl = cache_ttl_seconds
        self._cache: dict[str, tuple[Tier, float]] = {}

    def _cache_get(self, key: str) -> Tier | None:
        if key in self._cache:
            tier, ts = self._cache[key]
            if time.monotonic() - ts < self._cache_ttl:
                return tier
            del self._cache[key]
        return None

    def _cache_put(self, key: str, tier: Tier) -> None:
        self._cache[key] = (tier, time.monotonic())

    async def classify(
        self,
        session: SessionContext,
        messages: list[dict],
    ) -> Tier:
        cache_key = f"{session.agent_id}:{_fingerprint(messages)}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        backends = self._registry.get_healthy_backends(Tier.SMALL)
        if not backends:
            logger.warning("no small backends for classifier, defaulting to small tier")
            return Tier.SMALL

        backend = backends[0]
        payload = {
            "model": "classifier",
            "messages": [
                {"role": "system", "content": _CLASSIFIER_PROMPT},
                {"role": "user", "content": json.dumps(messages[-3:])},
            ],
            "max_tokens": 10,
            "temperature": 0,
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.post(f"{backend.base_url}/v1/chat/completions", json=payload)
                r.raise_for_status()
                content = r.json()["choices"][0]["message"]["content"].strip()
                tier_str = json.loads(content).get("tier", "small")
                tier = Tier(tier_str) if tier_str in Tier._value2member_map_ else Tier.SMALL
        except Exception as exc:
            logger.warning("classifier call failed (%s), defaulting to small", exc)
            tier = Tier.SMALL

        self._cache_put(cache_key, tier)
        return tier
