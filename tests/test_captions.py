"""Florence-2 captioning. Model inference tests skip if not cached."""

import pytest
from PIL import Image, UnidentifiedImageError

from collectors import captions

needs_model = pytest.mark.skipif(
    not captions.is_available(), reason="caption model not downloaded"
)


def test_corrupt_image_raises(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image at all")
    with pytest.raises((UnidentifiedImageError, OSError)):
        captions.caption_image(str(bad))


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        captions.caption_image("/nonexistent/nope.png")


@needs_model
def test_caption_sample_image(tmp_path):
    path = tmp_path / "scene.png"
    img = Image.new("RGB", (256, 256), (200, 40, 40))
    img.paste(Image.new("RGB", (100, 100), (250, 250, 250)), (78, 78))
    img.save(path)
    caption = captions.caption_image(str(path))
    assert isinstance(caption, str) and len(caption) > 5
