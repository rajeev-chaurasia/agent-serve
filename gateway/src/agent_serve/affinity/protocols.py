from typing import Protocol, runtime_checkable

from ..core.enums import Tier
from ..core.models import BackendInfo, SessionContext


@runtime_checkable
class AffinitySchedulerProtocol(Protocol):
    def select_backend(
        self, session: SessionContext, tier: Tier, candidates: list[BackendInfo]
    ) -> BackendInfo:
        """Select which backend to route this session to.

        For the first turn of a session, or after the sticky backend goes down,
        this picks a backend and stores the binding. On subsequent turns it returns
        the stored binding if the backend is still healthy.

        Args:
            session: current session context including session_id and turn count.
            tier: the tier already chosen by the tier router.
            candidates: healthy backends for the chosen tier, ordered arbitrarily.

        Returns:
            The selected BackendInfo. Must be one of the candidates.

        Raises:
            BackendUnavailableException if candidates is empty.
        """
        ...

    def invalidate(self, session_id: str) -> None:
        """Remove the sticky binding for a session (e.g., on session end or TTL expiry)."""
        ...

    def on_backend_down(self, backend_id: str, tier: Tier) -> None:
        """Called when a backend is marked down. Must re-assign all sessions pinned to it."""
        ...
