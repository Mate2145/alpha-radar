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

# Use today's date in Europe/Budapest.
# If you want yesterday's digest instead, change this line.
DIGEST_DATE=$(TZ=Europe/Budapest date +%F)

export LLM_PROVIDER="${LLM_PROVIDER:-codex_cli}"

echo "[$(date -Is)] Starting alpha-radar digest for ${DIGEST_DATE}"

python -m app.main ingest-all
python -m app.main build-digest --date "$DIGEST_DATE"
python -m app.main export-digest --date "$DIGEST_DATE"
python -m app.main send-digest --date "$DIGEST_DATE"

echo "[$(date -Is)] Finished alpha-radar digest for ${DIGEST_DATE}"
