"""Rebuild the Qdrant collection and re-embed every meme.

Needed after the vector schema changes (e.g. adding the `description` vector),
since a collection's named vectors are fixed at creation time.

The server holds the embedded-Qdrant lock, so stop it first:

    launchctl stop com.tfibanisa.server
    .venv/bin/python scripts/reindex.py
    launchctl start com.tfibanisa.server

Usage: .venv/bin/python scripts/reindex.py [--batch 200]
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from collectors import embeddings
from db import store
from db.init import init_db
from server import qdrant_store
from server.qdrant_schema import create_collection_if_not_exists, delete_collection


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch", type=int, default=200, help="progress print interval")
    args = ap.parse_args()

    config.ensure_dirs()
    conn = init_db()
    client = qdrant_store.get_client()

    print(f"Recreating collection '{config.QDRANT_COLLECTION}' ...")
    delete_collection(client)
    create_collection_if_not_exists(client)

    rows = conn.execute("SELECT id FROM memes ORDER BY id").fetchall()
    print(f"Re-embedding {len(rows)} memes ...")
    start = time.time()
    indexed = skipped = 0
    for i, row in enumerate(rows, 1):
        meme = store.get_meme(conn, row["id"])
        if not meme:
            continue
        vectors = embeddings.embed_multifield(
            meme.get("dialogue_te"), meme.get("dialogue_en"), meme.get("caption"),
            description=meme.get("description"),
        )
        if not vectors:
            skipped += 1
            continue
        qdrant_store.upsert_meme(
            client, meme["id"], vectors,
            payload={
                "movie_title_en": meme.get("movie_title_en"),
                "movie_title_te": meme.get("movie_title_te"),
                "actors": meme.get("actors") or [],
                "emotion_tags": meme.get("emotion_tags") or [],
                "context_tags": meme.get("context_tags") or [],
                "verified": bool(meme.get("verified")),
            },
        )
        indexed += 1
        if i % args.batch == 0:
            rate = i / (time.time() - start)
            print(f"  ... {i}/{len(rows)} ({rate:.1f}/s)")
    client.close()
    print(f"Done in {time.time() - start:.0f}s: {indexed} indexed, "
          f"{skipped} skipped (no text yet)")


if __name__ == "__main__":
    main()
