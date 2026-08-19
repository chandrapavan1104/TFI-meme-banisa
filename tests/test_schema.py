"""Schema creation, migration idempotency, and store CRUD basics."""

from db import store
from db.schema import SCHEMA_VERSION, apply_migrations


def test_schema_creates_all_tables(conn):
    tables = {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    for t in ("memes", "metadata", "embeddings_log", "jobs", "searches", "memes_fts"):
        assert t in tables


def test_migration_idempotent(conn):
    v1 = apply_migrations(conn)
    v2 = apply_migrations(conn)
    assert v1 == v2 == SCHEMA_VERSION


def test_meme_crud_roundtrip(conn):
    assert store.create_meme(conn, "abc123", "abc123.png")
    assert not store.create_meme(conn, "abc123", "abc123.png")  # duplicate

    meme = store.get_meme(conn, "abc123")
    assert meme["image_path"] == "abc123.png"
    assert meme["actors"] == [] and not meme["verified"]

    updated = store.update_metadata(
        conn, "abc123",
        {"dialogue_te": "ఈ జీవితం", "actors": ["Chiranjeevi"], "emotion_tags": ["sad"]},
        mark_verified=True,
    )
    assert updated["verified"]
    assert updated["actors"] == ["Chiranjeevi"]
    assert store.list_actors(conn) == ["Chiranjeevi"]
    assert store.list_emotions(conn) == ["sad"]


def test_fts_search(conn):
    store.create_meme(conn, "m1", "m1.png")
    store.create_meme(conn, "m2", "m2.png")
    store.update_metadata(conn, "m1", {"dialogue_te": "ఈ జీవితం ఒక సమరం"})
    store.update_metadata(conn, "m2", {"caption": "a happy dance scene"})

    assert store.fts_search(conn, "జీవితం") == ["m1"]
    assert store.fts_search(conn, "happy dance") == ["m2"]
    assert store.fts_search(conn, "nonexistentword") == []
    # Malicious/odd FTS syntax must not raise.
    assert store.fts_search(conn, '"AND OR NOT (') == []


def test_jobs_lifecycle(conn):
    store.create_meme(conn, "m1", "m1.png")
    job_id = store.create_job(conn, "m1", "CAPTION")
    store.update_job(conn, job_id, "RUNNING", bump_attempts=True)
    store.update_job(conn, job_id, "DONE")
    jobs = store.jobs_for_meme(conn, "m1")
    assert jobs[0]["status"] == "DONE" and jobs[0]["attempts"] == 1


def test_search_analytics(conn):
    store.log_search(conn, "sad scene", {}, 3, 42.0)
    store.log_search(conn, "sad scene", {}, 2, 38.0)
    store.log_search(conn, "dance", {}, 1, 20.0)
    top = store.top_queries(conn)
    assert top[0]["query"] == "sad scene" and top[0]["count"] == 2
