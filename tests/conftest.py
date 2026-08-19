"""Shared fixtures: isolated data dirs, embedded Qdrant, fake ML collectors."""

import hashlib
import io
import random

import pytest
from PIL import Image

import config


@pytest.fixture()
def tmp_home(tmp_path, monkeypatch):
    """Point all config paths at a per-test temp directory."""
    home = tmp_path / "tfibanisa"
    monkeypatch.setattr(config, "HOME_DIR", home)
    monkeypatch.setattr(config, "IMAGES_DIR", home / "images")
    monkeypatch.setattr(config, "LOGS_DIR", home / "logs")
    monkeypatch.setattr(config, "DB_PATH", home / "test.db")
    monkeypatch.setattr(config, "QDRANT_PATH", home / "qdrant")
    monkeypatch.setattr(config, "QDRANT_MODE", "embedded")
    config.ensure_dirs()
    return home


@pytest.fixture()
def conn(tmp_home):
    from db.init import init_db

    conn = init_db()
    yield conn
    conn.close()


@pytest.fixture()
def qclient(tmp_home):
    from server.qdrant_store import get_client

    client = get_client()
    yield client
    client.close()


def fake_vector(text: str) -> list[float]:
    """Deterministic bag-of-words vector: shared tokens => higher cosine sim."""
    vec = [0.0] * config.EMBEDDING_DIM
    for token in text.lower().split():
        rng = random.Random(hashlib.md5(token.encode()).hexdigest())
        for i in range(config.EMBEDDING_DIM):
            vec[i] += rng.uniform(-1, 1)
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


@pytest.fixture()
def fake_collectors(monkeypatch):
    """Replace model calls with fast deterministic fakes."""
    from collectors import captions, embeddings, ocr

    monkeypatch.setattr(embeddings, "is_available", lambda: True)
    monkeypatch.setattr(embeddings, "embed_text", lambda t: fake_vector(t))
    monkeypatch.setattr(captions, "is_available", lambda: True)
    monkeypatch.setattr(
        captions, "caption_image", lambda p: "a man crying in the rain"
    )
    monkeypatch.setattr(ocr, "is_available", lambda: True)
    monkeypatch.setattr(ocr, "extract_text", lambda p, lang=None: "ఈ జీవితం ఒక సమరం")


@pytest.fixture()
def client(tmp_home, fake_collectors):
    """TestClient with lifespan (real embedded Qdrant, fake models)."""
    from fastapi.testclient import TestClient

    from server.app import app

    with TestClient(app) as c:
        yield c
    # Release embedded Qdrant lock for the next test.
    app.state.qclient.close()


def make_image_bytes(seed: int = 0, fmt: str = "PNG") -> bytes:
    rng = random.Random(seed)
    img = Image.new(
        "RGB", (64, 64),
        (rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255)),
    )
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def upload(client, seed=0, **form):
    data = make_image_bytes(seed)
    return client.post(
        "/api/memes/upload",
        files={"file": (f"meme{seed}.png", data, "image/png")},
        data=form,
    )


def wait_done(client, meme_id, timeout=10.0):
    """Poll the status endpoint until jobs finish."""
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        s = client.get(f"/api/memes/{meme_id}/status").json()
        if s["status"] == "done":
            return s
        time.sleep(0.05)
    raise TimeoutError(f"jobs for {meme_id} did not finish: {s}")
