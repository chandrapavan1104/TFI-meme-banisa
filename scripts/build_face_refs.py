"""Build per-actor face reference embeddings for auto-tagging.

Two stages, per actor:
  1. Fetch the actor's Wikipedia portrait and embed the largest face in it.
  2. Bootstrap in-domain references: scan memes already tagged with the actor
     (via pack-name inference) and adopt detected faces that match the
     Wikipedia embedding at a looser threshold. Meme faces are stylized and
     wildly expressive, so these extra references widen recall a lot.

Writes ~/.tfibanisa/face_refs.json. Re-run any time; it rebuilds from scratch.

Usage: .venv/bin/python scripts/build_face_refs.py [--bootstrap-threshold 0.30]
       [--max-domain-refs 8]
"""

import argparse
import io
import json
import sys
import time
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from collectors import faces
from db.init import init_db

# Actor -> candidate Wikipedia article titles (first that resolves wins).
ACTORS: dict[str, list[str]] = {
    "Brahmanandam": ["Brahmanandam"],
    "Chiranjeevi": ["Chiranjeevi"],
    "Allu Arjun": ["Allu Arjun"],
    "Pawan Kalyan": ["Pawan Kalyan"],
    "Mahesh Babu": ["Mahesh Babu"],
    "Prabhas": ["Prabhas"],
    "Jr NTR": ["N. T. Rama Rao Jr."],
    "Balakrishna": ["Nandamuri Balakrishna"],
    "Venkatesh": ["Venkatesh (actor)", "Daggubati Venkatesh"],
    "Ravi Teja": ["Ravi Teja"],
    "Ram Charan": ["Ram Charan"],
    "Nani": ["Nani (actor)"],
    "Vijay Deverakonda": ["Vijay Deverakonda"],
    "Samantha": ["Samantha Ruth Prabhu"],
    "Ali": ["Ali (actor)"],
    "Sunil": ["Sunil (actor)"],
    "M. S. Narayana": ["M. S. Narayana"],
    "Posani Krishna Murali": ["Posani Krishna Murali"],
    "Rajendra Prasad": ["Rajendra Prasad (actor)"],
    "Prakash Raj": ["Prakash Raj"],
    "Vennela Kishore": ["Vennela Kishore"],
    "Sampoornesh Babu": ["Sampoornesh Babu"],
}

UA = {"User-Agent": "TFI-meme-banisa/0.1 (personal meme tagger)"}


def wiki_portrait(client: httpx.Client, titles: list[str]) -> Image.Image | None:
    from urllib.parse import quote

    for title in titles:
        try:
            r = None
            for attempt in range(4):  # Wikipedia throttles bursts; back off
                r = client.get(
                    "https://en.wikipedia.org/api/rest_v1/page/summary/"
                    + quote(title, safe=""),
                    headers=UA, timeout=20, follow_redirects=True,
                )
                if r.status_code != 429:
                    break
                time.sleep(2 ** attempt)
            if r is None or r.status_code != 200:
                continue
            data = r.json()
            # Prefer the cached thumbnail: plenty for face embedding, and the
            # image host rate-limits original-size downloads aggressively.
            candidates = [
                (data.get("thumbnail") or {}).get("source"),
                (data.get("originalimage") or {}).get("source"),
            ]
            for url in filter(None, candidates):
                for attempt in range(4):
                    img = client.get(url, headers=UA, timeout=30, follow_redirects=True)
                    if img.status_code != 429:
                        break
                    time.sleep(3 * 2 ** attempt)
                if img.status_code == 200:
                    return Image.open(io.BytesIO(img.content)).convert("RGB")
        except (httpx.HTTPError, OSError):
            continue
    return None


def largest_face_embedding(img: Image.Image) -> np.ndarray | None:
    bgr = np.asarray(img)[:, :, ::-1]
    detected = faces.get_app().get(bgr)
    if not detected:
        return None
    best = max(detected, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    emb = np.asarray(best.normed_embedding, dtype=np.float32)
    return emb / np.linalg.norm(emb)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bootstrap-threshold", type=float, default=0.30)
    ap.add_argument("--max-domain-refs", type=int, default=8)
    ap.add_argument(
        "--only-missing", action="store_true",
        help="keep existing refs; only fetch actors not in face_refs.json",
    )
    args = ap.parse_args()

    conn = init_db()
    refs: dict[str, list[list[float]]] = {}
    if args.only_missing and faces.REFS_PATH.exists():
        refs = json.loads(faces.REFS_PATH.read_text())

    with httpx.Client() as client:
        for actor, titles in ACTORS.items():
            if args.only_missing and actor in refs:
                continue
            time.sleep(1.0)  # stay under Wikipedia's burst limits
            img = wiki_portrait(client, titles)
            if img is None:
                print(f"!! {actor}: no Wikipedia portrait found — skipped")
                continue
            wiki_emb = largest_face_embedding(img)
            if wiki_emb is None:
                print(f"!! {actor}: no face detected in portrait — skipped")
                continue
            refs[actor] = [wiki_emb.tolist()]

            # Stage 2: bootstrap from memes already tagged with this actor.
            rows = conn.execute(
                "SELECT m.id, m.image_path FROM memes m "
                "JOIN metadata md ON md.meme_id = m.id "
                "WHERE md.actors LIKE ?", (f'%"{actor}"%',),
            ).fetchall()
            domain: list[tuple[float, np.ndarray]] = []
            for row in rows:
                path = config.IMAGES_DIR / row["image_path"]
                try:
                    for emb in faces.face_embeddings(str(path)):
                        sim = float(wiki_emb @ emb)
                        if sim >= args.bootstrap_threshold:
                            domain.append((sim, emb))
                except Exception:
                    continue
            domain.sort(key=lambda t: t[0], reverse=True)
            for _, emb in domain[: args.max_domain_refs]:
                refs[actor].append(emb.tolist())
            print(
                f"   {actor}: wiki ref ok, {len(rows)} tagged memes scanned, "
                f"{min(len(domain), args.max_domain_refs)} in-domain refs added"
            )

    faces.save_refs(refs)
    print(f"\nSaved references for {len(refs)} actors -> {faces.REFS_PATH}")


if __name__ == "__main__":
    main()
