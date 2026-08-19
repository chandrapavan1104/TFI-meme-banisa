"""CRUD helpers over the SQLite database.

All functions take an open sqlite3.Connection (see db.init.connect) and are
synchronous; the server calls them directly (SQLite is fast enough here) or
from worker threads for job updates. A module-level lock serializes access:
one connection is shared between the request threadpool and the job worker,
and sqlite3 cursors are not safe under concurrent use.
"""

import functools
import json
import sqlite3
import threading

_db_lock = threading.RLock()


def _locked(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _db_lock:
            return fn(*args, **kwargs)

    return wrapper

_JSON_FIELDS = {"actors", "emotion_tags", "context_tags"}
_METADATA_FIELDS = {
    "movie_title_te", "movie_title_en", "actors",
    "dialogue_te", "dialogue_en", "dialogue_roman",
    "emotion_tags", "context_tags", "caption", "ocr_raw", "manual_notes",
}
_FTS_FIELDS = (
    "dialogue_te", "dialogue_en", "dialogue_roman",
    "caption", "ocr_raw", "movie_title_te", "movie_title_en", "manual_notes",
)


@_locked
def _row_to_meme(row: sqlite3.Row) -> dict:
    d = dict(row)
    for f in _JSON_FIELDS:
        if f in d:
            d[f] = json.loads(d[f] or "[]")
    d["auto_generated"] = bool(d.get("auto_generated", 1))
    d["verified"] = bool(d.get("verified", 0))
    d["animated"] = bool(d.get("animated", 0))
    return d


# --- Memes -----------------------------------------------------------------

@_locked
def create_meme(
    conn: sqlite3.Connection, meme_id: str, image_path: str, animated: bool = False
) -> bool:
    """Insert a meme + empty metadata row. Returns False if it already exists."""
    try:
        conn.execute(
            "INSERT INTO memes (id, image_path, animated) VALUES (?, ?, ?)",
            (meme_id, image_path, int(animated)),
        )
    except sqlite3.IntegrityError:
        return False
    conn.execute("INSERT INTO metadata (meme_id) VALUES (?)", (meme_id,))
    conn.commit()
    return True


@_locked
def get_meme(conn: sqlite3.Connection, meme_id: str) -> dict | None:
    row = conn.execute(
        """SELECT m.*, md.movie_title_te, md.movie_title_en, md.actors,
                  md.dialogue_te, md.dialogue_en, md.dialogue_roman,
                  md.emotion_tags, md.context_tags, md.caption, md.ocr_raw,
                  md.manual_notes
           FROM memes m JOIN metadata md ON md.meme_id = m.id
           WHERE m.id = ?""",
        (meme_id,),
    ).fetchone()
    return _row_to_meme(row) if row else None


@_locked
def list_memes(
    conn: sqlite3.Connection,
    limit: int = 10,
    offset: int = 0,
    verified: bool | None = None,
    animated: bool | None = None,
    pack: str | None = None,
    actor: str | None = None,
    untagged: bool = False,
    cluster: int | None = None,
) -> tuple[list[dict], int]:
    """Paginated meme list, newest first. Returns (rows, total_count)."""
    clauses, params = [], []
    if verified is not None:
        clauses.append("m.verified = ?")
        params.append(int(verified))
    if animated is not None:
        clauses.append("m.animated = ?")
        params.append(int(animated))
    if pack:
        clauses.append("json_extract(md.context_tags, '$[0]') = ?")
        params.append(pack)
    if actor:
        clauses.append("md.actors LIKE ?")
        params.append(f'%"{actor}"%')
    if untagged:  # no recognized face, no dialogue, no OCR text — junk candidates
        clauses.append(
            "md.actors = '[]' AND COALESCE(md.dialogue_te,'') = '' "
            "AND COALESCE(md.ocr_raw,'') = ''"
        )
    if cluster is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM faces f WHERE f.meme_id = m.id AND f.cluster = ?)"
        )
        params.append(cluster)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    total = conn.execute(
        f"SELECT COUNT(*) FROM memes m JOIN metadata md ON md.meme_id = m.id {where}",
        params,
    ).fetchone()[0]
    rows = conn.execute(
        f"""SELECT m.*, md.movie_title_te, md.movie_title_en, md.actors,
                   md.dialogue_te, md.dialogue_en, md.dialogue_roman,
                   md.emotion_tags, md.context_tags, md.caption, md.ocr_raw,
                   md.manual_notes
            FROM memes m JOIN metadata md ON md.meme_id = m.id
            {where} ORDER BY m.upload_date DESC, m.id LIMIT ? OFFSET ?""",
        (*params, limit, offset),
    ).fetchall()
    return [_row_to_meme(r) for r in rows], total


