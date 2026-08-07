"""Tests for AffinityScheduler (the real implementation, not the reference).

These tests exercise the public contract of AffinityScheduler independently of
any FastAPI infrastructure.  Each test creates a fresh scheduler instance so
Prometheus counter deltas are scoped to the operation under test, and the
sticky map never carries state across test boundaries.

We use concrete fakes and a real BackendRegistry rather than mocks: fakes are
honest about what the code actually sees, and BackendRegistry is already
well-tested — reinventing it here would add noise without adding confidence.
"""

import threading

import pytest

from agent_serve.affinity.scheduler import AffinityScheduler
from agent_serve.backends.registry import BackendRegistry
from agent_serve.config.models import (
    AffinityConfig,
    BackendConfig,
    GatewayConfig,
)
from agent_serve.core.enums import BackendStatus, Tier
from agent_serve.core.exceptions import BackendUnavailableException
from agent_serve.core.models import BackendInfo, SessionContext
from agent_serve.telemetry.metrics import (
    AFFINITY_BROKEN_TOTAL,
    AFFINITY_HITS_TOTAL,
    AFFINITY_MISSES_TOTAL,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_backends(n: int, tier: Tier = Tier.SMALL) -> list[BackendInfo]:
    """Produce n BackendInfo instances with predictable, unique IDs.

    The base_url is deliberately unreachable; nothing in these tests sends
    actual HTTP traffic.
    """
    return [
        BackendInfo(
            id=f"{tier.value}-{i}",
            tier=tier,
            base_url=f"http://unreachable:{8000 + i}",
            gpu=i,
            max_inflight=64,
        )
        for i in range(n)
    ]


def _scheduler_for(
    backends: list[BackendInfo], ttl: int = 1800
) -> tuple[AffinityScheduler, BackendRegistry]:
    """Build a scheduler backed by a real BackendRegistry seeded from backends.

    Returns both objects so tests that need to mark a backend down can call
    registry.mark_status() without having to reach into scheduler internals.
    """
    config = GatewayConfig(
        backends=[
            BackendConfig(
                id=b.id,
                tier=b.tier,
                base_url=b.base_url,
                gpu=b.gpu,
                max_inflight=b.max_inflight,
            )
            for b in backends
        ],
        affinity=AffinityConfig(sticky_ttl_seconds=ttl),
    )
    registry = BackendRegistry(config)
    return AffinityScheduler(registry, sticky_ttl_seconds=ttl), registry


def _counter_value(counter, tier: str) -> float:
    """Read the current value of a labelled Prometheus counter.

    We access _value.get() rather than the public API because the public API
    only exposes the value through the /metrics scrape format — not useful
    inside unit tests.  This is a known pattern in prometheus_client testing.
    """
    return counter.labels(tier=tier)._value.get()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_new_session_gets_backend_assigned():
    # The scheduler must never leave a valid session without a backend when
    # at least one candidate exists.  Raising here would silently drop user
    # requests, which is worse than any routing suboptimality.
    backends = _make_backends(2)
    scheduler, _ = _scheduler_for(backends)
    session = SessionContext(session_id="fresh-session-001", agent_id="a")

    result, _ = scheduler.select_backend(session, Tier.SMALL, backends)

    assert result.id in {b.id for b in backends}


def test_same_session_returns_same_backend_on_repeat_calls():
    # Prefix-cache locality only pays off when consecutive turns of a session
    # land on the same vLLM instance.  If the binding drifts between calls, the
    # cache is cold and we pay the full KV-recompute cost.
    backends = _make_backends(3)
    scheduler, _ = _scheduler_for(backends)
    session = SessionContext(session_id="sticky-001", agent_id="a")

    first, _ = scheduler.select_backend(session, Tier.SMALL, backends)
    second, _ = scheduler.select_backend(session, Tier.SMALL, backends)

    assert first.id == second.id


def test_different_sessions_distribute_across_backends():
    # HRW should spread sessions across all available backends — if every
    # session landed on the same backend we would have effectively a single
    # point of load, which defeats the purpose of having multiple backends.
    # 40 sessions with 2 backends: P(all on one backend) ≈ 2 * (1/2)^40 ≈ 0.
    backends = _make_backends(2)
    scheduler, _ = _scheduler_for(backends)

    assigned = set()
    for i in range(40):
        session = SessionContext(session_id=f"spread-{i:03d}", agent_id="a")
        result, _ = scheduler.select_backend(session, Tier.SMALL, backends)
        assigned.add(result.id)

    assert len(assigned) == 2, (
        "HRW distributed all 40 sessions to the same backend — "
        "likely a hash collision in the key construction"
    )


def test_hit_metric_incremented_on_sticky_reuse():
    # A hit means the prefix cache can serve the request — that's the whole
    # point of session affinity.  If the counter isn't moving, something has
    # broken the binding path silently.
    backends = _make_backends(2)
    scheduler, _ = _scheduler_for(backends)
    session = SessionContext(session_id="hit-metric-001", agent_id="a")

    # Establish the binding first (a miss).
    scheduler.select_backend(session, Tier.SMALL, backends)

    before = _counter_value(AFFINITY_HITS_TOTAL, "small")
    scheduler.select_backend(session, Tier.SMALL, backends)
    after = _counter_value(AFFINITY_HITS_TOTAL, "small")

    assert after - before == 1


def test_miss_metric_incremented_on_new_session():
    # A miss on the first call is expected — the scheduler has no prior
    # knowledge of the session.  What matters is that the counter records it
    # so operators can see the first-turn miss rate on dashboards.
    backends = _make_backends(2)
    scheduler, _ = _scheduler_for(backends)
    session = SessionContext(session_id="miss-metric-001", agent_id="a")

    before = _counter_value(AFFINITY_MISSES_TOTAL, "small")
    scheduler.select_backend(session, Tier.SMALL, backends)
    after = _counter_value(AFFINITY_MISSES_TOTAL, "small")

    assert after - before == 1


def test_empty_candidates_raises_backend_unavailable():
    # Returning None or a sentinel value would force every caller to null-check;
    # an exception gives the caller a typed, unambiguous signal that the tier
    # is completely offline.
    backends = _make_backends(1)
    scheduler, _ = _scheduler_for(backends)
    session = SessionContext(session_id="no-candidates-001", agent_id="a")

    with pytest.raises(BackendUnavailableException):
        scheduler.select_backend(session, Tier.SMALL, [])


def test_invalidate_clears_sticky_binding():
    # After a session ends (or is force-evicted), the binding must be gone.
    # If it lingers, the next session that reuses the same session_id — e.g.
    # after a client reconnect — would be sent to whatever backend the old
    # session was using, which may no longer be the right choice.
    backends = _make_backends(2)
    scheduler, _ = _scheduler_for(backends)
    session = SessionContext(session_id="invalidate-001", agent_id="a")

    scheduler.select_backend(session, Tier.SMALL, backends)
    scheduler.invalidate(session.session_id)

    # The next call on this session_id must be treated as a fresh arrival.
    before = _counter_value(AFFINITY_MISSES_TOTAL, "small")
    scheduler.select_backend(session, Tier.SMALL, backends)
    after = _counter_value(AFFINITY_MISSES_TOTAL, "small")

    assert after - before == 1, (
        "Select after invalidate should produce a miss — the old binding must "
        "not survive eviction"
    )


def test_on_backend_down_migrates_pinned_sessions():
    # When a backend goes down mid-flight, sessions pinned to it must move to
    # a survivor immediately — waiting for a TTL expiry would route those
    # sessions to a dead host for up to 30 minutes.
    backends = _make_backends(2)
    scheduler, registry = _scheduler_for(backends)
    b0, b1 = backends[0], backends[1]

    # Force five sessions onto b0 by presenting it as the sole candidate.
    # This is realistic: a caller who already knows the session's tier might
    # narrow the candidate list before passing it in.
    sessions = [
        SessionContext(session_id=f"migrate-{i}", agent_id="a") for i in range(5)
    ]
    for s in sessions:
        result, _ = scheduler.select_backend(s, Tier.SMALL, [b0])
        assert result.id == b0.id

    # Simulate the probe loop detecting b0 as down and updating the registry.
    registry.mark_status(b0.id, BackendStatus.DOWN)
    scheduler.on_backend_down(b0.id, Tier.SMALL)

    # All sessions should now route to b1 without requiring another miss cycle.
    for s in sessions:
        result, _ = scheduler.select_backend(s, Tier.SMALL, backends)
        assert result.id == b1.id, (
            f"Session {s.session_id} still routes to {result.id} after b0 went down"
        )


def test_on_backend_down_increments_broken_metric():
    # Operators need a signal whenever affinity is disrupted so they can
    # investigate whether prefix-cache hit rates are degraded beyond normal.
    # Silence here would mean broken-affinity events are invisible in dashboards.
    backends = _make_backends(2)
    scheduler, registry = _scheduler_for(backends)
    b0 = backends[0]
    session = SessionContext(session_id="broken-metric-001", agent_id="a")

    # Pin the session to b0.
    scheduler.select_backend(session, Tier.SMALL, [b0])

    before = _counter_value(AFFINITY_BROKEN_TOTAL, "small")
    registry.mark_status(b0.id, BackendStatus.DOWN)
    scheduler.on_backend_down(b0.id, Tier.SMALL)
    after = _counter_value(AFFINITY_BROKEN_TOTAL, "small")

    assert after - before == 1


def test_on_backend_down_with_no_survivors_evicts_sessions():
    # If every backend for a tier is gone there is nowhere to migrate sessions.
    # Keeping a binding that points at a dead host is worse than evicting it:
    # the next request would see the dead backend in the sticky entry, pass the
    # candidate_ids check if the caller still lists it, and stream into /dev/null.
    # Eviction forces a clean re-hash when healthy backends return.
    backends = _make_backends(1)
    scheduler, registry = _scheduler_for(backends)
    only_backend = backends[0]
    session = SessionContext(session_id="evict-on-no-survivors", agent_id="a")

    scheduler.select_backend(session, Tier.SMALL, backends)

    # The sole backend disappears — no survivors.
    registry.mark_status(only_backend.id, BackendStatus.DOWN)
    scheduler.on_backend_down(only_backend.id, Tier.SMALL)

    # Binding must have been removed, not left pointing at the dead host.
    assert session.session_id not in scheduler._sticky

    # When a new backend comes online the session should be admissible without error.
    new_backend = BackendInfo(
        id="small-replacement",
        tier=Tier.SMALL,
        base_url="http://unreachable:9001",
        gpu=0,
        max_inflight=64,
    )
    result, _ = scheduler.select_backend(session, Tier.SMALL, [new_backend])
    assert result.id == new_backend.id


def test_select_backend_returns_hit_false_on_first_turn_true_on_subsequent():
    # The hit flag is the source of truth for affinity_hit in API responses.
    # Turn 1 must be False (no prior binding); turn 2+ must be True.
    backends = _make_backends(2)
    scheduler, _ = _scheduler_for(backends)
    session = SessionContext(session_id="hit-flag-001", agent_id="a")

    _, hit1 = scheduler.select_backend(session, Tier.SMALL, backends)
    _, hit2 = scheduler.select_backend(session, Tier.SMALL, backends)
    _, hit3 = scheduler.select_backend(session, Tier.SMALL, backends)

    assert hit1 is False, "Turn 1 should be a miss — no prior binding exists"
    assert hit2 is True, "Turn 2 should be a hit — binding was established on turn 1"
    assert hit3 is True, "Turn 3 should remain a hit"


def test_ttl_expiry_produces_miss_not_hit():
    # A TTL of zero means the binding expires at the instant it is written.
    # Any call after the first must be a miss — the scheduler must not serve
    # a cached decision from a binding that has already expired.
    # This is important for correctness: expired entries should behave as if
    # they were never written, not as immortal sticky decisions.
    backends = _make_backends(1)
    scheduler, _ = _scheduler_for(backends, ttl=0)
    session = SessionContext(session_id="ttl-zero-001", agent_id="a")

    # First call is always a miss (new session).
    miss_before = _counter_value(AFFINITY_MISSES_TOTAL, "small")
    scheduler.select_backend(session, Tier.SMALL, backends)

    # With ttl=0, expires_at == time.monotonic() at write time.  By the time
    # the second call reads time.monotonic() the condition expires_at > now
    # evaluates to False (monotonic never decreases), so the entry is not reused.
    hit_before = _counter_value(AFFINITY_HITS_TOTAL, "small")
    scheduler.select_backend(session, Tier.SMALL, backends)
    hit_after = _counter_value(AFFINITY_HITS_TOTAL, "small")
    miss_after = _counter_value(AFFINITY_MISSES_TOTAL, "small")

    assert hit_after == hit_before, "Expired binding must not produce a hit"
    assert miss_after - miss_before == 2, (
        "Both calls should be misses when ttl=0: first is always a miss, "
        "second sees an already-expired binding"
    )


def test_thread_safety_concurrent_select_backend():
    # FastAPI runs sync route handlers in a thread pool.  Twenty threads
    # hitting select_backend simultaneously should all complete without
    # exceptions or corrupted state — the RLock in AffinityScheduler is
    # the guard, and this test confirms it actually holds under contention.
    backends = _make_backends(3)
    scheduler, _ = _scheduler_for(backends)

    results: list[BackendInfo] = []
    errors: list[Exception] = []
    # A plain list is sufficient here because CPython's GIL protects
    # list.append() against torn writes; we only need the RLock to protect
    # the scheduler's internal sticky map.
    result_lock = threading.Lock()

    def worker(thread_idx: int) -> None:
        try:
            session = SessionContext(
                session_id=f"concurrent-{thread_idx:03d}", agent_id="a"
            )
            backend, _ = scheduler.select_backend(session, Tier.SMALL, backends)
            with result_lock:
                results.append(backend)
        except Exception as exc:  # noqa: BLE001
            with result_lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent select_backend raised: {errors}"
    assert len(results) == 20
    assert all(isinstance(r, BackendInfo) for r in results)
    assert all(r.id in {b.id for b in backends} for r in results)
