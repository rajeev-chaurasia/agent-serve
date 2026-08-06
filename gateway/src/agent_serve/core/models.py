from pydantic import BaseModel, Field

from .enums import BackendStatus, RoutingReason, Tier


class BackendInfo(BaseModel):
    id: str
    tier: Tier
    base_url: str
    gpu: int
    max_inflight: int
    status: BackendStatus = BackendStatus.HEALTHY


class SessionContext(BaseModel):
    session_id: str
    agent_id: str
    turn: int = 0
    assigned_backend_id: str | None = None
    tier_hint: Tier = Tier.AUTO


class RoutingDecision(BaseModel):
    tier: Tier
    backend_id: str
    reason: RoutingReason
    classifier_used: bool = False
    queue_wait_ms: float = 0.0
    affinity_hit: bool = False


class AgentServeMeta(BaseModel):
    tier: Tier
    backend_id: str
    queue_wait_ms: float
    affinity_hit: bool
    routing_reason: RoutingReason


class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class HealthStatus(BaseModel):
    backend_id: str
    status: BackendStatus
    last_probe_result: str | None = None
    consecutive_failures: int = 0
