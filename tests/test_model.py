"""Tests for the edge model (pure Pillow, no GUI)."""

import pytest
from PIL import Image, ImageChops

from image_lab.model import (
    TRANSPARENT,
    Edges,
    adjust_edge,
    apply_edges,
    output_box,
    output_size,
    visible_rect,
)

W, H = 10, 6
SIZE = (W, H)


@pytest.fixture
def img():
    """10x6 image where every pixel has a distinct color, so offsets are checkable."""
    im = Image.new("RGBA", SIZE)
    im.putdata([(x * 20, y * 40, 100, 255) for y in range(H) for x in range(W)])
    return im


def px(x, y):
    """Color of original pixel (x, y) in the fixture image."""
    return (x * 20, y * 40, 100, 255)


def _identical(a, b):
    return a.size == b.size and ImageChops.difference(a, b).getbbox() is None


# --- geometry -------------------------------------------------------------


def test_output_box_and_size():
    e = Edges(left=2, top=-1, right=-3, bottom=4)
    assert output_box(SIZE, e) == (-2, 1, 7, 10)
    assert output_size(SIZE, e) == (9, 9)


def test_visible_rect_clips_to_image():
    assert visible_rect(SIZE, Edges(left=5, top=5, right=5, bottom=5)) == (0, 0, W, H)
    assert visible_rect(SIZE, Edges(left=-2, top=-1, right=-3, bottom=-2)) == (2, 1, 7, 4)


# --- apply_edges ------------------------------------------------------------


def test_zero_edges_returns_identical_image(img):
    out = apply_edges(img, Edges())
    assert _identical(out, img)
    assert out is not img


def test_original_is_not_modified(img):
    before = img.copy()
    apply_edges(img, Edges(left=-3, top=2))
    assert _identical(img, before)


@pytest.mark.parametrize(
    "edges, size, offset, pad_pixel",
    [
        (Edges(left=3), (13, 6), (3, 0), (0, 0)),
        (Edges(top=2), (10, 8), (0, 2), (0, 0)),
        (Edges(right=4), (14, 6), (0, 0), (13, 0)),
        (Edges(bottom=1), (10, 7), (0, 0), (0, 6)),
    ],
)
def test_pad_single_side(img, edges, size, offset, pad_pixel):
    out = apply_edges(img, edges)
    assert out.size == size
    ox, oy = offset
    assert out.getpixel((ox, oy)) == px(0, 0)
    assert out.getpixel((ox + W - 1, oy + H - 1)) == px(W - 1, H - 1)
    assert out.getpixel(pad_pixel) == TRANSPARENT


@pytest.mark.parametrize(
    "edges, size, first_kept",
    [
        (Edges(left=-3), (7, 6), (3, 0)),
        (Edges(top=-2), (10, 4), (0, 2)),
        (Edges(right=-4), (6, 6), (0, 0)),
        (Edges(bottom=-1), (10, 5), (0, 0)),
    ],
)
def test_crop_single_side(img, edges, size, first_kept):
    out = apply_edges(img, edges)
    assert out.size == size
    fx, fy = first_kept
    assert out.getpixel((0, 0)) == px(fx, fy)
    assert out.getpixel((size[0] - 1, size[1] - 1)) == px(fx + size[0] - 1, fy + size[1] - 1)


def test_mixed_pad_and_crop(img):
    out = apply_edges(img, Edges(left=2, right=-3, top=-1, bottom=2))
    assert out.size == (9, 7)
    assert out.getpixel((0, 0)) == TRANSPARENT  # left pad
    assert out.getpixel((2, 0)) == px(0, 1)  # first kept pixel after top crop
    assert out.getpixel((8, 4)) == px(6, 5)  # last kept pixel after right crop
    assert out.getpixel((5, 6)) == TRANSPARENT  # bottom pad


def test_pad_fill_color(img):
    out = apply_edges(img, Edges(left=1), fill=(255, 255, 255, 255))
    assert out.getpixel((0, 0)) == (255, 255, 255, 255)
    assert out.getpixel((1, 0)) == px(0, 0)


def test_transparent_image_pixels_stay_transparent_over_fill():
    im = Image.new("RGBA", (2, 1), TRANSPARENT)
    out = apply_edges(im, Edges(right=1), fill=(255, 0, 0, 255))
    assert out.getpixel((0, 0)) == TRANSPARENT
    assert out.getpixel((2, 0)) == (255, 0, 0, 255)


def test_apply_edges_accepts_rgb():
    out = apply_edges(Image.new("RGB", (2, 2), (9, 9, 9)), Edges(top=1))
    assert out.mode == "RGBA"
    assert out.getpixel((0, 0)) == TRANSPARENT
    assert out.getpixel((0, 1)) == (9, 9, 9, 255)


# --- adjust_edge (drag math and clamping) -----------------------------------


def test_adjust_edge_moves_one_side():
    assert adjust_edge(SIZE, Edges(), "left", 5) == Edges(left=5)
    assert adjust_edge(SIZE, Edges(), "bottom", -2) == Edges(bottom=-2)


def test_crop_to_zero_width_clamps_to_one():
    e = adjust_edge(SIZE, Edges(), "right", -W)
    assert e == Edges(right=-(W - 1))
    assert output_size(SIZE, e)[0] == 1


def test_crop_far_past_image_clamps_to_one():
    e = adjust_edge(SIZE, Edges(), "top", -1000)
    assert output_size(SIZE, e)[1] == 1


def test_clamp_accounts_for_opposite_crop():
    e = adjust_edge(SIZE, Edges(left=-4), "right", -100)
    assert e == Edges(left=-4, right=-5)
    assert visible_rect(SIZE, e) == (4, 0, 5, H)


def test_crop_cannot_remove_image_even_with_opposite_pad():
    # Padding the right does not allow cropping the whole image away from the left.
    e = adjust_edge(SIZE, Edges(right=20), "left", -100)
    assert e.left == -(W - 1)
    x0, _, x1, _ = visible_rect(SIZE, e)
    assert x1 - x0 == 1


def test_symmetric_moves_both_sides():
    assert adjust_edge(SIZE, Edges(), "left", 3, symmetric=True) == Edges(left=3, right=3)
    assert adjust_edge(SIZE, Edges(), "bottom", -2, symmetric=True) == Edges(top=-2, bottom=-2)


def test_symmetric_crop_clamps():
    e = adjust_edge(SIZE, Edges(), "right", -100, symmetric=True)
    assert e.left == e.right
    x0, _, x1, _ = visible_rect(SIZE, e)
    assert x1 - x0 >= 1
    # One more step inward would remove the image.
    assert W + 2 * (e.left - 1) < 1


def test_symmetric_clamp_with_uneven_start():
    # Step -2 leaves 2 px visible; step -3 would leave 0 (both sides crop), so stop at -2.
    e = adjust_edge(SIZE, Edges(left=-6, right=2), "left", -100, symmetric=True)
    assert e == Edges(left=-8, right=0)


def test_adjust_edge_does_not_touch_other_axis():
    e = adjust_edge(SIZE, Edges(top=3, bottom=-1), "left", -2)
    assert (e.top, e.bottom) == (3, -1)
