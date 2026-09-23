"""Tests for the edit model: edges, clamping, orientation, paint mask (pure Pillow, no GUI)."""

import pytest
from PIL import Image, ImageChops

from image_lab.model import (
    IDENTITY,
    TRANSPARENT,
    Edges,
    Stroke,
    Transform,
    adjust_edge,
    affine,
    apply_edges,
    apply_mask,
    apply_transform,
    clamp_edges,
    flip_edges_h,
    flip_edges_v,
    flipped_h,
    flipped_v,
    invert,
    map_point,
    output_box,
    output_size,
    render,
    render_mask,
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


# --- free angle -----------------------------------------------------------------


def test_transformed_size_free_angle():
    # 10x6 at 30 degrees: 10*cos30 + 6*sin30 = 11.66, 10*sin30 + 6*cos30 = 10.20.
    assert transformed_size(SIZE, Transform(30)) == (12, 11)
    assert transformed_size(SIZE, Transform(-30)) == (12, 11)
    assert transformed_size(SIZE, Transform(45)) == (12, 12)


@pytest.mark.parametrize("angle", [90, 180, -90])
def test_pillow_affine_convention_matches_transpose(img, angle):
    # The free-angle path uses Pillow's AFFINE with the model's inverse matrix. At a
    # right angle with NEAREST it must equal the exact transpose, which proves the
    # matrix and Pillow agree on pixel centers.
    t = Transform(angle, mirror=True)
    via_affine = img.transform(
        transformed_size(SIZE, t),
        Image.Transform.AFFINE,
        invert(affine(SIZE, t)),
        resample=Image.Resampling.NEAREST,
    )
    assert _identical(via_affine, apply_transform(img, t))


def test_free_angle_export():
    src = Image.new("RGBA", (40, 20), (200, 10, 10, 255))
    out = apply_transform(src, Transform(30))
    assert out.size == transformed_size((40, 20), Transform(30))
    # The uncovered corners are transparent; the middle is the image color.
    assert out.getpixel((0, 0))[3] == 0
    assert out.getpixel((out.width - 1, out.height - 1))[3] == 0
    assert out.getpixel((out.width // 2, out.height // 2)) == (200, 10, 10, 255)


def test_free_angle_keeps_rgb_under_transparency():
    src = Image.new("RGBA", (40, 20), (50, 60, 70, 0))
    out = apply_transform(src, Transform(20))
    assert out.getpixel((out.width // 2, out.height // 2)) == (50, 60, 70, 0)


def test_fill_does_not_cover_rotation_corners():
    src = Image.new("RGBA", (40, 20), (200, 10, 10, 255))
    out = render(src, Edges(left=2), fill=(0, 255, 0, 255), transform=Transform(30))
    assert out.getpixel((0, 0)) == (0, 255, 0, 255)  # padding
    assert out.getpixel((2, 0))[3] == 0  # rotation corner stays transparent


def test_clamp_edges():
    assert clamp_edges(SIZE, EDGES) == EDGES
    # Width 10 allows 9 px of crop; 2 px too many are given back, one per side.
    assert clamp_edges(SIZE, Edges(left=-5, right=-6)) == Edges(left=-4, right=-5)
    # A side can only give back what it cropped.
    assert clamp_edges(SIZE, Edges(left=-12, right=-1)) == Edges(left=-9)
    assert clamp_edges(SIZE, Edges(top=-3, bottom=-3)) == Edges(top=-2, bottom=-3)
    assert clamp_edges(SIZE, Edges(left=-20, right=4)) == Edges(left=-9, right=4)


# --- paint mask -------------------------------------------------------------------


def test_render_mask_disc_and_line():
    # A dot at the center of pixel (5, 3) with radius 1 covers that pixel only nearby.
    mask = render_mask(SIZE, (Stroke(((5.5, 3.5),), radius=1),))
    assert mask.mode == "L" and mask.size == SIZE
    assert mask.getpixel((5, 3)) == 255
    assert mask.getpixel((8, 3)) == 0 and mask.getpixel((5, 0)) == 0
    line = render_mask(SIZE, (Stroke(((0.5, 0.5), (9.5, 0.5)), radius=0.5),))
    assert all(line.getpixel((x, 0)) == 255 for x in range(W))
    assert line.getpixel((0, 2)) == 0


def test_render_mask_restore_order():
    erase = Stroke(((0.5, 0.5), (9.5, 0.5)), radius=0.5)
    restore = Stroke(((4.5, 0.5),), radius=0.5, erase=False)
    mask = render_mask(SIZE, (erase, restore))
    assert mask.getpixel((4, 0)) == 0
    assert mask.getpixel((3, 0)) == 255
    # Erasing again after the restore wins, because strokes apply in order.
    again = render_mask(SIZE, (erase, restore, erase))
    assert again.getpixel((4, 0)) == 255


def test_apply_mask_keeps_rgb(img):
    mask = render_mask(SIZE, (Stroke(((2.5, 2.5),), radius=0.5),))
    out = apply_mask(img, mask)
    assert out.getpixel((2, 2)) == px(2, 2)[:3] + (0,)
    assert out.getpixel((3, 3)) == px(3, 3)
    assert img.getpixel((2, 2)) == px(2, 2)  # original untouched


def test_apply_mask_keeps_partial_alpha():
    src = Image.new("RGBA", (2, 1), (10, 20, 30, 128))
    out = apply_mask(src, render_mask((2, 1), (Stroke(((0.5, 0.5),), radius=0.5),)))
    assert out.getpixel((0, 0)) == (10, 20, 30, 0)
    assert out.getpixel((1, 0)) == (10, 20, 30, 128)


def test_render_masks_before_turning(img):
    # Strokes are in original pixels: erasing original (0, 0) and turning right puts
    # the transparent pixel at the view's top-right corner.
    strokes = (Stroke(((0.5, 0.5),), radius=0.5),)
    out = render(img, Edges(), transform=RIGHT, strokes=strokes)
    assert out.getpixel((H - 1, 0)) == px(0, 0)[:3] + (0,)
    assert out.getpixel((0, 0))[3] == 255


def test_render_mask_survives_free_angle():
    src = Image.new("RGBA", (40, 20), (50, 60, 70, 255))
    # Erase everything; the RGB must survive the bicubic rotation under alpha 0.
    strokes = (Stroke(((20.0, 10.0),), radius=40),)
    out = render(src, Edges(), transform=Transform(25), strokes=strokes)
    assert out.getpixel((out.width // 2, out.height // 2)) == (50, 60, 70, 0)


# --- clamping, exhaustively on small images (invariant 4) ----------------------------

VALUES = range(-6, 4)
AXES = {"left": ("left", "right"), "right": ("left", "right")}
AXES.update({"top": ("top", "bottom"), "bottom": ("top", "bottom")})


def _visible(length, a, b):
    """Image pixels left on an axis of `length` with edge values a and b."""
    return length + min(a, 0) + min(b, 0)


def _all_edges():
    for a in VALUES:
        for b in VALUES:
            yield a, b


@pytest.mark.parametrize("symmetric", [False, True])
@pytest.mark.parametrize("side", ["left", "top", "right", "bottom"])
@pytest.mark.parametrize("length", [1, 2, 3, 5])
def test_adjust_edge_always_keeps_a_pixel(length, side, symmetric):
    size = (length, length)
    first, second = AXES[side]
    for a, b in _all_edges():
        if _visible(length, a, b) < 1:
            continue  # adjust_edge requires a valid start
        start = Edges(**{first: a, second: b})
        for amount in range(-8, 9):
            e = adjust_edge(size, start, side, amount, symmetric)
            assert _visible(length, getattr(e, first), getattr(e, second)) >= 1
            assert min(output_size(size, e)) >= 1
            step = getattr(e, side) - getattr(start, side)
            # Never moves further than asked, and only stops short when one more
            # step inward would crop the image away.
            assert amount <= step <= max(amount, 0)
            if step != amount:
                assert adjust_edge(size, e, side, -1, symmetric) == e


@pytest.mark.parametrize("length", [1, 2, 3, 5])
def test_clamp_edges_is_valid_idempotent_and_minimal(length):
    size = (length, length)
    for a, b in _all_edges():
        for c, d in [(0, 0), (-2, 3)]:
            edges = Edges(left=a, right=b, top=c, bottom=d)
            e = clamp_edges(size, edges)
            assert _visible(length, e.left, e.right) >= 1
            assert _visible(length, e.top, e.bottom) >= 1
            assert clamp_edges(size, e) == e
            # Only crops are reduced, never past zero, and pads are untouched.
            for side in ("left", "right"):
                before, after = getattr(edges, side), getattr(e, side)
                assert after == before if before >= 0 else before <= after <= 0
            if _visible(length, a, b) >= 1:
                assert (e.left, e.right) == (a, b)
            else:
                # Exactly one pixel is given back: no more crop is returned than needed.
                assert _visible(length, e.left, e.right) == 1
            if _visible(length, c, d) >= 1:
                assert (e.top, e.bottom) == (c, d)
