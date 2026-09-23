"""Headless tests for ImageCanvas: hit testing, edge drags, drag-out, paint input, leaving."""

import pytest
from conftest import drag_edge, mouse_drag, send_mouse
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QPixmap
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


# --- hover and cursors ---------------------------------------------------------


def test_hover_sets_edge_and_cursor(canvas):
    send_mouse(canvas, QEvent.MouseMove, (600, 300))
    assert canvas.hovered_edge == "right"
    assert canvas.cursor().shape() == Qt.SizeHorCursor
    send_mouse(canvas, QEvent.MouseMove, (400, 402))
    assert canvas.hovered_edge == "bottom"
    assert canvas.cursor().shape() == Qt.SizeVerCursor
    send_mouse(canvas, QEvent.MouseMove, (400, 300))
    assert canvas.hovered_edge is None
    assert canvas.cursor().shape() == Qt.OpenHandCursor  # inside: can drag the image out
    send_mouse(canvas, QEvent.MouseMove, (50, 50))
    assert canvas.hovered_edge is None
    assert canvas.cursor().shape() == Qt.ArrowCursor


def test_hover_snapshot(canvas, artifacts_dir):
    send_mouse(canvas, QEvent.MouseMove, (600, 300))
    assert canvas.grab().save(str(artifacts_dir / "m4_hover_right.png"))


# --- dragging -------------------------------------------------------------------


@pytest.mark.parametrize("side", ["left", "top", "right", "bottom"])
def test_pad_and_crop_each_side(canvas, side):
    drag_edge(canvas, side, 40)
    assert getattr(canvas.edges, side) == 40
    drag_edge(canvas, side, -70)
    assert getattr(canvas.edges, side) == -30


def test_view_frozen_during_drag_and_refit_on_release(canvas):
    drag_edge(canvas, "right", 40, release=False)
    assert canvas.edges == Edges(right=40)
    # Mid-drag the view has not moved, even though the output box grew.
    assert (canvas.origin.x(), canvas.origin.y()) == (200, 200)
    send_mouse(canvas, QEvent.MouseButtonRelease, (640, 300), Qt.LeftButton, Qt.NoButton)
    # After release the 440-wide output is recentered: 400 - 440/2 = 180.
    assert canvas.origin.x() == pytest.approx(180)


def test_resize_during_drag_does_not_refit(canvas, qapp):
    drag_edge(canvas, "right", 40, release=False)
    canvas.resize(700, 500)
    qapp.processEvents()
    assert (canvas.origin.x(), canvas.origin.y()) == (200, 200)
    send_mouse(canvas, QEvent.MouseButtonRelease, (640, 300), Qt.LeftButton, Qt.NoButton)


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
    mouse_drag(c, [(r.right(), y), (r.right() + 32, y)])
    assert c.edges == Edges(right=100)
    c.close()


def test_cannot_crop_to_nothing(canvas):
    drag_edge(canvas, "left", -5000)
    size = (400, 200)
    x0, _, x1, _ = visible_rect(size, canvas.edges)
    assert x1 - x0 == 1
    assert output_size(size, canvas.edges)[0] == 1


def test_shift_drag_is_symmetric(canvas):
    drag_edge(canvas, "top", 25, mods=Qt.ShiftModifier)
    assert canvas.edges == Edges(top=25, bottom=25)


def test_drag_inside_does_not_change_edges(canvas):
    mouse_drag(canvas, [(400, 300), (450, 350)])
    assert canvas.edges == Edges()


def test_edges_changed_signal(canvas):
    seen = []
    canvas.edgesChanged.connect(lambda: seen.append(canvas.edges))
    drag_edge(canvas, "bottom", 10)
    assert seen and seen[-1] == Edges(bottom=10)


def test_drag_snapshot(canvas, artifacts_dir):
    # Pad left and crop right, then save what the user sees after release.
    drag_edge(canvas, "left", 60)
    drag_edge(canvas, "right", -120)
    assert canvas.edges == Edges(left=60, right=-120)
    assert canvas.grab().save(str(artifacts_dir / "m4_pad_left_crop_right.png"))


def test_new_image_resets_edges(canvas):
    drag_edge(canvas, "right", 40)
    canvas.set_image(solid_pixmap(100, 100))
    assert canvas.edges == Edges()


# --- drag out ---------------------------------------------------------------------


def _count_drag_outs(canvas):
    seen = []
    canvas.dragOutRequested.connect(lambda: seen.append(True))
    return seen


