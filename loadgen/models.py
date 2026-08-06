from pydantic import BaseModel, Field
from enum import Enum


class LoadMode(str, Enum):
    OPEN_LOOP = "open_loop"    # fixed RPS regardless of completion
    CLOSED_LOOP = "closed_loop"  # fixed concurrency


class TurnSpec(BaseModel):
    """Distribution spec for turns per session."""
    min_turns: int = 1
    max_turns: int = 5
    # Prompt sizes in chars
    system_prompt_chars: int = 2000
    user_prompt_chars: int = 200
    tool_call_probability: float = 0.3


class ProfileConfig(BaseModel):
    name: str
    description: str
    mode: LoadMode
    # For closed_loop: number of concurrent sessions
    concurrency: int = 10
    # For open_loop: requests per second
    target_rps: float = 5.0
    # Total sessions to run
    total_sessions: int = 100
    # Think time between turns in seconds
    think_time_seconds: float = 0.5
    turn_spec: TurnSpec = TurnSpec()
    tier_hint: str = "auto"


class ResultRow(BaseModel):
    request_id: str
    session_id: str
    agent_id: str
    tier: str
    backend_id: str
    ttft_ms: float
    e2e_ms: float
    input_tokens: int
    output_tokens: int
    affinity_hit: bool
    status_code: int
    timestamp_iso: str
    profile: str
