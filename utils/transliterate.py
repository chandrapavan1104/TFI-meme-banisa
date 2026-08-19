"""Roman-script Telugu -> native script transliteration.

Search queries typed in Roman letters ("ee jeevitham oka samaram") are
converted to Telugu script before embedding, since Vyakyarth retrieval is
strongest on native script. Uses indic-transliteration's ITRANS scheme —
an approximation for casual romanization, but close enough for embedding
similarity (both forms are embedded and searched).
"""

import re

from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

_TELUGU_RE = re.compile(r"[ఀ-౿]")
_LATIN_RE = re.compile(r"[A-Za-z]")

# Queries containing these are treated as English, not Romanized Telugu —
# transliterating English words produces gibberish embeddings.
_ENGLISH_WORDS = {
    "the", "a", "an", "is", "are", "was", "in", "on", "of", "and", "or", "to",
    "with", "at", "for", "from", "his", "her", "my", "your", "man", "woman",
    "guy", "girl", "boy", "people", "scene", "movie", "actor", "hero", "face",
    "crying", "laughing", "smiling", "dancing", "fighting", "angry", "sad",
    "happy", "funny", "comedy", "love", "dance", "fight", "cry", "laugh",
    "smile", "rain", "tears", "shocked", "surprised", "confused",
}


def contains_telugu(text: str) -> bool:
    return bool(_TELUGU_RE.search(text))


def is_roman(text: str) -> bool:
    """True for Latin-script text with no Telugu characters."""
    return bool(_LATIN_RE.search(text)) and not contains_telugu(text)


def looks_like_roman_telugu(text: str) -> bool:
    """True for Roman-script text that is plausibly Romanized Telugu
    (i.e. contains no common English words)."""
    if not is_roman(text):
        return False
    tokens = {t.lower() for t in re.findall(r"[A-Za-z]+", text)}
    return not (tokens & _ENGLISH_WORDS)


def roman_to_telugu(text: str) -> str:
    """Transliterate Roman Telugu to native script (e.g. "jeevitham" -> జీవితం).

    Mixed-script input is returned unchanged; only pure Roman text is converted.
    """
    if not text or not is_roman(text):
        return text
    return transliterate(text.lower(), sanscript.ITRANS, sanscript.TELUGU)
