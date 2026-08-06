# Operations Runbook — agent-serve

This runbook covers day-to-day operations, common failure modes, and recovery procedures for the agent-serve stack.

## 1. Starting the Stack

```bash
# Start all services in detached mode
docker compose up -d

# Watch startup — vLLM model loading takes 2-5 minutes per backend
docker compose logs -f vllm-big vllm-small-0

# Confirm all services are running
docker compose ps

# Verify gateway health
curl http://localhost:8000/healthz
```

Expected output from `docker compose ps` when healthy:
```
NAME              STATUS          PORTS
gateway           running         0.0.0.0:8000->8000/tcp
vllm-big          running         0.0.0.0:8001->8001/tcp
vllm-small-0      running         0.0.0.0:8002->8002/tcp
prometheus        running         0.0.0.0:9090->9090/tcp
otel-collector    running         0.0.0.0:4317->4317/tcp
grafana           running         0.0.0.0:3000->3000/tcp
```

To stop the stack gracefully:
```bash
docker compose down
```

To stop and remove volumes (wipes Prometheus data and Grafana state):
```bash
docker compose down -v
```

## 2. Common Failures

### 2.1 vLLM OOM (Out of Memory)

**Symptom**: `vllm-big` or `vllm-small-0` exits with `torch.cuda.OutOfMemoryError` or `CUDA out of memory`.

**Check logs**:
```bash
docker compose logs vllm-big | grep -i "oom\|out of memory\|cuda error"
```

**Remediation**:
1. Reduce `--gpu-memory-utilization` in `configs/vllm-big.env` or `configs/vllm-small.env` (e.g., from 0.92 to 0.88)
2. Reduce `--max-num-seqs` to lower KV cache reservation (e.g., from 64 to 48)
3. Reduce `--max-model-len` if you don't need long contexts (e.g., 8192 instead of 16384)
4. Restart the affected service: `docker compose restart vllm-big`
5. Record the new flags in `MODELS.md`

### 2.2 Model Download Fails

**Symptom**: vLLM container exits with `401 Unauthorized`, `Repository not found`, or `OSError: [Errno 28] No space left on device`.

**Check**:
```bash
# Check HF_TOKEN is set and correct
docker compose exec vllm-big env | grep HUGGING_FACE_HUB_TOKEN

# Check disk space on the Docker data volume
df -h /var/lib/docker

# Try a manual download test
docker run --rm -e HUGGING_FACE_HUB_TOKEN=$HF_TOKEN \
  huggingface/transformers-cli whoami
```

**Remediation for 401**: Regenerate your HF token at https://huggingface.co/settings/tokens and update `.env`.

**Remediation for disk space**: You need approximately 200 GB free:
- 70B FP8: ~35 GB
- 7B BF16: ~14 GB
- Docker overhead: ~10 GB
- Buffer: remainder

Clean Docker cache if needed:
```bash
docker system prune --volumes
```

**Remediation for gated models**: Ensure your HF account has accepted the model license at the model's HuggingFace page (Llama 3.3 requires Meta's license acceptance).

### 2.3 Gateway Returns 503

**Symptom**: All requests to the gateway return `HTTP 503 Service Unavailable`.

**Check**:
```bash
# Gateway internal backend status
curl http://localhost:8000/status

# Check vLLM health directly
curl http://localhost:8001/health   # big tier
curl http://localhost:8002/health   # small tier

# Check gateway logs
docker compose logs -f gateway | tail -50
```

**Remediation**:
1. If a vLLM backend is down, restart it: `docker compose restart vllm-big`
2. If the gateway cannot reach backends, check Docker networking: `docker compose exec gateway ping vllm-big`
3. If queue is full (check `queue_depth` metric in Grafana), reduce incoming traffic or increase `max_queue_size` in `configs/gateway.yaml`
4. Check `configs/gateway.yaml` has correct `base_url` values (Docker service names, not localhost)

### 2.4 FP8 on sm_120 (sm_120) Issues

**Symptom**: `vllm-big` fails to start with errors referencing `sm_120`, `compute capability`, or `No kernel found for fp8`.

**Background**: 96 GB workstation GPU uses CUDA compute capability 12.0 (sm_120). FP8 GEMM kernels in early vLLM releases may not include sm_120 PTX. This is a known gap as of early 2026.

**Immediate remediation**:
1. Check if a newer vLLM image has sm_120 FP8 support: https://github.com/vllm-project/vllm/releases
2. If not, switch to AWQ: edit `configs/vllm-big.env`, change `--quantization fp8` to `--quantization awq` and update `MODEL_BIG` to an AWQ checkpoint
3. See `MODELS.md` for the full fallback sequence

**Required action**: File an issue at https://github.com/vllm-project/vllm/issues with:
- GPU: 96 GB workstation GPU
- CUDA compute capability: sm_120
- vLLM version (from docker image tag)
- Full error traceback from `docker compose logs vllm-big`
- Record the issue link in `CONTRIBUTIONS.md`

## 3. Health Checks

### Gateway

