# Routing

Every request that reaches the gateway must be assigned to a tier (small or big) before it can be dispatched to a backend. Routing is a three-stage pipeline that goes from cheap to expensive: a header check, a deterministic rule, then an LLM call if neither of those resolves the tier.

## The Three Stages

```
Request
  |
  +-- X-Tier-Hint: small  --->  route to small tier immediately
  |
  +-- X-Tier-Hint: big    --->  route to big tier immediately
  |
  +-- X-Tier-Hint: auto (default)
        |
        +-- RuleBasedRouter
        |     |-- prompt_length >= threshold?  --->  big tier
        |     |-- role == assistant with tool_calls?  --->  small tier (tool followup)
        |     |-- inconclusive  --->  pass to ClassifierRouter
        |
        +-- ClassifierRouter
              |-- send last 3 messages to vllm-small-0
              |-- parse {"tier": "small"} or {"tier": "big"}
              |-- cache result for 5 min (keyed on agent_id + message fingerprint)
              |-- on failure: default to small
```

## Tier Hint Header

The `X-Tier-Hint` header is the fastest path. If a client already knows which tier it wants, it sets this header and skips both rule-based and classifier routing. This is what the load generator uses when running saturation studies on a specific tier.

Valid values: `small`, `big`, `auto` (default if header is absent).

## Rule-Based Router

The rule-based router runs synchronously with no external calls. It applies two rules in order:

**Prompt length threshold.** If the combined character count of all messages exceeds `routing.prompt_length_threshold` in `configs/gateway.yaml` (default 2000 characters), the request routes to the big tier. This catches long-context requests like document summarization before spending a classifier call.

**Tool followup.** If the last message has `role=assistant` and a non-empty `tool_calls` field, the request is identified as a tool followup in an existing conversation. These route to the small tier because the model just needs to execute the function and continue, not generate a complex plan.

If neither rule fires, control passes to the classifier.

## Classifier Router

The classifier makes a single-turn call to `vllm-small-0` with a specialized system prompt and the last 3 messages of the conversation. It expects a JSON response with one key:

```json
{"tier": "small"}
```

or

```json
{"tier": "big"}
```

The classifier prompt is deliberately biased toward small:

- Small examples: factual Q&A, definitions, short summaries, translations, calculations, simple explanations
- Big examples: multi-file code generation (>100 LOC), complex proofs, document-length synthesis (>10 sources), requests that explicitly say "be thorough"
- Default: when in doubt, route to small

The 7B model handles this classification well. In manual testing with 11 representative prompts, 8 simple factual questions correctly routed to small and 3 genuinely complex requests correctly routed to big.

Results are cached for 5 minutes per (agent_id, message-fingerprint) pair, so multi-turn sessions do not pay the classification cost on every turn.

On any failure (timeout, bad JSON, parse error), the classifier defaults to small rather than big. This is intentional: the small model costs less, and falling back to small for an uncategorized request is cheaper than falling back to big.

## RoutingDecision

After routing resolves, the gateway creates a `RoutingDecision` with:

```python
RoutingDecision(
    tier=Tier.SMALL,
    backend_id="small-1",       # filled after affinity scheduling
    reason=RoutingReason.CLASSIFIER,
    classifier_used=True,
    queue_wait_ms=2.4,
    affinity_hit=True,
)
```

This decision is attached to the response as `x_agent_serve` metadata so clients and the load generator can record the actual routing outcome for each request.

## Metrics

The gateway exposes these routing-related Prometheus metrics:

| Metric | Labels | Description |
|--------|--------|-------------|
| `agentserve_requests_total` | tier, reason, status | Request count by routing decision |
| `agentserve_classifier_calls_total` | outcome (success/error) | Classifier invocations |
| `agentserve_classifier_cache_hits_total` | - | Cache hits (avoided LLM calls) |
| `agentserve_routing_latency_ms` | tier | Time from request arrival to backend selection |
