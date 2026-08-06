# ============================================================
# REFERENCE IMPLEMENTATION — NOT USED IN PRODUCTION
#
# This file exists so the owner can understand one correct
# approach before writing their own in scheduler.py.
# It is excluded from the import chain and not instantiated
# anywhere. Do not modify it — treat it as read-only reference.
# ============================================================

import hashlib
import logging
import threading
import time

from ..backends.protocols import BackendRegistryProtocol
from ..core.enums import Tier
from ..core.exceptions import BackendUnavailableException
from ..core.models import BackendInfo, SessionContext
from ..telemetry.metrics import (
    AFFINITY_BROKEN_TOTAL,
    AFFINITY_HITS_TOTAL,
    AFFINITY_MISSES_TOTAL,
)

logger = logging.getLogger(__name__)


def _hrw_score(session_id: str, backend_id: str) -> int:
    """Rendezvous (highest random weight) hash score for (session, backend) pair.

    Each (session, backend) pair gets a deterministic pseudo-random score.
    The backend with the highest score wins. This gives a consistent mapping
    that minimises re-assignments when a backend is added or removed.
    """
    key = f"{session_id}:{backend_id}".encode()
    return int(hashlib.sha256(key).hexdigest(), 16)


def _select_by_hrw(session_id: str, candidates: list[BackendInfo]) -> BackendInfo:
    return max(candidates, key=lambda b: _hrw_score(session_id, b.id))


class _StickyEntry:
    __slots__ = ("backend_id", "tier", "expires_at")

    def __init__(self, backend_id: str, tier: Tier, ttl: int) -> None:
        self.backend_id = backend_id
        self.tier = tier
        self.expires_at = time.monotonic() + ttl


class ReferenceAffinityScheduler:
    """Reference implementation of AffinitySchedulerProtocol using HRW hashing."""

    def __init__(self, registry: BackendRegistryProtocol, sticky_ttl_seconds: int = 1800) -> None:
        self._registry = registry
        self._ttl = sticky_ttl_seconds
        self._sticky: dict[str, _StickyEntry] = {}
        self._lock = threading.RLock()

    def select_backend(
        self, session: SessionContext, tier: Tier, candidates: list[BackendInfo]
    ) -> BackendInfo:
        if not candidates:
            raise BackendUnavailableException(tier=tier)

        candidate_ids = {b.id for b in candidates}
        with self._lock:
            entry = self._sticky.get(session.session_id)
            now = time.monotonic()
            if entry and entry.expires_at > now and entry.backend_id in candidate_ids:
                entry.expires_at = now + self._ttl  # refresh TTL on access
                AFFINITY_HITS_TOTAL.labels(tier=tier.value).inc()
                return next(b for b in candidates if b.id == entry.backend_id)

            # No valid sticky entry — pick via HRW and store.
            chosen = _select_by_hrw(session.session_id, candidates)
            self._sticky[session.session_id] = _StickyEntry(chosen.id, tier, self._ttl)
            AFFINITY_MISSES_TOTAL.labels(tier=tier.value).inc()
            return chosen

    def invalidate(self, session_id: str) -> None:
        with self._lock:
            self._sticky.pop(session_id, None)

    def on_backend_down(self, backend_id: str, tier: Tier) -> None:
        """Migrate all sessions pinned to the downed backend using HRW over remaining backends."""
        remaining = self._registry.get_healthy_backends(tier)
        remaining = [b for b in remaining if b.id != backend_id]
        with self._lock:
            affected = [
                sid
                for sid, entry in self._sticky.items()
                if entry.backend_id == backend_id and entry.tier == tier
            ]
            for sid in affected:
                if remaining:
                    new_backend = _select_by_hrw(sid, remaining)
                    self._sticky[sid].backend_id = new_backend.id
                else:
                    del self._sticky[sid]
                AFFINITY_BROKEN_TOTAL.labels(tier=tier.value).inc()
                logger.info("affinity broken: session %s migrated from %s", sid, backend_id)
