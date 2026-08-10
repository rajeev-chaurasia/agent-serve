#!/usr/bin/env bash
# Load study wrapper. Run after docker compose is up and all backends are healthy.
# Results go to studies/results/<run-id>/ as CSV files and summary.json.
#
# Usage:
#   bash studies/run_load_study.sh [--skip-drill]
#
# Options:
#   --skip-drill  Skip the failure drill (avoids stopping a container)
#
# Override the gateway URL:
#   GATEWAY_URL=http://myhost:8000 bash studies/run_load_study.sh

set -euo pipefail
cd "$(dirname "$0")/.."

GATEWAY_URL=${GATEWAY_URL:-http://localhost:8000}
SKIP_DRILL=""

for arg in "$@"; do
  case "$arg" in
    --skip-drill) SKIP_DRILL="--skip-drill" ;;
  esac
done

log() { echo "[study] $(date +%H:%M:%S) $*"; }

log "Checking gateway health..."
curl -sf "${GATEWAY_URL}/healthz" | grep -q "ok" || { echo "Gateway not healthy. Abort."; exit 1; }
log "Gateway healthy."

# Optional: lock GPU clocks before running for more stable measurements.
# Uncomment and set the clock frequency for your GPU.
# Requires sudo. Run once before the study, unlock after.
# sudo nvidia-smi -lgc 2520 -i 0
# sudo nvidia-smi -lgc 2520 -i 1

log "Starting study..."
python3 studies/run_study.py --gateway-url "${GATEWAY_URL}" ${SKIP_DRILL}

log "Done."
