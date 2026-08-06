import pytest
from pathlib import Path
from agent_serve.core.enums import Tier, BackendStatus
from agent_serve.core.models import BackendInfo, SessionContext
from agent_serve.config.models import (
    GatewayConfig, BackendConfig, AdmissionConfig,
    RoutingConfig, AffinityConfig, HealthConfig, TelemetryConfig,
)


@pytest.fixture
def small_backend():
    return BackendInfo(
        id="small-0", tier=Tier.SMALL, base_url="http://localhost:8002",
        gpu=0, max_inflight=64,
    )


@pytest.fixture
def big_backend():
    return BackendInfo(
        id="big-0", tier=Tier.BIG, base_url="http://localhost:8001",
        gpu=1, max_inflight=32,
    )


@pytest.fixture
def session():
    return SessionContext(session_id="test-session-001", agent_id="test-agent")


@pytest.fixture
def gateway_config(small_backend, big_backend):
    return GatewayConfig(
        backends=[
            BackendConfig(id=small_backend.id, tier=Tier.SMALL,
                         base_url=small_backend.base_url, gpu=0, max_inflight=64),
            BackendConfig(id=big_backend.id, tier=Tier.BIG,
                         base_url=big_backend.base_url, gpu=1, max_inflight=32),
        ],
        admission=AdmissionConfig(default_token_budget=1000, budget_window_seconds=60,
                                  max_queue_size=10, queue_timeout_seconds=2),
        routing=RoutingConfig(prompt_length_threshold=500, classifier_cache_ttl_seconds=30),
        affinity=AffinityConfig(sticky_ttl_seconds=300),
    )
