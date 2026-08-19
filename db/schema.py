"""SQLite schema and migrations for TFI-meme-banisa metadata."""

import sqlite3

SCHEMA_VERSION = 5

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
    # Migration 3: detected faces for clustering + labeling. One row per face
    # found in a meme; embedding is a float32 blob (512 dims, L2-normalized);
    # cluster is assigned by scripts/face_cluster.py; label is the human-given
    # character name.
    3: """
    CREATE TABLE IF NOT EXISTS faces (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        meme_id   TEXT NOT NULL REFERENCES memes(id) ON DELETE CASCADE,
        bbox      TEXT NOT NULL,            -- JSON [x1,y1,x2,y2]
        embedding BLOB NOT NULL,            -- float32[512]
        cluster   INTEGER,                  -- NULL until clustered
        label     TEXT                      -- character name once assigned
    );
    CREATE INDEX IF NOT EXISTS idx_faces_meme ON faces(meme_id);
    CREATE INDEX IF NOT EXISTS idx_faces_cluster ON faces(cluster);
    """,
    # Migration 4: cluster-level metadata (label + free-text description), and
    # rebuild the FTS table to include manual_notes so cluster descriptions
    # propagated into notes become keyword-searchable.
    4: """
    CREATE TABLE IF NOT EXISTS face_clusters (
        cluster     INTEGER PRIMARY KEY,
        label       TEXT,
        description TEXT,
        updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
    );
    DROP TABLE IF EXISTS memes_fts;
    CREATE VIRTUAL TABLE memes_fts USING fts5(
        meme_id UNINDEXED,
        dialogue_te, dialogue_en, dialogue_roman,
        caption, ocr_raw, movie_title_te, movie_title_en, manual_notes,
        tokenize='unicode61'
    );
    INSERT INTO memes_fts (meme_id, dialogue_te, dialogue_en, dialogue_roman,
                           caption, ocr_raw, movie_title_te, movie_title_en,
                           manual_notes)
        SELECT meme_id, COALESCE(dialogue_te,''), COALESCE(dialogue_en,''),
               COALESCE(dialogue_roman,''), COALESCE(caption,''),
               COALESCE(ocr_raw,''), COALESCE(movie_title_te,''),
               COALESCE(movie_title_en,''), COALESCE(manual_notes,'')
        FROM metadata;
    """,
    # Migration 5: first-class `description` on each meme — the primary search
    # signal. Filled from face-cluster descriptions and hand-editable. Indexed
    # in FTS (keyword) and embedded as its own Qdrant vector (semantic).
    5: """
    ALTER TABLE metadata ADD COLUMN description TEXT;
    DROP TABLE IF EXISTS memes_fts;
    CREATE VIRTUAL TABLE memes_fts USING fts5(
        meme_id UNINDEXED,
        description,
        dialogue_te, dialogue_en, dialogue_roman,
        caption, ocr_raw, movie_title_te, movie_title_en, manual_notes,
        tokenize='unicode61'
    );
    INSERT INTO memes_fts (meme_id, description, dialogue_te, dialogue_en,
                           dialogue_roman, caption, ocr_raw, movie_title_te,
                           movie_title_en, manual_notes)
        SELECT meme_id, COALESCE(description,''), COALESCE(dialogue_te,''),
               COALESCE(dialogue_en,''), COALESCE(dialogue_roman,''),
               COALESCE(caption,''), COALESCE(ocr_raw,''),
               COALESCE(movie_title_te,''), COALESCE(movie_title_en,''),
               COALESCE(manual_notes,'')
        FROM metadata;
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
