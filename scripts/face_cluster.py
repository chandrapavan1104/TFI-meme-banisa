"""Extract, cluster, and rank all faces in the collection for naming.

Step 1 (extract): detect every face in every meme, store its embedding + bbox
in the `faces` table, and save a cropped thumbnail to ~/.tfibanisa/faces/.
Resumable — memes already scanned are skipped (state in face_scan.json).

Step 2 (cluster): group faces by identity with agglomerative clustering
(average linkage, cosine distance) and store cluster ids ranked by frequency
(cluster 1 = most frequent face). Prints the ranking with suggested names from
existing face references.

Name the clusters in the admin UI (/admin -> Faces tab), which tags every
sticker in the cluster and teaches the recognizer.

Usage: .venv/bin/python scripts/face_cluster.py [--threshold 0.50]
       [--recluster-only] [--min-count 2]
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from collectors import faces
from db import store
from db.init import init_db

SCAN_STATE = config.HOME_DIR / "face_scan.json"


def save_crop(image_path: Path, bbox: list[float], face_id: int) -> None:
    img = Image.open(image_path).convert("RGB")
    x1, y1, x2, y2 = bbox
    pad_x, pad_y = (x2 - x1) * 0.3, (y2 - y1) * 0.3
    box = (
        max(0, int(x1 - pad_x)), max(0, int(y1 - pad_y)),
        min(img.width, int(x2 + pad_x)), min(img.height, int(y2 + pad_y)),
    )
    crop = img.crop(box)
    crop.thumbnail((180, 180))
    crop.save(config.FACES_DIR / f"{face_id}.jpg", "JPEG", quality=88)


def extract(conn) -> None:
    scanned: dict = json.loads(SCAN_STATE.read_text()) if SCAN_STATE.exists() else {}
    rows = conn.execute("SELECT id, image_path FROM memes").fetchall()
    todo = [r for r in rows if r["id"] not in scanned]
    print(f"Extracting faces: {len(todo)} memes to scan ({len(scanned)} done before)")
    start = time.time()
    for i, row in enumerate(todo, 1):
        path = config.IMAGES_DIR / row["image_path"]
        n = 0
        try:
            for bbox, emb in faces.detect_faces(str(path)):
                face_id = store.insert_face(conn, row["id"], bbox, emb.tobytes())
                try:
                    save_crop(path, bbox, face_id)
                except OSError:
                    pass
                n += 1
        except Exception as exc:  # noqa: BLE001 — skip unreadable images
            print(f"  !! {row['id']}: {type(exc).__name__}: {exc}")
        scanned[row["id"]] = n
        if i % 100 == 0:
            SCAN_STATE.write_text(json.dumps(scanned))
        if i % 500 == 0:
            print(f"  ... {i}/{len(todo)} ({i / (time.time() - start):.1f} memes/s)")
    SCAN_STATE.write_text(json.dumps(scanned))


def cluster(conn, threshold: float, min_count: int) -> None:
    from sklearn.cluster import AgglomerativeClustering

    rows = store.all_faces(conn)
    if len(rows) < 2:
        print("Not enough faces to cluster")
        return
    embs = np.stack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
    print(f"Clustering {len(rows)} faces (avg-linkage cosine, threshold {threshold}) ...")
    hac = AgglomerativeClustering(
        n_clusters=None, distance_threshold=threshold,
        metric="cosine", linkage="average",
    ).fit(embs)

    # Rank clusters by distinct-meme frequency; 1 = most frequent.
    by_label: dict[int, list[int]] = {}
    for idx, lab in enumerate(hac.labels_):
        by_label.setdefault(int(lab), []).append(idx)
    def meme_count(idxs): return len({rows[i]["meme_id"] for i in idxs})
    ranked = sorted(by_label.values(), key=meme_count, reverse=True)

    assignments: dict[int, int | None] = {}
    for rank, idxs in enumerate(ranked, start=1):
        cid = rank if len(idxs) > 1 else None  # singletons stay unclustered
        for i in idxs:
            assignments[rows[i]["id"]] = cid
    store.set_face_clusters(conn, assignments)

    # Print top clusters with suggestions from known references.
    refs = faces.load_refs() if faces.refs_available() else {}
    print(f"\n{'rank':>4}  {'memes':>5}  {'faces':>5}  suggestion")
    shown = 0
    for rank, idxs in enumerate(ranked, start=1):
        if len(idxs) < 2 or meme_count(idxs) < min_count or shown >= 40:
            continue
        centroid = embs[idxs].mean(axis=0)
        centroid /= np.linalg.norm(centroid)
        suggestion = ""
        best = 0.0
        for actor, mat in refs.items():
            sim = float(np.max(mat @ centroid))
            if sim > best and sim >= 0.40:
                suggestion, best = f"{actor} ({sim:.2f})", sim
        print(f"{rank:>4}  {meme_count(idxs):>5}  {len(idxs):>5}  {suggestion}")
        shown += 1
    n_multi = sum(1 for v in by_label.values() if len(v) > 1)
    print(f"\n{n_multi} clusters with 2+ faces; name them at /admin (Faces tab)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--threshold", type=float, default=0.50,
                    help="cosine distance cut (lower = stricter identity)")
    ap.add_argument("--min-count", type=int, default=2)
    ap.add_argument("--recluster-only", action="store_true",
                    help="skip extraction; just re-run clustering")
    args = ap.parse_args()

    config.ensure_dirs()
    conn = init_db()
    if not args.recluster_only:
        extract(conn)
    cluster(conn, args.threshold, args.min_count)


if __name__ == "__main__":
    main()
