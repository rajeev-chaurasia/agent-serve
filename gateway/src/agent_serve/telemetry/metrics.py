"""
Module-level Prometheus metric constants for agent-serve.

All metrics are registered against the default prometheus_client REGISTRY so
that make_asgi_app() exposes them on the /metrics endpoint without any
additional wiring.  Import these constants directly; never instantiate new
metrics in other modules — that would produce duplicate-registration errors
and split the data across registries.
"""

from prometheus_client import Counter, Histogram, Gauge

# ---------------------------------------------------------------------------
# Request-level counters and latency histograms
# ---------------------------------------------------------------------------

REQUESTS_TOTAL = Counter(
    "agent_serve_requests_total",
    "Total requests processed",
    ["tier", "backend", "outcome"],
)

TTFT_SECONDS = Histogram(
    "agent_serve_ttft_seconds",
    "Time to first token, in seconds",
    ["tier", "backend"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

E2E_SECONDS = Histogram(
    "agent_serve_e2e_seconds",
    "End-to-end request duration, in seconds",
    ["tier", "backend"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)

# ---------------------------------------------------------------------------
# Admission-queue metrics
# ---------------------------------------------------------------------------

QUEUE_WAIT_SECONDS = Histogram(
    "agent_serve_queue_wait_seconds",
    "Time spent waiting in the admission queue, in seconds",
    ["tier"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)

QUEUE_DEPTH = Gauge(
    "agent_serve_queue_depth",
    "Current number of requests waiting in queue",
    ["tier"],
)

# ---------------------------------------------------------------------------
# Token accounting
# ---------------------------------------------------------------------------

TOKENS_TOTAL = Counter(
    "agent_serve_tokens_total",
    "Total tokens processed",
    # direction distinguishes prompt tokens from completion tokens so callers
    # can compute cost and ratio without a secondary breakdown metric.
    ["direction", "tier"],  # direction: "prompt" | "completion"
)

# ---------------------------------------------------------------------------
# Session-affinity routing
# ---------------------------------------------------------------------------

AFFINITY_HITS_TOTAL = Counter(
    "agent_serve_affinity_hits_total",
    "Requests routed to the session-sticky backend",
    ["tier"],
)

AFFINITY_MISSES_TOTAL = Counter(
    "agent_serve_affinity_misses_total",
    "Requests that could not be routed to the session-sticky backend",
    ["tier"],
)

AFFINITY_BROKEN_TOTAL = Counter(
    "agent_serve_affinity_broken_total",
    "Session-backend bindings broken due to backend going down",
    ["tier"],
)

# ---------------------------------------------------------------------------
# Backend health
# ---------------------------------------------------------------------------

BACKEND_UP = Gauge(
    "agent_serve_backend_up",
    "1 if backend is healthy, 0 otherwise",
    ["backend", "tier"],
)

# ---------------------------------------------------------------------------
# Budget enforcement
# ---------------------------------------------------------------------------

BUDGET_REJECTS_TOTAL = Counter(
    "agent_serve_budget_rejects_total",
    "Requests rejected due to token budget exhaustion",
    ["agent_id"],
)
