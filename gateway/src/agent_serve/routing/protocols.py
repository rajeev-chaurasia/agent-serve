from typing import Protocol, runtime_checkable

from ..core.models import SessionContext, RoutingDecision


@runtime_checkable
class RouterProtocol(Protocol):
    async def route(self, session: SessionContext, messages: list[dict], tools: list | None) -> RoutingDecision:
        """Select a tier and backend for this request. Never raises — falls back to big tier on error."""
        ...
