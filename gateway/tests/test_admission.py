import asyncio
import pytest
from agent_serve.admission.controller import AdmissionController
from agent_serve.admission.queue import BackpressureQueue
from agent_serve.core.enums import Tier, BackendStatus
from agent_serve.core.exceptions import BudgetExceededException, BackendUnavailableException
from agent_serve.config.models import AdmissionConfig
from agent_serve.accounting.accountant import TokenAccountant
from agent_serve.backends.registry import BackendRegistry


@pytest.mark.asyncio
async def test_gate_allows_under_budget(gateway_config, session):
    accountant = TokenAccountant(gateway_config.admission)
    registry = BackendRegistry(gateway_config)
    ctrl = AdmissionController(gateway_config.admission, accountant, registry)
    await ctrl.gate(session, Tier.SMALL, 100)
    ctrl.release(session, Tier.SMALL)


@pytest.mark.asyncio
async def test_gate_rejects_over_budget(gateway_config, session):
    tight_admission = AdmissionConfig(
        default_token_budget=50,
        budget_window_seconds=60,
        max_queue_size=10,
        queue_timeout_seconds=2,
    )
    accountant = TokenAccountant(tight_admission)
    registry = BackendRegistry(gateway_config)
    ctrl = AdmissionController(tight_admission, accountant, registry)
    accountant.debit(session.agent_id, 50, 0)
    with pytest.raises(BudgetExceededException):
        await ctrl.gate(session, Tier.SMALL, 10)


@pytest.mark.asyncio
async def test_gate_rejects_no_healthy_backends(gateway_config, session):
    accountant = TokenAccountant(gateway_config.admission)
    registry = BackendRegistry(gateway_config)
    registry.mark_status("small-0", BackendStatus.DOWN)
    ctrl = AdmissionController(gateway_config.admission, accountant, registry)
    with pytest.raises(BackendUnavailableException):
        await ctrl.gate(session, Tier.SMALL, 10)


@pytest.mark.asyncio
async def test_backpressure_queue_raises_when_full():
    from agent_serve.core.exceptions import QueueFullException
    # max_inflight=1 means one concurrent slot; max_queue=1 allows one waiter.
    # A very short timeout ensures the waiting request is rejected quickly.
    q = BackpressureQueue(max_inflight=1, max_queue=1, timeout_seconds=0.01, tier="small")
    await q.acquire()  # takes the one inflight slot
    with pytest.raises(QueueFullException):
        await q.acquire()  # enters wait queue, times out, raises QueueFullException
    q.release()


@pytest.mark.asyncio
async def test_gate_and_release_cycle_allows_next_request(gateway_config, session):
    accountant = TokenAccountant(gateway_config.admission)
    registry = BackendRegistry(gateway_config)
    ctrl = AdmissionController(gateway_config.admission, accountant, registry)
    await ctrl.gate(session, Tier.SMALL, 50)
    ctrl.release(session, Tier.SMALL)
    # Should be admittable again after release
    await ctrl.gate(session, Tier.SMALL, 50)
    ctrl.release(session, Tier.SMALL)


@pytest.mark.asyncio
async def test_gate_big_tier(gateway_config, session):
    accountant = TokenAccountant(gateway_config.admission)
    registry = BackendRegistry(gateway_config)
    ctrl = AdmissionController(gateway_config.admission, accountant, registry)
    await ctrl.gate(session, Tier.BIG, 100)
    ctrl.release(session, Tier.BIG)


@pytest.mark.asyncio
async def test_release_without_gate_is_noop(gateway_config, session):
    accountant = TokenAccountant(gateway_config.admission)
    registry = BackendRegistry(gateway_config)
    ctrl = AdmissionController(gateway_config.admission, accountant, registry)
    # Release without a prior gate should not raise
    ctrl.release(session, Tier.SMALL)


@pytest.mark.asyncio
async def test_budget_rejection_message_contains_agent_id(gateway_config, session):
    tight = AdmissionConfig(
        default_token_budget=10,
        budget_window_seconds=60,
        max_queue_size=10,
        queue_timeout_seconds=2,
    )
    accountant = TokenAccountant(tight)
    registry = BackendRegistry(gateway_config)
    ctrl = AdmissionController(tight, accountant, registry)
    accountant.debit(session.agent_id, 10, 0)
    with pytest.raises(BudgetExceededException) as exc_info:
        await ctrl.gate(session, Tier.SMALL, 5)
    assert session.agent_id in str(exc_info.value)


@pytest.mark.asyncio
async def test_backend_unavailable_exception_carries_tier(gateway_config, session):
    accountant = TokenAccountant(gateway_config.admission)
    registry = BackendRegistry(gateway_config)
    registry.mark_status("big-0", BackendStatus.DOWN)
    ctrl = AdmissionController(gateway_config.admission, accountant, registry)
    with pytest.raises(BackendUnavailableException) as exc_info:
        await ctrl.gate(session, Tier.BIG, 10)
    assert exc_info.value.tier == Tier.BIG


@pytest.mark.asyncio
async def test_backpressure_queue_acquire_returns_float():
    q = BackpressureQueue(max_inflight=2, max_queue=5, timeout_seconds=1.0, tier="small")
    wait = await q.acquire()
    assert isinstance(wait, float)
    q.release()
