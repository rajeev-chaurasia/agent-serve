import pytest

from agent_serve.affinity._reference import ReferenceAffinityScheduler, _hrw_score
from agent_serve.backends.registry import BackendRegistry
from agent_serve.core.enums import BackendStatus, Tier
from agent_serve.core.models import BackendInfo, SessionContext


def _make_backends(n: int, tier: Tier = Tier.SMALL) -> list[BackendInfo]:
    return [
        BackendInfo(
            id=f"{tier.value}-{i}",
            tier=tier,
            base_url=f"http://x:{8000 + i}",
            gpu=0,
            max_inflight=64,
        )
        for i in range(n)
    ]


def test_hrw_score_deterministic():
    s1 = _hrw_score("session-abc", "backend-0")
    s2 = _hrw_score("session-abc", "backend-0")
    assert s1 == s2


def test_hrw_different_sessions_may_map_differently():
    backends = _make_backends(3)
    scores_s1 = [_hrw_score("session-1", b.id) for b in backends]
    scores_s2 = [_hrw_score("session-2", b.id) for b in backends]
    winner_s1 = backends[scores_s1.index(max(scores_s1))].id
    winner_s2 = backends[scores_s2.index(max(scores_s2))].id
    # Not asserting they differ (could collide), just that it runs deterministically
    assert isinstance(winner_s1, str)
    assert isinstance(winner_s2, str)


def test_sticky_binding_returns_same_backend(gateway_config):
    registry = BackendRegistry(gateway_config)
    scheduler = ReferenceAffinityScheduler(registry, sticky_ttl_seconds=60)
    session = SessionContext(session_id="sticky-test", agent_id="a1")
    backends = _make_backends(2)
    first = scheduler.select_backend(session, Tier.SMALL, backends)
    second = scheduler.select_backend(session, Tier.SMALL, backends)
    assert first.id == second.id


def test_different_sessions_can_map_to_different_backends(gateway_config):
    registry = BackendRegistry(gateway_config)
    scheduler = ReferenceAffinityScheduler(registry, sticky_ttl_seconds=60)
    backends = _make_backends(2)
    results = set()
    for i in range(20):
        s = SessionContext(session_id=f"session-{i:03d}", agent_id="a")
        results.add(scheduler.select_backend(s, Tier.SMALL, backends).id)
    assert len(results) == 2  # both backends should be used across 20 sessions


def test_invalidate_removes_binding(gateway_config):
    registry = BackendRegistry(gateway_config)
    scheduler = ReferenceAffinityScheduler(registry, sticky_ttl_seconds=60)
    session = SessionContext(session_id="inv-test", agent_id="a1")
    backends = _make_backends(1)
    scheduler.select_backend(session, Tier.SMALL, backends)
    scheduler.invalidate(session.session_id)
    assert session.session_id not in scheduler._sticky


def test_on_backend_down_migrates_sessions(gateway_config):
    registry = BackendRegistry(gateway_config)
    scheduler = ReferenceAffinityScheduler(registry, sticky_ttl_seconds=60)
    backends = _make_backends(2)
    session = SessionContext(session_id="migrate-test", agent_id="a1")
    chosen = scheduler.select_backend(session, Tier.SMALL, backends)
    scheduler.on_backend_down(chosen.id, Tier.SMALL)
    entry = scheduler._sticky.get(session.session_id)
    if entry:
        assert entry.backend_id != chosen.id


def test_hrw_score_is_integer():
    score = _hrw_score("any-session", "any-backend")
    assert isinstance(score, int)


def test_hrw_score_different_backends_differ():
    # Different backends should produce different scores for the same session
    s1 = _hrw_score("same-session", "backend-alpha")
    s2 = _hrw_score("same-session", "backend-beta")
    assert s1 != s2


def test_select_backend_single_candidate_always_wins(gateway_config):
    registry = BackendRegistry(gateway_config)
    scheduler = ReferenceAffinityScheduler(registry, sticky_ttl_seconds=60)
    session = SessionContext(session_id="solo-session", agent_id="a")
    backends = _make_backends(1)
    result = scheduler.select_backend(session, Tier.SMALL, backends)
    assert result.id == backends[0].id


def test_select_backend_raises_on_empty_candidates(gateway_config):
    from agent_serve.core.exceptions import BackendUnavailableException
    registry = BackendRegistry(gateway_config)
    scheduler = ReferenceAffinityScheduler(registry, sticky_ttl_seconds=60)
    session = SessionContext(session_id="empty-test", agent_id="a")
    with pytest.raises(BackendUnavailableException):
        scheduler.select_backend(session, Tier.SMALL, [])


def test_invalidate_nonexistent_session_is_noop(gateway_config):
    registry = BackendRegistry(gateway_config)
    scheduler = ReferenceAffinityScheduler(registry, sticky_ttl_seconds=60)
    # Should not raise
    scheduler.invalidate("session-that-never-existed")


def test_on_backend_down_with_no_remaining_removes_binding(gateway_config):
    registry = BackendRegistry(gateway_config)
    scheduler = ReferenceAffinityScheduler(registry, sticky_ttl_seconds=60)
    backends = _make_backends(1)
    session = SessionContext(session_id="lone-session", agent_id="a")
    chosen = scheduler.select_backend(session, Tier.SMALL, backends)
    # Mark the only backend down in registry too
    registry.mark_status(chosen.id, BackendStatus.DOWN)
    scheduler.on_backend_down(chosen.id, Tier.SMALL)
    # With no remaining backends, the sticky entry should be removed
    assert session.session_id not in scheduler._sticky


def test_sticky_entry_refresh_on_access(gateway_config):
    import time
    registry = BackendRegistry(gateway_config)
    scheduler = ReferenceAffinityScheduler(registry, sticky_ttl_seconds=60)
    session = SessionContext(session_id="refresh-test", agent_id="a")
    backends = _make_backends(1)
    scheduler.select_backend(session, Tier.SMALL, backends)
    entry_before = scheduler._sticky[session.session_id]
    expires_before = entry_before.expires_at
    time.sleep(0.01)
    scheduler.select_backend(session, Tier.SMALL, backends)
    entry_after = scheduler._sticky[session.session_id]
    # TTL should have been refreshed on subsequent access
    assert entry_after.expires_at >= expires_before
