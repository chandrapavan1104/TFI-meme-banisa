"""Environment configuration for TFI-banisa.

All settings come from environment variables (or a .env file loaded by the
shell) with sensible local defaults. Data lives under ~/.tfibanisa/.
"""

import os
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


# --- Storage ---------------------------------------------------------------
HOME_DIR = Path(_env("TFIBANISA_HOME", str(Path.home() / ".tfibanisa"))).expanduser()
IMAGES_DIR = HOME_DIR / "images"
LOGS_DIR = HOME_DIR / "logs"
DB_PATH = HOME_DIR / "tfibanisa.db"

# --- Qdrant ----------------------------------------------------------------
# "embedded": run Qdrant in-process, persisted to QDRANT_PATH (no Docker).
# "server":   connect to a running Qdrant at QDRANT_URL (docker-compose.yml).
QDRANT_MODE = _env("QDRANT_MODE", "embedded")
QDRANT_URL = _env("QDRANT_URL", "http://localhost:6333")
QDRANT_PATH = Path(_env("QDRANT_PATH", str(HOME_DIR / "qdrant"))).expanduser()
QDRANT_COLLECTION = _env("QDRANT_COLLECTION", "telugu_memes")

# --- Models ----------------------------------------------------------------
EMBEDDING_MODEL = _env("EMBEDDING_MODEL", "krutrim-ai-labs/Vyakyarth")
EMBEDDING_DIM = int(_env("EMBEDDING_DIM", "768"))
CAPTION_MODEL = _env("CAPTION_MODEL", "microsoft/Florence-2-base")
# Florence-2 task prompt: <CAPTION> (fastest) | <DETAILED_CAPTION> | <MORE_DETAILED_CAPTION>
CAPTION_TASK = _env("CAPTION_TASK", "<DETAILED_CAPTION>")
OCR_LANG = _env("OCR_LANG", "tel+eng")

# --- Server ----------------------------------------------------------------
HOST = _env("HOST", "0.0.0.0")
PORT = int(_env("PORT", "8000"))
MAX_UPLOAD_MB = int(_env("MAX_UPLOAD_MB", "10"))
LOG_LEVEL = _env("LOG_LEVEL", "INFO")

# --- Jobs ------------------------------------------------------------------
JOB_MAX_RETRIES = int(_env("JOB_MAX_RETRIES", "2"))


def ensure_dirs() -> None:
    """Create the data directories if they don't exist."""
    for d in (HOME_DIR, IMAGES_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)
