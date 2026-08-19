"""Fetch Telugu sticker packs from sticker.ly into the local store.

Searches sticker.ly (public app API) for Telugu movie/actor keywords, downloads
each pack's stickers, infers movie/actor metadata from the pack name, and
uploads everything to the local TFI-banisa API — which then runs the normal
caption/OCR/embed pipeline. Progress and dedupe state persist in
~/.tfibanisa/fetch_state.json, so re-running only fetches new content.

Usage:
    .venv/bin/python scripts/fetch_stickers.py [--api URL] [--max-stickers N]
        [--max-packs-per-keyword N] [--static-only] [--keywords k1,k2,...]
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

API_SEARCH = "http://api.sticker.ly/v3.1/stickerPack/search"
UA = "androidapp.stickerly/2.14.0 (SM-G970N; U; Android 29; en-US; scale=2.0)"
STATE_PATH = config.HOME_DIR / "fetch_state.json"

DEFAULT_KEYWORDS = [
    "telugu", "telugu comedy", "telugu memes", "telugu dialogues",
    "chiranjeevi", "pawan kalyan", "mahesh babu", "allu arjun", "prabhas",
    "jr ntr", "balakrishna", "brahmanandam", "venkatesh", "ravi teja",
    "ram charan", "nani telugu", "vijay deverakonda", "ali telugu",
    "baahubali", "pushpa", "rrr movie", "jathi ratnalu", "dj tillu",
]

# Case-insensitive substrings of pack names -> metadata.
KNOWN_ACTORS = {
    "chiranjeevi": "Chiranjeevi", "pawan": "Pawan Kalyan",
    "mahesh": "Mahesh Babu", "allu arjun": "Allu Arjun", "bunny": "Allu Arjun",
    "prabhas": "Prabhas", "ntr": "Jr NTR", "tarak": "Jr NTR",
    "balakrishna": "Balakrishna", "balayya": "Balakrishna",
    "brahmanandam": "Brahmanandam", "brahmi": "Brahmanandam",
    "venkatesh": "Venkatesh", "venky": "Venkatesh", "ravi teja": "Ravi Teja",
    "ram charan": "Ram Charan", "nani": "Nani",
    "deverakonda": "Vijay Deverakonda", "samantha": "Samantha", "ali": "Ali",
    "sunil": "Sunil", "vennela kishore": "Vennela Kishore",
}
KNOWN_MOVIES = {
    "baahubali": "Baahubali", "bahubali": "Baahubali", "pushpa": "Pushpa",
    "rrr": "RRR", "jathi ratnalu": "Jathi Ratnalu", "dj tillu": "DJ Tillu",
    "ala vaikunthapurramuloo": "Ala Vaikunthapurramuloo", "f2": "F2",
    "eega": "Eega", "magadheera": "Magadheera", "indra": "Indra",
}


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"packs": [], "hashes": []}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state))


def search_packs(client: httpx.Client, keyword: str, cursor: int) -> list[dict]:
    r = client.post(
        API_SEARCH,
        json={"keyword": keyword, "cursor": cursor, "limit": 20},
        headers={"User-Agent": UA},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["result"]["stickerPacks"]


def infer_metadata(pack_name: str) -> dict:
    low = pack_name.lower()
    actors = sorted({v for k, v in KNOWN_ACTORS.items() if k in low})
    movies = [v for k, v in KNOWN_MOVIES.items() if k in low]
    return {"actors": actors, "movie": movies[0] if movies else None}


def upload_sticker(
    api: str, client: httpx.Client, data: bytes, pack: dict, meta: dict
) -> str:
    form = {
        "context_tags": pack["name"].replace(",", " "),
        "manual_notes": (
            f"Source: sticker.ly pack '{pack['name']}' by "
            f"{pack.get('authorName', '?')} — {pack.get('shareUrl', '')}"
        ),
    }
    if meta["actors"]:
        form["actors"] = ",".join(meta["actors"])
    if meta["movie"]:
        form["movie_title_en"] = meta["movie"]
    r = client.post(
        f"{api}/api/memes/upload",
        files={"file": ("sticker.webp", data, "image/webp")},
        data=form,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["meme"]["id"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--max-stickers", type=int, default=500)
    ap.add_argument("--max-packs-per-keyword", type=int, default=6)
    ap.add_argument("--pages-per-keyword", type=int, default=2)
    ap.add_argument("--static-only", action="store_true")
    ap.add_argument("--keywords", help="comma-separated; overrides defaults")
    args = ap.parse_args()

    keywords = (
        [k.strip() for k in args.keywords.split(",") if k.strip()]
        if args.keywords else DEFAULT_KEYWORDS
    )
    state = load_state()
    seen_packs = set(state["packs"])
    seen_hashes = set(state["hashes"])
    uploaded = skipped = failed = 0

    with httpx.Client() as client:
        # Fail fast if the local server is down.
        client.get(f"{args.api}/health", timeout=10).raise_for_status()

        for keyword in keywords:
            if uploaded >= args.max_stickers:
                break
            packs_taken = 0
            for cursor in range(args.pages_per_keyword):
                if packs_taken >= args.max_packs_per_keyword:
                    break
                try:
                    packs = search_packs(client, keyword, cursor)
                except httpx.HTTPError as exc:
                    print(f"  !! search '{keyword}' p{cursor} failed: {exc}")
                    break
                for pack in packs:
                    if uploaded >= args.max_stickers or packs_taken >= args.max_packs_per_keyword:
                        break
                    if pack["packId"] in seen_packs or pack.get("isPaid"):
                        continue
                    if args.static_only and pack.get("isAnimated"):
                        continue
                    meta = infer_metadata(pack["name"])
                    print(
                        f"[{keyword}] pack {pack['packId']} '{pack['name']}' "
                        f"({len(pack['resourceFiles'])} stickers, "
                        f"{'animated' if pack.get('isAnimated') else 'static'})"
                    )
                    pack_ok = 0
                    for fname in pack["resourceFiles"]:
                        if uploaded >= args.max_stickers:
                            break
                        url = pack["resourceUrlPrefix"] + fname
                        try:
                            resp = client.get(url, timeout=30)
                            resp.raise_for_status()
                            data = resp.content
                        except httpx.HTTPError:
                            failed += 1
                            continue
                        digest = hashlib.sha256(data).hexdigest()[:16]
                        if digest in seen_hashes:
                            skipped += 1
                            continue
                        try:
                            upload_sticker(args.api, client, data, pack, meta)
                        except httpx.HTTPError as exc:
                            failed += 1
                            print(f"  !! upload failed: {exc}")
                            continue
                        seen_hashes.add(digest)
                        uploaded += 1
                        pack_ok += 1
                        time.sleep(0.15)  # politeness to the CDN
                    seen_packs.add(pack["packId"])
                    packs_taken += 1
                    print(f"    -> {pack_ok} uploaded (total {uploaded})")
                    state["packs"] = sorted(seen_packs)
                    state["hashes"] = sorted(seen_hashes)
                    save_state(state)
                time.sleep(0.3)

    print(
        f"\nDone: {uploaded} uploaded, {skipped} duplicates skipped, "
        f"{failed} failed. Background jobs are processing; watch progress at "
        f"{args.api} or /api/memes/{{id}}/status."
    )


if __name__ == "__main__":
    main()
