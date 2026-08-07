import threading
import time
from collections import defaultdict

from ..config.models import AdmissionConfig


class _WindowState:
    """Sliding-window token accumulator for one agent."""

    def __init__(self, budget: int, window_seconds: int) -> None:
        self.budget = budget
        self.window_seconds = window_seconds
        # list of (timestamp, tokens) tuples
        self._entries: list[tuple[float, int]] = []
        self._lock = threading.Lock()

    def _evict_expired(self, now: float) -> None:
        cutoff = now - self.window_seconds
        self._entries = [(ts, t) for ts, t in self._entries if ts >= cutoff]

    def current_usage(self) -> int:
        now = time.monotonic()
        with self._lock:
            self._evict_expired(now)
            return sum(t for _, t in self._entries)

    def add(self, tokens: int) -> None:
        now = time.monotonic()
        with self._lock:
            self._evict_expired(now)
            self._entries.append((now, tokens))

    def has_budget(self, estimated: int) -> bool:
        return self.current_usage() + estimated <= self.budget


class TokenAccountant:
    """Tracks per-agent token usage within a sliding time window."""

    def __init__(self, config: AdmissionConfig) -> None:
        self._config = config
        self._states: dict[str, _WindowState] = defaultdict(
            lambda: _WindowState(config.default_token_budget, config.budget_window_seconds)
        )

    def check_budget(self, agent_id: str, estimated_input_tokens: int) -> bool:
        return self._states[agent_id].has_budget(estimated_input_tokens)

    def debit(self, agent_id: str, input_tokens: int, output_tokens: int) -> None:
        self._states[agent_id].add(input_tokens + output_tokens)

    def get_usage(self, agent_id: str) -> dict:
        state = self._states[agent_id]
        return {
            "agent_id": agent_id,
            "tokens_used": state.current_usage(),
            "budget": state.budget,
            "window_seconds": state.window_seconds,
        }
