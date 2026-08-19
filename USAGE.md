# Usage Guide

Open http://localhost:8000.

## Uploading memes

Click **➕ Upload a meme**, pick a JPEG/PNG/WebP (≤10 MB), optionally fill in
movie, dialogue, actors, and emotions, and hit Upload. A progress bar tracks
the background pipeline (caption → OCR → embedding); the meme becomes
searchable when it completes (a few seconds per image).

Tips:
- Metadata is optional — auto-tagging alone is usually enough to find a meme
  later, but a movie name + emotions make filters much more useful.
- Re-uploading the same image is safe: it reuses the record and re-runs the
  pipeline (useful after model upgrades).
- Batch uploads via API:
  ```bash
  for f in ~/memes/*.jpg; do
    curl -s -X POST localhost:8000/api/memes/upload -F "file=@$f;type=image/jpeg" > /dev/null
  done
  ```

## Fetching stickers from the internet

`scripts/fetch_stickers.py` pulls public Telugu sticker packs from sticker.ly
(where most Telugu WhatsApp sticker packs are published) and feeds them through
the normal pipeline:

```bash
.venv/bin/python scripts/fetch_stickers.py --max-stickers 500
```

It searches a built-in list of Telugu movie/actor keywords (override with
`--keywords "pushpa,brahmanandam"`), infers movie/actor metadata from pack
names, records the source pack + author in each meme's notes, and skips
anything already fetched (state in `~/.tfibanisa/fetch_state.json`) — so
re-running it periodically only adds new packs. Use `--static-only` to skip
animated packs. Stickers are processed in the background after upload; the
collection becomes searchable as jobs complete.

## Searching

Type into the search box — results update as you type. All of these work:

- **Scene descriptions (English):** `man crying in the rain`
- **Native Telugu:** `చిరంజీవి కన్నీళ్లు`
- **Roman-script Telugu:** `ee jeevitham oka samaram` — transliterated
  automatically (shown as "searched as …")
- **Exact dialogue fragments** — keyword search ranks exact matches first

Click emotion/actor chips to filter (filters AND together). Each result shows
its similarity score and a *verified* badge for hand-checked memes.

## Editing metadata

Click any meme → a detail view shows the image, the auto-generated caption and
OCR text, and an edit form. Fix the dialogue, add translations, tags, actors,
notes — **Save** persists everything, re-embeds the meme, and marks it
*verified* (verified memes rank higher in search).

**Copy image** puts the meme on your clipboard for pasting into chats.

## Tips for best search results

1. Correct OCR'd dialogue for your favorite memes — exact dialogue search is
   the highest-precision path.
2. Add `dialogue_en` translations: they let English scene queries match
   dialogue semantically.
3. Use consistent emotion tags (`sad`, `happy`, `anger`, …) — they become
   filter chips.
4. Check `/api/analytics/top_queries` to see what you search for most, and
   curate those memes first.

## Actor tagging (face recognition)

Every upload is scanned for faces and matched against reference faces of ~21
Telugu actors; confident matches are added to the meme's actors automatically
(a meme with several people gets several tags). Tap a ⭐ actor chip to browse
one actor's stickers. To (re)build references or re-sweep the collection:

```bash
.venv/bin/python scripts/build_face_refs.py     # Wikipedia portraits + bootstrap
.venv/bin/python scripts/face_tag.py --dry-run  # preview matches
.venv/bin/python scripts/face_tag.py            # apply tags
```

## Admin: cleaning up junk

Open **/admin** (e.g. http://localhost:8010/admin) for a laptop-friendly
curation view: dense grid with a tile-size slider, filters by pack, actor,
static/animated, plus an "untagged only" filter that surfaces likely junk
(no recognized face, no dialogue, no OCR text). Click to select,
Shift+click for a range, ⌘A for all loaded, Delete key or the action bar
to bulk-delete (with confirmation). Deletion is permanent: image file,
metadata, and search index entries are all removed.

## Descriptions drive search

Each sticker has a **description** — the highest-weighted signal in search.
It is embedded as its own vector, so a query matches a description by meaning,
not just wording ("avoiding accountability" finds a sticker described as
"smugly refusing to take responsibility").

Two ways to fill them in:

- **Per face cluster** (fastest): /admin → Faces tab → write a description on a
  cluster and every sticker containing that face inherits it, tagged
  `[face #N] Name: text`. A sticker with two known faces accumulates both
  lines. Re-describing replaces only that cluster's line.
- **Per sticker**: open it in the store and edit the "⭐ Description" field.

Changing a description re-embeds the affected stickers automatically. Results
report `matched_fields`, showing whether a hit came from the description,
dialogue, or the auto-caption.
