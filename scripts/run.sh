#!/bin/bash
# Start the TFI-meme-banisa server (http://localhost:8000).
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && source .env && set +a
exec .venv/bin/uvicorn server.app:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
