# Model Pinning and VRAM Budget

This file is the authoritative record of which model checkpoints are deployed, the exact vLLM flags in use, and the VRAM allocation plan. Update it whenever you change a flag, swap a checkpoint, or record a HuggingFace commit hash after first download.

## Deployed Models

| Tier  | Model                                     | HF Repo                                          | Quant | GPU | VRAM Budget          | Key vLLM Flags |
|-------|-------------------------------------------|--------------------------------------------------|-------|-----|----------------------|----------------|
| big   | Qwen2.5-72B-Instruct-FP8-dynamic          | RedHatAI/Qwen2.5-72B-Instruct-FP8-dynamic        | FP8   | 1   | ~72 GB weights+KV    | `--max-model-len 8192 --enable-prefix-caching --gpu-memory-utilization 0.90 --max-num-seqs 32 --enable-chunked-prefill --enable-auto-tool-choice --tool-call-parser hermes` |
| small | Qwen2.5-7B-Instruct (×2 on GPU 0)        | Qwen/Qwen2.5-7B-Instruct                        | BF16  | 0   | ~14 GB weights+KV    | `--max-model-len 16384 --enable-prefix-caching --gpu-memory-utilization 0.45 --max-num-seqs 128 --enable-auto-tool-choice --tool-call-parser hermes` |

Using the same model family across both tiers (Qwen2.5) keeps tokenization identical, which matters for prompt-length routing thresholds and prefix-cache comparisons.

### Full vLLM Command Lines

**big (GPU 1):**
```
vllm serve RedHatAI/Qwen2.5-72B-Instruct-FP8-dynamic \
  --max-model-len 8192 \
  --enable-prefix-caching \
  --gpu-memory-utilization 0.90 \
  --max-num-seqs 32 \
  --enable-chunked-prefill \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --port 8001 \
  --host 0.0.0.0
```

**small-0 (GPU 0, port 8002):**
```
vllm serve Qwen/Qwen2.5-7B-Instruct \
  --max-model-len 16384 \
  --enable-prefix-caching \
  --gpu-memory-utilization 0.45 \
  --max-num-seqs 128 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --port 8002 \
  --host 0.0.0.0
```

**small-1 (GPU 0, port 8003):**
Same flags as small-0 except `--port 8003 --max-model-len 14000 --gpu-memory-utilization 0.43`.
Reduced from 0.45 because both instances share GPU 0 and CUDA graph capture (during small-0 startup)
temporarily holds additional memory, leaving small-1 with insufficient KV budget at 0.45/16384.
At 0.43/14000, the combined allocation is (0.45+0.43)×96 = 84.5 GB, within the 96 GB budget.

## HuggingFace Commit Hashes (pin after first download)

Record the exact commit hash for each model after the first successful download to ensure reproducibility.

| Model                                      | HF Commit Hash              | Recorded Date | Recorded By |
|--------------------------------------------|-----------------------------|---------------|-------------|
| RedHatAI/Qwen2.5-72B-Instruct-FP8-dynamic | 4d9910ef10cf92b072dad8ce7c2a2929fac4fe0f | 2026-08-07 | rchaurasia |
| Qwen/Qwen2.5-7B-Instruct                  | a09a35458c702b33eeacc393d103063234e8bc28 | 2026-08-07 | rchaurasia |

To record the commit hash after download:
```bash
python -c "
from huggingface_hub import model_info
for repo in ['RedHatAI/Qwen2.5-72B-Instruct-FP8-dynamic', 'Qwen/Qwen2.5-7B-Instruct']:
    print(repo, model_info(repo).sha)
"
```
Paste the SHAs into the table above and commit this file.

## VRAM Budget

Both RTX PRO 6000 Blackwell GPUs (SM120) have 96 GB GDDR7 VRAM each.

| GPU | Usage                                       | Allocation  | Notes |
|-----|---------------------------------------------|-------------|-------|
| 0   | Display driver overhead                     | ~700 MB     | GPU 0 is also the display GPU |
| 0   | Qwen2.5-7B-Instruct small-0 weights (BF16) | ~14 GB      | ~7B × 2 bytes |
| 0   | Qwen2.5-7B-Instruct small-1 weights (BF16) | ~14 GB      | second instance |
| 0   | KV cache, both small instances             | ~58 GB      | 2 × 0.45 × 96 = 86.4 GB budget; weights leave ~58 GB for KV |
| 0   | Headroom                                   | ~9 GB       | safety buffer |
| 1   | Qwen2.5-72B-Instruct-FP8 weights           | ~72 GB      | 72B × 1 byte FP8 |
| 1   | KV cache (big, 32 seqs)                    | ~14 GB      | 0.90 × 96 = 86.4 GB budget; 86.4 - 72 = 14.4 GB KV |
| 1   | Headroom                                   | ~9 GB       | includes CUDA libs, activation buffers |

> Monitor live allocation with `nvidia-smi` and the Grafana "KV cache usage %" panel after startup.

## Fallback Plan

If `RedHatAI/Qwen2.5-72B-Instruct-FP8-dynamic` fails to load on SM120:

1. **First fallback**: `Qwen/Qwen2.5-32B-Instruct` with `--quantization fp8`
   - ~16 GB weights (FP8), much more KV headroom
   - Change `MODEL_BIG` in `.env` or `configs/vllm-big.env`

2. **Second fallback**: `Qwen/Qwen2.5-72B-Instruct-AWQ`
   - AWQ 4-bit kernels have broader GPU compatibility than FP8
   - Replace `--quantization fp8` with `--quantization awq`
   - VRAM: ~36 GB for 72B AWQ, leaves ~50 GB for KV cache

3. **If all 72B options fail**: `Qwen/Qwen2.5-32B-Instruct` BF16, split across both GPUs with `--tensor-parallel-size 2`

File a GitHub issue against vllm-project/vllm for any SM120 FP8 failures and record it in `CONTRIBUTIONS.md`.

## vLLM Version Pinning

The vLLM image tag is `latest` during initial bring-up. Pin to a specific digest here after the first healthy boot.

| Service      | Image            | Tag / Digest                                                              | Pinned Date |
|--------------|------------------|---------------------------------------------------------------------------|-------------|
| vllm-big     | vllm/vllm-openai | sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52   | 2026-08-07  |
| vllm-small-0 | vllm/vllm-openai | sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52   | 2026-08-07  |
| vllm-small-1 | vllm/vllm-openai | sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52   | 2026-08-07  |

vLLM version: **0.26.0** (confirmed from container logs). All three services run the same image.

To update the pinned digest after a vLLM upgrade:
```bash
docker inspect vllm/vllm-openai:latest --format '{{.Id}}'
```
Replace the digest in the table above and update `docker-compose.yml` accordingly.

Any change to vLLM flags must be recorded in the table above with the date and reason.
