# TFI-banisa Implementation Tasks

**Estimated Total:** 64–104 hours | **Timeline:** 2–3 weeks (full-time) or 8–15 weeks (part-time, 5–10 hrs/week)

---

## Phase 1: Setup & Infrastructure (4–8 hours)

### 1.1 Environment & Dependencies Setup
- [ ] **1.1.1** Create `.env.example` with all required variables (Qdrant URL, model paths, storage paths, FastAPI config)
- [ ] **1.1.2** Create `requirements.txt` with all Python dependencies (qdrant-client, fastapi, uvicorn, sentence-transformers, transformers, pillow, pytesseract, indic-transliteration)
- [ ] **1.1.3** Create `setup.sh` script to:
  - [ ] Initialize Python `.venv`
  - [ ] Install Python dependencies
  - [ ] Download pre-trained models (Vyakyarth-1-Indic, Florence-2-base, Tesseract Telugu data)
  - [ ] Create required directories (`~/.tfibanisa/images`, `~/.tfibanisa/db`, etc.)
- [ ] **1.1.4** Test script on Mac Mini; document any missing dependencies

### 1.2 Docker & Qdrant Setup
- [ ] **1.2.1** Create `docker-compose.yml` with Qdrant service (port 6333, persistent volume)
- [ ] **1.2.2** Write startup script `./start-qdrant.sh` (one-liner: `docker-compose up -d`)
- [ ] **1.2.3** Verify Qdrant health check endpoint (`GET http://localhost:6333/health`)
- [ ] **1.2.4** Document resource requirements (RAM, disk) and tested performance

### 1.3 Database Schema & SQLite Setup
- [ ] **1.3.1** Create `db/schema.py` with SQLite table definitions:
  - [ ] `memes` table (id, image_path, upload_date, auto_generated, verified)
  - [ ] `metadata` table (meme_id, movie_title_te, movie_title_en, actors, dialogue_te, dialogue_en, dialogue_roman, emotion_tags, context_tags, manual_notes)
  - [ ] `embeddings_log` table (meme_id, embedding_model, text_vector_type, timestamp)
  - [ ] Migration version tracking
- [ ] **1.3.2** Create `db/init.py` to initialize DB on first run
- [ ] **1.3.3** Write unit tests for schema creation and migration

### 1.4 Qdrant Collection Schema
- [ ] **1.4.1** Create `server/qdrant_schema.py` to define:
  - [ ] Collection name: `telugu_memes`
  - [ ] Vector size: 768 (Vyakyarth-1-Indic)
  - [ ] Distance metric: COSINE
  - [ ] Payload schema (movie, actors, emotions, etc.)
- [ ] **1.4.2** Create client helper methods:
  - [ ] `create_collection_if_not_exists()`
  - [ ] `verify_collection_ready()`
  - [ ] `delete_collection()` (for testing)
- [ ] **1.4.3** Test collection creation and teardown

### 1.5 Config & Logging Setup
- [ ] **1.5.1** Create `config.py` with all environment variables and defaults
- [ ] **1.5.2** Set up structured logging (file + console, FastAPI request logging)
- [ ] **1.5.3** Create `log/` directory and rotation policy

**Phase 1 Acceptance Criteria:**
- ✅ `./setup.sh` runs without error
- ✅ Qdrant running on localhost:6333
- ✅ SQLite database initialized at `~/.tfibanisa/tfibanisa.db`
- ✅ All required models downloaded and cached
- ✅ Config loads correctly from `.env` or defaults

---

## Phase 2: Core API Endpoints (16–24 hours)

### 2.1 FastAPI Server Skeleton
- [ ] **2.1.1** Create `server/app.py` with FastAPI app, lifespan setup
- [ ] **2.1.2** Set up CORS, middleware, error handlers
- [ ] **2.1.3** Add `/health` endpoint (returns Qdrant status, model cache status)
- [ ] **2.1.4** Create `run.sh` script to start server with uvicorn (`uvicorn server.app:app --host 0.0.0.0 --port 8000`)

### 2.2 Meme Upload Endpoint
- [ ] **2.2.1** Create `POST /api/memes/upload` endpoint:
  - [ ] Accept multipart/form-data (image file + optional metadata: movie_title, dialogue_te, emotion_tags)
  - [ ] Save image to `~/.tfibanisa/images/` with unique hash name
  - [ ] Insert meme record into SQLite
  - [ ] Trigger async jobs: captioning, OCR, embedding (see Phase 3)
  - [ ] Return meme ID + initial metadata
