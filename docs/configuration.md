# Configuration

All runtime configuration lives in `configs/gateway.yaml`. This file is mounted into the gateway container at startup. Changes take effect after `docker compose restart gateway` (no image rebuild needed).

The vLLM backends are configured via environment files (`configs/vllm-big.env`, `configs/vllm-small.env`) that are loaded by docker-compose. Backend changes require a container restart: `docker compose up -d --force-recreate vllm-big`.

## Gateway Config (`configs/gateway.yaml`)

### Backends

```yaml
backends:
  - id: big-0
    tier: big
    base_url: http://vllm-big:8001
    gpu: 1
    max_inflight: 32

  - id: small-0
    tier: small
    base_url: http://vllm-small-0:8002
    gpu: 0
    max_inflight: 128

  - id: small-1
    tier: small
    base_url: http://vllm-small-1:8003
    gpu: 0
    max_inflight: 128
```

| Field | Description |
|-------|-------------|
| `id` | Unique backend identifier. Shows up in metrics labels and `x_agent_serve.backend_id`. |
| `tier` | `small` or `big`. The router only considers backends in the selected tier. |
| `base_url` | Docker service name (not localhost). Must match the service name in `docker-compose.yml`. |
| `gpu` | Which GPU this backend runs on. Informational only, not enforced by the gateway. |
| `max_inflight` | Maximum concurrent requests the gateway will send to this backend. Requests beyond this limit queue in the BackpressureQueue. |

### Admission Control

```yaml
admission:
  max_queue_size: 256
  queue_timeout_seconds: 30
  default_token_budget: 100000
  budget_window_seconds: 60
```

| Field | Description |
|-------|-------------|
| `max_queue_size` | Total number of requests that can wait in the global queue. Returns 503 immediately when full. |
| `queue_timeout_seconds` | How long a queued request waits before being rejected with 503. |
| `default_token_budget` | Input + output tokens an `agent_id` can consume per window before getting 429. |
| `budget_window_seconds` | Sliding window length for the token budget. |

### Routing

```yaml
routing:
  prompt_length_threshold: 2000
```

| Field | Description |
|-------|-------------|
| `prompt_length_threshold` | Combined character count of all messages above which the request goes to the big tier. Set to a very large number to disable length-based routing. |

### Affinity

```yaml
affinity:
  sticky_ttl_seconds: 1800
```

| Field | Description |
|-------|-------------|
| `sticky_ttl_seconds` | How long a session-to-backend binding stays valid (TTL is refreshed on each access). Set to 0 to effectively disable affinity. |

### Health Checking

```yaml
health:
  probe_interval_seconds: 10
  failures_to_mark_down: 3
  successes_to_mark_up: 2
  probe_timeout_seconds: 5
```

| Field | Description |
|-------|-------------|
| `probe_interval_seconds` | How often the health checker pings each backend. |
| `failures_to_mark_down` | Consecutive probe failures before a backend is marked DOWN. At 3 failures and 10s intervals, detection takes up to 30 seconds. |
| `successes_to_mark_up` | Consecutive probe successes before a downed backend re-enters rotation. |
| `probe_timeout_seconds` | Probe request timeout. |

### Telemetry

```yaml
telemetry:
  otel_endpoint: http://otel-collector:4317
  log_level: INFO
```

| Field | Description |
|-------|-------------|
| `otel_endpoint` | OTLP gRPC endpoint for traces. Set to empty string to disable tracing. |
| `log_level` | Gateway log level. `DEBUG` enables per-request routing decisions in structured JSON logs. |

## vLLM Config Files

### `configs/vllm-big.env`

```bash
MODEL_ID=RedHatAI/Qwen2.5-72B-Instruct-FP8-dynamic
VLLM_ARGS=--max-model-len 8192 --enable-prefix-caching --gpu-memory-utilization 0.90 \
  --max-num-seqs 32 --enable-chunked-prefill --enable-auto-tool-choice \
  --tool-call-parser hermes --port 8001 --host 0.0.0.0
```

### `configs/vllm-small.env`

```bash
MODEL_ID=Qwen/Qwen2.5-7B-Instruct
# Used by vllm-small-0. vllm-small-1 overrides max-model-len and gpu-memory-utilization
# in docker-compose.yml to avoid OOM when both instances share GPU 0.
VLLM_ARGS=--max-model-len 16384 --enable-prefix-caching --gpu-memory-utilization 0.45 \
  --max-num-seqs 128 --enable-auto-tool-choice --tool-call-parser hermes --port 8002 --host 0.0.0.0
```

Key vLLM flags used here:

| Flag | Effect |
|------|--------|
| `--max-model-len` | Maximum sequence length in tokens. Reduce this to free up KV cache memory. |
| `--enable-prefix-caching` | Caches KV tensors for prompt prefixes across requests. Required for affinity to deliver latency savings. |
| `--gpu-memory-utilization` | Fraction of GPU VRAM vLLM can use (weights + KV cache). The remainder stays as headroom. |
| `--max-num-seqs` | Maximum number of sequences vLLM keeps in flight at once. |
| `--enable-chunked-prefill` | (big only) Splits long prefill phases into chunks, reducing TTFT for concurrent requests. |
| `--enable-auto-tool-choice` | Enables tool-calling response format. |
| `--tool-call-parser hermes` | Which parser to use for tool-call output. `hermes` is compatible with Qwen2.5. |

## Environment Variables

Sensitive values go in `.env` (gitignored, never committed):

```bash
# .env
HF_TOKEN=hf_...            # Hugging Face token for model downloads
GATEWAY_PORT=8000           # Override gateway listen port (optional)
```

Copy `.env.example` to `.env` and fill in your values before starting the stack.

## docker-compose.yml Services

| Service | Port | GPU | Description |
|---------|------|-----|-------------|
| `gateway` | 8000 | none | FastAPI gateway (CPU) |
| `vllm-big` | 8001 | GPU 1 | 72B FP8 inference |
| `vllm-small-0` | 8002 | GPU 0 | 7B BF16 inference, first instance |
| `vllm-small-1` | 8003 | GPU 0 | 7B BF16 inference, second instance (slightly reduced VRAM settings) |
| `prometheus` | 9090 | none | Metrics collector |
| `otel-collector` | 4317 | none | Trace aggregator (OTLP gRPC) |
| `grafana` | 3000 | none | Dashboard (admin / admin on first login) |
