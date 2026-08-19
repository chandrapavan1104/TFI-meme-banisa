"""Hybrid search: Qdrant vector search + SQLite BM25, merged with RRF.

Pipeline per query:
  1. If the query is Roman script, also transliterate to Telugu.
  2. Embed all query variants (Vyakyarth) and search the three named vectors,
     with payload filters (emotions/actors/movie) applied inside Qdrant.
  3. BM25 keyword search over dialogue/caption/OCR text via FTS5.
  4. Merge with Reciprocal Rank Fusion: score = sum(1 / (K + rank)).
  5. Boost verified memes and rated memes, return top N with ranking reasons.
"""

import logging
import sqlite3
import time

from qdrant_client import QdrantClient

from collectors import embeddings
from db import store
from server import qdrant_store
from utils.transliterate import looks_like_roman_telugu, roman_to_telugu

log = logging.getLogger(__name__)

RRF_K = 60
VERIFIED_BONUS = 0.005
RATING_BONUS = 0.001  # per star


def _matches_filters(
    meme: dict,
    emotions: list[str] | None,
    actors: list[str] | None,
    movie: str | None,
    animated: bool | None,
) -> bool:
    """Post-filter applied to merged results (animated isn't in Qdrant payload)."""
    if emotions and not set(emotions) & set(meme.get("emotion_tags") or []):
        return False
    if actors and not set(actors) & set(meme.get("actors") or []):
        return False
    if movie and meme.get("movie_title_en") != movie:
        return False
    if animated is not None and meme.get("animated") != animated:
        return False
    return True


def hybrid_search(
    conn: sqlite3.Connection,
    qclient: QdrantClient,
    query: str,
    emotions: list[str] | None = None,
    actors: list[str] | None = None,
    movie: str | None = None,
    animated: bool | None = None,
    limit: int = 10,
) -> dict:
    """Run hybrid search; returns {results, duration_ms, query_telugu?}."""
    start = time.perf_counter()
    query = (query or "").strip()
    filters = {
        "emotions": emotions, "actors": actors, "movie": movie, "animated": animated,
    }
    if not query:
        return {"results": [], "duration_ms": 0.0}

    # 1. Query variants: raw + transliteration for Roman-script input.
    variants = [query]
    query_telugu = None
    if looks_like_roman_telugu(query):
        query_telugu = roman_to_telugu(query)
        if query_telugu and query_telugu != query:
            variants.append(query_telugu)

    # 2. Vector search (skipped if the embedding model isn't downloaded yet).
    vector_hits: list[tuple[str, float]] = []
    if embeddings.is_available():
        try:
            qvecs = [embeddings.embed_text(v) for v in variants]
            qfilter = qdrant_store.build_filter(emotions, actors, movie)
            vector_hits = qdrant_store.vector_search(
                qclient, qvecs, qfilter, limit=max(20, limit * 2)
            )
        except Exception:
            log.exception("Vector search failed; falling back to keyword-only")
    else:
        log.warning("Embedding model not available; keyword-only search")

    # 3. BM25 keyword search across all variants.
    bm25_ids = store.fts_search(conn, " ".join(variants), limit=max(20, limit * 2))

    # 4. Reciprocal Rank Fusion.
    rrf: dict[str, float] = {}
    vec_scores: dict[str, float] = {}
    bm25_rank: dict[str, int] = {}
    for rank, (meme_id, score) in enumerate(vector_hits):
        rrf[meme_id] = rrf.get(meme_id, 0.0) + 1.0 / (RRF_K + rank + 1)
        vec_scores[meme_id] = score
    for rank, meme_id in enumerate(bm25_ids):
        rrf[meme_id] = rrf.get(meme_id, 0.0) + 1.0 / (RRF_K + rank + 1)
        bm25_rank[meme_id] = rank + 1

    # 5. Load metadata, post-filter BM25-only hits, apply feedback boosts.
    results = []
    for meme_id, base in rrf.items():
        meme = store.get_meme(conn, meme_id)
        if not meme or not _matches_filters(meme, emotions, actors, movie, animated):
            continue
        score = base + (VERIFIED_BONUS if meme["verified"] else 0.0)
        score += RATING_BONUS * (meme.get("rating") or 0)
        results.append(
            {
                "meme": meme,
                "score": round(score, 6),
                "reasons": {
                    "vector_score": round(vec_scores[meme_id], 4)
                    if meme_id in vec_scores else None,
                    "keyword_rank": bm25_rank.get(meme_id),
                    "verified": meme["verified"],
                },
            }
        )
    results.sort(key=lambda r: r["score"], reverse=True)
    results = results[:limit]

    duration_ms = (time.perf_counter() - start) * 1000
    store.log_search(conn, query, filters, len(results), duration_ms)
    out = {"results": results, "duration_ms": round(duration_ms, 1)}
    if query_telugu:
        out["query_telugu"] = query_telugu
    return out
