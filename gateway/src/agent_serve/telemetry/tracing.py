"""
OpenTelemetry tracer setup and span-context helpers for agent-serve.

Call setup_tracing() once at application start (from the lifespan handler).
All other modules obtain a tracer via get_tracer() and open named spans with
the context-manager helpers below; they never construct TracerProvider or
OTLPSpanExporter themselves.
"""

from contextlib import contextmanager
from typing import Generator

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from ..config.models import TelemetryConfig

# Module-level tracer; initialised by setup_tracing().  The fallback in
# get_tracer() returns a no-op tracer so code that runs before setup_tracing()
# (e.g. during unit tests) does not raise.
_tracer: trace.Tracer | None = None


def setup_tracing(config: TelemetryConfig) -> None:
    """Initialise the global OTel provider and wire up OTLP export.

    Must be called exactly once, before the first request is served.
    """
    global _tracer
    provider = TracerProvider()
    exporter = OTLPSpanExporter(endpoint=config.otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("agent_serve")


def get_tracer() -> trace.Tracer:
    """Return the shared tracer, falling back to the OTel no-op tracer."""
    if _tracer is None:
        return trace.get_tracer("agent_serve")
    return _tracer


# ---------------------------------------------------------------------------
# Named span helpers
# Each helper yields the live Span so callers can attach extra attributes or
# record events without coupling them to the OTel API directly.
# ---------------------------------------------------------------------------

@contextmanager
def admission_span(session_id: str) -> Generator[trace.Span, None, None]:
    """Span covering the entire admission-queue phase for one request."""
    with get_tracer().start_as_current_span("admission") as span:
        span.set_attribute("session.id", session_id)
        yield span


@contextmanager
def route_span(session_id: str, tier: str) -> Generator[trace.Span, None, None]:
    """Span covering backend selection and affinity resolution."""
    with get_tracer().start_as_current_span("route") as span:
        span.set_attribute("session.id", session_id)
        span.set_attribute("route.tier", tier)
        yield span


@contextmanager
def backend_call_span(
    backend_id: str, streaming: bool
) -> Generator[trace.Span, None, None]:
    """Span covering the proxied call to an upstream backend.

    streaming=True signals that TTFT should be recorded as an event on
    this span rather than waiting for the response to close.
    """
    with get_tracer().start_as_current_span("backend_call") as span:
        span.set_attribute("backend.id", backend_id)
        span.set_attribute("backend.streaming", streaming)
        yield span


def instrument_app(app) -> None:
    """Attach the FastAPI auto-instrumentation to *app*.

    Wraps FastAPIInstrumentor so the rest of the codebase does not import from
    opentelemetry.instrumentation directly.
    """
    FastAPIInstrumentor.instrument_app(app)
