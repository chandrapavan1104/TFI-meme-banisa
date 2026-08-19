#!/bin/bash
# TFI-banisa one-shot setup: venv, dependencies, models, Tesseract, directories.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3.12}"
command -v "$PYTHON" >/dev/null || PYTHON=python3

echo "==> Python venv (.venv)"
[ -d .venv ] || "$PYTHON" -m venv .venv
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q

echo "==> Data directories (~/.tfibanisa)"
.venv/bin/python -c "import config; config.ensure_dirs(); print('   ', config.HOME_DIR)"

echo "==> SQLite schema"
.venv/bin/python -m db.init

echo "==> Tesseract + Telugu language data"
if ! command -v tesseract >/dev/null; then
  if command -v brew >/dev/null; then
    brew install tesseract
  else
    echo "   !! Homebrew not found — install Tesseract manually (see SETUP.md)"
  fi
fi
if command -v tesseract >/dev/null && ! tesseract --list-langs 2>/dev/null | grep -qx tel; then
  TESSDATA="$(brew --prefix 2>/dev/null || echo /usr/local)/share/tessdata"
  echo "   downloading tel.traineddata -> $TESSDATA"
  curl -sL -o "$TESSDATA/tel.traineddata" \
    https://github.com/tesseract-ocr/tessdata_best/raw/main/tel.traineddata
fi

echo "==> Downloading models (Vyakyarth ~1.1 GB, Florence-2 ~0.9 GB; cached in ~/.cache/huggingface)"
.venv/bin/python - <<'EOF'
from huggingface_hub import snapshot_download
import config
for repo in (config.EMBEDDING_MODEL, config.CAPTION_MODEL):
    print(f"    {repo}")
    snapshot_download(repo)
EOF

echo "==> Done. Start the server with: ./scripts/run.sh"
echo "    (Qdrant runs embedded by default — no Docker needed."
echo "     For a separate Qdrant server: ./scripts/start-qdrant.sh and set QDRANT_MODE=server)"
