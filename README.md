# TFI-banisa

A personal **Telugu movie meme/sticker store with semantic search**. Describe a
scene — *"actor crying in rain"*, *"చిరంజీవి కన్నీళ్లు"*, or Roman-script
*"ee jeevitham oka samaram"* — and retrieve matching memes from your own
collection. Everything runs locally: no cloud calls, no data leaves your Mac.

## How it works

```
                     upload image
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        Florence-2    Tesseract   your metadata
        (caption)    (Telugu OCR)  (movie, actors, tags)
              └───────────┼───────────┘
                          ▼
              Vyakyarth-1-Indic embeddings
              (dialogue_te / dialogue_en / caption, 768-dim each)
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
        Qdrant (vectors)      SQLite (metadata + FTS5 BM25)
              └───────────┬───────────┘
                          ▼
            hybrid search: vector + keyword,
            merged with Reciprocal Rank Fusion
```

- **Upload** an image → it's stored under `~/.tfibanisa/images/`, and three
  background jobs run: captioning, OCR, embedding. Telugu text found by OCR is
  auto-promoted to the searchable dialogue field.
- **Search** embeds your query (transliterating Roman Telugu to native script
  first), runs a filtered vector search in Qdrant plus a BM25 keyword search
  in SQLite, and merges both rankings with RRF. Verified and highly-rated
  memes get a boost.
- **Edit** any meme's metadata in the web UI; it re-embeds automatically and
  is marked verified.

## Quick start

```bash
./scripts/setup.sh      # venv, deps, models (~2 GB), Tesseract, data dirs
./scripts/run.sh        # serve http://localhost:8000
```

Open http://localhost:8000 — upload memes, then search.

Qdrant runs **embedded** (inside the server process, persisted to
`~/.tfibanisa/qdrant/`) — no Docker required. To use a separate Qdrant server
instead: `./scripts/start-qdrant.sh` (Docker) and set `QDRANT_MODE=server`.

To keep it running permanently: `./scripts/install-service.sh` (launchd:
starts on login, restarts on crash).

## API reference

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Qdrant + model cache status |
| POST | `/api/memes/upload` | multipart: `file` + optional `movie_title_en/te`, `dialogue_te/en`, `actors`, `emotion_tags` (comma-sep) |
| POST | `/api/memes/search` | JSON: `{query, emotions?, actors?, movie?, limit?}` |
| GET | `/api/memes?limit=&offset=&verified=` | paginated list |
| GET | `/api/memes/{id}` | full metadata + image URL |
| POST | `/api/memes/{id}/edit` | partial metadata update (marks verified, re-embeds) |
| POST | `/api/memes/{id}/rate` | `{rating: 1-5}` |
| GET | `/api/memes/{id}/status` | async job progress `{status, progress, errors}` |
| GET | `/api/movies` / `/api/actors` / `/api/emotions` | distinct values for filters |
| GET | `/api/analytics/top_queries` | most common searches |

Example search:

```bash
curl -X POST localhost:8000/api/memes/search \
  -H 'Content-Type: application/json' \
  -d '{"query": "sad scene in rain", "emotions": ["sad"], "limit": 5}'
```

Results include per-hit `score` and `reasons` (`vector_score`, `keyword_rank`,
`verified`) so you can see why something ranked.

## Models & limitations

| Component | Model | Notes |
|-----------|-------|-------|
| Text embeddings | [krutrim-ai-labs/Vyakyarth](https://huggingface.co/krutrim-ai-labs/Vyakyarth) (768-dim) | Telugu-native; handles cross-lingual and transliterated queries |
| Captioning | [microsoft/Florence-2-base](https://huggingface.co/microsoft/Florence-2-base) | task configurable via `CAPTION_TASK`; English captions only |
| OCR | Tesseract 5 + `tel.traineddata` | 60–80% on stylized meme text; both polarities tried automatically |
| Vector DB | Qdrant (embedded or Docker) | cosine similarity, payload-filtered |

Limitations: OCR struggles with heavily stylized/outlined fonts (edit the
dialogue manually — that also marks the meme verified); transliteration uses
the ITRANS scheme, which approximates casual romanization; captions are
English-only (they're embedded with the same multilingual model, so Telugu
queries still match them reasonably).

## Measured performance (Apple M4, 16 GB)

| Operation | Latency | Target |
|-----------|---------|--------|
| Embed one text | ~11 ms | <100 ms ✅ |
| OCR one image | ~175 ms | <200 ms ✅ |
| Caption one image (`<DETAILED_CAPTION>`) | ~700 ms | <500 ms ⚠️ (use `CAPTION_TASK=<CAPTION>` for ~400 ms) |
| Hybrid search (3-meme collection, end-to-end) | 150–200 ms | <1 s ✅ |
| Vector search @ 500 memes (embedded Qdrant) | ~2 ms median | <1 s ✅ |
| Model load (first request) | ~6 s embed, ~4 s caption | one-time |

Memory: ~3–4 GB with both models resident.

## Development

```bash
.venv/bin/python -m pytest tests/       # 32 tests; model tests auto-skip if models missing
```

See [SETUP.md](SETUP.md) for troubleshooting and [USAGE.md](USAGE.md) for a
user guide. Layout: `server/` (FastAPI, Qdrant, jobs, hybrid search),
`collectors/` (caption/OCR/embedding), `db/` (SQLite schema + store),
`utils/` (transliteration), `static/` (web UI), `scripts/` (setup/run/service).
