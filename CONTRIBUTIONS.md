# Upstream Contributions Tracker

## Purpose

This file tracks OSS issues and pull requests filed from the agent-serve project. The target is at least 2 quality bug reports or feature requests plus at least 1 merged PR, primarily targeting the vLLM project. File issues when you discover real problems during Blackwell/sm_120 bring-up, benchmarking, or flag exploration.

## Contribution Log

| Date | Upstream Repo | Issue / PR | Title | Status | Link |
|------|---------------|------------|-------|--------|------|
| TBD  | vllm-project/vllm | Issue TBD | TBD — to be filed after Blackwell/sm_120 FP8 kernel testing | Not filed | — |
| TBD  | vllm-project/vllm | Issue TBD | TBD — to be filed after Blackwell/sm_120 bring-up benchmarking | Not filed | — |

## Contribution Targets

### Priority 1 — Blackwell sm_120 Issues
- FP8 GEMM kernel availability for compute capability 12.0
- Any CUDA graph capture failures specific to sm_120
- Prefix caching correctness under FP8 on Blackwell

### Priority 2 — vLLM Operational Issues
- Chunked prefill interaction with FP8 quantization
- `--enable-prefix-caching` cache hit rate metrics (confirm exposed via `/metrics`)
- Per-request token count discrepancies between vLLM and gateway estimates

### Priority 3 — Small PR Opportunities
- Documentation fixes (flag documentation gaps, README corrections)
- Missing examples for dual-GPU deployment without tensor parallelism
- Grafana dashboard contribution to vLLM's example dashboards

## Filing Guidelines

When filing an issue:
1. Include GPU model, CUDA version, vLLM version, and Docker image digest
2. Include full error traceback (from `docker compose logs <service>`)
3. Include a minimal reproduction command
4. Label appropriately (`bug`, `hardware: blackwell`, `quantization: fp8`)
5. Record the link in the table above and update status as it progresses

Status values: `Not filed` | `Open` | `In Review` | `Merged` | `Closed (won't fix)` | `Closed (duplicate)`
