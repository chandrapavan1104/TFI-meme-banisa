# Project Context — TFI-banisa

> UNIVERSAL CONTEXT for all AI agents (Claude, Codex, Gemini).
> This file is mirrored to AGENTS.md and GEMINI.md — keep it as the
> single source of truth for what this project is and where it stands.
>
> AGENTS: when you make a meaningful change to this project, UPDATE the
> "Current State" and "Changelog" sections below before you finish.

## Overview
**TFI-banisa** — a personal Telugu movie meme/sticker store with semantic search. Users describe a scene ("actor crying in rain") and retrieve matching memes from a vector database, bypassing the browse-by-category limits of existing Telugu sticker apps (Sticker Babai, Stickers Raja).

Combines **image captioning** (Florence-2) + **OCR** (Tesseract, Telugu) + **multilingual embeddings** (Vyakyarth-1-Indic) + **self-hosted vector DB** (Qdrant) to deliver semantic search with zero cloud cost and full privacy.

## Tech Stack
- **Backend:** Python 3.11+, FastAPI, uvicorn.
- **Vector DB:** Qdrant (self-hosted, Docker).
- **Embeddings:** Vyakyarth-1-Indic (text, 768-dim, Telugu-native).
- **Image Captioning:** Florence-2-base (250M, ~200 ms/image on M3).
- **OCR:** Tesseract + Telugu training data.
- **Storage:** SQLite (metadata) + local filesystem (images).
- **Optional:** Ollama (local model serving).

## Architecture / Key Files
**Planned (during implementation):**
- `config.py` — environment config (paths, model names, Qdrant URL).
- `server/app.py` — FastAPI server with `/api/memes/*` endpoints.
- `server/qdrant_client.py` — Qdrant wrapper (search, upsert, schema).
- `collectors/captions.py` — Florence-2 image captioning.
- `collectors/ocr.py` — Tesseract OCR for Telugu text.
- `collectors/embeddings.py` — Vyakyarth-1-Indic text embedding.
- `db/schema.py` — SQLite schema for metadata + meme records.
- `static/index.html` — web UI (upload, search, edit).
- `scripts/setup.sh` — environment + Docker initialization.
- `tests/` — unit + integration tests.

## Conventions
- Match Code-as-a-chat style: concise module docstrings, small focused modules.
- Model inference happens locally; no cloud API calls except during setup.
- All meme data stored in `~/.tfibanisa/` (images, metadata, Qdrant data).
- Async job queue for time-consuming tasks (captioning, OCR, embedding).
- Test-first for critical paths (search accuracy, metadata integrity).

## Current State
**Bootstrap phase.** Repository created, no code yet. Research report complete
(telugu-meme-store-research.md in Code-as-a-chat repo provides full design).

Ready to begin **Phase 1: Setup** (Docker, environment, database schema).

## Changelog (most recent first)
- 2026-08-17 — Project initialized; research report completed. Tasks created for
  implementation (64–104 hours estimated).

## TODO / Next Steps
See `tasks.md` for detailed implementation roadmap (Phases 1–5, ~3 weeks).

**Immediate priorities:**
1. Phase 1: Environment setup + Qdrant + database schema (4–8 hrs).
2. Phase 2: Core API endpoints (16–24 hrs).
3. Phase 3: Auto-tagging pipeline (12–16 hrs).
