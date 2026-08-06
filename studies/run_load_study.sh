#!/usr/bin/env bash
# Load study orchestration script.
# Run this after docker compose is up and both backends are healthy.
# Output: studies/results/<run-id>/ with CSVs, manifest.json, and plots.

set -euo pipefail

GATEWAY_URL=${GATEWAY_URL:-http://localhost:8000}
RUN_ID=${RUN_ID:-$(date +%Y%m%d_%H%M%S)}
RESULTS_DIR="studies/results/${RUN_ID}"
WARMUP_SECONDS=${WARMUP_SECONDS:-120}
REPS=${REPS:-3}

mkdir -p "${RESULTS_DIR}"

log() { echo "[study] $(date +%H:%M:%S) $*"; }

# ---- GPU clock locking ----
# Uncomment and set appropriate base clock for your 96 GB workstation GPU
# Requires sudo. Run once before the study, unlock after.
# sudo nvidia-smi -lgc 2100 -i 0
# sudo nvidia-smi -lgc 2100 -i 1

log "Checking gateway health..."
curl -sf "${GATEWAY_URL}/healthz" | grep -q "ok" || { echo "Gateway not healthy. Abort."; exit 1; }

# ---- Warm-up ----
log "Warming up for ${WARMUP_SECONDS}s..."
python3 -m loadgen.generator \
  --gateway-url "${GATEWAY_URL}" \
  --profile loadgen/profiles/steady.yaml \
  --output "${RESULTS_DIR}/warmup.csv" &
WARMUP_PID=$!
sleep "${WARMUP_SECONDS}"
kill $WARMUP_PID 2>/dev/null || true
log "Warm-up complete."

# ---- Study 1: Saturation sweep ----
log "=== Study 1: Saturation sweep ==="
for CONCURRENCY in 1 2 4 8 16 24 32; do
  log "  concurrency=${CONCURRENCY}"
  for REP in $(seq 1 "${REPS}"); do
    python3 -c "
import asyncio, yaml, pathlib, sys
from loadgen.models import ProfileConfig, LoadMode, TurnSpec
from loadgen.generator import LoadGenerator
p = ProfileConfig(
  name='saturation',
  description='saturation sweep',
  mode=LoadMode.CLOSED_LOOP,
  concurrency=${CONCURRENCY},
  total_sessions=${CONCURRENCY} * 5,
  think_time_seconds=0.0,
  turn_spec=TurnSpec(min_turns=3, max_turns=3),
)
gen = LoadGenerator('${GATEWAY_URL}', p)
asyncio.run(gen.run(pathlib.Path('${RESULTS_DIR}/sat_c${CONCURRENCY}_r${REP}.csv')))
"
  done
done

# ---- Study 2: Affinity (deep sessions) ----
log "=== Study 2: Affinity — deep sessions ==="
for REP in $(seq 1 "${REPS}"); do
  python3 -m loadgen.generator \
    --gateway-url "${GATEWAY_URL}" \
    --profile loadgen/profiles/deep_sessions.yaml \
    --output "${RESULTS_DIR}/affinity_on_r${REP}.csv"
done
# Affinity OFF: set GATEWAY_AFFINITY_ENABLED=false and restart gateway, then re-run
# (documented in RUNBOOK.md — owner runs this manually)

# ---- Study 3: Routing economics (mixed profile) ----
log "=== Study 3: Routing economics ==="
for REP in $(seq 1 "${REPS}"); do
  python3 -m loadgen.generator \
    --gateway-url "${GATEWAY_URL}" \
    --profile loadgen/profiles/mixed.yaml \
    --output "${RESULTS_DIR}/mixed_r${REP}.csv"
done

# ---- Manifest ----
log "Writing manifest..."
python3 -c "
import json, subprocess, datetime, pathlib
manifest = {
  'run_id': '${RUN_ID}',
  'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
  'gateway_url': '${GATEWAY_URL}',
  'git_sha': subprocess.getoutput('git rev-parse --short HEAD'),
  'reps': ${REPS},
  'warmup_seconds': ${WARMUP_SECONDS},
}
pathlib.Path('${RESULTS_DIR}/manifest.json').write_text(json.dumps(manifest, indent=2))
"

# ---- Analysis ----
log "Running analysis..."
python3 studies/analysis.py --results-dir "${RESULTS_DIR}" --run-id "${RUN_ID}"

log "Study complete. Results in ${RESULTS_DIR}/"
