from ..backends.protocols import BackendRegistryProtocol
from ..config.models import RoutingConfig
from ..core.enums import RoutingReason, Tier
from ..core.models import SessionContext


class RuleBasedRouter:
    """Applies cheap, deterministic rules to select a tier without any model call.

    Returns None if no rule fires, signalling the caller should try the classifier.
    """

    def __init__(self, config: RoutingConfig, registry: BackendRegistryProtocol) -> None:
        self._config = config
        self._registry = registry

    def select_tier(
        self,
        session: SessionContext,
        messages: list[dict],
        tools: list | None,
    ) -> tuple[Tier, RoutingReason] | None:
        # Explicit hint takes highest priority
        if session.tier_hint != Tier.AUTO:
            return session.tier_hint, RoutingReason.TIER_HINT

        # Tool-call followup: the last message is a tool result — keep the same tier
        if (
            self._config.tool_followup_stays_same_tier
            and session.assigned_backend_id is not None
            and messages
            and messages[-1].get("role") == "tool"
        ):
            assigned = self._registry.get_backend(session.assigned_backend_id)
            if assigned is not None:
                return assigned.tier, RoutingReason.TOOL_FOLLOWUP

        # Long prompt → big tier
        total_chars = sum(len(m.get("content") or "") for m in messages)
        if total_chars > self._config.prompt_length_threshold:
            return Tier.BIG, RoutingReason.PROMPT_LENGTH

        return None
