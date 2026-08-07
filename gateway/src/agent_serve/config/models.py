from pydantic import BaseModel

from agent_serve.core.enums import Tier


class BackendConfig(BaseModel):
    id: str
    tier: Tier
    base_url: str
    gpu: int
    max_inflight: int
    model: str = ""


class AdmissionConfig(BaseModel):
    default_token_budget: int = 100000
    budget_window_seconds: int = 3600
    max_queue_size: int = 256
    queue_timeout_seconds: int = 30


class RoutingConfig(BaseModel):
    prompt_length_threshold: int = 2000
    classifier_cache_ttl_seconds: int = 300
    tool_followup_stays_same_tier: bool = True


class AffinityConfig(BaseModel):
    enabled: bool = True
    sticky_ttl_seconds: int = 1800
    rebalance_on_backend_recovery: bool = False


class HealthConfig(BaseModel):
    probe_interval_seconds: int = 10
    failures_to_mark_down: int = 3
    successes_to_mark_up: int = 2
    probe_timeout_seconds: int = 5


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://otel-collector:4317"
    prometheus_path: str = "/metrics"
    log_level: str = "info"


class GatewayConfig(BaseModel):
    backends: list[BackendConfig]
    admission: AdmissionConfig = AdmissionConfig()
    routing: RoutingConfig = RoutingConfig()
    affinity: AffinityConfig = AffinityConfig()
    health: HealthConfig = HealthConfig()
    telemetry: TelemetryConfig = TelemetryConfig()
