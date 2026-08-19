"""Embedded Qdrant: collection lifecycle, upsert, filtered vector search."""

from server import qdrant_store
from server.qdrant_schema import (
    create_collection_if_not_exists,
    delete_collection,
    verify_collection_ready,
)
from tests.conftest import fake_vector


def test_collection_lifecycle(qclient):
    assert verify_collection_ready(qclient)          # created by get_client()
    assert not create_collection_if_not_exists(qclient)  # already exists
    delete_collection(qclient)
    assert not verify_collection_ready(qclient)
    assert create_collection_if_not_exists(qclient)


def _seed(qclient):
    qdrant_store.upsert_meme(
        qclient, "m1",
        {"dialogue_te": fake_vector("జీవితం సమరం"), "caption": fake_vector("man crying rain")},
        {"emotion_tags": ["sad"], "actors": ["Chiranjeevi"], "movie_title_en": "Indra", "verified": True},
    )
    qdrant_store.upsert_meme(
        qclient, "m2",
        {"caption": fake_vector("happy dance celebration")},
        {"emotion_tags": ["happy"], "actors": ["Allu Arjun"], "movie_title_en": "Pushpa", "verified": False},
    )


def test_upsert_and_search(qclient):
    _seed(qclient)
    hits = qdrant_store.vector_search(qclient, [fake_vector("man crying rain")])
    assert hits[0][0] == "m1"
    hits = qdrant_store.vector_search(qclient, [fake_vector("happy dance")])
    assert hits[0][0] == "m2"


def test_filters(qclient):
    _seed(qclient)
    qv = [fake_vector("scene")]
    sad = qdrant_store.vector_search(
        qclient, qv, qdrant_store.build_filter(emotions=["sad"])
    )
    assert [h[0] for h in sad] == ["m1"]
    both = qdrant_store.vector_search(
        qclient, qv, qdrant_store.build_filter(emotions=["sad"], actors=["Allu Arjun"])
    )
    assert both == []  # AND logic: no meme matches both
    movie = qdrant_store.vector_search(
        qclient, qv, qdrant_store.build_filter(movie="Pushpa")
    )
    assert [h[0] for h in movie] == ["m2"]


def test_delete_point(qclient):
    _seed(qclient)
    qdrant_store.delete_meme(qclient, "m1")
    hits = qdrant_store.vector_search(qclient, [fake_vector("జీవితం సమరం")])
    assert all(h[0] != "m1" for h in hits)
