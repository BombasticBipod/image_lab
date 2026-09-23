"""Pillow to Qt image conversion, kept apart so files.py and model.py stay Qt-free."""

from PIL import Image
from PySide6.QtGui import QImage


def pil_to_qimage(img: Image.Image) -> QImage:
    """Convert a PIL image to a QImage that owns its own pixel memory."""
    img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, 4 * img.width, QImage.Format_RGBA8888)
    # QImage only wraps `data`; copy so Qt owns the pixels after `data` is freed.
    return qimg.copy()
