"""Text embedding with Vyakyarth-1-Indic (sentence-transformers).

The model is lazy-loaded on first use and cached in memory (~1 GB). All
functions are blocking; the server runs them in worker threads.
"""

import logging
import threading

import config

log = logging.getLogger(__name__)

_MAX_CHARS = 2000  # ~512 tokens; sentence-transformers truncates anyway
_model = None
_lock = threading.Lock()


def get_model():
    """Load and cache the embedding model (thread-safe)."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                log.info("Loading embedding model %s ...", config.EMBEDDING_MODEL)
                _model = SentenceTransformer(config.EMBEDDING_MODEL)
                log.info("Embedding model loaded")
    return _model


def is_available() -> bool:
    """True if the model is loadable from the local cache (no download)."""
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(config.EMBEDDING_MODEL, local_files_only=True)
        return True
    except Exception:
        return _model is not None


def embed_text(text: str) -> list[float]:
    """Embed one text into a normalized 768-dim vector.

    Raises ValueError on empty input; long text is truncated.
    """
    if not text or not text.strip():
        raise ValueError("cannot embed empty text")
    vec = get_model().encode(
        text.strip()[:_MAX_CHARS], normalize_embeddings=True
    )
    return vec.tolist()


def embed_multifield(
    dialogue_te: str | None,
    dialogue_en: str | None,
    caption: str | None,
    description: str | None = None,
) -> dict[str, list[float]]:
    """Embed each present text field. Returns {vector_name: vector}."""
    out: dict[str, list[float]] = {}
    for name, text in (
        ("description", description),
        ("dialogue_te", dialogue_te),
        ("dialogue_en", dialogue_en),
        ("caption", caption),
    ):
        if text and text.strip():
            out[name] = embed_text(text)
    return out
