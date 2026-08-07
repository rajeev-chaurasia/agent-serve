from agent_serve.core.enums import (
    AdmissionOutcome,
    BackendStatus,
    HealthProbeResult,
    RequestOutcome,
    RoutingReason,
    Tier,
)


def test_tier_values():
    assert Tier.SMALL == "small"
    assert Tier.BIG == "big"
    assert Tier.AUTO == "auto"
    assert Tier("small") == Tier.SMALL


def test_backend_status_values():
    assert BackendStatus.HEALTHY == "healthy"
    assert BackendStatus.DOWN == "down"


def test_routing_reason_values():
    reasons = {r.value for r in RoutingReason}
    assert "tier_hint" in reasons
    assert "classifier" in reasons
    assert "fallback" in reasons


def test_request_outcome_completeness():
    # Every outcome must have a value that doesn't collide
    values = [o.value for o in RequestOutcome]
    assert len(values) == len(set(values))


def test_str_enum_comparison():
    assert Tier.SMALL == "small"
    assert Tier.BIG == "big"


def test_admission_outcome_values():
    outcomes = {o.value for o in AdmissionOutcome}
    assert "allowed" in outcomes
    assert "budget_exceeded" in outcomes
    assert "queue_full" in outcomes
    assert "backend_down" in outcomes


def test_health_probe_result_values():
    results = {r.value for r in HealthProbeResult}
    assert "ok" in results
    assert "timeout" in results
    assert "error" in results


def test_backend_status_degraded():
    assert BackendStatus.DEGRADED == "degraded"


def test_tier_is_str_subclass():
    # StrEnum members should compare equal to plain strings
    assert isinstance(Tier.SMALL, str)
    assert isinstance(Tier.BIG, str)
    assert isinstance(Tier.AUTO, str)


def test_routing_reason_tool_followup():
    assert RoutingReason.TOOL_FOLLOWUP == "tool_followup"


def test_routing_reason_prompt_length():
    assert RoutingReason.PROMPT_LENGTH == "prompt_length"


def test_request_outcome_values_exist():
    values = {o.value for o in RequestOutcome}
    assert "success" in values
    assert "upstream_error" in values
    assert "gateway_error" in values
    assert "budget_rejected" in values
    assert "queue_rejected" in values