- [ ] **2.2.2** Validation: file type (JPEG, PNG), size limit (max 10 MB)
- [ ] **2.2.3** Error handling: invalid image, disk full, DB error
- [ ] **2.2.4** Test with 5–10 sample memes

### 2.3 Meme Search Endpoint (Vector + Keyword)
- [ ] **2.3.1** Create `POST /api/memes/search` endpoint:
  - [ ] Accept JSON: `{query: str, emotions?: [str], actors?: [str], limit?: int (default 10)}`
  - [ ] Embed query using Vyakyarth-1-Indic
  - [ ] Query Qdrant with optional filters (emotions, actors)
  - [ ] Return top K results with meme URLs, captions, similarity scores, metadata
- [ ] **2.3.2** Transliteration support: convert Roman Telugu query to native script before embedding
- [ ] **2.3.3** Handle edge cases: empty query, unknown filters, no results
- [ ] **2.3.4** Latency target: <1 second per search
- [ ] **2.3.5** Test with manual queries ("sad scene," "చిరంజీవి కన్నీళ్లు")

### 2.4 Meme Detail & Edit Endpoint
- [ ] **2.4.1** Create `GET /api/memes/{meme_id}` — retrieve full meme metadata + image URL
- [ ] **2.4.2** Create `POST /api/memes/{meme_id}/edit` endpoint:
  - [ ] Accept JSON with editable fields (dialogue_te, dialogue_en, dialogue_roman, emotion_tags, context_tags, movie_title_te, movie_title_en, actors, manual_notes)
  - [ ] Update SQLite + re-embed updated text fields
  - [ ] Update Qdrant vectors + payloads
  - [ ] Mark as `verified=true` if user manually edited
- [ ] **2.4.3** Partial updates: only provided fields are updated

### 2.5 List & Filter Endpoints
- [ ] **2.5.1** Create `GET /api/memes?limit=10&offset=0&verified=true` — paginated list of memes
- [ ] **2.5.2** Create `GET /api/movies` — list unique movies in collection
- [ ] **2.5.3** Create `GET /api/actors` — list unique actors
- [ ] **2.5.4** Create `GET /api/emotions` — list available emotion tags

### 2.6 Async Job Status Endpoint
- [ ] **2.6.1** Create `GET /api/memes/{meme_id}/status` — check if captioning/OCR/embedding still running
- [ ] **2.6.2** Return: `{status: "pending"|"processing"|"done", progress: 0-100, errors?: [str]}`

**Phase 2 Acceptance Criteria:**
- ✅ All endpoints return proper HTTP status codes
- ✅ Upload works: image saved, meme record created, async jobs triggered
- ✅ Search works: queries return results in <1 sec (before embedding jobs complete; results improve as metadata is generated)
- ✅ Edit works: metadata update persists to SQLite + Qdrant
- ✅ Basic integration tests pass (no unit tests yet; Phase 5)

---

## Phase 3: Auto-Tagging Pipeline (12–16 hours)

### 3.1 Image Captioning (Florence-2)
- [ ] **3.1.1** Create `collectors/captions.py`:
  - [ ] Load Florence-2-base model (lazy load, cache in memory)
  - [ ] `caption_image(image_path: str) → str` function
  - [ ] Handle errors: corrupt image, model OOM
- [ ] **3.1.2** Async job: after upload, caption image in background
  - [ ] Store caption in `metadata.auto_generated_caption`
  - [ ] Measure & log latency per image
- [ ] **3.1.3** Test on 5+ sample meme images; verify captions are sensible
- [ ] **3.1.4** Benchmark performance on M3/M2 Mac (target: <500 ms per image)

### 3.2 OCR for Telugu Script
- [ ] **3.2.1** Create `collectors/ocr.py`:
  - [ ] Set up Tesseract with Telugu trained data
  - [ ] `extract_text(image_path: str, lang: str = "tel") → str` function
  - [ ] Handle errors: missing Tesseract, corrupt image, no text
- [ ] **3.2.2** Async job: after upload, run OCR in background
  - [ ] Store raw OCR text in `metadata.extracted_dialogue_raw`
  - [ ] Log accuracy concerns in `metadata.manual_notes`
