from agent_serve.backends.registry import BackendRegistry
from agent_serve.core.enums import BackendStatus, Tier


def test_get_healthy_backends_filters_by_tier(gateway_config):
    registry = BackendRegistry(gateway_config)
    small = registry.get_healthy_backends(Tier.SMALL)
    big = registry.get_healthy_backends(Tier.BIG)
    assert all(b.tier == Tier.SMALL for b in small)
    assert all(b.tier == Tier.BIG for b in big)


def test_mark_down_removes_from_healthy(gateway_config, small_backend):
    registry = BackendRegistry(gateway_config)
    assert len(registry.get_healthy_backends(Tier.SMALL)) == 1
    registry.mark_status(small_backend.id, BackendStatus.DOWN)
    assert len(registry.get_healthy_backends(Tier.SMALL)) == 0


def test_mark_up_restores_to_healthy(gateway_config, small_backend):
    registry = BackendRegistry(gateway_config)
    registry.mark_status(small_backend.id, BackendStatus.DOWN)
    registry.mark_status(small_backend.id, BackendStatus.HEALTHY)
    assert len(registry.get_healthy_backends(Tier.SMALL)) == 1


def test_get_backend_by_id(gateway_config, small_backend):
    registry = BackendRegistry(gateway_config)
    b = registry.get_backend(small_backend.id)
    assert b is not None
    assert b.id == small_backend.id


def test_get_backend_unknown_id(gateway_config):
    registry = BackendRegistry(gateway_config)
    assert registry.get_backend("nonexistent") is None


def test_all_backends_returns_all(gateway_config):
    registry = BackendRegistry(gateway_config)
    all_b = registry.all_backends()
    assert len(all_b) == 2


def test_initial_state_all_healthy(gateway_config):
    registry = BackendRegistry(gateway_config)
    small = registry.get_healthy_backends(Tier.SMALL)
    big = registry.get_healthy_backends(Tier.BIG)
    assert len(small) == 1
    assert len(big) == 1


def test_mark_status_unknown_backend_is_noop(gateway_config):
    registry = BackendRegistry(gateway_config)
    # Should not raise
    registry.mark_status("does-not-exist", BackendStatus.DOWN)
    assert len(registry.all_backends()) == 2


def test_marking_degraded_excludes_from_healthy(gateway_config, big_backend):
    registry = BackendRegistry(gateway_config)
    registry.mark_status(big_backend.id, BackendStatus.DEGRADED)
    # Degraded backends are not HEALTHY, so should not appear in healthy list
    healthy = registry.get_healthy_backends(Tier.BIG)
    assert len(healthy) == 0


def test_both_down_returns_empty_for_each_tier(gateway_config, small_backend, big_backend):
    registry = BackendRegistry(gateway_config)
    registry.mark_status(small_backend.id, BackendStatus.DOWN)
    registry.mark_status(big_backend.id, BackendStatus.DOWN)
    assert registry.get_healthy_backends(Tier.SMALL) == []
    assert registry.get_healthy_backends(Tier.BIG) == []


def test_backend_tier_preserved_after_status_change(gateway_config, small_backend):
    registry = BackendRegistry(gateway_config)
    registry.mark_status(small_backend.id, BackendStatus.DOWN)
    registry.mark_status(small_backend.id, BackendStatus.HEALTHY)
    b = registry.get_backend(small_backend.id)
    assert b is not None
    assert b.tier == Tier.SMALL


def test_get_healthy_returns_correct_urls(gateway_config, small_backend):
    registry = BackendRegistry(gateway_config)
    healthy = registry.get_healthy_backends(Tier.SMALL)
    assert len(healthy) == 1
    assert healthy[0].base_url == small_backend.base_url
