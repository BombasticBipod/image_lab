"""Headless tests for MainWindow."""

import pytest
from PIL import Image
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from image_lab.app import NO_IMAGE_STATUS, MainWindow, status_text
from image_lab.model import Edges

pytestmark = pytest.mark.gui


@pytest.fixture
def window(qapp):
    win = MainWindow()
    win.resize(800, 600)
    win.show()
    qapp.processEvents()
    yield win
    win.close()


@pytest.fixture
def warnings(monkeypatch):
    """Capture QMessageBox.warning calls instead of opening a blocking dialog."""
    calls = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: calls.append(args))
    return calls


def _save_test_image(path, size=(400, 200)):
    img = Image.new("RGBA", size, (30, 140, 200, 255))
    # A transparent corner, so snapshots show the checkerboard behind it.
    img.paste((0, 0, 0, 0), (0, 0, size[0] // 4, size[1] // 4))
    img.save(path)
    return path


def _mime_for(path):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    return mime


def _menu_titles(win):
    return [action.text() for action in win.menuBar().actions()]


def test_window_opens_with_menus(window):
    assert window.windowTitle() == "image_lab"
    assert _menu_titles(window) == ["&File", "&Edit"]


def test_empty_state_snapshot(window, artifacts_dir):
    assert not window.canvas.has_image()
    assert window.grab().save(str(artifacts_dir / "m1_empty_window.png"))


def test_window_closes_cleanly(qapp):
    win = MainWindow()
    win.show()
    qapp.processEvents()
    assert win.close()


def test_load_path_shows_image_centered(window, tmp_path, artifacts_dir):
    path = _save_test_image(tmp_path / "wide.png", size=(2000, 1000))
    assert window.load_path(path)
    assert window.image.size == (2000, 1000)
    assert window.windowTitle() == "wide.png - image_lab"

    canvas = window.canvas
    assert canvas.has_image()
    assert canvas.scale < 1.0
    # Scaled to fit: the image takes at most 80% of the canvas width.
    assert 2000 * canvas.scale <= 0.8 * canvas.width() + 1e-6
    center_x = canvas.origin.x() + canvas.scale * 2000 / 2
    center_y = canvas.origin.y() + canvas.scale * 1000 / 2
    assert center_x == pytest.approx(canvas.width() / 2)
    assert center_y == pytest.approx(canvas.height() / 2)
    assert window.grab().save(str(artifacts_dir / "m2_loaded_wide.png"))


def test_small_image_is_not_upscaled(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "small.png", size=(40, 20)))
    assert window.canvas.scale == 1.0


def test_resize_refits(window, qapp, tmp_path):
    window.load_path(_save_test_image(tmp_path / "wide.png", size=(2000, 1000)))
    before = window.canvas.scale
    window.resize(500, 400)
    qapp.processEvents()
    assert window.canvas.scale < before


def test_bad_file_shows_error_and_keeps_state(window, tmp_path, warnings):
    bad = tmp_path / "broken.png"
    bad.write_bytes(b"not an image")
    assert not window.load_path(bad)
    assert len(warnings) == 1
    assert not window.canvas.has_image()


def test_drag_enter_accepts_image_rejects_other(window, tmp_path):
    for name, accepted in [("photo.png", True), ("notes.txt", False)]:
        # Events don't own their QMimeData; keep a Python reference alive.
        mime = _mime_for(tmp_path / name)
        event = QDragEnterEvent(QPoint(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        window.dragEnterEvent(event)
        assert event.isAccepted() == accepted, name


def test_drop_loads_image(window, tmp_path):
    path = _save_test_image(tmp_path / "dropped.png")
    mime = _mime_for(path)
    event = QDropEvent(QPointF(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    window.dropEvent(event)
    assert window.image_path == path
    assert window.canvas.has_image()


def test_open_dialog_loads_selected_file(window, tmp_path, monkeypatch):
    path = _save_test_image(tmp_path / "chosen.png")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))
    window.open_action.trigger()
    assert window.image_path == path


def test_status_text_format():
    text = status_text((1920, 1080), Edges(left=40, top=0, right=-120, bottom=40))
    assert text == "Original 1920×1080  |  L +40  T 0  R -120  B +40  |  Output 1840×1120"


def test_status_bar_tracks_image_and_edges(window, tmp_path):
    assert window.status_label.text() == NO_IMAGE_STATUS
    window.load_path(_save_test_image(tmp_path / "s.png", size=(400, 200)))
    assert window.status_label.text() == status_text((400, 200), Edges())

    # Drag the right edge outward; the status bar follows the canvas edges.
    canvas = window.canvas
    r = canvas._output_screen_rect()
    start = QPointF(r.right(), r.center().y())
    end = start + QPointF(50 * canvas.scale, 0)
    for kind, pos, button, buttons in [
        (QEvent.MouseMove, start, Qt.NoButton, Qt.NoButton),
        (QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton),
        (QEvent.MouseMove, end, Qt.NoButton, Qt.LeftButton),
        (QEvent.MouseButtonRelease, end, Qt.LeftButton, Qt.NoButton),
    ]:
        event = QMouseEvent(kind, pos, canvas.mapToGlobal(pos), button, buttons, Qt.NoModifier)
        QApplication.sendEvent(canvas, event)
    assert canvas.edges == Edges(right=50)
    assert window.status_label.text() == status_text((400, 200), Edges(right=50))


def test_open_dialog_cancel_does_nothing(window, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    window.open_action.trigger()
    assert not window.canvas.has_image()
