# Session Affinity

Session affinity is the mechanism that pins an agent session to a specific vLLM backend and keeps it there for the duration of the session. The primary benefit is KV-cache reuse: vLLM caches key-value tensors for the system prompt and prior turns, so a request that lands on the same backend as the previous turn skips recomputing those tokens.

## Why It Matters

In agentic workloads, the system prompt is often large (a few KB of instructions, tool definitions, and context) and identical across all turns of a session. Without affinity, load balancing distributes turns randomly across backends. Each backend would see only some of the session's turns, so the cached KV block from turn N is useless when turn N+1 lands on a different backend.

With affinity, all turns of the same session go to the same backend. The system-prompt KV block is computed once (on the first turn) and reused for every subsequent turn. In the load study, this cut warm-turn latency by roughly 3 to 5x compared to cold starts.

## How It Works (HRW)

The gateway uses Highest Random Weight (HRW) hashing, also called rendezvous hashing, to select a backend for a session. For each candidate backend, it computes a score:

```
score(session_id, backend_id) = hash(session_id + backend_id)
```

The backend with the highest score wins. Because the hash is deterministic and depends only on the session and backend IDs, the same session always maps to the same backend as long as the backend is healthy. If a backend goes down, HRW gracefully remaps the session to whichever remaining backend scores highest -- there is no central coordinator or rehashing of all sessions.

The implementation is in `gateway/src/agent_serve/affinity/scheduler.py`. The scheduler wraps the HRW selection with a sticky-binding table (a dict keyed by session_id) so that the winning backend is remembered across turns without recomputing the hash every time.

## Binding Lifecycle

When a session is first seen, `select_backend()` computes the HRW winner, writes an entry to the sticky table with a TTL (default 30 minutes), and returns the backend along with `affinity_hit=False`.

On subsequent calls for the same session, if the binding is still valid (not expired, backend still healthy), `select_backend()` returns the cached backend with `affinity_hit=True` and refreshes the TTL.

If the pinned backend goes down, `on_backend_down()` removes the binding, and the next request for that session picks a new backend via HRW from the remaining healthy set.

```python
# Return signature: (BackendInfo, bool)
# bool is True on a cache hit (same backend as last turn), False on first turn or rebind
backend, affinity_hit = scheduler.select_backend(session, tier, candidates)
```

The `affinity_hit` boolean shows up in the `x_agent_serve` response metadata and in Prometheus counters, so you can track the cache-hit rate in Grafana.

## Measured Impact

From the load study (72 requests each condition, 3 KB system prompt, c=6):

| Condition | Affinity Hit Rate | p50 E2E |
|-----------|:-----------------:|:-------:|
| Affinity ON (12 sessions x 6 turns, sticky IDs) | 83.3% | 18.5 s |
| Affinity OFF (72 single-turn sessions, fresh IDs) | 0.0% | 19.4 s |

The p50 difference (0.9 s) is modest because the backends are already queueing at c=6, which masks some of the cache benefit. The effect is more pronounced at lower load or with longer sessions (more turns per session = higher fraction of warm turns).

The expected hit rate for 6-turn sessions is 5/6 = 83.3%: turn 1 is always a miss (no binding exists yet), turns 2 through 6 are always hits. The measured 83.3% matches this exactly, confirming the scheduler works as designed.

## Configuration

```yaml
# configs/gateway.yaml
affinity:
  sticky_ttl_seconds: 1800    # how long a binding stays valid without activity
```

Setting `sticky_ttl_seconds` to 0 effectively disables affinity (all sessions are treated as first-turn). There is no separate enable/disable flag; TTL controls the behavior.

## Metrics

| Metric | Description |
|--------|-------------|
| `agentserve_affinity_hits_total` (tier label) | Requests that reused an existing backend binding |
| `agentserve_affinity_misses_total` (tier label) | Requests that needed a new binding (first turn or expired) |
| `agentserve_affinity_broken_total` (tier label) | Bindings invalidated because the pinned backend went down |
