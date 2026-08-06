from .enums import Tier


class GatewayException(Exception):
    """Base exception for all gateway errors."""

    status_code: int = 500
    detail: str = "An unexpected gateway error occurred."

    def __init__(self, detail: str | None = None, status_code: int | None = None) -> None:
        if detail is not None:
            self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.detail)


class BudgetExceededException(GatewayException):
    """Raised when an agent exceeds its token budget."""

    status_code: int = 429

    def __init__(self, agent_id: str, tokens_used: int, budget: int) -> None:
        self.agent_id = agent_id
        self.tokens_used = tokens_used
        self.budget = budget
        super().__init__(
            detail=(
                f"Agent '{agent_id}' has exceeded its token budget: "
                f"{tokens_used} used of {budget} allowed."
            )
        )


class QueueFullException(GatewayException):
    """Raised when the request queue is at capacity."""

    status_code: int = 429

    def __init__(self, retry_after_seconds: int = 30) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            detail=(
                f"Request queue is full. Retry after {retry_after_seconds} seconds."
            )
        )


class BackendUnavailableException(GatewayException):
    """Raised when no healthy backend is available for the requested tier."""

    status_code: int = 503

    def __init__(self, tier: Tier) -> None:
        self.tier = tier
        super().__init__(
            detail=f"No healthy backend available for tier '{tier.value}'."
        )


class ClassifierException(GatewayException):
    """Raised when the classifier fails to produce a routing decision."""

    status_code: int = 500

    def __init__(self, detail: str = "Classifier failed to determine routing tier.") -> None:
        super().__init__(detail=detail)
