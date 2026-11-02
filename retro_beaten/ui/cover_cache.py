"""Bounded Pillow thumbnail cache; no Tk objects survive window destruction."""

from functools import lru_cache
from pathlib import Path
from PIL import Image


def cover_signature(path):
    path = Path(path)
    try:
        stat = path.stat()
    except OSError:
        return str(path.absolute()), None, None
    return str(path.absolute()), stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=128)
def _thumbnail(signature, size):
    with Image.open(signature[0]) as source:
        width, height = source.size
        scale = min(size[0] / width, size[1] / height)
        display_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        # Keep 2x resolution for high-DPI screens without retaining full originals.
        source.thumbnail((display_size[0] * 2, display_size[1] * 2))
        image = source.convert("RGBA" if "A" in source.getbands() else "RGB")
    return image, display_size


def load_thumbnail(path, size):
    return _thumbnail(cover_signature(path), tuple(size))
