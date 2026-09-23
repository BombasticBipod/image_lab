"""Tests for image loading and saving (pure Pillow, no GUI)."""

from io import BytesIO

import pytest
from PIL import Image, UnidentifiedImageError

from image_lab.files import (
    ensure_extension,
    is_image_path,
    load_image,
    next_free_path,
    png_bytes,
    save_image,
)
from image_lab.model import TRANSPARENT, Edges, Stroke, Transform

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


# --- saving -------------------------------------------------------------------

WHITE = (255, 255, 255)


def _source():
    """4x2 opaque red image."""
    return Image.new("RGBA", (4, 2), RED)


def test_ensure_extension():
    assert ensure_extension("out", ".png").name == "out.png"
    assert ensure_extension("out.JPG", ".png").name == "out.JPG"
    assert ensure_extension("my.photo", ".webp").name == "my.photo.webp"


def test_png_round_trip_keeps_size_and_transparency(tmp_path):
    path = tmp_path / "out.png"
    save_image(_source(), Edges(left=2, bottom=-1), path)
    loaded = load_image(path)
    assert loaded.size == (6, 1)
    assert loaded.getpixel((0, 0)) == TRANSPARENT
    assert loaded.getpixel((2, 0)) == RED


def test_jpeg_flattens_padding_to_white(tmp_path):
    path = tmp_path / "out.jpg"
    save_image(_source(), Edges(right=8, top=8), path)
    with Image.open(path) as saved:
        assert saved.format == "JPEG"
        assert saved.mode == "RGB"
        assert saved.size == (12, 10)
        # JPEG is lossy: check "close to white" and "close to red", far from the boundary.
        assert all(c >= 250 for c in saved.getpixel((11, 0)))
        r, g, b = saved.getpixel((0, 9))
        assert r > 200 and g < 60 and b < 60


def test_bmp_flattens_to_white(tmp_path):
    path = tmp_path / "out.bmp"
    save_image(_source(), Edges(left=1), path)
    with Image.open(path) as saved:
        assert saved.mode == "RGB"
        assert saved.getpixel((0, 0)) == WHITE
        assert saved.getpixel((1, 0)) == RED[:3]


def test_webp_keeps_alpha(tmp_path):
    path = tmp_path / "out.webp"
    save_image(_source(), Edges(left=4), path)
    loaded = load_image(path)
    assert loaded.size == (8, 2)
    assert loaded.getpixel((0, 0))[3] == 0
    assert loaded.getpixel((7, 1))[3] == 255


def test_save_with_fill_color(tmp_path):
    path = tmp_path / "out.png"
    save_image(_source(), Edges(top=1), path, fill=(0, 255, 0, 255))
    assert load_image(path).getpixel((0, 0)) == (0, 255, 0, 255)


def test_save_applies_transform_before_edges(tmp_path):
    path = tmp_path / "out.png"
    # Turned right, the 4x2 source is 2x4; the top pad is in view pixels.
    save_image(_source(), Edges(top=1), path, transform=Transform(90))
    loaded = load_image(path)
    assert loaded.size == (2, 5)
    assert loaded.getpixel((0, 0))[3] == 0


def test_save_unsupported_extension_raises(tmp_path):
    with pytest.raises(ValueError):
        save_image(_source(), Edges(), tmp_path / "out.gif")


def test_next_free_path_numbers_existing_files(tmp_path):
    assert next_free_path(tmp_path, "a_edited", ".png") == tmp_path / "a_edited.png"
    (tmp_path / "a_edited.png").touch()
    assert next_free_path(tmp_path, "a_edited", ".png") == tmp_path / "a_edited_2.png"
    (tmp_path / "a_edited_2.png").touch()
    assert next_free_path(tmp_path, "a_edited", ".png") == tmp_path / "a_edited_3.png"


def test_next_free_path_missing_folder(tmp_path):
    assert next_free_path(tmp_path / "nope", "x", ".png") == tmp_path / "nope" / "x.png"


def test_png_bytes_round_trip():
    img = Image.new("RGBA", (3, 2), (5, 6, 7, 0))
    data = png_bytes(img)
    assert data.startswith(b"\x89PNG")
    assert load_image(BytesIO(data)).getpixel((0, 0)) == (5, 6, 7, 0)


# Erases pixel (0, 0) of the 4x2 source.
CORNER = (Stroke(((0.5, 0.5),), radius=0.5),)


def test_save_png_painted_pixels_transparent_with_rgb(tmp_path):
    path = tmp_path / "out.png"
    save_image(_source(), Edges(), path, strokes=CORNER)
    loaded = load_image(path)
    assert loaded.getpixel((0, 0)) == (255, 0, 0, 0)
    assert loaded.getpixel((1, 0)) == RED


def test_save_bmp_flattens_painted_pixels_to_white(tmp_path):
    path = tmp_path / "out.bmp"
    save_image(_source(), Edges(), path, strokes=CORNER)
    with Image.open(path) as saved:
        assert saved.getpixel((0, 0)) == (255, 255, 255)
        assert saved.getpixel((1, 0)) == RED[:3]


def test_save_does_not_modify_source(tmp_path):
    src = _source()
    before = src.copy()
    save_image(
        src,
        Edges(left=-2, top=1),
        tmp_path / "out.png",
        fill=(0, 255, 0, 255),
        transform=Transform(30, mirror=True),
        strokes=CORNER,
    )
    assert src.mode == before.mode
    assert src.size == before.size
    assert src.tobytes() == before.tobytes()
