#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# Load venv
source .venv/bin/activate

# Load .env if it exists
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

export LLM_PROVIDER="${LLM_PROVIDER:-codex_cli}"

echo "[$(date -Is)] Starting alpha-radar 6-hour broadcast digest"

python -m app.main ingest-all
python -m app.main build-window-digest --since-hours 6
python -m app.main export-window-digest
python -m app.main send-window-digest --broadcast

echo "[$(date -Is)] Finished alpha-radar 6-hour broadcast digest"
