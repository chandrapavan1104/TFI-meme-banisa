"""SQLite schema and migrations for TFI-meme-banisa metadata."""

import sqlite3

SCHEMA_VERSION = 2

# Migration 1: initial schema.
_MIGRATIONS: dict[int, str] = {
    1: """
    CREATE TABLE IF NOT EXISTS memes (
        id            TEXT PRIMARY KEY,          -- sha256[:16] of image bytes
        image_path    TEXT NOT NULL,             -- filename under IMAGES_DIR
        upload_date   TEXT NOT NULL DEFAULT (datetime('now')),
        auto_generated INTEGER NOT NULL DEFAULT 1,
        verified      INTEGER NOT NULL DEFAULT 0,
        rating        INTEGER                    -- optional 1-5 user rating
    );

    CREATE TABLE IF NOT EXISTS metadata (
        meme_id        TEXT PRIMARY KEY REFERENCES memes(id) ON DELETE CASCADE,
        movie_title_te TEXT,
        movie_title_en TEXT,
        actors         TEXT NOT NULL DEFAULT '[]',   -- JSON list
        dialogue_te    TEXT,
        dialogue_en    TEXT,
        dialogue_roman TEXT,
        emotion_tags   TEXT NOT NULL DEFAULT '[]',   -- JSON list
        context_tags   TEXT NOT NULL DEFAULT '[]',   -- JSON list
        caption        TEXT,                          -- Florence-2 auto caption
        ocr_raw        TEXT,                          -- raw Tesseract output
        manual_notes   TEXT
    );

    CREATE TABLE IF NOT EXISTS embeddings_log (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        meme_id          TEXT NOT NULL REFERENCES memes(id) ON DELETE CASCADE,
        embedding_model  TEXT NOT NULL,
        text_vector_type TEXT NOT NULL,          -- dialogue_te | dialogue_en | caption
        timestamp        TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS jobs (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        meme_id    TEXT NOT NULL REFERENCES memes(id) ON DELETE CASCADE,
        job_type   TEXT NOT NULL,                -- CAPTION | OCR | EMBED | RE_EMBED
        status     TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING | RUNNING | DONE | ERROR
        attempts   INTEGER NOT NULL DEFAULT 0,
        error      TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_jobs_meme ON jobs(meme_id);

    CREATE TABLE IF NOT EXISTS searches (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        query        TEXT NOT NULL,
        filters      TEXT NOT NULL DEFAULT '{}',  -- JSON
        result_count INTEGER NOT NULL,
        duration_ms  REAL NOT NULL,
        created_at   TEXT NOT NULL DEFAULT (datetime('now'))
    );

    -- Full-text search over all searchable text (BM25 via FTS5).
    CREATE VIRTUAL TABLE IF NOT EXISTS memes_fts USING fts5(
        meme_id UNINDEXED,
        dialogue_te, dialogue_en, dialogue_roman,
        caption, ocr_raw, movie_title_te, movie_title_en,
        tokenize='unicode61'
    );
    """,
    # Migration 2: distinguish animated stickers (multi-frame webp/gif) from
    # static image memes, so the UI/API can filter them.
    2: """
    ALTER TABLE memes ADD COLUMN animated INTEGER NOT NULL DEFAULT 0;
    """,
}


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Bring the database up to SCHEMA_VERSION. Returns the resulting version."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
    )
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    current = row[0] or 0
    for version in sorted(_MIGRATIONS):
        if version > current:
            conn.executescript(_MIGRATIONS[version])
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
            current = version
    conn.commit()
    return current
