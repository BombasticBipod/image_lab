"""Tests for ImageCanvas: hit testing and edge dragging, driven headless."""

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication

from image_lab.canvas import ImageCanvas, hit_edge
from image_lab.model import Edges, output_size, visible_rect

pytestmark = pytest.mark.gui

BOX = (100.0, 50.0, 300.0, 150.0)  # left, top, right, bottom


# --- hit_edge (no widget needed) -------------------------------------------


@pytest.mark.parametrize(
    "x, y, expected",
    [
        (100, 100, "left"),
        (95, 100, "left"),
        (300, 100, "right"),
        (307, 100, "right"),
        (200, 50, "top"),
        (200, 152, "bottom"),
        (200, 100, None),  # inside, far from every edge
        (80, 100, None),  # too far left
        (100, 20, None),  # left line extended, but past the side's extent
        (102, 54, "left"),  # corner region: left is closer than top
        (104, 51, "top"),  # corner region: top is closer than left
    ],
)
def test_hit_edge(x, y, expected):
    assert hit_edge(BOX, x, y) == expected


# --- widget helpers -----------------------------------------------------------


def send_mouse(widget, kind, x, y, button=Qt.NoButton, buttons=Qt.NoButton, mods=Qt.NoModifier):
    pos = QPointF(x, y)
    event = QMouseEvent(kind, pos, widget.mapToGlobal(pos), button, buttons, mods)
    QApplication.sendEvent(widget, event)


def drag(widget, start, end, mods=Qt.NoModifier, release=True):
    """Press at start, move to end (with the button held), and optionally release."""
    send_mouse(widget, QEvent.MouseMove, *start)
    send_mouse(widget, QEvent.MouseButtonPress, *start, Qt.LeftButton, Qt.LeftButton, mods)
    send_mouse(widget, QEvent.MouseMove, *end, Qt.NoButton, Qt.LeftButton, mods)
    if release:
        send_mouse(widget, QEvent.MouseButtonRelease, *end, Qt.LeftButton, Qt.NoButton, mods)


def solid_pixmap(w, h):
    pm = QPixmap(w, h)
    pm.fill(Qt.darkCyan)
    return pm


@pytest.fixture
def canvas(qapp):
    """800x600 canvas with a 400x200 image at scale 1: output box (200,200)-(600,400)."""
    c = ImageCanvas()
    c.resize(800, 600)
    c.show()
    qapp.processEvents()
    c.set_image(solid_pixmap(400, 200))
    assert c.scale == 1.0
    assert (c.origin.x(), c.origin.y()) == (200, 200)
    yield c
    c.close()


MIDPOINTS = {"left": (200, 300), "right": (600, 300), "top": (400, 200), "bottom": (400, 400)}
OUTWARD = {"left": (-1, 0), "right": (1, 0), "top": (0, -1), "bottom": (0, 1)}


def _drag_side(canvas, side, amount, **kwargs):
    """Drag a side outward by `amount` screen px (negative drags inward)."""
    sx, sy = MIDPOINTS[side]
    ux, uy = OUTWARD[side]
    drag(canvas, (sx, sy), (sx + ux * amount, sy + uy * amount), **kwargs)


# --- hover and cursors ---------------------------------------------------------


def test_hover_sets_edge_and_cursor(canvas):
    send_mouse(canvas, QEvent.MouseMove, 600, 300)
    assert canvas.hovered_edge == "right"
    assert canvas.cursor().shape() == Qt.SizeHorCursor
    send_mouse(canvas, QEvent.MouseMove, 400, 402)
    assert canvas.hovered_edge == "bottom"
    assert canvas.cursor().shape() == Qt.SizeVerCursor
    send_mouse(canvas, QEvent.MouseMove, 400, 300)
    assert canvas.hovered_edge is None
    assert canvas.cursor().shape() == Qt.ArrowCursor


def test_hover_snapshot(canvas, artifacts_dir):
    send_mouse(canvas, QEvent.MouseMove, 600, 300)
    assert canvas.grab().save(str(artifacts_dir / "m4_hover_right.png"))


