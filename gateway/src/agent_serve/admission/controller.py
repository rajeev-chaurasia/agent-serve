import logging

from ..core.enums import Tier, BackendStatus
from ..core.models import SessionContext
from ..core.exceptions import BudgetExceededException, BackendUnavailableException
from ..config.models import AdmissionConfig
from ..accounting.protocols import AccountantProtocol
from ..backends.protocols import BackendRegistryProtocol
from ..telemetry.metrics import BUDGET_REJECTS_TOTAL
from .queue import BackpressureQueue

logger = logging.getLogger(__name__)


class AdmissionController:
    """Enforces token budgets and per-tier concurrency limits before a request reaches a backend."""

    def __init__(
        self,
        config: AdmissionConfig,
        accountant: AccountantProtocol,
        registry: BackendRegistryProtocol,
    ) -> None:
        self._config = config
        self._accountant = accountant
        self._registry = registry
        # One queue per tier, sized to the aggregate max_inflight of healthy backends.
        self._queues: dict[Tier, BackpressureQueue] = {
            Tier.BIG: BackpressureQueue(
                max_inflight=self._total_inflight(Tier.BIG),
                max_queue=config.max_queue_size,
                timeout_seconds=config.queue_timeout_seconds,
                tier=Tier.BIG.value,
            ),
            Tier.SMALL: BackpressureQueue(
                max_inflight=self._total_inflight(Tier.SMALL),
                max_queue=config.max_queue_size,
                timeout_seconds=config.queue_timeout_seconds,
                tier=Tier.SMALL.value,
            ),
        }
        # Maps session_id → tier so release() knows which semaphore to give back.
        self._held: dict[str, Tier] = {}

    def _total_inflight(self, tier: Tier) -> int:
        backends = self._registry.get_healthy_backends(tier)
        total = sum(b.max_inflight for b in backends)
        return max(total, 1)

    async def gate(self, session: SessionContext, tier: Tier, estimated_tokens: int) -> None:
        # Budget check — fail fast before touching the queue.
        if not self._accountant.check_budget(session.agent_id, estimated_tokens):
            BUDGET_REJECTS_TOTAL.labels(agent_id=session.agent_id).inc()
            usage = self._accountant.get_usage(session.agent_id)
            raise BudgetExceededException(
                agent_id=session.agent_id,
                tokens_used=usage["tokens_used"],
                budget=usage["budget"],
            )
        # Verify at least one healthy backend exists before we queue the caller.
        if not self._registry.get_healthy_backends(tier):
            raise BackendUnavailableException(tier=tier)
        # Acquire a concurrency slot; may block up to queue_timeout_seconds.
        queue = self._queues[tier]
        wait_ms = (await queue.acquire()) * 1000
        self._held[session.session_id] = tier
        logger.debug(
            "admitted session %s tier=%s wait=%.1fms",
            session.session_id,
            tier,
            wait_ms,
        )

    def release(self, session: SessionContext, tier: Tier) -> None:
        held_tier = self._held.pop(session.session_id, None)
        if held_tier is not None:
            self._queues[held_tier].release()
