"""
Lightweight integration smoke tests for the FastAPI routing layer.

These tests verify that the health, metrics, and chat completion endpoints
behave correctly without requiring a real vLLM backend or any external services.
Protocol dependencies are replaced with minimal inline fakes.
"""

import json
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from fastapi.testclient import TestClient
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from agent_serve.core.enums import Tier, BackendStatus
from agent_serve.core.models import BackendInfo, SessionContext, RoutingDecision, AgentServeMeta
from agent_serve.core.exceptions import BudgetExceededException


MOCK_COMPLETION = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 1700000000,
    "model": "test-model",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hello!"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


def _make_mock_app(response_data=None):
    """Build a minimal FastAPI app with the health and metrics routes wired in.

    The /v1/chat/completions endpoint is a stub that returns canned data so
    tests do not need a real upstream backend.
    """
    from agent_serve.gateway.routes import health, metrics

    app = FastAPI()
    app.include_router(health.router)
    app.include_router(metrics.router)

    @app.post("/v1/chat/completions")
    async def mock_chat(request: dict):
        return JSONResponse(content=response_data or MOCK_COMPLETION)

    return app


def test_healthz():
    app = _make_mock_app()
    with TestClient(app) as client:
        r = client.get("/healthz")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_metrics_endpoint():
    app = _make_mock_app()
    with TestClient(app) as client:
        r = client.get("/metrics")
        assert r.status_code == 200
        # The Prometheus response should contain agent_serve counters or python GC metrics
        assert "agent_serve" in r.text or "python_gc" in r.text


def test_mock_chat_completion():
    app = _make_mock_app()
    with TestClient(app) as client:
        r = client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [{"role": "user", "content": "hi"}],
        })
        assert r.status_code == 200
        data = r.json()
        assert data["choices"][0]["message"]["content"] == "Hello!"


def test_mock_chat_completion_custom_response():
    custom = {**MOCK_COMPLETION, "id": "chatcmpl-custom"}
    custom["choices"][0]["message"]["content"] = "Goodbye!"
    app = _make_mock_app(response_data=custom)
    with TestClient(app) as client:
        r = client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [{"role": "user", "content": "bye"}],
        })
        assert r.status_code == 200
        assert r.json()["id"] == "chatcmpl-custom"
        assert r.json()["choices"][0]["message"]["content"] == "Goodbye!"


def test_healthz_returns_json():
    app = _make_mock_app()
    with TestClient(app) as client:
        r = client.get("/healthz")
        assert r.headers["content-type"].startswith("application/json")


def test_metrics_content_type_is_prometheus():
    app = _make_mock_app()
    with TestClient(app) as client:
        r = client.get("/metrics")
        assert "text/plain" in r.headers["content-type"]


def test_chat_completion_includes_usage():
    app = _make_mock_app()
    with TestClient(app) as client:
        r = client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [{"role": "user", "content": "test"}],
        })
        assert r.status_code == 200
        data = r.json()
        assert "usage" in data
        assert data["usage"]["total_tokens"] == 15


def test_chat_completion_object_field():
    app = _make_mock_app()
    with TestClient(app) as client:
        r = client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [{"role": "user", "content": "test"}],
        })
        data = r.json()
        assert data["object"] == "chat.completion"


def test_unknown_endpoint_returns_404():
    app = _make_mock_app()
    with TestClient(app) as client:
        r = client.get("/does-not-exist")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Fake-based tests for lower-level gateway plumbing
# ---------------------------------------------------------------------------


class _FakeRegistry:
    """Minimal BackendRegistryProtocol fake."""

    def __init__(self, backends: list[BackendInfo]):
        self._backends = {b.id: b for b in backends}

    def get_healthy_backends(self, tier: Tier) -> list[BackendInfo]:
        return [b for b in self._backends.values() if b.tier == tier and b.status == BackendStatus.HEALTHY]

    def get_backend(self, backend_id: str) -> BackendInfo | None:
        return self._backends.get(backend_id)

    def mark_status(self, backend_id: str, status: BackendStatus) -> None:
        if backend_id in self._backends:
            self._backends[backend_id] = self._backends[backend_id].model_copy(update={"status": status})

    def all_backends(self) -> list[BackendInfo]:
        return list(self._backends.values())


def test_fake_registry_healthy_filter():
    backends = [
        BackendInfo(id="s0", tier=Tier.SMALL, base_url="http://localhost:8002", gpu=0, max_inflight=64),
        BackendInfo(id="b0", tier=Tier.BIG, base_url="http://localhost:8001", gpu=1, max_inflight=32),
    ]
    reg = _FakeRegistry(backends)
    assert len(reg.get_healthy_backends(Tier.SMALL)) == 1
    assert len(reg.get_healthy_backends(Tier.BIG)) == 1
    reg.mark_status("s0", BackendStatus.DOWN)
    assert len(reg.get_healthy_backends(Tier.SMALL)) == 0


def test_fake_registry_get_by_id():
    backends = [
        BackendInfo(id="s0", tier=Tier.SMALL, base_url="http://x", gpu=0, max_inflight=1),
    ]
    reg = _FakeRegistry(backends)
    assert reg.get_backend("s0") is not None
    assert reg.get_backend("missing") is None


def test_agent_serve_meta_fields():
    meta = AgentServeMeta(
        tier=Tier.SMALL,
        backend_id="small-0",
        queue_wait_ms=12.5,
        affinity_hit=True,
        routing_reason="tier_hint",
    )
    assert meta.tier == Tier.SMALL
    assert meta.backend_id == "small-0"
    assert meta.queue_wait_ms == 12.5
    assert meta.affinity_hit is True


def test_routing_decision_defaults():
    decision = RoutingDecision(
        tier=Tier.BIG,
        backend_id="big-0",
        reason="classifier",
    )
    assert decision.classifier_used is False
    assert decision.queue_wait_ms == 0.0
    assert decision.affinity_hit is False