@_locked
def update_metadata(
    conn: sqlite3.Connection,
    meme_id: str,
    fields: dict,
    mark_verified: bool = False,
) -> dict | None:
    """Partial update of metadata fields; refreshes the FTS index.

    Only keys in _METADATA_FIELDS are applied. Returns the updated meme.
    """
    updates = {k: v for k, v in fields.items() if k in _METADATA_FIELDS}
    if updates:
        sets, params = [], []
        for k, v in updates.items():
            if k in _JSON_FIELDS:
                v = json.dumps(v or [])
            sets.append(f"{k} = ?")
            params.append(v)
        params.append(meme_id)
        conn.execute(
            f"UPDATE metadata SET {', '.join(sets)} WHERE meme_id = ?", params
        )
    if mark_verified:
        conn.execute("UPDATE memes SET verified = 1 WHERE id = ?", (meme_id,))
    conn.commit()
    refresh_fts(conn, meme_id)
    return get_meme(conn, meme_id)


@_locked
def set_rating(conn: sqlite3.Connection, meme_id: str, rating: int) -> None:
    conn.execute("UPDATE memes SET rating = ? WHERE id = ?", (rating, meme_id))
    conn.commit()


@_locked
def delete_meme(conn: sqlite3.Connection, meme_id: str) -> None:
    conn.execute("DELETE FROM memes_fts WHERE meme_id = ?", (meme_id,))
    conn.execute("DELETE FROM memes WHERE id = ?", (meme_id,))
    conn.commit()


# --- Distinct value lists ---------------------------------------------------

@_locked
def _distinct_json_values(conn: sqlite3.Connection, column: str) -> list[str]:
    values: set[str] = set()
    for (raw,) in conn.execute(f"SELECT {column} FROM metadata"):
        values.update(json.loads(raw or "[]"))
    return sorted(values)


@_locked
def list_packs(conn: sqlite3.Connection, limit: int = 60) -> list[dict]:
    """Sticker packs (first context tag), biggest first, with a cover image."""
    rows = conn.execute(
        """SELECT json_extract(md.context_tags, '$[0]') AS name,
                  COUNT(*) AS count, MIN(m.image_path) AS cover_path
           FROM metadata md JOIN memes m ON m.id = md.meme_id
           WHERE json_extract(md.context_tags, '$[0]') IS NOT NULL
             AND json_extract(md.context_tags, '$[0]') != ''
           GROUP BY name ORDER BY count DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


@_locked
def list_movies(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT DISTINCT movie_title_en, movie_title_te FROM metadata
           WHERE movie_title_en IS NOT NULL OR movie_title_te IS NOT NULL
           ORDER BY movie_title_en"""
    ).fetchall()
    return [dict(r) for r in rows]


@_locked
def list_actors(conn: sqlite3.Connection) -> list[str]:
    return _distinct_json_values(conn, "actors")


@_locked
def list_emotions(conn: sqlite3.Connection) -> list[str]:
    return _distinct_json_values(conn, "emotion_tags")


# --- Full-text search (BM25) ------------------------------------------------