# --- dragging -------------------------------------------------------------------


@pytest.mark.parametrize("side", ["left", "top", "right", "bottom"])
def test_pad_and_crop_each_side(canvas, side):
    _drag_side(canvas, side, 40)
    assert getattr(canvas.edges, side) == 40
    _drag_side_from_current(canvas, side, -70)
    assert getattr(canvas.edges, side) == -30


def _drag_side_from_current(canvas, side, amount):
    """Grab the side where it is now (after refits) and drag it by `amount` screen px."""
    r = canvas._output_screen_rect()
    points = {
        "left": (r.left(), r.center().y()),
        "right": (r.right(), r.center().y()),
        "top": (r.center().x(), r.top()),
        "bottom": (r.center().x(), r.bottom()),
    }
    sx, sy = points[side]
    ux, uy = OUTWARD[side]
    s = canvas.scale
    drag(canvas, (sx, sy), (sx + ux * amount * s, sy + uy * amount * s))


def test_view_frozen_during_drag_and_refit_on_release(canvas):
    _drag_side(canvas, "right", 40, release=False)
    assert canvas.edges == Edges(right=40)
    # Mid-drag the view has not moved, even though the output box grew.
    assert (canvas.origin.x(), canvas.origin.y()) == (200, 200)
    send_mouse(canvas, QEvent.MouseButtonRelease, 640, 300, Qt.LeftButton, Qt.NoButton)
    # After release the 440-wide output is recentered: 400 - 440/2 = 180.
    assert canvas.origin.x() == pytest.approx(180)


def test_resize_during_drag_does_not_refit(canvas, qapp):
    _drag_side(canvas, "right", 40, release=False)
    canvas.resize(700, 500)
    qapp.processEvents()
    assert (canvas.origin.x(), canvas.origin.y()) == (200, 200)
    send_mouse(canvas, QEvent.MouseButtonRelease, 640, 300, Qt.LeftButton, Qt.NoButton)


def test_drag_converts_screen_to_image_pixels(qapp):
    c = ImageCanvas()
    c.resize(800, 600)
    c.show()
    qapp.processEvents()
    c.set_image(solid_pixmap(2000, 1000))
    s = c.scale
    assert s == pytest.approx(0.32)
    r = c._output_screen_rect()
    y = r.center().y()
    drag(c, (r.right(), y), (r.right() + 32, y))
    assert c.edges == Edges(right=100)
    c.close()


def test_cannot_crop_to_nothing(canvas):
    _drag_side(canvas, "left", -5000)
    size = (400, 200)
    x0, _, x1, _ = visible_rect(size, canvas.edges)
    assert x1 - x0 == 1
    assert output_size(size, canvas.edges)[0] == 1


def test_shift_drag_is_symmetric(canvas):
    _drag_side(canvas, "top", 25, mods=Qt.ShiftModifier)
    assert canvas.edges == Edges(top=25, bottom=25)


def test_press_away_from_edges_does_nothing(canvas):
    drag(canvas, (400, 300), (450, 350))
    assert canvas.edges == Edges()


def test_edges_changed_signal(canvas):
    seen = []
    canvas.edgesChanged.connect(lambda: seen.append(canvas.edges))
    _drag_side(canvas, "bottom", 10)
    assert seen and seen[-1] == Edges(bottom=10)


def test_drag_snapshot(canvas, artifacts_dir):
    # Pad left and crop right, then save what the user sees after release.
    _drag_side(canvas, "left", 60)
    _drag_side_from_current(canvas, "right", -120)
    assert canvas.edges == Edges(left=60, right=-120)
    assert canvas.grab().save(str(artifacts_dir / "m4_pad_left_crop_right.png"))


def test_new_image_resets_edges(canvas):
    _drag_side(canvas, "right", 40)
    canvas.set_image(solid_pixmap(100, 100))
    assert canvas.edges == Edges()
