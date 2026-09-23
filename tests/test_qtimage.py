"""Tests for the Pillow <-> Qt conversions."""

import pytest
from PIL import Image
from PySide6.QtGui import QColor, QImage

from image_lab.qtimage import pil_to_qimage, qimage_to_pil

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


def test_qimage_to_pil_round_trip_with_alpha(qapp):
    img = Image.new("RGBA", (3, 2), (0, 0, 0, 0))
    img.putpixel((2, 1), (10, 20, 30, 255))
    img.putpixel((0, 0), (200, 100, 50, 128))
    back = qimage_to_pil(pil_to_qimage(img))
    assert back.mode == "RGBA"
    assert back.size == (3, 2)
    assert back.tobytes() == img.tobytes()


def test_qimage_to_pil_handles_padded_rows(qapp):
    # RGB888 rows of odd width are padded to 4 bytes; the stride must be respected.
    qimg = QImage(5, 3, QImage.Format_RGB888)
    qimg.fill(QColor(1, 2, 3))
    qimg.setPixelColor(4, 2, QColor(250, 0, 0))
    back = qimage_to_pil(qimg)
    assert back.size == (5, 3)
    assert back.getpixel((0, 0)) == (1, 2, 3, 255)
    assert back.getpixel((4, 2)) == (250, 0, 0, 255)
