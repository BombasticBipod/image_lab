"""Edit model: background matte, paint mask, orientation (flip, rotation), pad/crop edges,
and their geometry.

Pure Pillow, no Qt. The canvas preview and the export both use these helpers,
so what the user sees always matches what gets saved.

The background matte and paint strokes are in original-image pixels, so they stay on the
same pixels when the image is turned. The original image is first oriented by a
`Transform`; the result is the "view" image. Edges and rects are in view-image pixels.
Rects are (x0, y0, x1, y1) with
x1 and y1 exclusive, the same convention as Pillow's crop boxes. Points are
continuous: pixel (i, j) covers [i, i+1) x [j, j+1), as in Pillow's transforms.
"""

import math
from dataclasses import dataclass, replace

from PIL import Image, ImageChops, ImageDraw, ImageOps

Rect = tuple[int, int, int, int]
Size = tuple[int, int]
RGBA = tuple[int, int, int, int]
# Affine map (a, b, c, d, e, f): x' = a*x + b*y + c, y' = d*x + e*y + f.
Matrix = tuple[float, float, float, float, float, float]

TRANSPARENT: RGBA = (0, 0, 0, 0)

SIDES = ("left", "top", "right", "bottom")
OPPOSITE = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}


@dataclass(frozen=True)
class Edges:
    """Per-side edit in view-image pixels: positive pads, negative crops, zero is unchanged."""

    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0


def output_box(size: Size, edges: Edges) -> Rect:
    """The exported area, in view-image coordinates (may extend past the image)."""
    w, h = size
    return (-edges.left, -edges.top, w + edges.right, h + edges.bottom)


def output_size(size: Size, edges: Edges) -> Size:
    x0, y0, x1, y1 = output_box(size, edges)
    return (x1 - x0, y1 - y0)


def visible_rect(size: Size, edges: Edges) -> Rect:
    """The part of the image that survives the crop: image bounds ∩ output box."""
    w, h = size
    x0, y0, x1, y1 = output_box(size, edges)
    return (max(0, x0), max(0, y0), min(w, x1), min(h, y1))


def _axis_is_valid(length: int, a: int, b: int) -> bool:
    # At least one image pixel must stay visible on each axis. Only crops
    # (negative values) eat into the image; pads never do. This also keeps the
    # output at least 1 px, since pads only add to it.
    return length + min(a, 0) + min(b, 0) >= 1


def adjust_edge(size: Size, start: Edges, side: str, amount: int, symmetric: bool = False) -> Edges:
    """Move `side` outward by `amount` pixels (negative moves it inward), clamped.

    With `symmetric`, the opposite side moves by the same amount. If the move
    would crop away the whole image on that axis, the amount is reduced to the
    largest inward move that keeps one pixel visible. `start` must be valid.
    """
    sides = (side, OPPOSITE[side]) if symmetric else (side,)
    length = size[0] if side in ("left", "right") else size[1]

    def moved(step: int) -> Edges:
        return replace(start, **{s: getattr(start, s) + step for s in sides})

    def valid(step: int) -> bool:
        e = moved(step)
        if side in ("left", "right"):
            return _axis_is_valid(length, e.left, e.right)
        return _axis_is_valid(length, e.top, e.bottom)

    if not valid(amount):
        # Validity only gets worse as the step goes more negative, and step 0 is
        # valid (start is valid), so binary search for the most negative valid step.
        invalid, ok = amount, 0
        while ok - invalid > 1:
            mid = (invalid + ok) // 2
            if valid(mid):
                ok = mid
            else:
                invalid = mid
        amount = ok
    return moved(amount)


