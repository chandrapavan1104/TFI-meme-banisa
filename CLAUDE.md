# Project Context — TFI-meme-banisa

> UNIVERSAL CONTEXT for all AI agents (Claude, Codex, Gemini).
> This file is mirrored to AGENTS.md and GEMINI.md — keep it as the
> single source of truth for what this project is and where it stands.
>
> AGENTS: when you make a meaningful change to this project, UPDATE the
> "Current State" and "Changelog" sections below before you finish.

## Overview
**TFI-meme-banisa** — a personal Telugu movie meme/sticker store with semantic search. Users describe a scene ("actor crying in rain") and retrieve matching memes from a vector database, bypassing the browse-by-category limits of existing Telugu sticker apps (Sticker Babai, Stickers Raja).

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
- `config.py` — env config (paths, models, Qdrant mode/URL, server, jobs).
- `server/app.py` — FastAPI server: upload/search/edit/list/status endpoints, static UI.
- `server/qdrant_store.py` — Qdrant wrapper (client, upsert, filtered search). Named
  `qdrant_store` (not `qdrant_client`) to avoid shadowing the pip package.
- `server/qdrant_schema.py` — collection schema (3 named 768-dim vectors, payload indexes).
- `server/jobs.py` — asyncio job queue (CAPTION/OCR/EMBED/RE_EMBED, retries, status).
- `server/search.py` — hybrid search: vector + BM25, RRF merge, verified/rating boost.
- `collectors/captions.py` — Florence-2 captioning (flash_attn patched out for macOS).
- `collectors/ocr.py` — Tesseract Telugu OCR (tries both polarities for light-on-dark text).
- `collectors/embeddings.py` — Vyakyarth-1-Indic embeddings (lazy-loaded, 768-dim).
- `utils/transliterate.py` — Roman Telugu → native script (ITRANS).
- `db/schema.py` + `db/init.py` + `db/store.py` — SQLite schema/migrations + locked CRUD
  (one shared connection; all access serialized through a store-level RLock).
- `static/index.html` — web UI (upload w/ progress, live search, filters, edit modal, dark mode).
- `scripts/` — setup.sh, run.sh, start-qdrant.sh (optional Docker), launchd service installer.
- `tests/` — 32 unit + integration tests (real embedded Qdrant, fake or real models).

## Conventions
- Match Code-as-a-chat style: concise module docstrings, small focused modules.
- Model inference happens locally; no cloud API calls except during setup.
- All meme data stored in `~/.tfibanisa/` (images, metadata, Qdrant data).
- Async job queue for time-consuming tasks (captioning, OCR, embedding).
- Test-first for critical paths (search accuracy, metadata integrity).

## Current State
**Phases 1–5 implemented and verified live** (2026-08-18, Apple M4). All 32 tests
pass. Server runs with embedded Qdrant (no Docker needed); models downloaded and
cached; Tesseract + Telugu data installed. End-to-end verified: upload → auto
caption/OCR/embed → hybrid search (native Telugu, Roman transliteration, English
semantic, filters) all ranking correctly in <250 ms.

Key implementation decisions:
- Qdrant **embedded mode** by default (`QdrantClient(path=...)`) since Docker isn't
  installed; `QDRANT_MODE=server` + docker-compose.yml available but untested.
- One Qdrant point per meme with three optional named vectors (dialogue_te,
  dialogue_en, caption); search queries all three, merges by max score.
- Search = Qdrant vector search (payload-filtered) + SQLite FTS5 BM25, merged with
  RRF (k=60), + small verified/rating boosts.
- OCR'd Telugu text is auto-promoted to `dialogue_te` when dialogue is empty.
- Benchmarks (M4): embed 11 ms, OCR 175 ms, caption ~700 ms (<DETAILED_CAPTION>),
  vector search @500 memes ~2 ms.

## Changelog (most recent first)
- 2026-08-20 (late) — Descriptions promoted to the PRIMARY search signal:
  schema v5 adds metadata.description (own FTS column + own Qdrant vector, so
  the collection now has 4 named vectors: description/dialogue_te/dialogue_en/
  caption). Search switched to weighted RRF — description 3.0, dialogue 1.2,
  keyword 1.2, caption 0.6 — and results report matched_fields. Cluster
  descriptions now write into member memes' `description` (idempotent per
  cluster, multiple clusters accumulate) and enqueue RE_EMBED so semantic
  search updates immediately. Per-item description editable in the store's
  edit sheet and shown first in the admin inspector. scripts/reindex.py
  rebuilds the collection after vector-schema changes (run with the service
  stopped). 41 tests.
- 2026-08-20 (later) — Cluster curation tools: per-cluster descriptions (schema
  v4 face_clusters table; propagated idempotently into member memes' notes as
  "[face #N] Label: description"; FTS rebuilt to include manual_notes so
  descriptions are keyword-searchable), delete-entire-cluster (removes all
  member stickers + images + crops + index entries), and an Open action that
  filters the sticker grid by cluster with a dismissible chip. bulk_delete now
  also removes face-crop files. 39 tests.