def test_drag_from_inside_requests_drag_out_once(canvas):
    seen = _count_drag_outs(canvas)
    mouse_drag(canvas, [(400, 300), (450, 330)], release=False)
    send_mouse(canvas, QEvent.MouseMove, (480, 340), Qt.NoButton, Qt.LeftButton)
    send_mouse(canvas, QEvent.MouseButtonRelease, (480, 340), Qt.LeftButton, Qt.NoButton)
    assert seen == [True]
    assert canvas.edges == Edges()


def test_small_move_inside_does_not_drag_out(canvas):
    seen = _count_drag_outs(canvas)
    mouse_drag(canvas, [(400, 300), (401, 300)])
    assert seen == []


def test_press_on_edge_still_drags_edge_not_image(canvas):
    seen = _count_drag_outs(canvas)
    drag_edge(canvas, "right", 40)
    assert seen == []
    assert canvas.edges == Edges(right=40)


def test_press_outside_image_does_nothing(canvas):
    seen = _count_drag_outs(canvas)
    mouse_drag(canvas, [(50, 50), (150, 150)])
    assert seen == []


# --- leaving, other buttons, no image ---------------------------------------------


def _leave(canvas):
    QApplication.sendEvent(canvas, QEvent(QEvent.Leave))


def test_leave_clears_hover(canvas):
    send_mouse(canvas, QEvent.MouseMove, (600, 300))
    assert canvas.hovered_edge == "right"
    _leave(canvas)
    assert canvas.hovered_edge is None
    assert canvas.cursor().shape() == Qt.ArrowCursor


def test_leave_mid_drag_keeps_dragged_edge(canvas):
    drag_edge(canvas, "right", 40, release=False)
    _leave(canvas)
    assert canvas.hovered_edge == "right"
    assert canvas.is_dragging
    send_mouse(canvas, QEvent.MouseButtonRelease, (640, 300), Qt.LeftButton)
    assert canvas.edges == Edges(right=40)


def test_leave_hides_brush_outline(canvas):
    canvas.set_paint_mode(True)
    send_mouse(canvas, QEvent.MouseMove, (400, 300))
    assert canvas._brush_pos is not None
    _leave(canvas)
    assert canvas._brush_pos is None


@pytest.mark.parametrize("button", [Qt.RightButton, Qt.MiddleButton])
def test_other_buttons_do_not_drag_edges_or_image(canvas, button):
    seen = _count_drag_outs(canvas)
    mouse_drag(canvas, [(600, 300), (650, 300)], button=button)
    mouse_drag(canvas, [(400, 300), (450, 350)], button=button)
    assert canvas.edges == Edges()
    assert not canvas.is_dragging
    assert seen == []


def test_other_button_release_does_not_end_edge_drag(canvas):
    drag_edge(canvas, "right", 40, release=False)
    send_mouse(canvas, QEvent.MouseButtonRelease, (640, 300), Qt.RightButton, Qt.LeftButton)
    assert canvas.is_dragging
    send_mouse(canvas, QEvent.MouseButtonRelease, (640, 300), Qt.LeftButton)
    assert not canvas.is_dragging


def test_middle_button_does_not_paint(canvas):
    canvas.set_paint_mode(True)
    mouse_drag(canvas, [(300, 300), (400, 300)], button=Qt.MiddleButton)
    assert canvas.strokes == ()
    assert not canvas.is_dragging


def test_other_button_release_does_not_end_stroke(canvas):
    canvas.set_paint_mode(True)
    finished = []
    canvas.strokeFinished.connect(lambda: finished.append(True))
    mouse_drag(canvas, [(300, 300), (350, 300)], release=False)
    send_mouse(canvas, QEvent.MouseButtonRelease, (350, 300), Qt.RightButton, Qt.LeftButton)
    assert canvas.is_dragging and finished == []
    send_mouse(canvas, QEvent.MouseButtonRelease, (350, 300), Qt.LeftButton)
    assert finished == [True]
    assert len(canvas.strokes) == 1


def test_mouse_on_empty_canvas_does_nothing(qapp):
    c = ImageCanvas()
    c.resize(800, 600)
    c.show()
    qapp.processEvents()
    seen = _count_drag_outs(c)
    mouse_drag(c, [(400, 300), (500, 400)])
    assert c.hovered_edge is None
    assert not c.is_dragging
    assert seen == []
    c.set_paint_mode(True)
    mouse_drag(c, [(400, 300), (500, 400)])
    assert c.strokes == ()
    assert c._brush_pos is None
    c.close()
