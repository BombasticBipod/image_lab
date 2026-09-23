"""Tests for the Pillow to Qt conversion."""

import pytest
from PIL import Image
from PySide6.QtGui import QColor

from image_lab.qtimage import pil_to_qimage

pytestmark = pytest.mark.gui


def test_pil_to_qimage_keeps_size_and_pixels(qapp):
    img = Image.new("RGBA", (3, 2), (0, 0, 0, 0))
    img.putpixel((2, 1), (10, 20, 30, 255))
    qimg = pil_to_qimage(img)
    assert (qimg.width(), qimg.height()) == (3, 2)
    assert qimg.pixelColor(2, 1) == QColor(10, 20, 30, 255)
    assert qimg.pixelColor(0, 0).alpha() == 0


def test_pil_to_qimage_owns_memory(qapp):
    # The source image goes away; the QImage must still be valid.
    qimg = pil_to_qimage(Image.new("RGB", (4, 4), (5, 6, 7)))
    assert qimg.pixelColor(3, 3) == QColor(5, 6, 7)