- 2026-08-20 — Face clustering for step-by-step context labeling: schema v3
  `faces` table (embedding blobs, cluster ids, labels), face crops served at
  /faces, scripts/face_cluster.py (extract all faces -> agglomerative
  clustering, avg-linkage cosine 0.5 -> frequency-ranked clusters; 3,999 faces
  -> 484 clusters, resumable via face_scan.json). Admin "Faces" tab shows
  ranked cluster cards with sample crops + suggested names (centroid vs refs);
  naming a cluster tags all its stickers, stores the label, and folds the
  cluster's embeddings into face_refs.json so the recognizer learns. New
  GET /api/faces/clusters + POST /api/faces/clusters/{id}/label + cluster
  filter on the meme list. 38 tests.
- 2026-08-19 (late) — Admin curation page at /admin (laptop-optimized): dense
  uniform grid with adjustable tile size, filters (pack/actor/type/search +
  "untagged only" junk-candidate filter — matches memes with no face, dialogue,
  or OCR text), click/shift-click range/⌘A selection, floating action bar,
  Delete-key support, inspect lightbox, confirm-guarded bulk delete. New
  POST /api/memes/bulk_delete removes DB rows + FTS + Qdrant point + image
  file; list endpoint gains actor/untagged filters. 37 tests.
- 2026-08-19 (night) — Actor segregation via face recognition: InsightFace
  (buffalo_l ArcFace) in collectors/faces.py; per-actor references from
  Wikipedia portraits + in-domain bootstrap (scripts/build_face_refs.py, 21
  actors, refs in ~/.tfibanisa/face_refs.json); full-collection sweep
  (scripts/face_tag.py) tagged 896 memes with 932 matches (36 multi-actor,
  0 errors, threshold 0.38, one identity per face — best match only).
  New POST /api/memes/{id}/auto_tag (merge-only, never marks verified),
  FACE job in the upload pipeline, ⭐ actor chips in the UI.
- 2026-08-19 (evening) — End-user UI redesign modeled on sticker stores
  (sticker.ly/Sticker Babai): sticky rounded search + All/🖼/🎞 segmented control,
  emoji category chips that run semantic searches (Comedy/Sad/Angry/Love/...),
  horizontally scrolling pack shelf (new GET /api/packs + ?pack= list filter),
  masonry grid with GIF badges and hover quick-copy, tap-to-open bottom sheet
  with Copy/Share (Web Share API)/Save + star rating + "More like this" +
  collapsed edit form, upload moved to a FAB sheet, toasts. 34 tests.
- 2026-08-19 (later) — Static meme expansion: collection now 3,018 (2,076 static
  image memes / 942 animated), all processed, 0 job errors. New `animated` flag
  (schema v2, detected via PIL at upload, backfilled) with filters in list/search
  APIs and 🖼/🎞 toggle chips in the UI. Static-only fetch pulled 1,000 memes from
  42 packs using meme/comedian/Telugu-script keywords. Reddit (OAuth-only) and
  archive.org (no content) ruled out as extra sources.
- 2026-08-19 — Big fetch: collection now 2,018 stickers (all captioned + embedded;
  OCR text in 495, Telugu dialogue in 214; 6,063 jobs, 0 errors after recovering
  105 OCR jobs that failed under launchd's default PATH). Deployment: user installed
  the launchd service (com.tfibanisa.server, PORT=8010 via .env, plist carries a
  Homebrew PATH fix so tesseract resolves). Tailscale Serve: :443 → port 8000
  (user's Code-as-a-Chat app), :8010 → this store, :8443 → 8787. Phone URL:
  https://chandras-mac-mini.tailae1358.ts.net:8010
- 2026-08-18 (later) — Online sticker ingestion: `scripts/fetch_stickers.py` pulls
  public Telugu packs from sticker.ly's app API (search by movie/actor keywords,
  pack metadata inference, sha256 dedupe, resumable state in ~/.tfibanisa/
  fetch_state.json, source attribution in manual_notes). Upload endpoint now
  accepts context_tags/manual_notes; unfinished jobs are re-enqueued on server
  startup. NOT fetchable: Sticker Babai (app-only private backend, no public
  catalog) and Pinterest (403 without login; scraping violates their ToS).
- 2026-08-18 — Full implementation of Phases 1–5: config, SQLite schema/store,
  embedded Qdrant, FastAPI endpoints, async job queue, Florence-2 captioning,
  Tesseract Telugu OCR (dual-polarity), Vyakyarth embeddings, transliteration,
  hybrid RRF search, web UI, 32 tests, docs (README/SETUP/USAGE), launchd scripts.
  Verified live with real models + 3 sample Telugu memes.
- 2026-08-17 — Project initialized; research report completed. Tasks created for
  implementation (64–104 hours estimated).

## TODO / Next Steps
Remaining from `tasks.md` (see status notes there): Docker/Qdrant-server path
untested (1.2.3–1.2.4), OCR accuracy on a large real meme set unmeasured (3.2.3),
launchd service not yet installed/reboot-tested (5.6.3 — `./scripts/install-service.sh`).
Then: upload a real meme collection and tune search quality. Post-MVP ideas in tasks.md
(image-based search, emotion classifier, Telegram bot).