def _clamp_axis(length: int, a: int, b: int) -> tuple[int, int]:
    # Crops beyond what the axis allows are given back, split between the two sides.
    excess = 1 - (length + min(a, 0) + min(b, 0))
    if excess <= 0:
        return a, b
    crop_a, crop_b = -min(a, 0), -min(b, 0)
    give_b = min(crop_b, excess - min(crop_a, (excess + 1) // 2))
    return a + excess - give_b, b + give_b


def clamp_edges(size: Size, edges: Edges) -> Edges:
    """Edges made valid for an image of `size` by reducing crops that are too deep.

    Used when the view image changes size (a free-angle rotation), so at least one
    image pixel stays visible on each axis. Valid edges come back unchanged.
    """
    left, right = _clamp_axis(size[0], edges.left, edges.right)
    top, bottom = _clamp_axis(size[1], edges.top, edges.bottom)
    return Edges(left, top, right, bottom)


def apply_edges(img: Image.Image, edges: Edges, fill: RGBA = TRANSPARENT) -> Image.Image:
    """Return a new RGBA image with the edges applied; padding is filled with `fill`."""
    x0, y0, x1, y1 = output_box(img.size, edges)
    out = Image.new("RGBA", (x1 - x0, y1 - y0), fill)
    vis = visible_rect(img.size, edges)
    # paste() replaces pixels, so transparent image pixels stay transparent
    # rather than showing the fill color underneath.
    out.paste(img.convert("RGBA").crop(vis), (vis[0] - x0, vis[1] - y0))
    return out


# --- orientation ----------------------------------------------------------------


def _normalize_angle(angle: float) -> float:
    # Rounding removes float noise (so 90 stays exactly 90 after sums), then the
    # angle is folded into (-180, 180].
    a = round(angle, 6) % 360
    return a - 360 if a > 180 else a


@dataclass(frozen=True)
class Transform:
    """How the original is oriented in the view: an optional horizontal mirror, then a
    clockwise rotation by `angle` degrees, both about the image center.

    The view image is the bounding box of the result. `angle` is normalized to (-180, 180].
    """

    angle: float = 0.0
    mirror: bool = False

    def __post_init__(self):
        object.__setattr__(self, "angle", _normalize_angle(self.angle))

    @property
    def is_right_angle(self) -> bool:
        """True for 0, 90, 180 and -90 degrees, which transform without resampling."""
        return self.angle % 90 == 0


IDENTITY = Transform()

# The user flips and rotates what they see, so these compose on the view side:
# new view = operation(old view).


def rotated(t: Transform, degrees: float) -> Transform:
    """Rotate the view clockwise by `degrees`."""
    return Transform(t.angle + degrees, t.mirror)


def flipped_h(t: Transform) -> Transform:
    """Mirror the view left to right. A mirror after R(angle) equals R(-angle) after a mirror."""
    return Transform(-t.angle, not t.mirror)


def flipped_v(t: Transform) -> Transform:
    """Mirror the view top to bottom, which is a left-right mirror plus a half turn."""
    return rotated(flipped_h(t), 180)


def _cos_sin(angle: float) -> tuple[float, float]:
    exact = {0: (1, 0), 90: (0, 1), 180: (-1, 0), -90: (0, -1)}
    if angle in exact:
        return exact[angle]
    rad = math.radians(angle)
    return math.cos(rad), math.sin(rad)


def transformed_size(size: Size, t: Transform) -> Size:
    """Size of the view image: the bounding box of the rotated original, rounded up."""
    w, h = size
    c, s = _cos_sin(t.angle)
    # round() first so float noise like 10.0000000001 doesn't round up a whole pixel.
    return (
        max(1, math.ceil(round(w * abs(c) + h * abs(s), 6))),
        max(1, math.ceil(round(w * abs(s) + h * abs(c), 6))),
    )


def affine(size: Size, t: Transform) -> Matrix:
    """Map from original-image points to view-image points.

    y points down, so the rotation matrix [[c, -s], [s, c]] turns clockwise on screen.
    """
    w, h = size
    vw, vh = transformed_size(size, t)
    c, s = _cos_sin(t.angle)
    m = -1 if t.mirror else 1
    # Relative to the centers: v - vcenter = R * (M * (p - center)).
    a, b, d, e = c * m, -s, s * m, c
    return (a, b, vw / 2 - a * w / 2 - b * h / 2, d, e, vh / 2 - d * w / 2 - e * h / 2)


def invert(matrix: Matrix) -> Matrix:
    """Inverse of an affine map."""
    a, b, c, d, e, f = matrix
    det = a * e - b * d
    ia, ib, id_, ie = e / det, -b / det, -d / det, a / det
    return (ia, ib, -(ia * c + ib * f), id_, ie, -(id_ * c + ie * f))


def map_point(matrix: Matrix, point: tuple[float, float]) -> tuple[float, float]:
    a, b, c, d, e, f = matrix
    x, y = point
    return (a * x + b * y + c, d * x + e * y + f)


def view_to_source(point: tuple[float, float], size: Size, t: Transform) -> tuple[float, float]:
    """Original-image point under a view-image point."""
    return map_point(invert(affine(size, t)), point)


# Right-angle turns and mirrors keep pixels exact, so they use transpose().
_TRANSPOSE = {
    90: Image.Transpose.ROTATE_270,  # Pillow's ROTATE_* turn counterclockwise.
    180: Image.Transpose.ROTATE_180,
    -90: Image.Transpose.ROTATE_90,
}


def apply_transform(img: Image.Image, t: Transform) -> Image.Image:
    """Return the view image: `img` mirrored and rotated as `t` says, as RGBA.

    Right angles are exact. Other angles resample bicubically; the corners the rotation
    uncovers are transparent, and RGB under transparent pixels is kept.
    """
    out = img.convert("RGBA")
    if not t.is_right_angle:
        # Pillow resamples RGBA premultiplied, which blackens RGB under alpha 0, so the
        # color and alpha channels are resampled separately and merged.
        def turn(band: Image.Image) -> Image.Image:
            # Pillow's AFFINE data maps output points back to input points.
            return band.transform(
                transformed_size(img.size, t),
                Image.Transform.AFFINE,
                invert(affine(img.size, t)),
                resample=Image.Resampling.BICUBIC,
            )

        rgb = turn(out.convert("RGB"))
        rgb.putalpha(turn(out.getchannel("A")))
        return rgb
    if t.mirror:
        out = out.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if t.angle in _TRANSPOSE:
        out = out.transpose(_TRANSPOSE[t.angle])
    return out


# Edges belong to the view, so a view rotation or flip carries them along exactly.


def rotate_edges(edges: Edges, clockwise: bool) -> Edges:
    """Edges after the view turns 90 degrees: each side's edit moves to where that side went."""
    e = edges
    if clockwise:
        return Edges(left=e.bottom, top=e.left, right=e.top, bottom=e.right)
    return Edges(left=e.top, top=e.right, right=e.bottom, bottom=e.left)


def flip_edges_h(edges: Edges) -> Edges:
    return replace(edges, left=edges.right, right=edges.left)


def flip_edges_v(edges: Edges) -> Edges:
    return replace(edges, top=edges.bottom, bottom=edges.top)


# --- paint mask -------------------------------------------------------------------


@dataclass(frozen=True)
class Stroke:
    """One brush stroke in original-image points: erase makes pixels transparent,
    restore (erase=False) brings them back."""

    points: tuple[tuple[float, float], ...]
    radius: float
    erase: bool = True


@dataclass(frozen=True, eq=False)
class Matte:
    """Soft alpha from background removal ("L", original-image size): 255 keeps a
    pixel, 0 removes it. Compared by identity, so edit states compare without reading
    pixels; each removal creates a new `Matte`."""

    image: Image.Image


MASK_ON = 255


def render_mask(size: Size, strokes: tuple[Stroke, ...], matte: Matte | None = None) -> Image.Image:
    """Mask ("L") of erased pixels: 255 where erased, 0 elsewhere. Strokes apply in order.

    With a `matte`, the mask starts as the removed background (the matte inverted), so
    a restore stroke brings back background the removal took away.
    The brush is hard and round: a line as wide as the brush, plus a disc at every point.
    """
    mask = ImageOps.invert(matte.image) if matte is not None else Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    for stroke in strokes:
        value = MASK_ON if stroke.erase else 0
        r = stroke.radius
        # ImageDraw puts pixel (i, j)'s center at (i, j); ours is at (i + 0.5, j + 0.5).
        points = [(x - 0.5, y - 0.5) for x, y in stroke.points]
        if len(points) > 1:
            draw.line(points, fill=value, width=max(1, round(2 * r)))
        for x, y in points:
            # Pillow's discs under two pixels wide are unreliable (empty or spilling
            # into a neighbor), so a 1 px brush covers just the pixel under the point.
            if r >= 1:
                draw.ellipse((x - r, y - r, x + r, y + r), fill=value)
            draw.point((math.floor(x + 0.5), math.floor(y + 0.5)), fill=value)
    return mask


def apply_mask(img: Image.Image, mask: Image.Image) -> Image.Image:
    """Return `img` as RGBA with its alpha cut to 0 where `mask` is on. RGB is kept."""
    out = img.convert("RGBA")
    out.putalpha(ImageChops.multiply(out.getchannel("A"), ImageOps.invert(mask)))
    return out


def render(
    img: Image.Image,
    edges: Edges,
    fill: RGBA = TRANSPARENT,
    transform: Transform = IDENTITY,
    strokes: tuple[Stroke, ...] = (),
    matte: Matte | None = None,
) -> Image.Image:
    """The exported image: `img` with the background matte and then the paint mask
    applied, oriented by `transform`, then with `edges` and `fill` applied."""
    if strokes or matte is not None:
        img = apply_mask(img, render_mask(img.size, strokes, matte))
    return apply_edges(apply_transform(img, transform), edges, fill)
