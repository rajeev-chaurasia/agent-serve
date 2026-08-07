from typing import Protocol, runtime_checkable

from ..core.enums import Tier
from ..core.models import SessionContext


@runtime_checkable
class AdmissionControllerProtocol(Protocol):
    async def gate(self, session: SessionContext, tier: Tier, estimated_tokens: int) -> None:
        """Raise BudgetExceededException, QueueFullException, or BackendUnavailableException.
        Returns normally when the request is admitted and a slot is held."""
        ...

    def release(self, session: SessionContext, tier: Tier) -> None:
        """Release the concurrency slot after the response completes."""
        ...
