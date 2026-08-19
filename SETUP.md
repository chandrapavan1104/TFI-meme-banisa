# Setup Guide (macOS)

## Requirements

- macOS on Apple Silicon (tested: M4, 16 GB RAM; M2/M3 fine)
- Python 3.11+ (3.12 recommended)
- ~6 GB free disk: models ~2 GB in `~/.cache/huggingface/`, plus your memes
- Homebrew (for Tesseract)
- Docker **not** required (only for the optional `QDRANT_MODE=server` setup)

## One-shot setup

```bash
./scripts/setup.sh
```

This creates `.venv`, installs Python dependencies, creates `~/.tfibanisa/`
(images, SQLite DB, Qdrant data, logs), installs Tesseract + Telugu trained
data, and downloads both models.

Then start the server:

```bash
./scripts/run.sh
```

Verify: `curl http://localhost:8000/health` — everything should read
`true`/`ok`. The web UI header also shows live status (`qdrant ✓ · embed ✓ ·
caption ✓ · ocr ✓`).

## Configuration

Copy `.env.example` to `.env` and uncomment what you need (port, data
directory, model choices, Qdrant mode). `run.sh` sources `.env` automatically.

## Always-on service (launchd)

```bash
./scripts/install-service.sh
```

Installs `com.tfibanisa.server` as a user LaunchAgent: starts at login,
restarts on crash, logs to `~/.tfibanisa/logs/launchd.*.log`. Verify after a
reboot with `curl http://localhost:8000/health`. Uninstall:

```bash
launchctl unload ~/Library/LaunchAgents/com.tfibanisa.server.plist && rm ~/Library/LaunchAgents/com.tfibanisa.server.plist
```

## Troubleshooting

**"tesseract not found" / OCR jobs error**
`brew install tesseract`, then add Telugu data:
```bash
curl -sL -o "$(brew --prefix)/share/tessdata/tel.traineddata" https://github.com/tesseract-ocr/tessdata_best/raw/main/tel.traineddata
```
Check with `tesseract --list-langs` (must include `tel`).

**Model download fails / is slow**
Re-run `./scripts/setup.sh` — downloads resume. Behind a proxy, set
`HF_ENDPOINT`/`HTTPS_PROXY`. Models cache in `~/.cache/huggingface/hub/`.

**Port 8000 already in use**
Set `PORT=8010` in `.env` (or export it) and restart.

**"Storage folder ~/.tfibanisa/qdrant is already accessed by another instance"**
Embedded Qdrant allows one process at a time. Stop the other server instance,
or run a Qdrant server (`./scripts/start-qdrant.sh`, `QDRANT_MODE=server`)
which supports many clients.

**Florence-2 errors mentioning `flash_attn`**
Handled automatically (the import is patched out on macOS). If you see it,
check `transformers` is <4.50: `.venv/bin/pip show transformers`.

**Search returns nothing right after upload**
Captioning/OCR/embedding run in the background — check
`/api/memes/{id}/status`. Results appear once the EMBED job finishes.

**Logs**
`~/.tfibanisa/logs/tfibanisa.log` (rotates daily, 14 days kept).
