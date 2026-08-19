"""Database initialization: run `python -m db.init` to create/migrate the DB."""

import sqlite3
from pathlib import Path

import config
from db.schema import apply_migrations


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with sane defaults (WAL, foreign keys, rows as dicts)."""
    path = Path(db_path) if db_path else config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Create/migrate the database and return an open connection."""
    conn = connect(db_path)
    version = apply_migrations(conn)
    return conn


if __name__ == "__main__":
    config.ensure_dirs()
    conn = init_db()
    v = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    print(f"Database ready at {config.DB_PATH} (schema v{v})")
