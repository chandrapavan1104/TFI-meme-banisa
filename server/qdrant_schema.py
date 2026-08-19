"""Qdrant collection schema for TFI-banisa.

One point per meme, with up to three named 768-dim vectors (a point may have
any subset — e.g. caption only, until dialogue is added):
  - dialogue_te: Vyakyarth embedding of the Telugu dialogue
  - dialogue_en: embedding of the English translation
  - caption:     embedding of the Florence-2 auto caption

Payload carries the filterable metadata (movie, actors, emotions, verified).
"""

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

import config

COLLECTION = config.QDRANT_COLLECTION
VECTOR_NAMES = ("dialogue_te", "dialogue_en", "caption")

_PAYLOAD_INDEXES = {
    "movie_title_en": PayloadSchemaType.KEYWORD,
    "movie_title_te": PayloadSchemaType.KEYWORD,
    "actors": PayloadSchemaType.KEYWORD,
    "emotion_tags": PayloadSchemaType.KEYWORD,
    "verified": PayloadSchemaType.BOOL,
}


def create_collection_if_not_exists(client: QdrantClient) -> bool:
    """Create the collection + payload indexes. Returns True if newly created."""
    if client.collection_exists(COLLECTION):
        return False
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config={
            name: VectorParams(size=config.EMBEDDING_DIM, distance=Distance.COSINE)
            for name in VECTOR_NAMES
        },
    )
    for field, schema in _PAYLOAD_INDEXES.items():
        client.create_payload_index(
            collection_name=COLLECTION, field_name=field, field_schema=schema
        )
    return True


def verify_collection_ready(client: QdrantClient) -> bool:
    if not client.collection_exists(COLLECTION):
        return False
    info = client.get_collection(COLLECTION)
    vectors = info.config.params.vectors
    return isinstance(vectors, dict) and set(vectors) == set(VECTOR_NAMES)


def delete_collection(client: QdrantClient) -> None:
    """Drop the collection (used by tests)."""
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
