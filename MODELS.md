# Model Pinning and VRAM Budget

This file is the authoritative record of which model checkpoints are deployed, the exact vLLM flags in use, and the VRAM allocation plan. Update it whenever you change a flag, swap a checkpoint, or record a HuggingFace commit hash after first download.

## Deployed Models

| Tier  | Model                                   | HF Repo                                      | Quant | GPU | VRAM Budget       | Key vLLM Flags |
|-------|-----------------------------------------|----------------------------------------------|-------|-----|-------------------|----------------|
| big   | Llama-3.3-70B-Instruct                  | meta-llama/Llama-3.3-70B-Instruct            | FP8   | 1   | ~70 GB weights+KV | `--quantization fp8 --max-model-len 16384 --enable-prefix-caching --gpu-memory-utilization 0.92 --max-num-seqs 64 --enable-chunked-prefill` |
| small | Qwen2.5-7B-Instruct                     | Qwen/Qwen2.5-7B-Instruct                    | BF16  | 0   | ~14 GB weights+KV | `--max-model-len 16384 --enable-prefix-caching --gpu-memory-utilization 0.55 --max-num-seqs 128` |

### Full vLLM Command Lines

**big (GPU 1):**
```
python -m vllm.entrypoints.openai.api_server \
  --model meta-llama/Llama-3.3-70B-Instruct \
  --quantization fp8 \
  --max-model-len 16384 \
  --enable-prefix-caching \
  --gpu-memory-utilization 0.92 \
  --max-num-seqs 64 \
  --enable-chunked-prefill \
  --port 8001 \
  --host 0.0.0.0
```

**small (GPU 0):**
```
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-7B-Instruct \
  --max-model-len 16384 \
  --enable-prefix-caching \
  --gpu-memory-utilization 0.55 \
  --max-num-seqs 128 \
  --port 8002 \
  --host 0.0.0.0
```

## HuggingFace Commit Hashes (pin after first download)

Record the exact commit hash for each model after the first successful download to ensure reproducibility.

| Model                                 | HF Commit Hash              | Recorded Date | Recorded By |
|---------------------------------------|-----------------------------|---------------|-------------|
| meta-llama/Llama-3.3-70B-Instruct    | TBD — record after download | —             | —           |
| Qwen/Qwen2.5-7B-Instruct             | TBD — record after download | —             | —           |

To record the commit hash after download:
```bash
# From inside the container or on the host with huggingface_hub installed
python -c "
from huggingface_hub import model_info
info = model_info('meta-llama/Llama-3.3-70B-Instruct')
print(info.sha)
"
```
Then paste the SHA into the table above and commit this file.

## VRAM Budget

Both RTX PRO 6000 Blackwell GPUs have 96 GB GDDR7 VRAM each.

| GPU | Usage                          | Allocation  | Notes |
|-----|--------------------------------|-------------|-------|
| 0   | Display driver overhead        | ~700 MB     | GPU 0 is also the display GPU; driver headroom reserved |
| 0   | Qwen2.5-7B-Instruct (BF16)    | ~14 GB      | ~7B params × 2 bytes |
| 0   | KV cache (small, 128 seqs)    | ~28 GB      | gpu-memory-utilization 0.55 leaves ~53 GB; KV fills remainder |
| 0   | Free headroom                 | ~53 GB      | Buffer for KV growth and CUDA libs |
| 1   | Llama-3.3-70B-Instruct (FP8)  | ~35 GB      | ~70B params × 0.5 bytes |
| 1   | KV cache (big, 64 seqs)       | ~53 GB      | gpu-memory-utilization 0.92 allocates ~88 GB total |
| 1   | Free headroom                 | ~8 GB       | Safety margin |

> Note: KV cache sizes are estimates; vLLM allocates remaining VRAM after loading weights. Monitor with `nvidia-smi` and the Grafana "KV cache usage %" panel.

## Fallback Plan

If the 70B FP8 model fails to load on Blackwell (sm_120 architecture) due to missing kernel support in the pinned vLLM version:

1. **First fallback**: `Qwen/Qwen2.5-32B-Instruct` with FP8 quantization on GPU 1
   - ~16 GB weights (FP8), more headroom for KV cache
   - Change `MODEL_BIG` in `.env` and `VLLM_ARGS` in `configs/vllm-big.env`

2. **Second fallback**: `meta-llama/Llama-3.3-70B-Instruct-AWQ` (or Meta's official AWQ checkpoint)
   - AWQ kernels have broader GPU compatibility than FP8 kernels
   - Replace `--quantization fp8` with `--quantization awq` in `configs/vllm-big.env`
   - VRAM: ~35 GB for 70B AWQ (4-bit), leaves more KV budget

3. **If all 70B options fail**: run two instances of `Qwen/Qwen2.5-32B-Instruct` BF16 split across both GPUs using tensor parallelism (`--tensor-parallel-size 2`)

File a GitHub issue against vllm-project/vllm for any sm_120 FP8 failures and record it in `CONTRIBUTIONS.md`.

## vLLM Version Pinning

The vLLM version is pinned in `docker-compose.yml` via the image tag. Record the exact image digest here after first deployment:

| Service      | Image                        | Tag / Digest | Pinned Date |
|--------------|------------------------------|--------------|-------------|
| vllm-big     | vllm/vllm-openai             | TBD          | —           |
| vllm-small-0 | vllm/vllm-openai             | TBD          | —           |

To record the digest:
```bash
docker inspect vllm/vllm-openai:<tag> --format '{{.Id}}'
```

Any change to vLLM flags must be recorded in the table above with the date and the reason for the change.
