#!/bin/bash
# Start Qdrant as a Docker service (only needed with QDRANT_MODE=server;
# the default embedded mode needs no Docker).
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d
echo "Waiting for Qdrant..."
for _ in $(seq 1 30); do
  if curl -sf http://localhost:6333/healthz >/dev/null; then
    echo "Qdrant healthy at http://localhost:6333"
    exit 0
  fi
  sleep 1
done
echo "Qdrant did not become healthy in 30s" >&2
exit 1