- [ ] **3.2.3** Test on 10+ memes with Telugu text overlays
  - [ ] Document accuracy rate (target: 60–80% for stylized text)
  - [ ] Note which memes need manual correction

### 3.3 Text Embedding (Vyakyarth-1-Indic)
- [ ] **3.3.1** Create `collectors/embeddings.py`:
  - [ ] Load Vyakyarth-1-Indic model (lazy, cache)
  - [ ] `embed_text(text: str) → ndarray` function
  - [ ] Handle: empty text, very long text (truncate to 512 tokens)
- [ ] **3.3.2** Create `embed_multifield(dialogue_te, dialogue_en, caption) → embeddings_dict`
  - [ ] Generate separate embeddings for Telugu dialogue, English translation, auto-caption
  - [ ] Store all three in Qdrant payload + SQLite `embeddings_log`
- [ ] **3.3.3** Test embedding retrieval: verify 768-dim vectors
- [ ] **3.3.4** Benchmark on M3 (target: <100 ms per embedding)

### 3.4 Async Job Queue & Scheduling
- [ ] **3.4.1** Create simple in-process job queue (Python `asyncio.Queue` or Celery if needed)
  - [ ] Job types: CAPTION, OCR, EMBED, RE_EMBED
  - [ ] Job status: PENDING, RUNNING, DONE, ERROR
- [ ] **3.4.2** Worker process: pull jobs from queue, execute, update SQLite status
- [ ] **3.4.3** Graceful shutdown: finish running jobs before exit
- [ ] **3.4.4** Retry logic: up to 2 retries on failure; after 2 failures, mark as ERROR + log

### 3.5 Transliteration Support
- [ ] **3.5.1** Create `utils/transliterate.py`:
  - [ ] `roman_to_telugu(text: str) → str` (e.g., "Ee jeevitham" → "ఈ జీవితం")
  - [ ] Use `indic-transliteration` library
  - [ ] Handle: ambiguous transliterations, mixed scripts
- [ ] **3.5.2** On search query: if input is Roman script, convert to Telugu before embedding
- [ ] **3.5.3** Test with 5+ sample queries

**Phase 3 Acceptance Criteria:**
- ✅ Upload triggers all three async jobs
- ✅ Florence-2 captions 1 test image in <500 ms
- ✅ Tesseract extracts Telugu text (with ≥60% accuracy on test memes)
- ✅ Vyakyarth embeddings generated + stored in Qdrant
- ✅ Re-uploading same image → new job, not reusing old embeddings
- ✅ Status endpoint shows job progress

---

## Phase 4: Search & Hybrid Retrieval (8–12 hours)

### 4.1 Vector Search with Metadata Filters
- [ ] **4.1.1** Extend `POST /api/memes/search` to support:
  - [ ] Filter by emotion_tags (optional, pre-filter)
  - [ ] Filter by actors (optional)
  - [ ] Filter by movie (optional)
  - [ ] Combine filters with AND logic
- [ ] **4.1.2** Qdrant payload filtering: use `qdrant_client.models.Filter`
  - [ ] Ensure filters apply before vector search (faster)
- [ ] **4.1.3** Test: search for "sad scene" → should filter to sadness-tagged memes first

### 4.2 Hybrid Search (Keyword + Vector)
- [ ] **4.2.1** Implement BM25 keyword search on SQLite (`full_text_search` on dialogue_te, dialogue_en, caption)
  - [ ] OR integrate Qdrant's built-in BM25 if available
- [ ] **4.2.2** Create `hybrid_search(query, emotions=None) → results`:
  - [ ] Run vector search in Qdrant (get top 20)
  - [ ] Run BM25 on dialogue + captions (get top 20)
  - [ ] Merge results using **Reciprocal Rank Fusion (RRF)**
  - [ ] Return top 10
- [ ] **4.2.3** RRF formula: for each result, compute score = 1/(k + rank_in_list), then merge
- [ ] **4.2.4** Test on exact-dialogue queries: "ee jeevitham oka samaram" should rank exact match first

### 4.3 Reranking by User Feedback
- [ ] **4.3.1** Add `verified=true/false` column to memes table
  - [ ] Manual editing sets verified=true
- [ ] **4.3.2** Rerank results: show verified memes first, then auto-tagged
- [ ] **4.3.3** Optional: add user rating (1–5 stars) per search; rerank by rating

