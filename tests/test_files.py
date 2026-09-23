"""Tests for image loading and saving (pure Pillow, no GUI)."""

import pytest
from PIL import Image, UnidentifiedImageError

from image_lab.files import is_image_path, load_image

RED = (255, 0, 0, 255)
BLUE = (0, 0, 255, 255)

EXIF_ORIENTATION = 0x0112


def test_is_image_path():
    assert is_image_path("a/b/photo.JPG")
    assert is_image_path("x.tiff")
    assert not is_image_path("notes.txt")
    assert not is_image_path("no_extension")


def test_load_png_returns_rgba(tmp_path):
    path = tmp_path / "rgb.png"
    Image.new("RGB", (5, 3), (10, 20, 30)).save(path)
    img = load_image(path)
    assert img.mode == "RGBA"
    assert img.size == (5, 3)
    assert img.getpixel((0, 0)) == (10, 20, 30, 255)


def test_load_keeps_transparency(tmp_path):
    path = tmp_path / "alpha.png"
    Image.new("RGBA", (2, 2), (1, 2, 3, 0)).save(path)
    assert load_image(path).getpixel((1, 1)) == (1, 2, 3, 0)


def test_load_jpeg(tmp_path):
    path = tmp_path / "photo.jpg"
    Image.new("RGB", (8, 4), (200, 200, 200)).save(path)
    img = load_image(path)
    assert img.mode == "RGBA"
    assert img.size == (8, 4)


def test_load_applies_exif_orientation(tmp_path):
    # 4x2 image with red at top-left; orientation 6 means "rotate 90 degrees clockwise
    # to display", so the upright image is 2x4 with red at top-right.
    img = Image.new("RGBA", (4, 2), BLUE)
    img.putpixel((0, 0), RED)
    exif = Image.Exif()
    exif[EXIF_ORIENTATION] = 6
    path = tmp_path / "sideways.png"
    img.save(path, exif=exif)

    loaded = load_image(path)
    assert loaded.size == (2, 4)
    assert loaded.getpixel((1, 0)) == RED
    assert loaded.getpixel((0, 0)) == BLUE


def test_load_animated_gif_uses_first_frame(tmp_path):
    path = tmp_path / "anim.gif"
    frames = [Image.new("RGB", (3, 3), (255, 0, 0)), Image.new("RGB", (3, 3), (0, 0, 255))]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=100, loop=0)
    assert load_image(path).getpixel((1, 1)) == RED


def test_load_non_image_raises(tmp_path):
    path = tmp_path / "fake.png"
    path.write_bytes(b"this is not an image")
    with pytest.raises(UnidentifiedImageError):
        load_image(path)


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(OSError):
        load_image(tmp_path / "missing.png")
