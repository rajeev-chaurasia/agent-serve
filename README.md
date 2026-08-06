# agent-serve

agent-serve is a production-shaped serving stack for agentic LLM traffic that runs entirely on local hardware. It wraps two vLLM backends — a 7B small model and a 70B big model — behind a single OpenAI-compatible gateway that handles session-affinity scheduling, multi-tier routing, per-agent token budgets, and backpressure queuing, with full OpenTelemetry tracing and a Grafana dashboard for observability. The result is a self-hosted inference stack tuned for the long-session, tool-calling, mixed-concurrency patterns that agentic workloads produce on dual NVIDIA RTX PRO 6000 Blackwell GPUs.

## Architecture

```
                          ┌──────────────────────────────────────────┐
                          │              agent-serve                  │
                          │                                           │
  ┌──────────┐            │  ┌────────────────────────────────────┐  │
  │  Client  │──────────▶ │  │           Gateway :8000             │  │
  │ (agents) │            │  │   routing · affinity · budgets      │  │
  └──────────┘            │  │   admission · backpressure · OTel   │  │
                          │  └───────────┬──────────────┬──────────┘  │
                          │              │              │              │
                          │    ┌─────────▼──┐    ┌────▼──────────┐  │
                          │    │  vllm-big  │    │ vllm-small-0  │  │
                          │    │  GPU 1     │    │  GPU 0        │  │
                          │    │  70B FP8   │    │  7B BF16      │  │
                          │    │  :8001     │    │  :8002        │  │
                          │    └────────────┘    └───────────────┘  │
                          │                                           │
                          │  ┌────────────┐   ┌────────────────────┐ │
                          │  │ Prometheus │   │  OTel Collector    │ │
                          │  │   :9090    │   │      :4317         │ │
                          │  └─────┬──────┘   └─────────┬──────────┘ │
                          │        │                     │            │
                          │  ┌─────▼─────────────────────▼──────────┐ │
                          │  │         Grafana  :3000                │ │
                          │  └───────────────────────────────────────┘ │
                          └──────────────────────────────────────────┘
```

## Headline Results

Load study plots will appear here after running `studies/run_load_study.sh`.

## Quickstart

### Prerequisites

- Docker Engine with [Docker Compose v2](https://docs.docker.com/compose/install/) (`docker compose` not `docker-compose`)
- 2x NVIDIA RTX PRO 6000 Blackwell GPUs (each 96 GB VRAM)
- NVIDIA Container Toolkit installed and configured
- `HF_TOKEN` environment variable set (Hugging Face account with access to gated models)
- ~200 GB free disk space for model weights

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/rchaurasia/agent-serve.git
cd agent-serve

# 2. Copy and edit the environment file
cp .env.example .env
# Edit .env: set HF_TOKEN, adjust model IDs if needed

# 3. Start the full stack (this will download models on first run — takes time)
docker compose up -d

# 4. Watch startup logs (vLLM model load takes 2-5 minutes per backend)
docker compose logs -f vllm-big vllm-small-0
```

### Smoke Test

```bash
# Gateway health
curl http://localhost:8000/healthz

# OpenAI-compatible chat (routes to small tier automatically)
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "small",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 64
  }'

# Force big tier
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Agent-Tier: big" \
  -d '{
    "model": "big",
    "messages": [{"role": "user", "content": "Summarize quantum computing."}],
    "max_tokens": 256
  }'
```

## Key Features

- **Session-affinity scheduling** — agent sessions are pinned to a backend for KV cache reuse; TTL configurable
- **Multi-tier routing** — prompt-length heuristic (configurable threshold) routes short queries to 7B, long/complex to 70B
- **Per-agent token budgets** — sliding window rate limiter per `agent_id`, rejects at 429 when budget exhausted
- **Backpressure queuing** — bounded queue with configurable timeout; 503 on overflow rather than silent slowdown
- **OpenTelemetry tracing** — distributed traces from gateway through vLLM backends, exported via OTLP
- **Grafana dashboard** — pre-provisioned dashboard with traffic, latency (TTFT + E2E), scheduling, and economics panels

## Directory Structure

```
agent-serve/
├── README.md             # This file
├── MODELS.md             # Model pinning, VRAM budgets, vLLM flags
├── RUNBOOK.md            # Operations and failure recovery
├── CONTRIBUTIONS.md      # OSS upstream issues and PRs tracker
├── .env.example          # Environment variable template
├── docker-compose.yml    # Full stack definition
├── configs/
│   ├── gateway.yaml      # Gateway routing and admission config
│   ├── vllm-big.env      # vLLM big-tier env (GPU 1, 70B FP8)
│   ├── vllm-small.env    # vLLM small-tier env (GPU 0, 7B BF16)
│   ├── prometheus.yml    # Prometheus scrape config
│   └── grafana/
│       └── dashboard.json # Provisioned Grafana dashboard
├── gateway/              # Gateway application source
├── studies/              # Load study scripts and analysis notebooks
└── tests/                # Integration and smoke tests
```

## Studies

Running `studies/run_load_study.sh` executes a series of load scenarios using a locust-based harness:

- **Sweep 1** — concurrency ladder (1, 4, 8, 16, 32 concurrent agents) on the small tier
- **Sweep 2** — concurrency ladder on the big tier
- **Sweep 3** — mixed-tier traffic (70% small / 30% big), measuring routing overhead
- **Sweep 4** — session-affinity benefit: compare TTFT with and without sticky routing
- **Sweep 5** — token budget enforcement: confirm 429 rate at saturation

Results are written to `studies/results/` as CSV files and rendered as PNG plots via the accompanying Jupyter notebook (`studies/analysis.ipynb`).

## Owner

Rajeev Chaurasia — rchaurasia@nvidia.com