### 4.4 Search Analytics
- [ ] **4.4.1** Log each search: query, filters, results returned, execution time
- [ ] **4.4.2** Endpoint `GET /api/analytics/top_queries` — most common searches
- [ ] **4.4.3** Help identify what memes users are looking for

**Phase 4 Acceptance Criteria:**
- ✅ Filtered search (by emotion) returns only tagged memes
- ✅ Hybrid search finds exact dialogue match
- ✅ Multi-filter search works (emotion + actor + movie)
- ✅ All searches complete in <1 second
- ✅ Search results include similarity scores + reason for ranking

---

## Phase 5: Frontend, Testing & Deployment (8–16 hours)

### 5.1 Web UI (Upload & Search)
- [ ] **5.1.1** Create `static/index.html` with vanilla JS or lightweight React:
  - [ ] Upload form: image picker + optional metadata fields (movie, dialogue, emotion tags, actors)
  - [ ] Search form: text input + checkboxes for emotion/actor/movie filters
  - [ ] Results grid: thumbnails, caption, movie name, similarity score, "Copy image" button
  - [ ] Detail modal: full meme image, all metadata, edit form
- [ ] **5.1.2** Upload progress bar: poll `/api/memes/{id}/status` every 500ms
- [ ] **5.1.3** Search results update live as user types (debounce 300ms)
- [ ] **5.1.4** Dark mode support (match user's system preference)
- [ ] **5.1.5** Mobile responsive (works on iPhone screen too)

### 5.2 Unit Tests
- [ ] **5.2.1** Create `tests/test_embeddings.py`:
  - [ ] Test Vyakyarth embedding produces 768-dim vectors
  - [ ] Test transliteration (Roman → Telugu)
  - [ ] Test embedding same text twice → same vector
- [ ] **5.2.2** Create `tests/test_captions.py`:
  - [ ] Test Florence-2 on sample images
  - [ ] Test error handling (corrupt image)
- [ ] **5.2.3** Create `tests/test_ocr.py`:
  - [ ] Test Tesseract on sample Telugu text images
  - [ ] Measure accuracy on test set
- [ ] **5.2.4** Create `tests/test_qdrant.py`:
  - [ ] Test collection creation, vector upsert, search
  - [ ] Test filter logic (emotions, actors)

### 5.3 Integration Tests
- [ ] **5.3.1** Create `tests/test_integration.py`:
  - [ ] Upload a sample meme → verify it appears in SQLite + Qdrant
  - [ ] Search immediately (before caption jobs complete) → no results yet
  - [ ] Poll status until jobs done
  - [ ] Search again → meme found
  - [ ] Edit meme metadata → update persists
  - [ ] Search with edited dialogue → found via BM25
- [ ] **5.3.2** End-to-end flow test with 10 memes
- [ ] **5.3.3** Performance test: 1000 vector searches on 500-meme collection

### 5.4 Documentation
- [ ] **5.4.1** Write `README.md`:
  - [ ] Project overview, quick start
  - [ ] Architecture diagram (upload → captioning → embed → search)
  - [ ] API endpoint reference (with examples)
  - [ ] Model details + limitations
- [ ] **5.4.2** Write `SETUP.md`:
  - [ ] Step-by-step setup on Mac (with `setup.sh`)
  - [ ] Troubleshooting (Tesseract not found, model download fails, etc.)
  - [ ] System requirements (RAM, disk, Mac version)
- [ ] **5.4.3** Write `USAGE.md`:
  - [ ] How to upload memes
  - [ ] How to search + filter
  - [ ] How to edit metadata
  - [ ] Tips for best search results
- [ ] **5.4.4** Update `CLAUDE.md` with current status

### 5.5 Performance Benchmarking
- [ ] **5.5.1** Document latency for each operation:
  - [ ] Caption 1 meme: target <500 ms
  - [ ] OCR 1 meme: target <200 ms
  - [ ] Embed 1 text: target <100 ms
  - [ ] Search 500-meme collection: target <1 sec
- [ ] **5.5.2** Memory usage:
  - [ ] Model cache (Florence-2 + Vyakyarth): ~4–6 GB
  - [ ] Qdrant + 500 memes: ~500 MB–1 GB
  - [ ] SQLite: ~50 MB
  - [ ] Total: ~5–7 GB (fit on M3 Mac Mini)
- [ ] **5.5.3** Record baseline numbers; use for regression testing

### 5.6 Launchd Setup (Always-On Service)
- [ ] **5.6.1** Create `scripts/tfibanisa.plist` launchd config:
  - [ ] Start server on login
  - [ ] Restart on crash
  - [ ] Capture logs
- [ ] **5.6.2** Create `scripts/install-service.sh`:
  - [ ] Copy .plist to ~/Library/LaunchAgents/
  - [ ] `launchctl load` to start
- [ ] **5.6.3** Test: reboot, verify server running on localhost:8000

**Phase 5 Acceptance Criteria:**
- ✅ Web UI loads at http://localhost:8000
- ✅ Upload, search, edit workflows work end-to-end
- ✅ All unit tests pass
- ✅ Integration test (10 memes, full workflow) passes
- ✅ README + SETUP + USAGE docs complete
- ✅ Launchd service starts + restarts on reboot
- ✅ Performance benchmarks recorded

---

## Post-MVP Extensions (Optional, not in Phase 1–5)

### Image-Based Search
- [ ] Integrate SigLIP or multilingual-CLIP for image-to-query matching
- [ ] Upload screenshot of movie scene → search for matching memes
- Effort: 3–4 weeks

### Emotion Classification
- [ ] Train / fine-tune classifier to auto-detect emotion from image
- [ ] Improves auto-tagging accuracy
- Effort: 2–3 weeks

### Telegram Bot Integration
- [ ] Reuse existing Code-as-a-chat Telegram bot
- [ ] `/search_meme "sad scene"` command
- Effort: 1–2 weeks

### Multi-User Sharing
- [ ] User auth, meme collection sharing with friends
- [ ] Requires schema changes + permissions
- Effort: 6–8 weeks

### Recommendation Engine
- [ ] "If you searched for sad scenes, you might like this one"
- [ ] Based on search history + meme similarity
- Effort: 4–6 weeks

---

## Milestones & Dependencies

| Week | Phase | Key Deliverables | Blocker |
|------|-------|------------------|---------|
| 1 | 1 | Environment ready, Qdrant running, SQLite schema | None |
| 1–2 | 2 | Core API endpoints working on 10 test memes | Phase 1 |
| 2 | 3 | Captioning + OCR + embedding pipeline live | Phase 2 |
| 2–3 | 4 | Vector + hybrid search working | Phase 3 |
| 3 | 5 | Web UI, tests, docs, launchd service | Phase 4 |

---

## Effort Breakdown

| Phase | Task | Hours | Notes |
|-------|------|-------|-------|
| 1 | Setup & Infra | 4–8 | Most time on model downloads + Docker |
| 2 | Core API | 16–24 | FastAPI endpoints; straightforward |
| 3 | Auto-Tagging | 12–16 | Model integration; async job handling complexity |
| 4 | Search | 8–12 | Hybrid search merging logic |
| 5 | Frontend & Tests | 8–16 | UI polish + comprehensive testing |
| **Total** | — | **64–104** | Full-time: 2–3 weeks; part-time: 8–15 weeks |

---

## Testing Strategy

**Unit tests (Phase 5):** Each module (embeddings, captions, OCR) tested in isolation.
**Integration tests (Phase 5):** Full upload → search workflow on 10–50 test memes.
**Performance tests:** Search latency on 500+ meme collection.
**Manual testing:** Upload personal meme collection, verify search quality.

---

## Success Metrics (End-to-End)

1. ✅ Upload 500 personal memes in <2 hours (auto-caption + OCR batch).
2. ✅ Search "sad scene" → retrieve 5+ matching memes in <1 sec.
3. ✅ Search exact dialogue → exact match ranks first.
4. ✅ Edit meme metadata → changes persist and affect search.
5. ✅ All data remains local (no cloud calls, no privacy leaks).
6. ✅ Launchd keeps service alive; survives reboot.

---

## Notes

- Research doc: `/Users/dark_mamba/Projects/Code-as-a-chat/telugu-meme-store-research.md` (comprehensive background)
- Model cache location: `~/.cache/huggingface/hub/` (Vyakyarth, Florence-2)
- Qdrant data: Docker volume (persistent)
- Meme storage: `~/.tfibanisa/images/` (local filesystem)
- Logs: `~/.tfibanisa/logs/` (rotating daily)

**Start date:** [TBD] | **Target completion:** 2–3 weeks (full-time)
