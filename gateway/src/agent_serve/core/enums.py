from enum import Enum


class Tier(str, Enum):
    SMALL = "small"
    BIG = "big"
    AUTO = "auto"


class BackendStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


class RoutingReason(str, Enum):
    TIER_HINT = "tier_hint"        # X-Tier-Hint header
    PROMPT_LENGTH = "prompt_length"  # prompt exceeded threshold
    TOOL_FOLLOWUP = "tool_followup"  # continuing a tool call sequence
    CLASSIFIER = "classifier"        # small-model classifier decided
    FALLBACK = "fallback"            # no healthy backend for desired tier


class AdmissionOutcome(str, Enum):
    ALLOWED = "allowed"
    BUDGET_EXCEEDED = "budget_exceeded"
    QUEUE_FULL = "queue_full"
    BACKEND_DOWN = "backend_down"


class RequestOutcome(str, Enum):
    SUCCESS = "success"
    UPSTREAM_ERROR = "upstream_error"
    GATEWAY_ERROR = "gateway_error"
    BUDGET_REJECTED = "budget_rejected"
    QUEUE_REJECTED = "queue_rejected"


class HealthProbeResult(str, Enum):
    OK = "ok"
    TIMEOUT = "timeout"
    ERROR = "error"
