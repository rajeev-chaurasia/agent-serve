import hashlib
import logging
import threading
import time

from ..backends.protocols import BackendRegistryProtocol
from ..core.enums import Tier
from ..core.exceptions import BackendUnavailableException
from ..core.models import BackendInfo, SessionContext
from ..telemetry.metrics import AFFINITY_BROKEN_TOTAL, AFFINITY_HITS_TOTAL, AFFINITY_MISSES_TOTAL

logger = logging.getLogger(__name__)


def _hrw_score(session_id: str, backend_id: str) -> int:
    """Compute a deterministic rendezvous (HRW) score for a (session, backend) pair.

    HRW assigns each pair a pseudo-random weight derived from their combined identity.
    The backend with the highest score wins. Because the score depends only on the
    pair and not on the overall backend set, removing one backend shifts only the
    sessions that were pinned to it — all other sessions stay put. A consistent ring
    would spread the disruption more evenly but requires more bookkeeping; HRW is
    simpler and the disruption profile is exactly what we want for prefix-cache locality.
    """
    key = f"{session_id}:{backend_id}".encode()
    return int(hashlib.sha256(key).hexdigest(), 16)


def _select_by_hrw(session_id: str, candidates: list[BackendInfo]) -> BackendInfo:
    """Return the candidate with the highest HRW score for this session."""
    return max(candidates, key=lambda b: _hrw_score(session_id, b.id))


class _StickyEntry:
    """A single session → backend binding with a sliding expiry timestamp.

    __slots__ cuts per-instance overhead significantly. In a busy gateway
    the sticky map can hold tens of thousands of concurrent sessions, so
    shaving ~100 bytes per entry matters.
    """

    __slots__ = ("backend_id", "tier", "expires_at")

    def __init__(self, backend_id: str, tier: Tier, ttl: int) -> None:
        self.backend_id = backend_id
        self.tier = tier
        self.expires_at = time.monotonic() + ttl


class AffinityScheduler:
    """Session-affinity scheduler that routes multi-turn sessions to a stable backend.

    The goal is to keep vLLM's prefix-cache warm across the turns of a single session.
    The first turn hashes the session to a backend via HRW; subsequent turns reuse that
    binding for as long as the backend stays healthy and the session stays active.

    Hashing scheme — rendezvous (HRW):
        For each candidate backend we compute SHA-256(session_id:backend_id) and pick
        the maximum. This gives a globally consistent mapping: when one backend goes
        down, only its pinned sessions need to be re-hashed; everyone else is undisturbed.

    TTL — sliding, not fixed:
        Every hit refreshes the expiry window. A session that keeps making requests
        retains its binding indefinitely. A session that goes idle for longer than
        sticky_ttl_seconds will be re-hashed on its next request (still likely lands
        on the same backend, but counted as a miss).

    Thread safety:
        FastAPI runs sync route handlers in a thread pool, so select_backend is called
        from multiple threads concurrently. asyncio.Lock cannot be awaited from worker
        threads, and a plain threading.Lock would deadlock if on_backend_down (a sync
        admin path) ever called back through a path that re-enters the same lock.
        threading.RLock is the safe, minimal choice here.
    """

    def __init__(self, registry: BackendRegistryProtocol, sticky_ttl_seconds: int = 1800) -> None:
        self._registry = registry
        self._ttl = sticky_ttl_seconds
        # Keyed by session_id. We accept unbounded growth here; a production deployment
        # should pair this with a periodic sweep or use a TTLCache wrapper if memory
        # pressure becomes measurable. For now, expired entries are evicted lazily on
        # the next access from that session.
        self._sticky: dict[str, _StickyEntry] = {}
        self._lock = threading.RLock()

    def select_backend(
        self, session: SessionContext, tier: Tier, candidates: list[BackendInfo]
    ) -> BackendInfo:
        """Route a session turn to the best backend, reusing any live sticky binding.

        Returns the same backend as previous turns when the binding is valid, so the
        vLLM instance's prefix cache hit rate stays high. Falls through to HRW when
        the binding is missing, expired, or the pinned backend is no longer in candidates.
        """
        if not candidates:
            raise BackendUnavailableException(tier=tier)

        # Build the set once so the per-entry lookup is O(1).
        candidate_ids = {b.id for b in candidates}

        with self._lock:
            entry = self._sticky.get(session.session_id)
            now = time.monotonic()

            if entry and entry.expires_at > now and entry.backend_id in candidate_ids:
                # Slide the window forward so active sessions never expire mid-conversation.
                entry.expires_at = now + self._ttl
                AFFINITY_HITS_TOTAL.labels(tier=tier.value).inc()
                # Return the caller's BackendInfo object, not a reconstructed one — the
                # caller's list is the authoritative view of the backend's current state.
                return next(b for b in candidates if b.id == entry.backend_id)

            # Either no entry, TTL expired, or the pinned backend left the candidate set.
            # HRW over the current candidates gives us a deterministic, stable assignment.
            chosen = _select_by_hrw(session.session_id, candidates)
            self._sticky[session.session_id] = _StickyEntry(chosen.id, tier, self._ttl)
            AFFINITY_MISSES_TOTAL.labels(tier=tier.value).inc()
            return chosen

    def invalidate(self, session_id: str) -> None:
        """Drop the sticky binding for a session.

        Called on session close or explicit eviction. Subsequent requests from this
        session_id will be treated as new arrivals and re-hashed.
        """
        with self._lock:
            self._sticky.pop(session_id, None)

    def on_backend_down(self, backend_id: str, tier: Tier) -> None:
        """Migrate all sessions pinned to a backend that just went down.

        We fetch the surviving healthy backends before acquiring our lock to avoid a
        potential lock-ordering deadlock: the registry has its own internal lock, and
        calling into it while holding _lock would invert the order if the registry ever
        needed to call back into us. Fetching first is safe — in the worst case we
        migrate a session to a backend that goes down a millisecond later; the next
        select_backend call will catch the stale entry through the candidate_ids check.

        Migrated sessions are re-hashed over survivors so the disruption is no larger
        than necessary. If no survivors exist we evict the sessions entirely; they will
        be re-admitted (and counted as misses) when a new backend comes online and the
        caller retries.
        """
        survivors = [b for b in self._registry.get_healthy_backends(tier) if b.id != backend_id]

        with self._lock:
            affected = [
                sid
                for sid, entry in self._sticky.items()
                if entry.backend_id == backend_id and entry.tier == tier
            ]

            for sid in affected:
                if survivors:
                    new_backend = _select_by_hrw(sid, survivors)
                    self._sticky[sid].backend_id = new_backend.id
                    logger.warning(
                        "affinity broken: session %s migrated from %s to %s (tier=%s)",
                        sid,
                        backend_id,
                        new_backend.id,
                        tier.value,
                    )
                else:
                    # No live backends to absorb the session. Evict rather than hold a
                    # binding to a dead backend; the session will re-hash when it retries.
                    del self._sticky[sid]
                    logger.warning(
                        "affinity broken: session %s evicted (no survivors tier=%s, %s down)",
                        sid,
                        tier.value,
                        backend_id,
                    )

                AFFINITY_BROKEN_TOTAL.labels(tier=tier.value).inc()
