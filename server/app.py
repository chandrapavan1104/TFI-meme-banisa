"""TFI-meme-banisa FastAPI server: upload, search, edit, and browse Telugu memes."""

import hashlib
import io
import logging
import logging.handlers
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

import config
from collectors import captions, embeddings, ocr
from db import store
from db.init import init_db
from server import jobs as jobs_mod
from server import search as search_mod
from server.qdrant_schema import verify_collection_ready
from server.qdrant_store import get_client

log = logging.getLogger("tfibanisa")

_ALLOWED_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _setup_logging() -> None:
    config.ensure_dirs()
    root = logging.getLogger()
    if any(isinstance(h, logging.handlers.TimedRotatingFileHandler) for h in root.handlers):
        return
    root.setLevel(config.LOG_LEVEL)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        config.LOGS_DIR / "tfibanisa.log", when="midnight", backupCount=14
    )
    file_handler.setFormatter(fmt)
    root.addHandler(console)
    root.addHandler(file_handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    config.ensure_dirs()
    app.state.conn = init_db()
    app.state.qclient = get_client()
    app.state.jobs = jobs_mod.JobQueue(app.state.conn, app.state.qclient)
    app.state.jobs.start()
    app.state.jobs.requeue_unfinished()
    log.info("TFI-meme-banisa started (qdrant mode=%s)", config.QDRANT_MODE)
    yield
    await app.state.jobs.shutdown()
    app.state.conn.close()
    log.info("TFI-meme-banisa stopped")


app = FastAPI(title="TFI-meme-banisa", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    if request.url.path.startswith("/api"):
        log.info(
            "%s %s -> %d (%.0f ms)",
            request.method, request.url.path, response.status_code,
            (time.perf_counter() - start) * 1000,
        )
    return response


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": f"internal error: {exc}"})


def _meme_out(meme: dict) -> dict:
    return {**meme, "image_url": f"/images/{meme['image_path']}"}


# --- Health -----------------------------------------------------------------

@app.get("/health")
def health(request: Request):
    qdrant_ok = False
    try:
        qdrant_ok = verify_collection_ready(request.app.state.qclient)
    except Exception:
        pass
    return {
        "status": "ok" if qdrant_ok else "degraded",
        "qdrant": {"mode": config.QDRANT_MODE, "collection_ready": qdrant_ok},
        "models": {
            "embedding": {"id": config.EMBEDDING_MODEL, "cached": embeddings.is_available()},
            "caption": {"id": config.CAPTION_MODEL, "cached": captions.is_available()},
            "ocr": {"lang": config.OCR_LANG, "available": ocr.is_available()},
        },
    }


# --- Upload -----------------------------------------------------------------

@app.post("/api/memes/upload", status_code=201)
async def upload_meme(
    request: Request,
    file: UploadFile = File(...),
    movie_title_en: str | None = Form(None),
    movie_title_te: str | None = Form(None),
    dialogue_te: str | None = Form(None),
    dialogue_en: str | None = Form(None),
    actors: str | None = Form(None),        # comma-separated
    emotion_tags: str | None = Form(None),  # comma-separated
    context_tags: str | None = Form(None),  # comma-separated
    manual_notes: str | None = Form(None),
):
    if file.content_type not in _ALLOWED_TYPES:
        raise HTTPException(415, f"unsupported type {file.content_type}; use JPEG/PNG/WebP")
    data = await file.read()
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"file exceeds {config.MAX_UPLOAD_MB} MB limit")
    try:
        Image.open(io.BytesIO(data)).verify()
        animated = bool(getattr(Image.open(io.BytesIO(data)), "is_animated", False))
    except (UnidentifiedImageError, OSError):
        raise HTTPException(422, "file is not a valid image")

    meme_id = hashlib.sha256(data).hexdigest()[:16]
    filename = meme_id + _ALLOWED_TYPES[file.content_type]
    conn = request.app.state.conn

    try:
        (config.IMAGES_DIR / filename).write_bytes(data)
    except OSError as exc:
        raise HTTPException(507, f"could not save image: {exc}")

    created = store.create_meme(conn, meme_id, filename, animated=animated)
    fields = {
        "movie_title_en": movie_title_en,
        "movie_title_te": movie_title_te,
        "dialogue_te": dialogue_te,
        "dialogue_en": dialogue_en,
        "actors": [a.strip() for a in (actors or "").split(",") if a.strip()],
        "emotion_tags": [e.strip() for e in (emotion_tags or "").split(",") if e.strip()],
        "context_tags": [c.strip() for c in (context_tags or "").split(",") if c.strip()],
        "manual_notes": manual_notes,
    }
    meme = store.update_metadata(
        conn, meme_id, {k: v for k, v in fields.items() if v}
    )
    # Always (re-)run the pipeline — also on duplicate upload, per spec.
    request.app.state.jobs.enqueue_pipeline(meme_id)
    return JSONResponse(
        status_code=201 if created else 200,
        content={"meme": _meme_out(meme), "duplicate": not created},
    )


# --- Search -----------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str
    emotions: list[str] | None = None
    actors: list[str] | None = None
    movie: str | None = None
    animated: bool | None = None  # true = only animated, false = only static
    limit: int = Field(default=10, ge=1, le=100)


@app.post("/api/memes/search")
def search_memes(request: Request, body: SearchRequest):
    result = search_mod.hybrid_search(
        request.app.state.conn,
        request.app.state.qclient,
        body.query,
        emotions=body.emotions,
        actors=body.actors,
        movie=body.movie,
        animated=body.animated,
        limit=body.limit,
    )
    result["results"] = [
        {**r, "meme": _meme_out(r["meme"])} for r in result["results"]
    ]
    return result


# --- List & lookups ---------------------------------------------------------

@app.get("/api/memes")
def list_memes(
    request: Request,
    limit: int = 10,
    offset: int = 0,
    verified: bool | None = None,
    animated: bool | None = None,
    pack: str | None = None,
):
    rows, total = store.list_memes(
        request.app.state.conn, limit=min(limit, 100), offset=offset,
        verified=verified, animated=animated, pack=pack,
    )
    return {"memes": [_meme_out(m) for m in rows], "total": total}


@app.get("/api/packs")
def get_packs(request: Request, limit: int = 60):
    packs = store.list_packs(request.app.state.conn, limit=min(limit, 200))
    return {
        "packs": [
            {**p, "cover_url": f"/images/{p.pop('cover_path')}"} for p in packs
        ]
    }


@app.get("/api/movies")
def get_movies(request: Request):
    return {"movies": store.list_movies(request.app.state.conn)}


@app.get("/api/actors")
def get_actors(request: Request):
    return {"actors": store.list_actors(request.app.state.conn)}


@app.get("/api/emotions")
def get_emotions(request: Request):
    return {"emotions": store.list_emotions(request.app.state.conn)}


@app.get("/api/analytics/top_queries")
def get_top_queries(request: Request, limit: int = 20):
    return {"queries": store.top_queries(request.app.state.conn, limit=min(limit, 100))}


# --- Detail, edit, status ---------------------------------------------------

def _get_or_404(request: Request, meme_id: str) -> dict:
    meme = store.get_meme(request.app.state.conn, meme_id)
    if not meme:
        raise HTTPException(404, f"meme {meme_id} not found")
    return meme


@app.get("/api/memes/{meme_id}")
def get_meme(request: Request, meme_id: str):
    return {"meme": _meme_out(_get_or_404(request, meme_id))}


class EditRequest(BaseModel):
    movie_title_te: str | None = None
    movie_title_en: str | None = None
    actors: list[str] | None = None
    dialogue_te: str | None = None
    dialogue_en: str | None = None
    dialogue_roman: str | None = None
    emotion_tags: list[str] | None = None
    context_tags: list[str] | None = None
    manual_notes: str | None = None


@app.post("/api/memes/{meme_id}/edit")
def edit_meme(request: Request, meme_id: str, body: EditRequest):
    _get_or_404(request, meme_id)
    fields = body.model_dump(exclude_unset=True)  # partial update
    meme = store.update_metadata(
        request.app.state.conn, meme_id, fields, mark_verified=True
    )
    request.app.state.jobs.enqueue(meme_id, jobs_mod.RE_EMBED)
    return {"meme": _meme_out(meme)}


class AutoTagRequest(BaseModel):
    actors: list[str]


@app.post("/api/memes/{meme_id}/auto_tag")
def auto_tag_meme(request: Request, meme_id: str, body: AutoTagRequest):
    """Merge auto-detected actors (face recognition) into a meme.

    Unlike /edit this never removes tags and never marks the meme verified.
    """
    meme = _get_or_404(request, meme_id)
    merged = sorted(set(meme["actors"]) | set(body.actors))
    if merged != sorted(meme["actors"]):
        meme = store.update_metadata(
            request.app.state.conn, meme_id, {"actors": merged}
        )
        request.app.state.jobs.enqueue(meme_id, jobs_mod.RE_EMBED)
    return {"meme": _meme_out(meme)}


class RateRequest(BaseModel):
    rating: int = Field(ge=1, le=5)


@app.post("/api/memes/{meme_id}/rate")
def rate_meme(request: Request, meme_id: str, body: RateRequest):
    _get_or_404(request, meme_id)
    store.set_rating(request.app.state.conn, meme_id, body.rating)
    return {"meme": _meme_out(_get_or_404(request, meme_id))}


@app.get("/api/memes/{meme_id}/status")
def meme_status(request: Request, meme_id: str):
    _get_or_404(request, meme_id)
    return jobs_mod.status_for_meme(request.app.state.conn, meme_id)


# --- Static files -----------------------------------------------------------

app.mount("/images", StaticFiles(directory=str(config.IMAGES_DIR), check_dir=False), name="images")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")
