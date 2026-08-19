"""In-process async job queue for captioning, OCR, and embedding.

A single asyncio worker pulls jobs FIFO and runs the blocking model calls in
a thread. Jobs for one meme are enqueued CAPTION -> OCR -> EMBED, so the
single worker satisfies the dependency order naturally. Job state lives in
the SQLite `jobs` table (PENDING/RUNNING/DONE/ERROR, with retries).
"""

import asyncio
import logging
import sqlite3
import threading
from dataclasses import dataclass

from qdrant_client import QdrantClient

import config
from collectors import captions, embeddings, ocr
from db import store
from server import qdrant_store
from utils.transliterate import contains_telugu

log = logging.getLogger(__name__)

CAPTION, OCR, EMBED, RE_EMBED = "CAPTION", "OCR", "EMBED", "RE_EMBED"


@dataclass
class Job:
    id: int
    meme_id: str
    job_type: str


class JobQueue:
    def __init__(self, conn: sqlite3.Connection, qclient: QdrantClient):
        self.conn = conn
        self.qclient = qclient
        self.queue: asyncio.Queue[Job | None] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: int | None = None

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._loop_thread = threading.get_ident()
        self._worker_task = self._loop.create_task(self._worker())

    def _put(self, item: Job | None) -> None:
        """Thread-safe put: sync endpoints run in FastAPI's threadpool."""
        if self._loop and threading.get_ident() != self._loop_thread:
            self._loop.call_soon_threadsafe(self.queue.put_nowait, item)
        else:
            self.queue.put_nowait(item)

    async def shutdown(self) -> None:
        """Finish the running job, then stop (pending jobs stay PENDING in DB)."""
        self._put(None)
        if self._worker_task:
            await self._worker_task

    # -- enqueue ------------------------------------------------------------

    def enqueue(self, meme_id: str, job_type: str) -> int:
        job_id = store.create_job(self.conn, meme_id, job_type)
        self._put(Job(job_id, meme_id, job_type))
        return job_id

    def enqueue_pipeline(self, meme_id: str) -> list[int]:
        """Full auto-tagging pipeline for a newly uploaded meme."""
        return [self.enqueue(meme_id, t) for t in (CAPTION, OCR, EMBED)]

    def requeue_unfinished(self) -> int:
        """Re-enqueue jobs left PENDING/RUNNING by a previous server run."""
        rows = store.unfinished_jobs(self.conn)
        for r in rows:
            self._put(Job(r["id"], r["meme_id"], r["job_type"]))
        if rows:
            log.info("Re-enqueued %d unfinished jobs from previous run", len(rows))
        return len(rows)

    # -- worker -------------------------------------------------------------

    async def _worker(self) -> None:
        while True:
            job = await self.queue.get()
            if job is None:
                return
            await self._run_with_retries(job)

    async def _run_with_retries(self, job: Job) -> None:
        handler = {
            CAPTION: self._do_caption,
            OCR: self._do_ocr,
            EMBED: self._do_embed,
            RE_EMBED: self._do_embed,
        }[job.job_type]
        last_error = ""
        for attempt in range(1 + config.JOB_MAX_RETRIES):
            store.update_job(self.conn, job.id, "RUNNING", bump_attempts=True)
            try:
                await asyncio.to_thread(handler, job.meme_id)
                store.update_job(self.conn, job.id, "DONE")
                return
            except Exception as exc:  # noqa: BLE001 — job errors are recorded, not fatal
                last_error = f"{type(exc).__name__}: {exc}"
                log.warning(
                    "Job %s %s for %s failed (attempt %d): %s",
                    job.id, job.job_type, job.meme_id, attempt + 1, last_error,
                )
        store.update_job(self.conn, job.id, "ERROR", error=last_error)

    # -- handlers (run in a thread) -----------------------------------------

    def _image_path(self, meme_id: str) -> str:
        meme = store.get_meme(self.conn, meme_id)
        if not meme:
            raise ValueError(f"meme {meme_id} not found")
        return str(config.IMAGES_DIR / meme["image_path"])

    def _do_caption(self, meme_id: str) -> None:
        if not captions.is_available():
            raise RuntimeError(
                f"caption model {config.CAPTION_MODEL} not downloaded — run setup.sh"
            )
        caption = captions.caption_image(self._image_path(meme_id))
        store.update_metadata(self.conn, meme_id, {"caption": caption})

    def _do_ocr(self, meme_id: str) -> None:
        if not ocr.is_available():
            raise RuntimeError("tesseract (with Telugu data) not installed")
        text = ocr.extract_text(self._image_path(meme_id))
        fields: dict = {"ocr_raw": text}
        # If OCR found Telugu text and no dialogue was provided, use it as the
        # dialogue so it becomes searchable immediately (user can correct later).
        meme = store.get_meme(self.conn, meme_id)
        if text and contains_telugu(text) and not (meme.get("dialogue_te") or "").strip():
            fields["dialogue_te"] = " ".join(text.split())
        store.update_metadata(self.conn, meme_id, fields)

    def _do_embed(self, meme_id: str) -> None:
        meme = store.get_meme(self.conn, meme_id)
        if not meme:
            raise ValueError(f"meme {meme_id} not found")
        vectors = embeddings.embed_multifield(
            meme.get("dialogue_te"), meme.get("dialogue_en"), meme.get("caption")
        )
        if not vectors:
            log.info("No text to embed yet for %s; skipping upsert", meme_id)
            return
        qdrant_store.upsert_meme(
            self.qclient,
            meme_id,
            vectors,
            payload={
                "movie_title_en": meme.get("movie_title_en"),
                "movie_title_te": meme.get("movie_title_te"),
                "actors": meme.get("actors") or [],
                "emotion_tags": meme.get("emotion_tags") or [],
                "context_tags": meme.get("context_tags") or [],
                "verified": bool(meme.get("verified")),
            },
        )
        for vector_type in vectors:
            store.log_embedding(
                self.conn, meme_id, config.EMBEDDING_MODEL, vector_type
            )


def status_for_meme(conn: sqlite3.Connection, meme_id: str) -> dict:
    """Aggregate job status: {status, progress 0-100, errors, jobs}."""
    jobs = store.jobs_for_meme(conn, meme_id)
    if not jobs:
        return {"status": "done", "progress": 100, "errors": [], "jobs": []}
    done = sum(1 for j in jobs if j["status"] in ("DONE", "ERROR"))
    errors = [f"{j['job_type']}: {j['error']}" for j in jobs if j["status"] == "ERROR"]
    if done == len(jobs):
        status = "done"
    elif any(j["status"] == "RUNNING" for j in jobs):
        status = "processing"
    else:
        status = "pending" if done == 0 else "processing"
    return {
        "status": status,
        "progress": int(100 * done / len(jobs)),
        "errors": errors,
        "jobs": [
            {"type": j["job_type"], "status": j["status"], "error": j["error"]}
            for j in jobs
        ],
    }
