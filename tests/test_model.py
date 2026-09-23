"""Tests for the edit model: edges and orientation (pure Pillow, no GUI)."""

import pytest
from PIL import Image, ImageChops

from image_lab.model import (
    IDENTITY,
    TRANSPARENT,
    Edges,
    Transform,
    adjust_edge,
    affine,
    apply_edges,
    apply_transform,
    flip_edges_h,
    flip_edges_v,
    flipped_h,
    flipped_v,
    invert,
    map_point,
    output_box,
    output_size,
    render,
    rotate_edges,
    rotated,
    transformed_size,
    view_to_source,
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


# --- orientation ----------------------------------------------------------------

T = Image.Transpose
RIGHT = rotated(IDENTITY, 90)
LEFT = rotated(IDENTITY, -90)


def test_angle_is_normalized():
    assert Transform(270).angle == -90
    assert Transform(-180).angle == 180
    assert Transform(360).angle == 0
    assert Transform(0.1 + 0.2 - 0.3 + 90).angle == 90


def test_view_operations_compose():
    assert flipped_h(flipped_h(IDENTITY)) == IDENTITY
    assert flipped_v(flipped_v(IDENTITY)) == IDENTITY
    t = IDENTITY
    for _ in range(4):
        t = rotated(t, 90)
    assert t == IDENTITY
    assert rotated(RIGHT, -90) == IDENTITY


@pytest.mark.parametrize(
    "angle, size", [(0, (10, 6)), (90, (6, 10)), (180, (10, 6)), (-90, (6, 10))]
)
def test_transformed_size_right_angles(angle, size):
    assert transformed_size(SIZE, Transform(angle)) == size
    assert transformed_size(SIZE, Transform(angle, mirror=True)) == size


@pytest.mark.parametrize(
    "transform, ops",
    [
        (IDENTITY, []),
        (RIGHT, [T.ROTATE_270]),
        (LEFT, [T.ROTATE_90]),
        (Transform(180), [T.ROTATE_180]),
        (flipped_h(IDENTITY), [T.FLIP_LEFT_RIGHT]),
        (flipped_v(IDENTITY), [T.FLIP_TOP_BOTTOM]),
        # Operations apply to the view in order: turn right, then mirror what is seen.
        (flipped_h(RIGHT), [T.ROTATE_270, T.FLIP_LEFT_RIGHT]),
        (rotated(flipped_v(IDENTITY), 90), [T.FLIP_TOP_BOTTOM, T.ROTATE_270]),
    ],
)
def test_apply_transform_matches_view_operations(img, transform, ops):
    expected = img
    for op in ops:
        expected = expected.transpose(op)
    assert _identical(apply_transform(img, transform), expected)


@pytest.mark.parametrize(
    "transform", [RIGHT, LEFT, Transform(180), flipped_h(RIGHT), flipped_v(IDENTITY)]
)
def test_affine_agrees_with_pixels(img, transform):
    # Pixel centers of the original must land on the pixel with the same color.
    view = apply_transform(img, transform)
    m = affine(SIZE, transform)
    for x, y in [(0, 0), (9, 0), (3, 5), (9, 5)]:
        vx, vy = map_point(m, (x + 0.5, y + 0.5))
        assert view.getpixel((int(vx), int(vy))) == px(x, y)


@pytest.mark.parametrize("transform", [RIGHT, flipped_h(IDENTITY), Transform(33.3, mirror=True)])
def test_view_to_source_inverts_affine(transform):
    m = affine(SIZE, transform)
    for p in [(0.0, 0.0), (2.5, 4.0), (10.0, 6.0)]:
        back = view_to_source(map_point(m, p), SIZE, transform)
        assert back == pytest.approx(p)
    assert map_point(invert(m), map_point(m, (1.0, 2.0))) == pytest.approx((1.0, 2.0))


def test_apply_transform_leaves_original_alone(img):
    before = img.copy()
    apply_transform(img, flipped_h(RIGHT))
    assert _identical(img, before)


EDGES = Edges(left=2, top=-1, right=-3, bottom=4)


@pytest.mark.parametrize(
    "turn, edge_op, pixel_op",
    [
        (lambda t: rotated(t, 90), lambda e: rotate_edges(e, clockwise=True), T.ROTATE_270),
        (lambda t: rotated(t, -90), lambda e: rotate_edges(e, clockwise=False), T.ROTATE_90),
        (flipped_h, flip_edges_h, T.FLIP_LEFT_RIGHT),
        (flipped_v, flip_edges_v, T.FLIP_TOP_BOTTOM),
    ],
)
def test_edges_follow_the_view(img, turn, edge_op, pixel_op):
    # Turning or flipping after editing turns or flips the exact same output.
    before = render(img, EDGES, (1, 2, 3, 255), IDENTITY)
    after = render(img, edge_op(EDGES), (1, 2, 3, 255), turn(IDENTITY))
    assert _identical(after, before.transpose(pixel_op))


def test_render_applies_edges_in_view_pixels(img):
    # After a right turn the view is 6x10; cropping its top row removes original column 0.
    out = render(img, Edges(top=-1), transform=RIGHT)
    assert out.size == (6, 9)
    assert out.getpixel((0, 0)) == px(1, 5)
