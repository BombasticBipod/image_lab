"""Shared pytest fixtures and mouse helpers for the headless GUI tests.

Qt must use the offscreen platform so GUI tests run headless. The environment
variable has to be set before any QApplication exists, hence module level.
"""

import os
from pathlib import Path

import pytest

# Assigned, not setdefault: a QT_QPA_PLATFORM left in the shell must not open real windows.
os.environ["QT_QPA_PLATFORM"] = "offscreen"
# The offscreen platform finds no fonts on Windows and draws text as boxes
# unless it is pointed at the system font folder.
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ["WINDIR"], "Fonts"))

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

ARTIFACTS_DIR = Path(__file__).parent / "_artifacts"

# Outward direction of each side on screen.
OUTWARD = {"left": (-1, 0), "right": (1, 0), "top": (0, -1), "bottom": (0, 1)}


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole test session."""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def artifacts_dir() -> Path:
    """Folder for screenshots written by GUI tests (git-ignored)."""
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    return ARTIFACTS_DIR


# --- mouse helpers ------------------------------------------------------------------


def _point(pos) -> QPointF:
    return QPointF(pos) if isinstance(pos, QPointF) else QPointF(*pos)


def send_mouse(
    widget, kind, pos, button=Qt.NoButton, buttons=Qt.NoButton, mods=Qt.NoModifier
) -> None:
    """Send one synthetic mouse event at `pos` (a QPointF or an (x, y) tuple)."""
    p = _point(pos)
    event = QMouseEvent(kind, p, widget.mapToGlobal(p), button, buttons, mods)
    QApplication.sendEvent(widget, event)


def mouse_drag(widget, points, button=Qt.LeftButton, mods=Qt.NoModifier, release=True) -> None:
    """Hover the first point, press `button`, move through the rest, and optionally release."""
    first, *rest = [_point(p) for p in points]
    send_mouse(widget, QEvent.MouseMove, first, mods=mods)
    send_mouse(widget, QEvent.MouseButtonPress, first, button, button, mods)
    for p in rest:
        send_mouse(widget, QEvent.MouseMove, p, Qt.NoButton, button, mods)
    if release:
        last = rest[-1] if rest else first
        send_mouse(widget, QEvent.MouseButtonRelease, last, button, mods=mods)


def edge_point(canvas, side) -> QPointF:
    """Screen midpoint of `side` of the canvas's output box, where it is now."""
    r = canvas._output_screen_rect()
    return {
        "left": QPointF(r.left(), r.center().y()),
        "right": QPointF(r.right(), r.center().y()),
        "top": QPointF(r.center().x(), r.top()),
        "bottom": QPointF(r.center().x(), r.bottom()),
    }[side]


def drag_edge(canvas, side, image_px, mods=Qt.NoModifier, release=True) -> None:
    """Drag `side` outward by `image_px` image pixels (negative drags inward)."""
    start = edge_point(canvas, side)
    ux, uy = OUTWARD[side]
    end = start + QPointF(ux, uy) * (image_px * canvas.scale)
    mouse_drag(canvas, [start, end], mods=mods, release=release)
