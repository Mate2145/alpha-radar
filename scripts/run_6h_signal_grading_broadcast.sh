#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

LOG_DIR="data/signal-grading/schedule-logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/6h-signal-grading-broadcast-$(date -u +%Y%m%dT%H%M%SZ).log"

exec > >(tee -a "$LOG_FILE") 2>&1

# Load venv
source .venv/bin/activate

# Load .env if it exists
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

export LLM_PROVIDER="${LLM_PROVIDER:-codex_cli}"

echo "[$(date -Is)] Starting alpha-radar 6-hour signal grading broadcast pipeline"
echo "[$(date -Is)] Schedule log: $LOG_FILE"
echo "[$(date -Is)] LLM_PROVIDER=${LLM_PROVIDER}"
echo "[$(date -Is)] CODEX_MODEL=${CODEX_MODEL:-unset}"

WINDOW_TO="$(date -u +%Y-%m-%dT%H:%M:%S)"
WINDOW_FROM="$(date -u -d '6 hours ago' +%Y-%m-%dT%H:%M:%S)"

echo "[$(date -Is)] Window from: $WINDOW_FROM"
echo "[$(date -Is)] Window to: $WINDOW_TO"

python -m app.main ingest-all
.venv/bin/python scripts/run_signal_grading.py --from-to "$WINDOW_FROM" "$WINDOW_TO"
python -m app.main build-window-digest --from "$WINDOW_FROM" --to "$WINDOW_TO"
python -m app.main export-window-digest
python -m app.main send-window-digest --broadcast

echo "[$(date -Is)] Finished alpha-radar 6-hour signal grading broadcast pipeline"
