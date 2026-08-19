"""Vyakyarth embeddings + transliteration. Model tests skip if not cached."""

import pytest

import config
from collectors import embeddings
from utils.transliterate import contains_telugu, is_roman, roman_to_telugu

needs_model = pytest.mark.skipif(
    not embeddings.is_available(), reason="embedding model not downloaded"
)


def test_script_detection():
    assert contains_telugu("ఈ జీవితం")
    assert not contains_telugu("ee jeevitham")
    assert is_roman("ee jeevitham oka samaram")
    assert not is_roman("ఈ జీవితం")
    assert not is_roman("mixed ఈ జీవితం")


def test_roman_to_telugu():
    out = roman_to_telugu("jeevitham")
    assert contains_telugu(out)
    # Native/mixed input passes through unchanged.
    assert roman_to_telugu("ఈ జీవితం") == "ఈ జీవితం"
    assert roman_to_telugu("") == ""


def test_empty_text_raises():
    with pytest.raises(ValueError):
        embeddings.embed_text("   ")


@needs_model
def test_embedding_dimensions():
    vec = embeddings.embed_text("ఈ జీవితం ఒక సమరం")
    assert len(vec) == config.EMBEDDING_DIM


@needs_model
def test_embedding_deterministic():
    a = embeddings.embed_text("sad scene in the rain")
    b = embeddings.embed_text("sad scene in the rain")
    assert a == b


@needs_model
def test_multifield():
    out = embeddings.embed_multifield("ఈ జీవితం", None, "a crying man")
    assert set(out) == {"dialogue_te", "caption"}
    assert all(len(v) == config.EMBEDDING_DIM for v in out.values())


@needs_model
def test_long_text_truncated():
    vec = embeddings.embed_text("word " * 5000)
    assert len(vec) == config.EMBEDDING_DIM


@needs_model
def test_cross_lingual_similarity():
    """Native and transliterated Telugu should embed closer than unrelated text."""
    import numpy as np

    native = np.array(embeddings.embed_text("ఈ జీవితం ఒక సమరం"))
    translit = np.array(embeddings.embed_text(roman_to_telugu("ee jIvitaM oka samaraM")))
    unrelated = np.array(embeddings.embed_text("a recipe for tomato soup"))
    assert native @ translit > native @ unrelated


def test_english_not_treated_as_roman_telugu():
    from utils.transliterate import looks_like_roman_telugu

    assert not looks_like_roman_telugu("man crying in the rain")
    assert looks_like_roman_telugu("ee jeevitham oka samaram")
    assert not looks_like_roman_telugu("ఈ జీవితం")
