# Upstream Contributions Tracker

## Purpose

This file tracks OSS issues and pull requests filed from the agent-serve project. The target is at least 2 quality bug reports or feature requests plus at least 1 merged PR, primarily targeting the vLLM project. File issues when you discover real problems during sm_120 bring-up, benchmarking, or flag exploration.

## Contribution Log

| Date | Upstream Repo | Issue / PR | Title | Status | Link |
|------|---------------|------------|-------|--------|------|
| 2026-08-07 | vllm-project/vllm | Issue — docs | `CUDA_VISIBLE_DEVICES` vs Docker `device_ids` re-indexing causes NVMLError_InvalidArgument on sm_120 | To file | — |
| 2026-08-07 | vllm-project/vllm | Issue — docs | Serving `compressed-tensors` FP8 models (RedHatAI/neuralmagic) must NOT use `--quantization fp8`; auto-detected from config.json | To file | — |

## Contribution Targets

### Priority 1 — sm_120 Issues
- FP8 GEMM kernel availability for compute capability 12.0
- Any CUDA graph capture failures specific to sm_120
- Prefix caching correctness under FP8 on sm_120

### Priority 2 — vLLM Operational Issues
- Chunked prefill interaction with FP8 quantization
- `--enable-prefix-caching` cache hit rate metrics (confirm exposed via `/metrics`)
- Per-request token count discrepancies between vLLM and gateway estimates

### Priority 3 — Small PR Opportunities
- Documentation fixes (flag documentation gaps, README corrections)
- Missing examples for dual-GPU deployment without tensor parallelism
- Grafana dashboard contribution to vLLM's example dashboards

## Issue Drafts

### Issue 1: CUDA_VISIBLE_DEVICES + Docker device_ids re-indexing trap

**Repo:** vllm-project/vllm  
**Labels:** `bug`, `documentation`

**Summary:**  
When Docker Compose assigns a GPU via `device_ids: ["1"]`, Docker re-indexes that GPU as
`CUDA_VISIBLE_DEVICES=0` inside the container. Setting `CUDA_VISIBLE_DEVICES=1` in the env file
on top of that causes an `NVMLError_InvalidArgument` crash because the container sees only one
GPU (index 0) but the env var requests index 1.

**Reproduction:**
```yaml
# docker-compose.yml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          device_ids: ["1"]   # physical GPU 1 → mapped to container index 0
          capabilities: [gpu]
```
```env
# vllm-big.env — WRONG
CUDA_VISIBLE_DEVICES=1   # crashes; physical GPU 1 is already index 0 inside container
```
**Fix:** Always set `CUDA_VISIBLE_DEVICES=0` when a single GPU is passed via `device_ids`.

**Environment:** sm_120 GPU, CUDA 12.8, vLLM 0.26.0, Docker 27.x

---

### Issue 2: compressed-tensors FP8 models must not use --quantization fp8

**Repo:** vllm-project/vllm  
**Labels:** `documentation`, `quantization: fp8`

**Summary:**  
Models in RedHatAI/neuralmagic `compressed-tensors` FP8 format (e.g.
`RedHatAI/Qwen2.5-72B-Instruct-FP8-dynamic`) embed quantization config in `config.json`.
Passing `--quantization fp8` causes a Pydantic `ValidationError` on startup because vLLM
tries to apply a second quantization pass over an already-quantized model. The correct
invocation omits the flag entirely — vLLM auto-detects `compressed-tensors` from the config.

**Reproduction:**
```bash
# WRONG — crashes with ValidationError
vllm serve RedHatAI/Qwen2.5-72B-Instruct-FP8-dynamic --quantization fp8

# CORRECT
vllm serve RedHatAI/Qwen2.5-72B-Instruct-FP8-dynamic
```

**Suggestion:** Add a warning when `--quantization fp8` is combined with a model that already
has a `quantization_config` in its `config.json`, or document this in the FP8 serving guide.

**Environment:** sm_120 GPU, CUDA 12.8, vLLM 0.26.0

---

## Filing Guidelines

When filing an issue:
1. Include GPU model, CUDA version, vLLM version, and Docker image digest
2. Include full error traceback (from `docker compose logs <service>`)
3. Include a minimal reproduction command
4. Label appropriately (`bug`, `quantization: fp8`)
5. Record the link in the table above and update status as it progresses

Status values: `Not filed` | `Open` | `In Review` | `Merged` | `Closed (won't fix)` | `Closed (duplicate)`
