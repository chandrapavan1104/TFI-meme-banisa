"""Image captioning with Florence-2-base.

Lazy-loads the model on first use (~500 MB, ~250 ms/image on Apple Silicon).
Florence-2's remote code unconditionally imports flash_attn, which doesn't
exist on macOS — we patch transformers' import scanner to drop it.
"""

import logging
import threading
import time
from unittest.mock import patch

from PIL import Image

import config

log = logging.getLogger(__name__)

# <CAPTION> ~400ms, <DETAILED_CAPTION> ~700ms, <MORE_DETAILED_CAPTION> ~950ms (M4).
_TASK = config.CAPTION_TASK
_model = None
_processor = None
_lock = threading.Lock()


def _flash_attn_free_get_imports():
    """Wrap transformers' import scanner to drop flash_attn (unavailable on macOS)."""
    from transformers import dynamic_module_utils

    original = dynamic_module_utils.get_imports

    def patched(filename):
        return [i for i in original(filename) if i != "flash_attn"]

    return patched


def _device() -> str:
    import torch

    return "mps" if torch.backends.mps.is_available() else "cpu"


def get_model():
    """Load and cache Florence-2 (thread-safe)."""
    global _model, _processor
    if _model is None:
        with _lock:
            if _model is None:
                import torch
                from transformers import AutoModelForCausalLM, AutoProcessor

                log.info("Loading caption model %s ...", config.CAPTION_MODEL)
                with patch(
                    "transformers.dynamic_module_utils.get_imports",
                    _flash_attn_free_get_imports(),
                ):
                    _processor = AutoProcessor.from_pretrained(
                        config.CAPTION_MODEL, trust_remote_code=True
                    )
                    model = AutoModelForCausalLM.from_pretrained(
                        config.CAPTION_MODEL,
                        trust_remote_code=True,
                        torch_dtype=torch.float32,
                    )
                _model = model.to(_device()).eval()
                log.info("Caption model loaded on %s", _device())
    return _model, _processor


def is_available() -> bool:
    """True if the model is loadable from the local cache (no download)."""
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(config.CAPTION_MODEL, local_files_only=True)
        return True
    except Exception:
        return _model is not None


def caption_image(image_path: str) -> str:
    """Generate a detailed caption for one image.

    Raises FileNotFoundError / PIL.UnidentifiedImageError on bad input.
    """
    import torch

    image = Image.open(image_path).convert("RGB")
    model, processor = get_model()
    start = time.perf_counter()
    inputs = processor(text=_TASK, images=image, return_tensors="pt").to(_device())
    with torch.no_grad():
        generated = model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            max_new_tokens=128,
            num_beams=1,
            do_sample=False,
            early_stopping=False,
        )
    raw = processor.batch_decode(generated, skip_special_tokens=False)[0]
    parsed = processor.post_process_generation(
        raw, task=_TASK, image_size=(image.width, image.height)
    )
    caption = (parsed.get(_TASK) or "").strip()
    log.info(
        "Captioned %s in %.0f ms", image_path, (time.perf_counter() - start) * 1000
    )
    return caption
