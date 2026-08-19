"""Telugu OCR with Tesseract.

Requires `brew install tesseract` plus tel.traineddata in the tessdata dir.
Degrades gracefully: is_available() gates the OCR job when Tesseract or the
Telugu language pack is missing.
"""

import logging
import shutil

from PIL import Image

import config

log = logging.getLogger(__name__)


def is_available() -> bool:
    """True if the tesseract binary exists and supports the configured langs."""
    if not shutil.which("tesseract"):
        return False
    try:
        import pytesseract

        langs = set(pytesseract.get_languages(config="") or [])
    except Exception:
        return False
    needed = set(config.OCR_LANG.split("+"))
    return needed.issubset(langs)


def extract_text(image_path: str, lang: str | None = None) -> str:
    """Run OCR on an image; returns extracted text ('' when no text found).

    Raises RuntimeError when Tesseract is missing, and PIL errors on bad images.
    """
    if not shutil.which("tesseract"):
        raise RuntimeError(
            "tesseract not found — install with: brew install tesseract "
            "(then add tel.traineddata, see SETUP.md)"
        )
    import pytesseract
    from PIL import ImageOps

    gray = ImageOps.grayscale(Image.open(image_path))
    lang = lang or config.OCR_LANG
    # Meme text is often light-on-dark; Tesseract wants dark-on-light, so try
    # both polarities and keep whichever finds more text.
    best = ""
    for candidate in (gray, ImageOps.invert(gray)):
        text = pytesseract.image_to_string(candidate, lang=lang)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        cleaned = "\n".join(lines)
        if len(cleaned) > len(best):
            best = cleaned
    return best
