import logging

from ..core.enums import Tier, RoutingReason
from ..core.models import SessionContext, RoutingDecision
from ..config.models import RoutingConfig
from ..backends.protocols import BackendRegistryProtocol
from .rules import RuleBasedRouter
from .classifier import ClassifierRouter

logger = logging.getLogger(__name__)


class TierRouter:
    """Two-stage tier router: cheap deterministic rules first, classifier second.

    Every routing decision is logged with its reason for the economics study.
    """

    def __init__(
        self,
        config: RoutingConfig,
        registry: BackendRegistryProtocol,
    ) -> None:
        self._registry = registry
        self._rules = RuleBasedRouter(config, registry)
        self._classifier = ClassifierRouter(
            registry, cache_ttl_seconds=config.classifier_cache_ttl_seconds
        )

    async def route(
        self,
        session: SessionContext,
        messages: list[dict],
        tools: list | None,
    ) -> RoutingDecision:
        rule_result = self._rules.select_tier(session, messages, tools)
        if rule_result is not None:
            tier, reason = rule_result
            classifier_used = False
        else:
            tier = await self._classifier.classify(session, messages)
            reason = RoutingReason.CLASSIFIER
            classifier_used = True

        # Pick first healthy backend for the chosen tier; fall back to opposite tier
        backends = self._registry.get_healthy_backends(tier)
        if not backends:
            fallback = Tier.BIG if tier == Tier.SMALL else Tier.SMALL
            backends = self._registry.get_healthy_backends(fallback)
            if backends:
                logger.warning("tier %s has no healthy backends, falling back to %s", tier, fallback)
                tier = fallback
                reason = RoutingReason.FALLBACK

        if not backends:
            # Affinity scheduler will also fail — raise via BackendUnavailableException upstream
            backend_id = "__unavailable__"
        else:
            backend_id = backends[0].id  # affinity scheduler will override this

        decision = RoutingDecision(
            tier=tier,
            backend_id=backend_id,
            reason=reason,
            classifier_used=classifier_used,
        )
        logger.info(
            "route session=%s tier=%s backend=%s reason=%s classifier=%s",
            session.session_id, tier, backend_id, reason, classifier_used,
        )
        return decision
