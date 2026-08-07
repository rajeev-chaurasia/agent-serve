from agent_serve.backends.registry import BackendRegistry
from agent_serve.config.models import RoutingConfig
from agent_serve.core.enums import RoutingReason, Tier
from agent_serve.core.models import SessionContext
from agent_serve.routing.rules import RuleBasedRouter


def _make_registry(gateway_config):
    return BackendRegistry(gateway_config)


def test_tier_hint_takes_priority(gateway_config, session):
    registry = _make_registry(gateway_config)
    router = RuleBasedRouter(RoutingConfig(), registry)
    session_with_hint = session.model_copy(update={"tier_hint": Tier.BIG})
    result = router.select_tier(session_with_hint, [{"role": "user", "content": "hi"}], None)
    assert result is not None
    tier, reason = result
    assert tier == Tier.BIG
    assert reason == RoutingReason.TIER_HINT


def test_long_prompt_routes_to_big(gateway_config, session):
    registry = _make_registry(gateway_config)
    config = RoutingConfig(prompt_length_threshold=100)
    router = RuleBasedRouter(config, registry)
    long_msg = [{"role": "user", "content": "x" * 200}]
    result = router.select_tier(session, long_msg, None)
    assert result is not None
    tier, reason = result
    assert tier == Tier.BIG
    assert reason == RoutingReason.PROMPT_LENGTH


def test_short_prompt_returns_none(gateway_config, session):
    registry = _make_registry(gateway_config)
    config = RoutingConfig(prompt_length_threshold=1000)
    router = RuleBasedRouter(config, registry)
    short_msg = [{"role": "user", "content": "hi"}]
    result = router.select_tier(session, short_msg, None)
    assert result is None


def test_auto_hint_does_not_force_tier(gateway_config, session):
    registry = _make_registry(gateway_config)
    router = RuleBasedRouter(RoutingConfig(prompt_length_threshold=1000), registry)
    session_auto = session.model_copy(update={"tier_hint": Tier.AUTO})
    result = router.select_tier(session_auto, [{"role": "user", "content": "short"}], None)
    assert result is None


def test_small_hint_routes_to_small(gateway_config, session):
    registry = _make_registry(gateway_config)
    router = RuleBasedRouter(RoutingConfig(), registry)
    session_small = session.model_copy(update={"tier_hint": Tier.SMALL})
    result = router.select_tier(session_small, [{"role": "user", "content": "hi"}], None)
    assert result is not None
    tier, reason = result
    assert tier == Tier.SMALL
    assert reason == RoutingReason.TIER_HINT


def test_hint_takes_priority_over_long_prompt(gateway_config, session):
    registry = _make_registry(gateway_config)
    router = RuleBasedRouter(RoutingConfig(prompt_length_threshold=10), registry)
    # Explicit SMALL hint even with a long message should win
    session_small = session.model_copy(update={"tier_hint": Tier.SMALL})
    long_msg = [{"role": "user", "content": "x" * 100}]
    result = router.select_tier(session_small, long_msg, None)
    assert result is not None
    tier, reason = result
    assert tier == Tier.SMALL
    assert reason == RoutingReason.TIER_HINT


def test_tool_followup_routes_to_assigned_tier(gateway_config):
    registry = _make_registry(gateway_config)
    config = RoutingConfig(tool_followup_stays_same_tier=True, prompt_length_threshold=10000)
    router = RuleBasedRouter(config, registry)
    session_with_backend = SessionContext(
        session_id="s1",
        agent_id="a1",
        tier_hint=Tier.AUTO,
        assigned_backend_id="small-0",
    )
    tool_followup_msgs = [{"role": "tool", "content": "result"}]
    result = router.select_tier(session_with_backend, tool_followup_msgs, None)
    assert result is not None
    tier, reason = result
    assert reason == RoutingReason.TOOL_FOLLOWUP
    assert tier == Tier.SMALL


def test_tool_followup_disabled_falls_through(gateway_config, session):
    registry = _make_registry(gateway_config)
    config = RoutingConfig(tool_followup_stays_same_tier=False, prompt_length_threshold=10000)
    router = RuleBasedRouter(config, registry)
    session_with_backend = session.model_copy(update={"assigned_backend_id": "small-0"})
    tool_followup_msgs = [{"role": "tool", "content": "result"}]
    # With followup disabled and short message, should return None
    result = router.select_tier(session_with_backend, tool_followup_msgs, None)
    assert result is None


def test_empty_messages_returns_none(gateway_config, session):
    registry = _make_registry(gateway_config)
    router = RuleBasedRouter(RoutingConfig(prompt_length_threshold=1000), registry)
    result = router.select_tier(session, [], None)
    assert result is None


def test_prompt_length_exact_threshold_does_not_trigger(gateway_config, session):
    registry = _make_registry(gateway_config)
    config = RoutingConfig(prompt_length_threshold=100)
    router = RuleBasedRouter(config, registry)
    # Exactly 100 chars — threshold is `> threshold`, so 100 should not trigger
    msg = [{"role": "user", "content": "a" * 100}]
    result = router.select_tier(session, msg, None)
    assert result is None


def test_prompt_length_one_over_threshold_triggers(gateway_config, session):
    registry = _make_registry(gateway_config)
    config = RoutingConfig(prompt_length_threshold=100)
    router = RuleBasedRouter(config, registry)
    msg = [{"role": "user", "content": "a" * 101}]
    result = router.select_tier(session, msg, None)
    assert result is not None
    tier, reason = result
    assert tier == Tier.BIG
    assert reason == RoutingReason.PROMPT_LENGTH
