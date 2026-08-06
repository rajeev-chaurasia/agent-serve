from typing import Protocol, runtime_checkable


@runtime_checkable
class AccountantProtocol(Protocol):
    def check_budget(self, agent_id: str, estimated_input_tokens: int) -> bool:
        """Return True if the request is within budget."""
        ...

    def debit(self, agent_id: str, input_tokens: int, output_tokens: int) -> None:
        """Record actual token usage after a response completes."""
        ...

    def get_usage(self, agent_id: str) -> dict:
        """Return current window usage for an agent."""
        ...
