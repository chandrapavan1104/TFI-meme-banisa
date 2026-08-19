"""Tesseract OCR. Tests skip when tesseract/Telugu data are missing."""

import pytest
from PIL import Image, ImageDraw

from collectors import ocr

needs_tesseract = pytest.mark.skipif(
    not ocr.is_available(), reason="tesseract with tel+eng not installed"
)


def _text_image(tmp_path, text: str):
    img = Image.new("RGB", (600, 120), "white")
    ImageDraw.Draw(img).text((20, 40), text, fill="black")
    path = tmp_path / "text.png"
    img.save(path)
    return str(path)


@needs_tesseract
def test_extract_english_text(tmp_path):
    path = _text_image(tmp_path, "HELLO WORLD")
    out = ocr.extract_text(path, lang="eng").upper()
    assert "HELLO" in out


@needs_tesseract
def test_no_text_image(tmp_path):
    img = Image.new("RGB", (200, 200), "white")
    path = tmp_path / "blank.png"
    img.save(path)
    assert ocr.extract_text(path) == ""


def test_missing_binary_raises(monkeypatch, tmp_path):
    monkeypatch.setattr("shutil.which", lambda _: None)
    img = Image.new("RGB", (50, 50), "white")
    path = tmp_path / "x.png"
    img.save(path)
    with pytest.raises(RuntimeError, match="tesseract not found"):
        ocr.extract_text(str(path))