@_locked
def refresh_fts(conn: sqlite3.Connection, meme_id: str) -> None:
    """Rebuild the FTS row for one meme from its current metadata."""
    row = conn.execute(
        f"SELECT {', '.join(_FTS_FIELDS)} FROM metadata WHERE meme_id = ?",
        (meme_id,),
    ).fetchone()
    conn.execute("DELETE FROM memes_fts WHERE meme_id = ?", (meme_id,))
    if row:
        conn.execute(
            f"INSERT INTO memes_fts (meme_id, {', '.join(_FTS_FIELDS)}) "
            f"VALUES (?{', ?' * len(_FTS_FIELDS)})",
            (meme_id, *[row[f] or "" for f in _FTS_FIELDS]),
        )
    conn.commit()


@_locked
def fts_search(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[str]:
    """BM25 keyword search. Returns meme_ids best-first. Never raises on syntax."""
    # Quote each term to avoid FTS5 query-syntax errors on user input.
    terms = [t.replace('"', '""') for t in query.split() if t.strip()]
    if not terms:
        return []
    match = " OR ".join(f'"{t}"' for t in terms)
    try:
        rows = conn.execute(
            "SELECT meme_id FROM memes_fts WHERE memes_fts MATCH ? "
            "ORDER BY bm25(memes_fts) LIMIT ?",
            (match, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [r["meme_id"] for r in rows]


# --- Jobs -------------------------------------------------------------------

@_locked
def create_job(conn: sqlite3.Connection, meme_id: str, job_type: str) -> int:
    cur = conn.execute(
        "INSERT INTO jobs (meme_id, job_type) VALUES (?, ?)", (meme_id, job_type)
    )
    conn.commit()
    return cur.lastrowid


@_locked
def update_job(
    conn: sqlite3.Connection,
    job_id: int,
    status: str,
    error: str | None = None,
    bump_attempts: bool = False,
) -> None:
    conn.execute(
        "UPDATE jobs SET status = ?, error = ?, updated_at = datetime('now'), "
        "attempts = attempts + ? WHERE id = ?",
        (status, error, int(bump_attempts), job_id),
    )
    conn.commit()


@_locked
def unfinished_jobs(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, meme_id, job_type FROM jobs "
        "WHERE status IN ('PENDING', 'RUNNING') ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


@_locked
def jobs_for_meme(conn: sqlite3.Connection, meme_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM jobs WHERE meme_id = ? ORDER BY id", (meme_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# --- Faces (clustering + labeling) -------------------------------------------

@_locked
def insert_face(
    conn: sqlite3.Connection, meme_id: str, bbox: list[float], embedding: bytes
) -> int:
    cur = conn.execute(
        "INSERT INTO faces (meme_id, bbox, embedding) VALUES (?, ?, ?)",
        (meme_id, json.dumps(bbox), embedding),
    )
    conn.commit()
    return cur.lastrowid


@_locked
def all_faces(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT id, meme_id, embedding, cluster, label FROM faces").fetchall()
    return [dict(r) for r in rows]


@_locked
def set_face_clusters(conn: sqlite3.Connection, assignments: dict[int, int | None]) -> None:
    conn.executemany(
        "UPDATE faces SET cluster = ? WHERE id = ?",
        [(c, fid) for fid, c in assignments.items()],
    )
    conn.commit()


@_locked
def clusters_summary(
    conn: sqlite3.Connection, min_count: int = 2, limit: int = 100,
    unlabeled_only: bool = False,
) -> list[dict]:
    """Ranked clusters: sticker count, face count, label, sample face ids."""
    where = "WHERE f.cluster IS NOT NULL"
    if unlabeled_only:
        where += " AND f.label IS NULL"
    rows = conn.execute(
        f"""SELECT f.cluster AS cluster, COUNT(*) AS faces,
                   COUNT(DISTINCT f.meme_id) AS memes,
                   MAX(f.label) AS label, MAX(fc.description) AS description
            FROM faces f LEFT JOIN face_clusters fc ON fc.cluster = f.cluster
            {where} GROUP BY f.cluster
            HAVING COUNT(DISTINCT f.meme_id) >= ?
            ORDER BY memes DESC LIMIT ?""",
        (min_count, limit),
    ).fetchall()
    out = []
    for r in rows:
        samples = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM faces WHERE cluster = ? ORDER BY id LIMIT 6",
                (r["cluster"],),
            )
        ]
        out.append({**dict(r), "samples": samples})
    return out


@_locked
def cluster_meme_ids(conn: sqlite3.Connection, cluster: int) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT meme_id FROM faces WHERE cluster = ?", (cluster,)
    ).fetchall()
    return [r["meme_id"] for r in rows]


@_locked
def label_cluster(conn: sqlite3.Connection, cluster: int, label: str) -> int:
    cur = conn.execute(
        "UPDATE faces SET label = ? WHERE cluster = ?", (label, cluster)
    )
    conn.execute(
        "INSERT INTO face_clusters (cluster, label) VALUES (?, ?) "
        "ON CONFLICT(cluster) DO UPDATE SET label = excluded.label, "
        "updated_at = datetime('now')",
        (cluster, label),
    )
    conn.commit()
    return cur.rowcount


@_locked
def set_cluster_description(
    conn: sqlite3.Connection, cluster: int, description: str
) -> None:
    conn.execute(
        "INSERT INTO face_clusters (cluster, description) VALUES (?, ?) "
        "ON CONFLICT(cluster) DO UPDATE SET description = excluded.description, "
        "updated_at = datetime('now')",
        (cluster, description),
    )
    conn.commit()


@_locked
def cluster_meta(conn: sqlite3.Connection, cluster: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM face_clusters WHERE cluster = ?", (cluster,)
    ).fetchone()
    return dict(row) if row else None


@_locked
def delete_cluster_meta(conn: sqlite3.Connection, cluster: int) -> None:
    conn.execute("DELETE FROM face_clusters WHERE cluster = ?", (cluster,))
    conn.commit()


@_locked
def face_ids_for_memes(conn: sqlite3.Connection, meme_ids: list[str]) -> list[int]:
    if not meme_ids:
        return []
    q = ",".join("?" * len(meme_ids))
    rows = conn.execute(
        f"SELECT id FROM faces WHERE meme_id IN ({q})", meme_ids
    ).fetchall()
    return [r["id"] for r in rows]


@_locked
def cluster_embeddings(conn: sqlite3.Connection, cluster: int, limit: int = 5) -> list[bytes]:
    rows = conn.execute(
        "SELECT embedding FROM faces WHERE cluster = ? ORDER BY id LIMIT ?",
        (cluster, limit),
    ).fetchall()
    return [r["embedding"] for r in rows]


# --- Embeddings log ---------------------------------------------------------

@_locked
def log_embedding(
    conn: sqlite3.Connection, meme_id: str, model: str, vector_type: str
) -> None:
    conn.execute(
        "INSERT INTO embeddings_log (meme_id, embedding_model, text_vector_type) "
        "VALUES (?, ?, ?)",
        (meme_id, model, vector_type),
    )
    conn.commit()


# --- Search analytics -------------------------------------------------------

@_locked
def log_search(
    conn: sqlite3.Connection,
    query: str,
    filters: dict,
    result_count: int,
    duration_ms: float,
) -> None:
    conn.execute(
        "INSERT INTO searches (query, filters, result_count, duration_ms) "
        "VALUES (?, ?, ?, ?)",
        (query, json.dumps(filters), result_count, duration_ms),
    )
    conn.commit()


@_locked
def top_queries(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        """SELECT query, COUNT(*) AS count, AVG(duration_ms) AS avg_ms,
                  MAX(created_at) AS last_used
           FROM searches GROUP BY query ORDER BY count DESC, last_used DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
