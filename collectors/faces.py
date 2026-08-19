"""Face detection + recognition for actor auto-tagging.

Uses InsightFace (SCRFD detector + ArcFace embeddings, buffalo_l model pack,
~275 MB, auto-downloaded to ~/.insightface on first use). ArcFace embeddings
are robust to expression/pose, which matters for memes.

Reference faces per actor live in ~/.tfibanisa/face_refs.json:
    {"Chiranjeevi": [[512 floats], ...], ...}
Each actor may have several reference embeddings (e.g. a Wikipedia portrait
plus in-domain sticker faces found by bootstrapping); a face matches an actor
by its best cosine similarity across that actor's references.
"""

import json
import logging
import threading

import numpy as np
from PIL import Image

import config

log = logging.getLogger(__name__)

REFS_PATH = config.HOME_DIR / "face_refs.json"
# ArcFace cosine similarity: same person is typically >0.4; stylized meme
# faces run lower, so the auto-tag threshold trades precision vs recall.
MATCH_THRESHOLD = 0.38

_app = None
_lock = threading.Lock()


def get_app():
    """Load and cache the InsightFace pipeline (thread-safe)."""
    global _app
    if _app is None:
        with _lock:
            if _app is None:
                from insightface.app import FaceAnalysis

                log.info("Loading InsightFace buffalo_l ...")
                app = FaceAnalysis(
                    name="buffalo_l",
                    allowed_modules=["detection", "recognition"],
                    providers=["CPUExecutionProvider"],
                )
                app.prepare(ctx_id=-1, det_size=(640, 640))
                _app = app
                log.info("InsightFace loaded")
    return _app


def is_available() -> bool:
    try:
        import insightface  # noqa: F401

        return True
    except ImportError:
        return False


def refs_available() -> bool:
    return REFS_PATH.exists()


def load_refs() -> dict[str, np.ndarray]:
    """{actor: (n_refs, 512) L2-normalized embedding matrix}."""
    raw = json.loads(REFS_PATH.read_text())
    out = {}
    for actor, vecs in raw.items():
        m = np.asarray(vecs, dtype=np.float32)
        out[actor] = m / np.linalg.norm(m, axis=1, keepdims=True)
    return out


def save_refs(refs: dict[str, list[list[float]]]) -> None:
    REFS_PATH.write_text(json.dumps(refs))


def detect_faces(image_path: str) -> list[tuple[list[float], np.ndarray]]:
    """Detect faces; return [(bbox [x1,y1,x2,y2], normalized 512-dim embedding)].

    Animated images use their first frame. Returns [] when no face is found.
    """
    img = Image.open(image_path).convert("RGB")
    bgr = np.asarray(img)[:, :, ::-1]  # insightface expects BGR
    faces = get_app().get(bgr)
    out = []
    for f in faces:
        emb = f.normed_embedding
        if emb is not None:
            out.append(
                ([float(v) for v in f.bbox], np.asarray(emb, dtype=np.float32))
            )
    return out


def face_embeddings(image_path: str) -> list[np.ndarray]:
    """Embeddings only (see detect_faces)."""
    return [emb for _, emb in detect_faces(image_path)]


def match_actors(
    embeddings: list[np.ndarray],
    refs: dict[str, np.ndarray],
    threshold: float = MATCH_THRESHOLD,
) -> dict[str, float]:
    """Match faces to actors: each face gets at most ONE identity (its best
    match above the threshold). Multiple actors can only come from multiple
    faces — one ambiguous face never tags two people.

    Returns {actor: best_similarity}.
    """
    matched: dict[str, float] = {}
    for emb in embeddings:
        best_actor, best_sim = None, threshold
        for actor, mat in refs.items():
            sim = float(np.max(mat @ emb))
            if sim >= best_sim:
                best_actor, best_sim = actor, sim
        if best_actor and best_sim > matched.get(best_actor, -1.0):
            matched[best_actor] = best_sim
    return matched