```bash
# Simple liveness check
curl -s http://localhost:8000/healthz
# Expected: {"status": "ok"}

# Backend status (which backends are up/down)
curl -s http://localhost:8000/status | python3 -m json.tool
```

### vLLM Backends

```bash
# Big tier
curl -s http://localhost:8001/health
# Expected: {"status": "ok"} or HTTP 200

# Small tier
curl -s http://localhost:8002/health
```

### Prometheus

```bash
# Check Prometheus is scraping all targets
curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool | grep -A2 '"health"'
```

## 4. Scaling Knobs

All tunable parameters live in `configs/gateway.yaml`. Restart the gateway after changes:

```bash
docker compose restart gateway
```

| Parameter | Location | Effect |
|-----------|----------|--------|
| `max_inflight` per backend | `backends[].max_inflight` | Caps concurrent in-flight requests per backend |
| `max_queue_size` | `admission.max_queue_size` | Global bounded queue depth; 503 when full |
| `queue_timeout_seconds` | `admission.queue_timeout_seconds` | How long a queued request waits before 503 |
| `default_token_budget` | `admission.default_token_budget` | Tokens per agent per window before 429 |
| `budget_window_seconds` | `admission.budget_window_seconds` | Sliding window for token budget (seconds) |
| `prompt_length_threshold` | `routing.prompt_length_threshold` | Chars above which prompt routes to big tier |
| `sticky_ttl_seconds` | `affinity.sticky_ttl_seconds` | How long a session stays pinned to a backend |

On the vLLM side, the relevant knobs are in `configs/vllm-big.env` and `configs/vllm-small.env`. Changes require container restart:

```bash
docker compose up -d --force-recreate vllm-big
```

## 5. GPU Clock Locking for Benchmarks

Unrestricted GPU boost clocks produce noisy latency measurements. Lock clocks before running load studies:

```bash
# Find available clock speeds for GPU 0 and GPU 1
nvidia-smi -q -d SUPPORTED_CLOCKS | grep -A2 "GPU 00000000"

# Lock both GPUs to base clock (example — substitute actual values)
sudo nvidia-smi -i 0 -lgc 2520   # GPU 0 (small model)
sudo nvidia-smi -i 1 -lgc 2520   # GPU 1 (big model)

# Verify
nvidia-smi -q -d CLOCK | grep "Graphics Clock"

# Reset to default (auto boost) after benchmarks
sudo nvidia-smi -i 0 -rgc
sudo nvidia-smi -i 1 -rgc
```

Also set persistence mode to prevent driver unloads between runs:
```bash
sudo nvidia-smi -pm 1
```

## 6. Grafana

- **URL**: http://localhost:3000
- **Default credentials**: admin / admin (change on first login)
- **Dashboard**: "agent-serve" (pre-provisioned, appears in the General folder)

The dashboard has four rows:
1. **Traffic & Latency** — RPS, TTFT p50/p99, E2E latency p50/p99 by tier
2. **Scheduling** — queue depth, queue wait time, affinity hit rate
3. **Backends** — running/waiting sequences per vLLM instance, KV cache utilization
4. **Economics** — tokens/s by tier, token budget rejection rate

If the dashboard does not appear, check provisioning:
```bash
docker compose logs grafana | grep -i provision
```

## 7. Failure Drill Procedure

Run this drill periodically to verify the gateway correctly handles backend failures.

```bash
# Step 1: Confirm baseline health
curl http://localhost:8000/healthz
curl http://localhost:8000/status

# Step 2: Stop the big-tier backend
docker compose stop vllm-big

# Step 3: Send a request that would route to big tier
# Expected: 503 or graceful degradation to small tier (depending on config)
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Agent-Tier: big" \
  -d '{"model": "big", "messages": [{"role": "user", "content": "test"}], "max_tokens": 8}'

# Step 4: Watch gateway logs — should see backend marked DOWN after health probe failures
docker compose logs -f gateway | grep -i "down\|health\|backend"

# Step 5: Observe Grafana — "Backends" row should show vllm-big as unavailable

# Step 6: Recover the backend
docker compose start vllm-big

# Step 7: Wait for health probes to mark it UP (probe_interval=10s, successes_to_mark_up=2 → ~20s)
sleep 25
curl http://localhost:8000/status

# Step 8: Confirm traffic resumes to big tier
```

## 8. Log Locations

All logs are available via Docker Compose:

```bash
# Tail all services
docker compose logs -f

# Tail a specific service
docker compose logs -f gateway
docker compose logs -f vllm-big
docker compose logs -f vllm-small-0
docker compose logs -f prometheus
docker compose logs -f otel-collector
docker compose logs -f grafana

# Dump last N lines
docker compose logs --tail=200 vllm-big

# Filter for errors
docker compose logs vllm-big 2>&1 | grep -i "error\|exception\|traceback"
```

For persistent log storage across restarts, configure Docker's log driver in `docker-compose.yml` or use the OTel collector to forward structured logs to a backend.

OTel traces are exported to the collector at `localhost:4317` (gRPC) and can be forwarded to Jaeger, Tempo, or any OTLP-compatible backend by updating `configs/otel-collector.yaml`.
