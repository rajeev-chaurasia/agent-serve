# Model Pinning and VRAM Budget

This file is the authoritative record of which model checkpoints are deployed, the exact vLLM flags in use, and the VRAM allocation plan. Update it whenever you change a flag, swap a checkpoint, or record a HuggingFace commit hash after first download.

## Deployed Models

| Tier  | Model                                     | HF Repo                                          | Quant | GPU | VRAM Budget          | Key vLLM Flags |
|-------|-------------------------------------------|--------------------------------------------------|-------|-----|----------------------|----------------|
| big   | Qwen2.5-72B-Instruct-FP8                  | neuralmagic/Qwen2.5-72B-Instruct-FP8            | FP8   | 1   | ~72 GB weights+KV    | `--quantization fp8 --max-model-len 8192 --enable-prefix-caching --gpu-memory-utilization 0.90 --max-num-seqs 32 --enable-chunked-prefill` |
| small | Qwen2.5-7B-Instruct (×2 on GPU 0)        | Qwen/Qwen2.5-7B-Instruct                        | BF16  | 0   | ~14 GB weights+KV    | `--max-model-len 16384 --enable-prefix-caching --gpu-memory-utilization 0.45 --max-num-seqs 128` |

Using the same model family across both tiers (Qwen2.5) keeps tokenization identical, which matters for prompt-length routing thresholds and prefix-cache comparisons.

### Full vLLM Command Lines

**big (GPU 1):**
```
vllm serve neuralmagic/Qwen2.5-72B-Instruct-FP8 \
  --quantization fp8 \
  --max-model-len 8192 \
  --enable-prefix-caching \
  --gpu-memory-utilization 0.90 \
  --max-num-seqs 32 \
  --enable-chunked-prefill \
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
  --port 8002 \
  --host 0.0.0.0
```

**small-1 (GPU 0, port 8003):**
Same flags as small-0 with `--port 8003`. Two instances share GPU 0 at `gpu-memory-utilization 0.45` each; combined allocation is 86.4 GB, safely within the 96 GB budget.

## HuggingFace Commit Hashes (pin after first download)

Record the exact commit hash for each model after the first successful download to ensure reproducibility.

| Model                                      | HF Commit Hash              | Recorded Date | Recorded By |
|--------------------------------------------|-----------------------------|---------------|-------------|
| neuralmagic/Qwen2.5-72B-Instruct-FP8      | TBD — record after download | —             | —           |
| Qwen/Qwen2.5-7B-Instruct                  | TBD — record after download | —             | —           |

To record the commit hash after download:
```bash
python -c "
from huggingface_hub import model_info
for repo in ['neuralmagic/Qwen2.5-72B-Instruct-FP8', 'Qwen/Qwen2.5-7B-Instruct']:
    print(repo, model_info(repo).sha)
"
```
Paste the SHAs into the table above and commit this file.

## VRAM Budget

Both 96 GB workstation GPU GPUs (SM120) have 96 GB GDDR7 VRAM each.

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

If `neuralmagic/Qwen2.5-72B-Instruct-FP8` fails to load on SM120:

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

| Service      | Image                   | Tag / Digest | Pinned Date |
|--------------|-------------------------|--------------|-------------|
| vllm-big     | vllm/vllm-openai        | TBD          | —           |
| vllm-small-0 | vllm/vllm-openai        | TBD          | —           |
| vllm-small-1 | vllm/vllm-openai        | TBD          | —           |

To pin the digest after first successful start:
```bash
docker inspect vllm/vllm-openai:latest --format '{{.Id}}'
```
Replace `latest` in `docker-compose.yml` with the digest and update the table above.

Any change to vLLM flags must be recorded in the table above with the date and reason.
