import logging
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ...core.enums import RequestOutcome, Tier
from ...core.exceptions import GatewayException
from ...core.models import AgentServeMeta, SessionContext
from ...core.schemas import ChatCompletionRequest
from ...telemetry.metrics import E2E_SECONDS, REQUESTS_TOTAL, TOKENS_TOTAL, TTFT_SECONDS
from ...telemetry.tracing import admission_span, backend_call_span, route_span
from ..dependencies import get_admission, get_affinity, get_proxy, get_registry, get_router

logger = logging.getLogger(__name__)
router = APIRouter()


def _build_session(
    body: ChatCompletionRequest,
    x_session_id: str | None,
    x_agent_id: str | None,
    x_tier_hint: str | None,
) -> SessionContext:
    tier_hint = Tier.AUTO
    if x_tier_hint and x_tier_hint in Tier._value2member_map_:
        tier_hint = Tier(x_tier_hint)
    return SessionContext(
        session_id=x_session_id or str(uuid.uuid4()),
        agent_id=x_agent_id or "anonymous",
        tier_hint=tier_hint,
    )


def _strip_gateway_fields(body: ChatCompletionRequest) -> dict:
    """Return a dict ready to forward to vLLM, with no gateway-only fields."""
    d = body.model_dump(exclude_none=True, by_alias=False)
    for key in ("session_id", "agent_id", "tier_hint", "x_session_id", "x_agent_id", "x_tier_hint"):
        d.pop(key, None)
    return d


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    body: ChatCompletionRequest,
    x_session_id: str | None = Header(None),
    x_agent_id: str | None = Header(None),
    x_tier_hint: str | None = Header(None),
    admission=Depends(get_admission),
    tier_router=Depends(get_router),
    affinity=Depends(get_affinity),
    proxy=Depends(get_proxy),
    registry=Depends(get_registry),
):
    session = _build_session(body, x_session_id, x_agent_id, x_tier_hint)
    messages = [m.model_dump() for m in body.messages]
    estimated_tokens = sum(len(m.get("content") or "") for m in messages) // 4 + 50

    start = time.monotonic()

    try:
        # Stage 1: Route — determine tier and initial backend
        with route_span(session.session_id, session.tier_hint.value):
            decision = await tier_router.route(session, messages, body.tools)

        # Stage 2: Affinity — let the scheduler pick the sticky backend
        candidates = registry.get_healthy_backends(decision.tier)
        backend, affinity_hit = affinity.select_backend(session, decision.tier, candidates)
        decision = decision.model_copy(update={
            "backend_id": backend.id,
            "affinity_hit": affinity_hit,
        })

        # Stage 3: Admission — budget and concurrency gate
        with admission_span(session.session_id):
            await admission.gate(session, decision.tier, estimated_tokens)

        payload = _strip_gateway_fields(body)
        if backend.model:
            payload["model"] = backend.model
        headers = {"Content-Type": "application/json"}
        meta = AgentServeMeta(
            tier=decision.tier,
            backend_id=backend.id,
            queue_wait_ms=decision.queue_wait_ms,
            affinity_hit=decision.affinity_hit,
            routing_reason=decision.reason,
        )

        if body.stream:
            return StreamingResponse(
                _stream(session, backend, payload, headers, meta, proxy, admission, start),
                media_type="text/event-stream",
                headers={
                    "X-Agent-Serve-Tier": decision.tier.value,
                    "X-Agent-Serve-Backend": backend.id,
                },
            )
        else:
            return await _complete(
                session, backend, payload, headers, meta, proxy, admission, start
            )

    except GatewayException as exc:
        REQUESTS_TOTAL.labels(
            tier="unknown", backend="none", outcome=RequestOutcome.BUDGET_REJECTED.value
        ).inc()
        return JSONResponse(
            status_code=exc.status_code, content={"error": {"message": exc.detail}}
        )
    except Exception:
        logger.exception("unhandled error for session %s", session.session_id)
        return JSONResponse(
            status_code=500, content={"error": {"message": "internal gateway error"}}
        )


async def _stream(
    session: SessionContext,
    backend,
    payload: dict,
    headers: dict,
    meta: AgentServeMeta,
    proxy,
    admission,
    start: float,
) -> AsyncIterator[bytes]:
    ttft_recorded = False
    try:
        with backend_call_span(backend.id, streaming=True):
            async for chunk in proxy.stream(backend, "/v1/chat/completions", payload, headers):
                if not ttft_recorded:
                    TTFT_SECONDS.labels(tier=meta.tier.value, backend=backend.id).observe(
                        time.monotonic() - start
                    )
                    ttft_recorded = True
                yield chunk
        E2E_SECONDS.labels(tier=meta.tier.value, backend=backend.id).observe(
            time.monotonic() - start
        )
        REQUESTS_TOTAL.labels(
            tier=meta.tier.value, backend=backend.id, outcome=RequestOutcome.SUCCESS.value
        ).inc()
    except Exception:
        REQUESTS_TOTAL.labels(
            tier=meta.tier.value,
            backend=backend.id,
            outcome=RequestOutcome.UPSTREAM_ERROR.value,
        ).inc()
        yield b"data: [DONE]\n\n"
    finally:
        admission.release(session, meta.tier)


async def _complete(
    session: SessionContext,
    backend,
    payload: dict,
    headers: dict,
    meta: AgentServeMeta,
    proxy,
    admission,
    start: float,
) -> JSONResponse:
    try:
        with backend_call_span(backend.id, streaming=False):
            result = await proxy.call(backend, "/v1/chat/completions", payload, headers)
        elapsed = time.monotonic() - start
        E2E_SECONDS.labels(tier=meta.tier.value, backend=backend.id).observe(elapsed)
        TTFT_SECONDS.labels(tier=meta.tier.value, backend=backend.id).observe(elapsed)
        REQUESTS_TOTAL.labels(
            tier=meta.tier.value, backend=backend.id, outcome=RequestOutcome.SUCCESS.value
        ).inc()
        usage = result.get("usage", {})
        if usage:
            TOKENS_TOTAL.labels(direction="prompt", tier=meta.tier.value).inc(
                usage.get("prompt_tokens", 0)
            )
            TOKENS_TOTAL.labels(direction="completion", tier=meta.tier.value).inc(
                usage.get("completion_tokens", 0)
            )
        result["x_agent_serve"] = meta.model_dump()
        return JSONResponse(content=result)
    except Exception:
        REQUESTS_TOTAL.labels(
            tier=meta.tier.value,
            backend=backend.id,
            outcome=RequestOutcome.UPSTREAM_ERROR.value,
        ).inc()
        return JSONResponse(
            status_code=502, content={"error": {"message": "upstream error"}}
        )
    finally:
        admission.release(session, meta.tier)
