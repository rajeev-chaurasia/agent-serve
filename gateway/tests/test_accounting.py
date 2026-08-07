import pytest

from agent_serve.accounting.accountant import TokenAccountant
from agent_serve.config.models import AdmissionConfig


@pytest.fixture
def accountant():
    return TokenAccountant(AdmissionConfig(
        default_token_budget=1000,
        budget_window_seconds=5,
    ))


def test_initial_budget_available(accountant):
    assert accountant.check_budget("agent-1", 500) is True


def test_budget_exceeded(accountant):
    accountant.debit("agent-1", 800, 200)  # uses 1000 tokens
    assert accountant.check_budget("agent-1", 1) is False


def test_budget_respected_under_limit(accountant):
    accountant.debit("agent-1", 300, 100)  # uses 400
    assert accountant.check_budget("agent-1", 500) is True
    assert accountant.check_budget("agent-1", 601) is False


def test_separate_agents_independent(accountant):
    accountant.debit("agent-1", 900, 100)
    assert accountant.check_budget("agent-1", 1) is False
    assert accountant.check_budget("agent-2", 1000) is True


def test_get_usage_returns_correct_fields(accountant):
    accountant.debit("agent-x", 200, 50)
    usage = accountant.get_usage("agent-x")
    assert usage["agent_id"] == "agent-x"
    assert usage["tokens_used"] == 250
    assert usage["budget"] == 1000


def test_debit_accumulates_across_calls(accountant):
    accountant.debit("agent-2", 100, 50)
    accountant.debit("agent-2", 200, 100)
    usage = accountant.get_usage("agent-2")
    assert usage["tokens_used"] == 450


def test_check_budget_exact_limit(accountant):
    # Using exactly the budget should be allowed
    assert accountant.check_budget("agent-3", 1000) is True
    # One more than the budget should be rejected
    assert accountant.check_budget("agent-3", 1001) is False


def test_zero_tokens_always_allowed(accountant):
    accountant.debit("agent-4", 999, 0)
    assert accountant.check_budget("agent-4", 0) is True


def test_get_usage_unknown_agent_returns_zero(accountant):
    usage = accountant.get_usage("never-seen")
    assert usage["tokens_used"] == 0
    assert usage["budget"] == 1000


def test_window_seconds_in_usage(accountant):
    accountant.debit("agent-5", 10, 5)
    usage = accountant.get_usage("agent-5")
    assert usage["window_seconds"] == 5


def test_multiple_agents_track_independently(accountant):
    accountant.debit("agent-a", 600, 0)
    accountant.debit("agent-b", 200, 0)
    assert accountant.check_budget("agent-a", 401) is False
    assert accountant.check_budget("agent-b", 799) is True
    assert accountant.check_budget("agent-b", 801) is False
