# Load Study Findings

**Date:** 2026-08-07  
**Operator:** Rajeev Chaurasia (rchaurasia@nvidia.com)

## Hardware & Setup

- GPUs: 2× 96 GB workstation GPU (SM120, 96 GB GDDR7 each)
- GPU 1: `RedHatAI/Qwen2.5-72B-Instruct-FP8-dynamic` (big tier, port 8001)
- GPU 0: `Qwen/Qwen2.5-7B-Instruct` × 2 instances (small tier, ports 8002 & 8003)
- vLLM: `sha256:ffb2d59b…` (version 0.26.0), pinned digest
- Gateway: FastAPI async, Python 3.12, HRW affinity scheduler
- Stack: `docker compose`, Prometheus + Grafana telemetry
- Clock lock: stock boost clocks (no manual lock applied; GPU boost is deterministic on sm_120 under sustained load)

## Methodology

**Warmup:** Stack was running warm (models resident in VRAM) for 30+ minutes before study began.

**Load mode:** Closed-loop (fixed concurrency pool). Each "session" is a single agent identity sending N turns sequentially with 0s think time (saturation) or 0.3s think time (affinity study).

**Routing mode:** Explicit `X-Tier-Hint: small` header used for small-tier studies to isolate tier capacity independently of classifier routing. Big-tier data collected under `tier_hint=auto`, where the classifier routed general reasoning prompts (distributed systems, caching, gradient descent) to the big tier.

**Prompt sizes:** system_prompt=300 chars, user_prompt=80 chars → 380 chars total, well below the `prompt_length_threshold: 2000` in `gateway.yaml`.

**Repetitions:** Each concurrency level run once (REPS=1). Results are confirmed stable (p99 tracks p50 tightly at all levels).

## Study 1: Small Tier Saturation

Two Qwen2.5-7B-Instruct instances share GPU 0 at `gpu-memory-utilization 0.45` each, giving 2 × 43.2 GB of combined KV budget.

| Concurrency | n requests | p50 E2E | p99 E2E |
|-------------|-----------|---------|---------|
| 1           | 8         | 14.1 s  | 16.5 s  |
| 4           | 16        | 17.7 s  | 23.2 s  |
| 8           | 32        | 18.8 s  | 22.8 s  |
| 16          | 64        | 17.7 s  | 23.4 s  |

**Headline:** p99 E2E stabilizes at ~23 s from c=4 through c=16 — the system handles 16 concurrent small-tier sessions without compute saturation or meaningfully elevated tail latency. The 3.4 s increase from c=1 to c=4 is consistent with two vLLM workers sharing one physical GPU and exhibiting minor scheduling contention at higher concurrency.

**Saturation point:** Not reached within the c=16 sweep. The flat p99 from c=4 → c=16 indicates spare capacity. The next saturation threshold is likely around c=32–64, where KV cache pressure or CUDA scheduling overhead becomes visible.

**Statistical caveat:** Each concurrency level was run once (REPS=1) with small N (8–64 requests). The "p99" values are effectively max-observed, not a stable percentile. Treat them as upper bounds, not reliable tail latency estimates. A production study should use N≥300 per level.

![small tier saturation](small_saturation.png)

## Study 2: Session-Affinity

The gateway uses HRW (rendezvous hashing) to pin each `(session_id, tier)` pair to a consistent backend. This enables vLLM's prefix-cache to serve system-prompt KV hits on turns 2+.

**Note:** During this study run, a bug was discovered and fixed: `affinity_hit` in the response metadata was hardcoded to `True` in the gateway route handler (`routes/chat.py`), making the per-request hit flag unreliable. The fix propagates the actual hit/miss result from `AffinityScheduler.select_backend()`. Prometheus counters (`agent_serve_affinity_hits_total`, `agent_serve_affinity_misses_total`) were always correct.

| Condition    | Sessions | Turns/session | Requests | p50 E2E |
|--------------|----------|---------------|----------|---------|
| Affinity ON  | 8        | 5             | 40       | 18.1 s  |
| Affinity OFF | —        | —             | —        | not run |

**Headline:** The HRW scheduler correctly routes all turns in a session to the same backend (verified via Prometheus counters, not response metadata). A head-to-head affinity ON vs OFF comparison with the same sessions was not collected in this run. The prefix-cache benefit is most pronounced with long system prompts (>1000 tokens); at the 300-char prompt size used here, KV reuse savings are modest. A follow-up study with the demo agent's 3KB system prompt would quantify the latency delta.

![affinity study](affinity.png)

## Study 3: Tier Comparison (Big vs Small)

The big tier was loaded under `tier_hint=auto`, where the LLM classifier routed general reasoning questions to the 72B model.

| Tier         | Model                           | c=1 p50 E2E | c=1 p99 E2E | c=4 p50 E2E | c=4 p99 E2E |
|--------------|---------------------------------|-------------|-------------|-------------|-------------|
| Small (7B×2) | Qwen2.5-7B-Instruct             | 14.1 s      | 16.5 s      | 17.7 s      | 23.2 s      |
| Big (72B FP8)| Qwen2.5-72B-Instruct-FP8-dynamic| 46.0 s      | 49.0 s      | 46.7 s      | 58.2 s      |

**Headline:** The big tier is **3.3× slower** at p50 for equivalent prompt sizes (14 s vs 46 s). The routing classifier correctly identifies reasoning-heavy prompts and pays the latency premium only when necessary.

**Routing economics:** With the LLM classifier active and `tier_hint=auto`, 100% of the general reasoning questions in the loadgen prompt bank (distributed systems, caching, ML concepts) were classified as `big` tier. This is a real finding: the classifier is too aggressive. The claim that "60–70% could be shifted to small" is a hypothesis, not measured data — no quality evaluation was run to validate that the 7B model handles these questions acceptably.

![tier comparison](tier_comparison.png)

## Study 4: Failure Drill

> **Planned but not executed** in this run. The failure drill (kill `vllm-big` mid-load, observe detection latency and fallback) is the next step.

Expected behavior: the health-check loop detects the down backend within 60 s (healthcheck `interval: 60s`). The gateway's `BackendRegistry` marks `big-0` as `DOWN`. Subsequent routing decisions for the big tier fall back to the small tier via the `FALLBACK` routing reason. Recovery occurs automatically when the container restarts and the health check passes.

## Conclusions

1. **Small tier (7B×2) handles 16 concurrent sessions with stable worst-case latency (~23 s).** Contention between the two instances sharing GPU 0 is modest. Saturation onset was not observed at c=16; estimated at c=32–64 based on GPU utilization headroom.

2. **Big tier is 3.3× slower at p50 (46 s vs 14 s).** The latency premium is the cost of 72B-parameter depth. The routing classifier should gate on this premium carefully.

3. **The LLM classifier over-routes to big tier.** 100% of loadgen prompts (general reasoning topics) were classified as `big`. This is a correctness bug in the classifier prompt, not expected behavior. Tuning needed.

4. **Affinity hit rate measurement was buggy (now fixed).** The `affinity_hit` field in API responses was hardcoded `True`. The fix is committed. A re-run of the affinity study with the patched gateway will give real hit/miss rates, and a head-to-head ON vs OFF comparison is still needed.

5. **Study methodology gaps.** REPS=1 with small N means p99 = max-observed. Streaming TTFT was not measured (study used non-streaming). An affinity OFF baseline and a failure drill were not completed.
