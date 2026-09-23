"""Edge model: a pad/crop edit as four integers, and all geometry derived from it.

Pure Pillow, no Qt. The canvas preview and the export both use these helpers,
so what the user sees always matches what gets saved.

Coordinates are original-image pixels. Rects are (x0, y0, x1, y1) with x1 and y1
exclusive, the same convention as Pillow's crop boxes.
"""

from dataclasses import dataclass, replace

from PIL import Image

Rect = tuple[int, int, int, int]
Size = tuple[int, int]
RGBA = tuple[int, int, int, int]

TRANSPARENT: RGBA = (0, 0, 0, 0)

SIDES = ("left", "top", "right", "bottom")
OPPOSITE = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}


@dataclass(frozen=True)
class Edges:
    """Per-side edit in original pixels: positive pads, negative crops, zero is unchanged."""

    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0


def output_box(size: Size, edges: Edges) -> Rect:
    """The exported area, in original-image coordinates (may extend past the image)."""
    w, h = size
    return (-edges.left, -edges.top, w + edges.right, h + edges.bottom)


def output_size(size: Size, edges: Edges) -> Size:
    x0, y0, x1, y1 = output_box(size, edges)
    return (x1 - x0, y1 - y0)


def visible_rect(size: Size, edges: Edges) -> Rect:
    """The part of the original that survives the crop: image bounds ∩ output box."""
    w, h = size
    x0, y0, x1, y1 = output_box(size, edges)
    return (max(0, x0), max(0, y0), min(w, x1), min(h, y1))


def _axis_is_valid(length: int, a: int, b: int) -> bool:
    # At least one original pixel must stay visible on each axis. Only crops
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


def apply_edges(img: Image.Image, edges: Edges, fill: RGBA = TRANSPARENT) -> Image.Image:
    """Return a new RGBA image with the edges applied; padding is filled with `fill`."""
    x0, y0, x1, y1 = output_box(img.size, edges)
    out = Image.new("RGBA", (x1 - x0, y1 - y0), fill)
    vis = visible_rect(img.size, edges)
    # paste() replaces pixels, so transparent image pixels stay transparent
    # rather than showing the fill color underneath.
    out.paste(img.convert("RGBA").crop(vis), (vis[0] - x0, vis[1] - y0))
    return out
