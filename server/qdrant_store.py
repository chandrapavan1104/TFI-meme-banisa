"""Qdrant client wrapper: connection, upsert, filtered vector search.

Named qdrant_store (not qdrant_client) to avoid shadowing the pip package.
"""

import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
)

import config
from server.qdrant_schema import COLLECTION, VECTOR_NAMES, create_collection_if_not_exists

_NAMESPACE = uuid.UUID("7f1baa15-0000-4000-8000-000000000000")


def point_id_for(meme_id: str) -> str:
    """Deterministic UUID point id derived from the meme id."""
    return str(uuid.uuid5(_NAMESPACE, meme_id))


def get_client() -> QdrantClient:
    """Connect per config: embedded on-disk mode (default) or remote server."""
    if config.QDRANT_MODE == "server":
        client = QdrantClient(url=config.QDRANT_URL)
    else:
        config.QDRANT_PATH.mkdir(parents=True, exist_ok=True)
        client = QdrantClient(path=str(config.QDRANT_PATH))
    create_collection_if_not_exists(client)
    return client


def upsert_meme(
    client: QdrantClient,
    meme_id: str,
    vectors: dict[str, list[float]],
    payload: dict,
) -> None:
    """Upsert a meme's vectors + payload (replaces the existing point)."""
    vectors = {k: v for k, v in vectors.items() if k in VECTOR_NAMES}
    if not vectors:
        return
    payload = {**payload, "meme_id": meme_id}
    client.upsert(
        collection_name=COLLECTION,
        points=[PointStruct(id=point_id_for(meme_id), vector=vectors, payload=payload)],
    )


def delete_meme(client: QdrantClient, meme_id: str) -> None:
    client.delete(collection_name=COLLECTION, points_selector=[point_id_for(meme_id)])


def build_filter(
    emotions: list[str] | None = None,
    actors: list[str] | None = None,
    movie: str | None = None,
) -> Filter | None:
    """AND-combined payload filter, applied by Qdrant before vector scoring."""
    must = []
    if emotions:
        must.append(FieldCondition(key="emotion_tags", match=MatchAny(any=emotions)))
    if actors:
        must.append(FieldCondition(key="actors", match=MatchAny(any=actors)))
    if movie:
        must.append(FieldCondition(key="movie_title_en", match=MatchValue(value=movie)))
    return Filter(must=must) if must else None


def vector_search_by_field(
    client: QdrantClient,
    query_vectors: list[list[float]],
    query_filter: Filter | None = None,
    limit: int = 20,
) -> dict[str, list[tuple[str, float]]]:
    """Search each named vector separately with every query vector.

    Returns {vector_name: [(meme_id, score)] sorted best-first}, so callers can
    weight the fields differently (descriptions outrank auto-captions).
    """
    out: dict[str, list[tuple[str, float]]] = {}
    for name in VECTOR_NAMES:
        best: dict[str, float] = {}
        for qv in query_vectors:
            hits = client.query_points(
                collection_name=COLLECTION,
                query=qv,
                using=name,
                query_filter=query_filter,
                limit=limit,
                with_payload=["meme_id"],
            ).points
            for hit in hits:
                mid = (hit.payload or {}).get("meme_id")
                if mid and hit.score > best.get(mid, -1.0):
                    best[mid] = hit.score
        out[name] = sorted(best.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return out


def vector_search(
    client: QdrantClient,
    query_vectors: list[list[float]],
    query_filter: Filter | None = None,
    limit: int = 20,
) -> list[tuple[str, float]]:
    """Flattened view of vector_search_by_field: best score per meme."""
    best: dict[str, float] = {}
    for hits in vector_search_by_field(
        client, query_vectors, query_filter, limit
    ).values():
        for mid, score in hits:
            if score > best.get(mid, -1.0):
                best[mid] = score
    return sorted(best.items(), key=lambda kv: kv[1], reverse=True)[:limit]
