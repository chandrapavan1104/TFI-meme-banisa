"""Face-recognition sweep: tag actors across the whole meme collection.

For every meme, detect faces (a meme can hold several people), match each
face against the per-actor references built by build_face_refs.py, and merge
every confident match into the meme's actors via POST /api/memes/{id}/auto_tag
(which never removes tags and never marks memes verified).

Run with --dry-run first to inspect the score distribution and proposed tags
before writing anything.

Usage:
    .venv/bin/python scripts/face_tag.py [--api URL] [--threshold 0.38]
        [--dry-run] [--limit N] [--only-untagged]
"""

import argparse
import collections
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from collectors import faces
from db.init import init_db


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--threshold", type=float, default=faces.MATCH_THRESHOLD)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="0 = all memes")
    ap.add_argument(
        "--only-untagged", action="store_true",
        help="skip memes that already have actor tags",
    )
    args = ap.parse_args()

    refs = faces.load_refs()
    print(f"References: {len(refs)} actors "
          f"({sum(m.shape[0] for m in refs.values())} embeddings)")

    conn = init_db()
    where = "WHERE md.actors = '[]'" if args.only_untagged else ""
    rows = conn.execute(
        f"SELECT m.id, m.image_path FROM memes m "
        f"JOIN metadata md ON md.meme_id = m.id {where} ORDER BY m.id"
    ).fetchall()
    if args.limit:
        rows = rows[: args.limit]
    print(f"Scanning {len(rows)} memes (threshold {args.threshold}) ...")

    per_actor: collections.Counter = collections.Counter()
    multi = no_face = tagged = failed = 0
    start = time.time()

    with httpx.Client() as client:
        if not args.dry_run:
            client.get(f"{args.api}/health", timeout=10).raise_for_status()
        for i, row in enumerate(rows, 1):
            path = config.IMAGES_DIR / row["image_path"]
            try:
                embs = faces.face_embeddings(str(path))
            except Exception:
                failed += 1
                continue
            if not embs:
                no_face += 1
                continue
            matched = faces.match_actors(embs, refs, threshold=args.threshold)
            if not matched:
                continue
            if len(matched) > 1:
                multi += 1
            for actor in matched:
                per_actor[actor] += 1
            if args.dry_run:
                names = ", ".join(f"{a} ({s:.2f})" for a, s in sorted(matched.items()))
                print(f"  {row['id']}: {len(embs)} face(s) -> {names}")
            else:
                try:
                    client.post(
                        f"{args.api}/api/memes/{row['id']}/auto_tag",
                        json={"actors": sorted(matched)},
                        timeout=30,
                    ).raise_for_status()
                    tagged += 1
                except httpx.HTTPError as exc:
                    failed += 1
                    print(f"  !! tag {row['id']} failed: {exc}")
            if i % 250 == 0:
                rate = i / (time.time() - start)
                print(f"  ... {i}/{len(rows)} ({rate:.1f} memes/s)")

    print(f"\n{'DRY RUN — ' if args.dry_run else ''}Done in "
          f"{time.time() - start:.0f}s: {sum(per_actor.values())} matches on "
          f"{len(rows)} memes ({multi} multi-actor, {no_face} without faces, "
          f"{failed} errors{'' if args.dry_run else f', {tagged} memes tagged'})")
    for actor, n in per_actor.most_common():
        print(f"  {n:5d}  {actor}")


if __name__ == "__main__":
    main()
