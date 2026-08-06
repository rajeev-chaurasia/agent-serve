# ============================================================
# TODO(owner): implement the scheduling logic in this file.
# See _reference.py for a complete reference implementation
# using rendezvous (HRW) hashing — read it for context,
# then implement your own version here.
# ============================================================

import logging

from ..backends.protocols import BackendRegistryProtocol
from ..core.enums import Tier
from ..core.exceptions import BackendUnavailableException
from ..core.models import BackendInfo, SessionContext

logger = logging.getLogger(__name__)


class AffinityScheduler:
    """Session-affinity scheduler for cache-aware backend selection.

    Goal: route consecutive turns of the same session to the same backend
    so vLLM's prefix-cache / KV-cache stays warm, reducing TTFT on later turns.

    Design notes (fill in during implementation):
    - Hashing scheme: rendezvous (HRW) or consistent ring — your choice.
    - Sticky map: session_id -> backend_id with TTL.
    - On backend failure: deterministic re-hash to remaining healthy backends,
      increment AFFINITY_BROKEN_TOTAL metric.
    - Metrics: AFFINITY_HITS_TOTAL when sticky binding used, AFFINITY_MISSES_TOTAL
      when a new assignment is made.
    """

    def __init__(self, registry: BackendRegistryProtocol, sticky_ttl_seconds: int = 1800) -> None:
        # TODO(owner): initialize data structures (sticky map, TTL tracking, lock)
        raise NotImplementedError

    def select_backend(
        self, session: SessionContext, tier: Tier, candidates: list[BackendInfo]
    ) -> BackendInfo:
        """Select a backend for this session, preferring an existing sticky binding.

        TODO(owner): implement
        - Look up session_id in the sticky map.
        - If found and backend is in candidates: record affinity hit metric, return it.
        - If not found or backend gone: run hashing over candidates, store new binding,
          record affinity miss metric.
        - Refresh TTL on each access.
        """
        raise NotImplementedError

    def invalidate(self, session_id: str) -> None:
        """Remove the sticky binding for a session.

        TODO(owner): remove session_id from the sticky map and clean up TTL state.
        """
        raise NotImplementedError

    def on_backend_down(self, backend_id: str, tier: Tier) -> None:
        """Re-assign all sessions pinned to a backend that just went down.

        TODO(owner): scan sticky map for entries pointing to backend_id,
        re-hash them to the remaining healthy backends, increment AFFINITY_BROKEN_TOTAL
        for each session migrated.
        """
        raise NotImplementedError
