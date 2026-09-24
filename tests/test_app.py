"""Headless tests for MainWindow."""

import threading
import time
from io import BytesIO

import pytest
from conftest import drag_edge, edge_point, mouse_drag, send_mouse
from PIL import Image
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QImage, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QFileDialog,
    QLineEdit,
    QMessageBox,
    QToolButton,
)

import image_lab.app as app_module
from image_lab.app import COLOR_DIALOG_OPTIONS, NO_IMAGE_STATUS, MainWindow, fill_label, status_text
from image_lab.files import png_bytes
from image_lab.model import Edges, Transform

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def out_dir(tmp_path, monkeypatch):
    """Point the default export folder at a temp folder so tests never touch the real out/."""
    folder = tmp_path / "out"
    monkeypatch.setattr(app_module, "OUT_DIR", folder)
    return folder


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
    assert _menu_titles(window) == ["&File", "&Edit", "&Image"]


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


def test_bad_file_keeps_current_image_and_edits(window, tmp_path, warnings):
    good = _save_test_image(tmp_path / "good.png", size=(400, 200))
    window.load_path(good)
    drag_edge(window.canvas, "left", 20)
    bad = tmp_path / "broken.png"
    bad.write_bytes(b"not an image")
    assert not window.load_path(bad)
    assert len(warnings) == 1
    assert window.image_path == good
    assert window.windowTitle() == "good.png - image_lab"
    assert window.canvas.edges == Edges(left=20)
    assert window.undo_action.isEnabled()


def test_decompression_bomb_shows_error(window, tmp_path, warnings, monkeypatch):
    path = _save_test_image(tmp_path / "huge.png", size=(400, 200))
    # Pillow raises DecompressionBombError above twice this many pixels.
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    assert not window.load_path(path)
    assert len(warnings) == 1
    assert not window.canvas.has_image()


def test_drag_enter_accepts_image_rejects_other(window, tmp_path):
    for name, accepted in [("photo.png", True), ("notes.txt", False)]:
        # Events don't own their QMimeData; keep a Python reference alive.
        mime = _mime_for(tmp_path / name)
        event = QDragEnterEvent(QPoint(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        window.dragEnterEvent(event)
        assert event.isAccepted() == accepted, name


def test_non_local_url_is_not_accepted_or_loaded(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png"))
    mime = QMimeData()
    mime.setUrls([QUrl("https://example.com/photo.png")])
    enter = QDragEnterEvent(QPoint(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    window.dragEnterEvent(enter)
    assert not enter.isAccepted()
    drop = QDropEvent(QPointF(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    window.dropEvent(drop)
    assert window.image_path == tmp_path / "a.png"


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
    assert text == (
        "Original 1920×1080  |  L +40  T 0  R -120  B +40  |  Output 1840×1120  |  Fill transparent"
    )


def test_status_bar_tracks_image_and_edges(window, tmp_path):
    assert window.status_label.text() == NO_IMAGE_STATUS
    window.load_path(_save_test_image(tmp_path / "s.png", size=(400, 200)))
    assert window.status_label.text() == status_text((400, 200), Edges())

    # Drag the right edge outward; the status bar follows the canvas edges.
    drag_edge(window.canvas, "right", 50)
    assert window.canvas.edges == Edges(right=50)
    assert window.status_label.text() == status_text((400, 200), Edges(right=50))


def test_open_dialog_cancel_does_nothing(window, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    window.open_action.trigger()
    assert not window.canvas.has_image()


# --- saving -------------------------------------------------------------------


def _fake_save_dialog(monkeypatch, path, chosen_filter="PNG (*.png)"):
    """Replace the save dialog; record the default path it was offered."""
    offered = {}

    def fake(parent, caption, directory, filters, selected):
        offered.update(directory=directory, filters=filters, selected=selected)
        return (str(path), chosen_filter)

    monkeypatch.setattr(QFileDialog, "getSaveFileName", fake)
    return offered


def test_save_disabled_until_image_loaded(window, tmp_path):
    assert not window.save_as_action.isEnabled()
    window.load_path(_save_test_image(tmp_path / "a.png"))
    assert window.save_as_action.isEnabled()


def test_save_dialog_default_name_and_filters(window, tmp_path, monkeypatch, out_dir):
    window.load_path(_save_test_image(tmp_path / "photo.png"))
    offered = _fake_save_dialog(monkeypatch, "")  # user cancels
    window.save_as_action.trigger()
    assert offered["directory"] == str(out_dir / "photo_edited.png")
    assert offered["filters"].split(";;") == [
        "PNG (*.png)",
        "JPEG (*.jpg *.jpeg)",
        "WebP (*.webp)",
        "BMP (*.bmp)",
    ]


@pytest.mark.parametrize(
    "chosen_filter, typed, expected_name, expected_format",
    [
        ("PNG (*.png)", "out.png", "out.png", "PNG"),
        ("JPEG (*.jpg *.jpeg)", "out", "out.jpg", "JPEG"),
        ("WebP (*.webp)", "out", "out.webp", "WEBP"),
        ("BMP (*.bmp)", "out.bmp", "out.bmp", "BMP"),
        ("PNG (*.png)", "out.jpeg", "out.jpeg", "JPEG"),  # typed extension wins
    ],
)
def test_export_size_matches_status_bar(
    window, tmp_path, monkeypatch, chosen_filter, typed, expected_name, expected_format
):
    window.load_path(_save_test_image(tmp_path / "src.png", size=(400, 200)))
    # Set edges through a real drag so the status bar reflects them.
    drag_edge(window.canvas, "bottom", 30)
    assert "Output 400×230" in window.status_label.text()

    _fake_save_dialog(monkeypatch, tmp_path / typed, chosen_filter)
    window.save_as_action.trigger()
    saved = tmp_path / expected_name
    with Image.open(saved) as img:
        assert img.format == expected_format
        assert f"Output {img.width}×{img.height}" in window.status_label.text()
    assert window.statusBar().currentMessage() == f"Saved to {saved}"


def test_save_failure_shows_error(window, tmp_path, monkeypatch):
    window.load_path(_save_test_image(tmp_path / "src.png"))
    errors = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: errors.append(args))
    # A directory that doesn't exist makes Pillow raise OSError.
    assert not window.save_to(tmp_path / "missing_dir" / "out.png")
    assert len(errors) == 1


# --- reset, enabled states, padding fill ----------------------------------------


def test_image_actions_disabled_until_loaded(window, tmp_path):
    actions = [
        window.quick_save_action,
        window.save_as_action,
        window.copy_action,
        window.reset_action,
        window.fill_action,
        window.transparent_action,
        window.rotate_left_action,
        window.rotate_right_action,
        window.flip_h_action,
        window.flip_v_action,
        window.remove_bg_action,
        window.paint_action,
        window.brush_smaller_action,
        window.brush_larger_action,
    ]
    assert not any(a.isEnabled() for a in actions)
    assert not window.save_button.isEnabled()
    assert window.open_action.isEnabled()
    assert window.paste_action.isEnabled()
    window.load_path(_save_test_image(tmp_path / "a.png"))
    assert all(a.isEnabled() for a in actions)
    assert window.save_button.isEnabled()


def test_reset_restores_zero_edges_and_refits(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    origin_before = window.canvas.origin
    drag_edge(window.canvas, "left", 80)
    assert window.canvas.edges == Edges(left=80)
    assert window.reset_action.shortcut().toString() == "Ctrl+R"
    window.reset_action.trigger()
    assert window.canvas.edges == Edges()
    assert window.canvas.origin == origin_before
    assert window.status_label.text() == status_text((400, 200), Edges())


def test_fill_label():
    assert fill_label((1, 2, 3, 0)) == "transparent"
    assert fill_label((255, 128, 0, 255)) == "#FF8000"
    assert fill_label((255, 128, 0, 64)) == "#FF800040"


def _fake_color_dialog(monkeypatch, color):
    calls = []

    def fake(initial, parent, title, options):
        calls.append((initial, options))
        return color

    monkeypatch.setattr(QColorDialog, "getColor", fake)
    return calls


def test_choose_fill_sets_preview_status_and_export(window, tmp_path, monkeypatch):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    calls = _fake_color_dialog(monkeypatch, QColor("#FF8000"))
    window.fill_action.trigger()
    assert calls[0][1] == COLOR_DIALOG_OPTIONS
    assert window.canvas.fill == (255, 128, 0, 255)
    assert window.status_label.text().endswith("Fill #FF8000")

    drag_edge(window.canvas, "top", 20)
    out = tmp_path / "filled.png"
    assert window.save_to(out)
    with Image.open(out) as saved:
        assert saved.convert("RGBA").getpixel((5, 5)) == (255, 128, 0, 255)


def test_choose_fill_cancel_keeps_fill(window, tmp_path, monkeypatch):
    window.load_path(_save_test_image(tmp_path / "a.png"))
    _fake_color_dialog(monkeypatch, QColor())  # invalid color = cancelled
    window.fill_action.trigger()
    assert window.canvas.fill == (0, 0, 0, 0)


def test_transparent_action_clears_fill(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png"))
    window.set_fill((10, 20, 30, 255))
    window.transparent_action.trigger()
    assert window.canvas.fill[3] == 0
    assert window.status_label.text().endswith("Fill transparent")


def test_fill_survives_reset_and_new_image(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png"))
    window.set_fill((10, 20, 30, 255))
    window.reset_action.trigger()
    window.load_path(_save_test_image(tmp_path / "b.png"))
    assert window.canvas.fill == (10, 20, 30, 255)


def test_color_dialog_has_hex_field(qapp):
    # The Qt color dialog (non-native) includes a hex line edit; confirm it exists
    # with our options so hex entry is available to the user.
    dialog = QColorDialog()
    dialog.setOptions(COLOR_DIALOG_OPTIONS)
    edits = dialog.findChildren(QLineEdit)
    dialog.setCurrentColor(QColor("#12AB34"))
    assert any(e.text().upper() == "#12AB34" for e in edits)


def test_fill_snapshot(window, tmp_path, artifacts_dir):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    drag_edge(window.canvas, "left", 60)
    drag_edge(window.canvas, "bottom", 40)
    window.set_fill((255, 128, 0, 255))
    assert window.grab().save(str(artifacts_dir / "m6_orange_fill.png"))


# --- Save button and out folder ---------------------------------------------------


def test_save_button_is_split_quick_save_with_save_as_arrow(window):
    button = window.save_button
    assert button.defaultAction() is window.quick_save_action
    assert button.popupMode() == QToolButton.MenuButtonPopup
    assert button.menu().actions() == [window.save_as_action]


def test_save_shortcuts(window):
    assert window.quick_save_action.shortcut().toString() == "Ctrl+S"
    assert window.save_as_action.shortcut().toString() == "Ctrl+Shift+S"


def test_quick_save_writes_numbered_files_in_out(window, tmp_path, out_dir):
    window.load_path(_save_test_image(tmp_path / "cat.png", size=(400, 200)))
    drag_edge(window.canvas, "left", 25)
    assert not out_dir.exists()  # created on first save

    window.save_button.click()
    window.quick_save_action.trigger()
    first, second = out_dir / "cat_edited.png", out_dir / "cat_edited_2.png"
    assert first.exists() and second.exists()
    with Image.open(first) as img:
        assert img.size == (425, 200)
    assert window.statusBar().currentMessage() == f"Saved to {second}"


def test_quick_save_error_when_out_folder_cannot_be_made(window, tmp_path, monkeypatch):
    window.load_path(_save_test_image(tmp_path / "cat.png"))
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where a folder should be")
    monkeypatch.setattr(app_module, "OUT_DIR", blocker / "out")
    errors = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: errors.append(args))
    window.quick_save()
    assert len(errors) == 1
    assert not (blocker / "out").exists()


def test_quick_save_disabled_without_image(window, out_dir):
    assert not window.quick_save_action.isEnabled()
    assert not window.save_button.isEnabled()
    window.quick_save()
    assert not out_dir.exists()


def test_toolbar_snapshot(window, tmp_path, artifacts_dir):
    window.load_path(_save_test_image(tmp_path / "a.png"))
    assert window.grab().save(str(artifacts_dir / "p2a_toolbar_save_button.png"))


# --- undo / redo ------------------------------------------------------------------


def test_undo_redo_shortcuts(window):
    # The shortcut is whatever Qt resolves for the platform (Ctrl+Y on Windows,
    # Ctrl+Shift+Z on Linux), not a hardcoded key.
    assert window.undo_action.shortcut() == QKeySequence(QKeySequence.Undo)
    assert window.redo_action.shortcut() == QKeySequence(QKeySequence.Redo)


def test_undo_redo_drags(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    assert not window.undo_action.isEnabled()
    drag_edge(window.canvas, "right", 40)
    drag_edge(window.canvas, "top", -30)
    assert window.canvas.edges == Edges(right=40, top=-30)

    window.undo_action.trigger()
    assert window.canvas.edges == Edges(right=40)
    assert window.status_label.text() == status_text((400, 200), Edges(right=40))
    window.undo_action.trigger()
    assert window.canvas.edges == Edges()
    assert not window.undo_action.isEnabled()

    window.redo_action.trigger()
    window.redo_action.trigger()
    assert window.canvas.edges == Edges(right=40, top=-30)
    assert not window.redo_action.isEnabled()


def test_one_drag_is_one_undo_step(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    canvas = window.canvas
    start = edge_point(canvas, "right")
    # Many moves while the button is held, then one release.
    mouse_drag(canvas, [start + QPointF(step * 10, 0) for step in range(6)])
    assert canvas.edges.right > 0
    window.undo_action.trigger()
    assert canvas.edges == Edges()


def test_drag_without_change_adds_no_step(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png"))
    drag_edge(window.canvas, "left", 0)
    assert not window.undo_action.isEnabled()


def test_reset_ignored_during_drag(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    drag_edge(window.canvas, "left", 20)
    drag_edge(window.canvas, "right", 15, release=False)
    assert window.canvas.is_dragging
    window.reset_action.trigger()
    assert window.canvas.is_dragging
    assert window.canvas.edges == Edges(left=20, right=15)
    send_mouse(
        window.canvas, QEvent.MouseButtonRelease, edge_point(window.canvas, "right"), Qt.LeftButton
    )
    # The ignored reset recorded no step: undo goes back to before the second drag.
    window.undo()
    assert window.canvas.edges == Edges(left=20)


def test_undo_reset_and_fill(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png"))
    drag_edge(window.canvas, "left", 20)
    window.set_fill((255, 0, 0, 255))
    window.reset_action.trigger()
    assert window.canvas.edges == Edges()

    window.undo_action.trigger()  # undo reset
    assert window.canvas.edges == Edges(left=20)
    assert window.canvas.fill == (255, 0, 0, 255)
    window.undo_action.trigger()  # undo fill
    assert window.canvas.fill[3] == 0
    assert window.canvas.edges == Edges(left=20)
    assert window.status_label.text().endswith("Fill transparent")


def test_new_edit_after_undo_clears_redo(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png"))
    drag_edge(window.canvas, "left", 20)
    window.undo_action.trigger()
    assert window.redo_action.isEnabled()
    drag_edge(window.canvas, "bottom", 10)
    assert not window.redo_action.isEnabled()


def test_load_clears_history(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png"))
    drag_edge(window.canvas, "left", 20)
    window.load_path(_save_test_image(tmp_path / "b.png"))
    assert not window.undo_action.isEnabled()
    window.undo_action.trigger()
    assert window.canvas.edges == Edges()


def test_undo_ignored_during_drag(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    drag_edge(window.canvas, "left", 20)
    canvas = window.canvas
    drag_edge(canvas, "right", 15, release=False)
    assert canvas.is_dragging
    window.undo_action.trigger()
    assert canvas.edges.left == 20 and canvas.edges.right > 0


# --- copy / paste -----------------------------------------------------------------


@pytest.fixture
def clipboard(qapp):
    board = QApplication.clipboard()
    board.clear()
    yield board
    board.clear()


def test_copy_paste_shortcuts(window):
    assert window.copy_action.shortcut().toString() == "Ctrl+C"
    assert window.paste_action.shortcut().toString() == "Ctrl+V"
    assert not window.copy_action.isEnabled()
    assert window.paste_action.isEnabled()


def test_copy_puts_edited_image_on_clipboard(window, tmp_path, clipboard):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    drag_edge(window.canvas, "left", 30)
    window.copy_action.trigger()

    mime = clipboard.mimeData()
    qimg = QImage(mime.imageData())
    assert (qimg.width(), qimg.height()) == (430, 200)
    # The PNG data keeps the transparent padding.
    png = Image.open(BytesIO(mime.data("image/png").data()))
    assert png.size == (430, 200)
    assert png.convert("RGBA").getpixel((0, 100))[3] == 0
    assert window.statusBar().currentMessage() == "Copied 430×200 image"


def test_paste_image_data_replaces_image(window, tmp_path, clipboard, out_dir):
    window.load_path(_save_test_image(tmp_path / "a.png"))
    drag_edge(window.canvas, "left", 30)
    qimg = QImage(60, 40, QImage.Format_ARGB32)
    qimg.fill(QColor(0, 200, 0))
    clipboard.setImage(qimg)

    window.paste_action.trigger()
    assert window.image.size == (60, 40)
    assert window.image_path is None
    assert window.windowTitle() == "pasted - image_lab"
    assert window.canvas.edges == Edges()
    assert not window.undo_action.isEnabled()

    window.quick_save_action.trigger()
    assert (out_dir / "pasted_edited.png").exists()


def test_paste_prefers_png_data_for_transparency(window, clipboard):
    mime = QMimeData()
    mime.setData("image/png", png_bytes(Image.new("RGBA", (4, 3), (9, 9, 9, 0))))
    clipboard.setMimeData(mime)
    window.paste_action.trigger()
    assert window.image.size == (4, 3)
    assert window.image.getpixel((0, 0)) == (9, 9, 9, 0)


def test_paste_copied_file_loads_it(window, tmp_path, clipboard):
    path = _save_test_image(tmp_path / "copied.png")
    clipboard.setMimeData(_mime_for(path))
    window.paste_action.trigger()
    assert window.image_path == path
    assert window.windowTitle() == "copied.png - image_lab"


def test_paste_without_image_does_nothing(window, tmp_path, clipboard):
    window.load_path(_save_test_image(tmp_path / "a.png"))
    clipboard.setText("just text")
    window.paste_action.trigger()
    assert window.image_path == tmp_path / "a.png"
    assert window.statusBar().currentMessage() == "Clipboard has no image"


def test_paste_falls_back_to_bitmap_when_png_data_is_corrupt(window, clipboard):
    mime = QMimeData()
    mime.setData("image/png", b"not a png")
    qimg = QImage(5, 7, QImage.Format_ARGB32)
    qimg.fill(QColor(0, 200, 0))
    mime.setImageData(qimg)
    clipboard.setMimeData(mime)
    window.paste_action.trigger()
    assert window.image.size == (5, 7)
    assert window.image.getpixel((0, 0)) == (0, 200, 0, 255)


def test_copy_then_paste_round_trip(window, tmp_path, clipboard):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    drag_edge(window.canvas, "bottom", 50)
    window.copy_action.trigger()
    window.paste_action.trigger()
    assert window.image.size == (400, 250)
    assert window.image.getpixel((10, 240))[3] == 0


# --- drag out -----------------------------------------------------------------------


@pytest.fixture
def captured_drags(window, monkeypatch):
    """Record QDrag objects instead of running the blocking drag loop."""
    drags = []
    monkeypatch.setattr(window, "_exec_drag", lambda drag: drags.append(drag))
    return drags


def _drag_out(window):
    """Press inside the image and move far enough to start a drag-out."""
    center = window.canvas._output_screen_rect().center()
    mouse_drag(window.canvas, [center, center + QPointF(40, 40)])


def test_drag_out_offers_png_file_and_image(window, tmp_path, out_dir, captured_drags):
    window.load_path(_save_test_image(tmp_path / "cat.png", size=(400, 200)))
    drag_edge(window.canvas, "top", 30)
    _drag_out(window)

    assert len(captured_drags) == 1
    mime = captured_drags[0].mimeData()
    path = out_dir / "cat_edited.png"
    assert [u.toLocalFile() for u in mime.urls()] == [path.as_posix()]
    with Image.open(path) as img:
        assert img.format == "PNG"
        assert img.size == (400, 230)
    assert mime.hasImage()
    assert not captured_drags[0].pixmap().isNull()


def test_repeated_drag_out_reuses_file_until_edited(window, tmp_path, out_dir, captured_drags):
    window.load_path(_save_test_image(tmp_path / "cat.png"))
    _drag_out(window)
    _drag_out(window)
    assert sorted(p.name for p in out_dir.iterdir()) == ["cat_edited.png"]

    drag_edge(window.canvas, "left", 10)
    _drag_out(window)
    assert sorted(p.name for p in out_dir.iterdir()) == ["cat_edited.png", "cat_edited_2.png"]
    urls = captured_drags[-1].mimeData().urls()
    assert urls[0].toLocalFile().endswith("cat_edited_2.png")


def test_drag_out_starts_no_drag_when_save_fails(
    window, tmp_path, out_dir, captured_drags, monkeypatch
):
    window.load_path(_save_test_image(tmp_path / "cat.png"))
    errors = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: errors.append(args))

    def failing_save(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(app_module, "save_image", failing_save)
    _drag_out(window)
    assert captured_drags == []
    assert len(errors) == 1


def test_drop_from_own_drag_is_ignored(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png"))
    other = _save_test_image(tmp_path / "other.png")
    mime = _mime_for(other)

    class OwnDrop(QDropEvent):
        def source(self):
            return window.canvas

    event = OwnDrop(QPointF(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    window.dropEvent(event)
    assert window.image_path == tmp_path / "a.png"


# --- rotate and flip ------------------------------------------------------------


def _pixel_image(path):
    """A 4x2 image with four distinct colors, so orientation is checkable in exports."""
    img = Image.new("RGBA", (4, 2), (0, 0, 255, 255))
    img.putpixel((0, 0), (255, 0, 0, 255))
    img.putpixel((3, 0), (0, 255, 0, 255))
    img.putpixel((0, 1), (255, 255, 0, 255))
    img.save(path)
    return path


def test_orientation_shortcuts_and_menu(window):
    assert window.rotate_left_action.shortcut().toString() == "Ctrl+["
    assert window.rotate_right_action.shortcut().toString() == "Ctrl+]"
    image_menu = window.menuBar().actions()[2].menu()
    assert image_menu.actions()[:4] == window._orient_actions


def test_rotate_right_turns_export_and_edges(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    drag_edge(window.canvas, "left", 30)
    window.rotate_right_action.trigger()
    assert window.canvas.transform == Transform(90)
    # The padding that was on the left is now on top.
    assert window.canvas.edges == Edges(top=30)
    assert window.edited_image().size == (200, 430)
    assert window.status_label.text() == status_text(
        (400, 200), Edges(top=30), transform=Transform(90)
    )
    assert "Output 200×430" in window.status_label.text()


def test_rotate_and_flip_pixels(window, tmp_path):
    window.load_path(_pixel_image(tmp_path / "p.png"))
    red, green, yellow = (255, 0, 0, 255), (0, 255, 0, 255), (255, 255, 0, 255)
    window.rotate_right()
    out = window.edited_image()
    assert out.size == (2, 4)
    # Turning right puts the bottom-left pixel at the top-left.
    assert out.getpixel((0, 0)) == yellow and out.getpixel((1, 0)) == red
    window.rotate_left()
    window.flip_horizontal()
    out = window.edited_image()
    assert out.getpixel((0, 0)) == green and out.getpixel((3, 0)) == red
    window.flip_horizontal()
    window.flip_vertical()
    out = window.edited_image()
    assert out.getpixel((0, 0)) == yellow and out.getpixel((0, 1)) == red


def test_saved_file_is_rotated(window, tmp_path):
    window.load_path(_pixel_image(tmp_path / "p.png"))
    window.rotate_left()
    path = tmp_path / "turned.png"
    assert window.save_to(path)
    with Image.open(path) as img:
        assert img.size == (2, 4)
        # Turning left puts the top-right pixel at the top-left.
        assert img.getpixel((0, 0)) == (0, 255, 0, 255)


def test_edge_drag_after_rotate_uses_view_pixels(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    window.rotate_right()
    drag_edge(window.canvas, "bottom", 50)
    assert window.canvas.edges == Edges(bottom=50)
    assert window.edited_image().size == (200, 450)


def test_orientation_undo_redo_and_reset(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    drag_edge(window.canvas, "left", 20)
    window.rotate_right()
    window.flip_horizontal()
    window.undo()
    assert window.canvas.transform == Transform(90)
    assert window.canvas.edges == Edges(top=20)
    window.undo()
    assert window.canvas.transform == Transform()
    assert window.canvas.edges == Edges(left=20)
    window.redo()
    assert window.canvas.transform == Transform(90)
    window.reset_action.trigger()
    assert window.canvas.transform == Transform()
    assert window.canvas.edges == Edges()
    window.undo()
    assert window.canvas.transform == Transform(90)


def test_new_image_loads_upright(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png"))
    window.rotate_right()
    window.load_path(_save_test_image(tmp_path / "b.png"))
    assert window.canvas.transform == Transform()
    assert not window.undo_action.isEnabled()


def test_rotate_ignored_during_drag(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png"))
    canvas = window.canvas
    mouse_drag(canvas, [edge_point(canvas, "left")], release=False)
    assert canvas.is_dragging
    window.rotate_right()
    assert canvas.transform == Transform()


def test_pixmap_is_converted_once_per_load(window, tmp_path, qapp, monkeypatch):
    # Invariant 6: turns, free angles, drags, paint, undo and repaints reuse the load's pixmap.
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    pixmap = window.canvas._pixmap
    conversions = []
    monkeypatch.setattr(app_module, "pil_to_qimage", lambda img: conversions.append(img))
    window.rotate_right()
    window.flip_horizontal()
    window.angle_box.setValue(20)
    drag_edge(window.canvas, "left", 30)
    window.set_paint_mode(True)
    _paint(window.canvas, [_screen(window.canvas, 50, 50)])
    window.undo()
    window.redo()
    window.reset_action.trigger()
    window.canvas.repaint()
    qapp.processEvents()
    assert window.canvas._pixmap is pixmap
    assert conversions == []


def test_rotate_flip_snapshots(window, tmp_path, artifacts_dir):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    drag_edge(window.canvas, "right", 60)
    window.set_fill((255, 128, 0, 255))
    window.rotate_right()
    assert window.grab().save(str(artifacts_dir / "p3a_rotated_right.png"))
    window.flip_vertical()
    assert window.grab().save(str(artifacts_dir / "p3a_rotated_flipped_v.png"))


# --- free angle -----------------------------------------------------------------


def test_angle_box_disabled_until_loaded(window, tmp_path):
    assert not window.angle_box.isEnabled()
    window.load_path(_save_test_image(tmp_path / "a.png"))
    assert window.angle_box.isEnabled()
    assert window.angle_box.value() == 0


def test_angle_box_rotates_export(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    window.angle_box.setValue(30)
    assert window.canvas.transform == Transform(30)
    # 400*cos30 + 200*sin30 = 446.4; 400*sin30 + 200*cos30 = 373.2
    assert window.edited_image().size == (447, 374)
    assert "Output 447×374" in window.status_label.text()


def test_angle_box_follows_turns_undo_and_load(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png"))
    window.angle_box.setValue(12.5)
    window.rotate_right()
    assert window.angle_box.value() == 102.5
    window.flip_horizontal()
    assert window.angle_box.value() == -102.5
    window.undo()
    assert window.angle_box.value() == 102.5
    window.undo()
    assert window.angle_box.value() == 12.5
    window.undo()
    assert window.angle_box.value() == 0
    window.redo()
    window.load_path(_save_test_image(tmp_path / "b.png"))
    assert window.angle_box.value() == 0


def test_angle_change_is_one_undo_step_and_keeps_mirror(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png"))
    window.flip_horizontal()
    window.angle_box.setValue(-15)
    assert window.canvas.transform == Transform(-15, mirror=True)
    window.undo()
    assert window.canvas.transform == Transform(0, mirror=True)


def test_angle_change_clamps_deep_crops(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    window.rotate_right()  # view is 200x400
    drag_edge(window.canvas, "bottom", -350)
    assert window.canvas.edges == Edges(bottom=-350)
    # Back at 0 degrees the view is only 200 tall, so the crop shrinks to 199.
    window.angle_box.setValue(0)
    assert window.canvas.edges == Edges(bottom=-199)


def test_angle_box_snaps_back_during_drag(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    drag_edge(window.canvas, "right", 15, release=False)
    window.angle_box.setValue(30)
    assert window.canvas.transform == Transform()
    assert window.angle_box.value() == 0
    send_mouse(
        window.canvas, QEvent.MouseButtonRelease, edge_point(window.canvas, "right"), Qt.LeftButton
    )
    # Only the drag was recorded.
    window.undo()
    assert window.canvas.edges == Edges()
    assert not window.undo_action.isEnabled()


def test_free_angle_snapshot(window, tmp_path, artifacts_dir):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    drag_edge(window.canvas, "left", 40)
    window.set_fill((255, 128, 0, 255))
    window.angle_box.setValue(30)
    assert window.grab().save(str(artifacts_dir / "p3b_free_angle_30.png"))


# --- paint transparency -------------------------------------------------------------


def _paint(canvas, points, button=Qt.LeftButton):
    """Paint through screen points with synthetic mouse events."""
    mouse_drag(canvas, points, button=button)


def _screen(canvas, x, y):
    """Screen point of view-image point (x, y)."""
    o, s = canvas.origin, canvas.scale
    return (o.x() + s * x, o.y() + s * y)


def test_paint_action_and_brush_controls(window, tmp_path):
    assert window.paint_action.shortcut().toString() == "B"
    assert window.paint_action.isCheckable()
    assert not window.paint_action.isEnabled()
    window.load_path(_save_test_image(tmp_path / "a.png"))
    assert window.paint_action.isEnabled()
    window.paint_action.trigger()
    assert window.canvas.paint_mode
    window.brush_box.setValue(20)
    assert window.canvas.brush_size == 20
    window.brush_larger_action.trigger()
    assert window.brush_box.value() == 25 and window.canvas.brush_size == 25
    window.brush_smaller_action.trigger()
    assert window.canvas.brush_size == 20
    window.brush_box.setValue(1)
    window.brush_larger()
    assert window.canvas.brush_size == 2
    window.paint_action.trigger()
    assert not window.canvas.paint_mode


def test_paint_stroke_erases_in_export(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    window.set_paint_mode(True)
    window.brush_box.setValue(20)
    canvas = window.canvas
    _paint(canvas, [_screen(canvas, 200, 100), _screen(canvas, 300, 100)])
    assert len(canvas.strokes) == 1
    stroke = canvas.strokes[0]
    assert stroke.erase and stroke.radius == 10
    assert stroke.points[0] == pytest.approx((200, 100), abs=0.01)
    out = window.edited_image()
    assert out.getpixel((250, 100)) == (30, 140, 200, 0)  # RGB kept under alpha 0
    assert out.getpixel((250, 130))[3] == 255
    assert canvas.edges == Edges()  # painting never moves edges


def test_right_drag_restores(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    window.set_paint_mode(True)
    canvas = window.canvas
    _paint(canvas, [_screen(canvas, 100, 100), _screen(canvas, 300, 100)])
    _paint(canvas, [_screen(canvas, 200, 100)], button=Qt.RightButton)
    assert [s.erase for s in canvas.strokes] == [True, False]
    out = window.edited_image()
    assert out.getpixel((200, 100))[3] == 255
    assert out.getpixel((120, 100))[3] == 0


def test_paint_after_rotate_uses_original_pixels(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    window.rotate_right()  # view is 200x400; view (x, y) shows original (y, 199 - x)
    window.set_paint_mode(True)
    canvas = window.canvas
    _paint(canvas, [_screen(canvas, 50.5, 300.5)])
    assert canvas.strokes[0].points[0] == pytest.approx((300.5, 149.5), abs=0.01)
    window.rotate_left()
    assert window.edited_image().getpixel((300, 149))[3] == 0


def test_paint_mode_disables_edges_and_drag_out(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    requests = []
    window.canvas.dragOutRequested.connect(lambda: requests.append(1))
    window.set_paint_mode(True)
    drag_edge(window.canvas, "left", 50)
    assert window.canvas.edges == Edges()
    assert window.canvas.hovered_edge is None
    assert not requests
    assert window.canvas.cursor().shape() == Qt.CrossCursor


def test_paint_undo_redo_and_reset(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    window.set_paint_mode(True)
    canvas = window.canvas
    _paint(canvas, [_screen(canvas, 100, 100)])
    _paint(canvas, [_screen(canvas, 300, 100)])
    assert len(canvas.strokes) == 2
    window.undo()
    assert len(canvas.strokes) == 1
    assert window.edited_image().getpixel((300, 100))[3] == 255
    window.redo()
    assert len(canvas.strokes) == 2
    window.reset_action.trigger()
    assert canvas.strokes == ()
    window.undo()
    assert len(canvas.strokes) == 2


def test_undo_ignored_mid_stroke(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    window.set_paint_mode(True)
    canvas = window.canvas
    _paint(canvas, [_screen(canvas, 100, 100)])
    p = QPointF(*_screen(canvas, 300, 100))
    send_mouse(canvas, QEvent.MouseButtonPress, p, Qt.LeftButton, Qt.LeftButton)
    assert canvas.is_dragging
    window.undo()
    window.set_paint_mode(False)
    assert canvas.paint_mode
    assert window.paint_action.isChecked()
    send_mouse(canvas, QEvent.MouseButtonRelease, p, Qt.LeftButton)
    assert len(canvas.strokes) == 2


def test_new_image_clears_paint(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png"))
    window.set_paint_mode(True)
    _paint(window.canvas, [_screen(window.canvas, 50, 50)])
    window.load_path(_save_test_image(tmp_path / "b.png"))
    assert window.canvas.strokes == ()


def test_saved_painted_png(window, tmp_path, out_dir):
    window.load_path(_save_test_image(tmp_path / "cat.png", size=(400, 200)))
    window.set_paint_mode(True)
    _paint(window.canvas, [_screen(window.canvas, 200, 100)])
    window.quick_save()
    with Image.open(out_dir / "cat_edited.png") as img:
        assert img.getpixel((200, 100)) == (30, 140, 200, 0)


def test_paint_snapshot(window, tmp_path, artifacts_dir):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    window.angle_box.setValue(15)
    window.set_paint_mode(True)
    window.brush_box.setValue(50)
    canvas = window.canvas
    _paint(
        canvas, [_screen(canvas, 150, 150), _screen(canvas, 250, 200), _screen(canvas, 350, 150)]
    )
    _paint(canvas, [_screen(canvas, 250, 200)], button=Qt.RightButton)
    hover = QPointF(*_screen(canvas, 330, 280))
    send_mouse(canvas, QEvent.MouseMove, hover)
    assert window.grab().save(str(artifacts_dir / "p3c_paint_half_transparent.png"))


# --- background removal -----------------------------------------------------------


class _FakeRemover:
    """Stands in for `matting.ProcessRemover`: keeps the left half, removes the right half.
    With `gate`, `predict` waits until the test sets it, so a run can be caught midway;
    `cancel` releases the gate and makes the run raise `Cancelled`, like the real one."""

    def __init__(self):
        self.path = None
        self.gate = None
        self.error = None
        self.calls = 0
        self.cancels = 0
        self.closed = False
        self._cancelled = False

    def predict(self, img):
        self.calls += 1
        self._cancelled = False
        if self.gate is not None:
            self.gate.wait(5)
        if self._cancelled:
            raise app_module.matting.Cancelled()
        if self.error is not None:
            raise self.error
        matte = Image.new("L", img.size, 0)
        matte.paste(255, (0, 0, img.width // 2, img.height))
        return matte

    def cancel(self):
        self.cancels += 1
        self._cancelled = True
        if self.gate is not None:
            self.gate.set()

    def close(self):
        self.closed = True
        self.cancel()


@pytest.fixture
def remover(window, monkeypatch):
    """A fake remover, with the optional packages and the model reported as present."""
    fake = _FakeRemover()
    window.remover = fake
    monkeypatch.setattr(app_module.matting, "is_installed", lambda: True)
    monkeypatch.setattr(app_module.matting, "has_model", lambda path=None: True)
    return fake


def _finish_removal(window, qapp):
    """Wait for the worker thread, then deliver its queued signal."""
    thread = window._removal_thread
    if thread is not None:
        thread.join(5)
    qapp.processEvents()


def _start_gated_removal(window, remover, tmp_path):
    """Load an opaque image and start a removal that waits for `remover.gate`."""
    remover.gate = threading.Event()
    window.load_path(_opaque_image(tmp_path))
    window.remove_background()
    assert window.is_removing


def _opaque_image(tmp_path, size=(400, 200)):
    path = tmp_path / "opaque.png"
    Image.new("RGBA", size, (30, 140, 200, 255)).save(path)
    return path


def test_remove_background_action_in_image_menu(window):
    image_menu = window.menuBar().actions()[2].menu()
    assert window.remove_bg_action in image_menu.actions()


def test_remove_background_makes_background_transparent(window, qapp, tmp_path, remover):
    window.load_path(_opaque_image(tmp_path))
    window.remove_bg_action.trigger()
    assert window.is_removing
    assert not window.remove_bg_action.isEnabled()
    _finish_removal(window, qapp)
    assert not window.is_removing
    assert window.remove_bg_action.isEnabled()
    assert window.statusBar().currentMessage() == app_module.REMOVED_MESSAGE
    out = window.edited_image()
    assert out.getpixel((50, 100)) == (30, 140, 200, 255)
    # Removed pixels keep their RGB under alpha 0, like painted ones.
    assert out.getpixel((350, 100)) == (30, 140, 200, 0)
    # The original is never modified.
    assert window.image.getpixel((350, 100))[3] == 255


def test_remove_background_runs_on_the_loaded_image(window, qapp, tmp_path, remover):
    seen = []
    remover.predict = lambda img: seen.append(img) or Image.new("L", img.size, 255)
    window.load_path(_opaque_image(tmp_path))
    window.remove_background()
    _finish_removal(window, qapp)
    assert seen == [window.image]


def test_remove_background_is_one_undo_step(window, qapp, tmp_path, remover):
    window.load_path(_opaque_image(tmp_path))
    window.remove_background()
    _finish_removal(window, qapp)
    assert window.canvas.matte is not None
    window.undo()
    assert window.canvas.matte is None
    assert window.edited_image().getpixel((350, 100))[3] == 255
    window.redo()
    assert window.edited_image().getpixel((350, 100))[3] == 0


def test_reset_clears_background_removal(window, qapp, tmp_path, remover):
    window.load_path(_opaque_image(tmp_path))
    window.remove_background()
    _finish_removal(window, qapp)
    window.reset_edits()
    assert window.canvas.matte is None
    assert window.edited_image().getpixel((350, 100))[3] == 255
    window.undo()
    assert window.canvas.matte is not None


def test_restore_brush_brings_back_removed_background(window, qapp, tmp_path, remover):
    window.load_path(_opaque_image(tmp_path))
    window.remove_background()
    _finish_removal(window, qapp)
    window.set_paint_mode(True)
    canvas = window.canvas
    _paint(canvas, [_screen(canvas, 300, 100)], button=Qt.RightButton)
    out = window.edited_image()
    assert out.getpixel((300, 100))[3] == 255
    assert out.getpixel((380, 100))[3] == 0


def test_removal_is_saved_and_follows_orientation(window, qapp, tmp_path, remover):
    window.load_path(_opaque_image(tmp_path))
    window.remove_background()
    _finish_removal(window, qapp)
    window.rotate_right()  # view (x, y) shows original (y, 199 - x)
    path = tmp_path / "turned.png"
    assert window.save_to(path)
    with Image.open(path) as saved:
        assert saved.size == (200, 400)
        assert saved.getpixel((100, 50))[3] == 255  # original (50, 99): kept half
        assert saved.getpixel((100, 350))[3] == 0  # original (350, 99): removed half


def test_second_run_is_blocked_while_one_runs(window, qapp, tmp_path, remover):
    _start_gated_removal(window, remover, tmp_path)
    window.remove_background()
    remover.gate.set()
    _finish_removal(window, qapp)
    assert remover.calls == 1


# --- the lock while a removal runs ----------------------------------------------------


def test_overlay_covers_the_canvas_during_a_run(window, qapp, tmp_path, remover):
    _start_gated_removal(window, remover, tmp_path)
    canvas = window.canvas
    overlay = canvas.busy_overlay
    assert canvas.is_busy
    assert overlay.geometry() == canvas.rect()
    assert overlay.title == app_module.REMOVING_MESSAGE
    assert overlay.detail == app_module.LOCKED_DETAIL
    assert overlay.spinning
    remover.gate.set()
    _finish_removal(window, qapp)
    assert not canvas.is_busy
    assert not overlay.spinning


def test_every_edit_and_export_is_off_during_a_run(window, qapp, tmp_path, remover):
    window.load_path(_opaque_image(tmp_path))
    drag_edge(window.canvas, "left", 10)  # so undo has something to undo
    remover.gate = threading.Event()
    window.remove_background()
    controls = [*window._image_actions, window.angle_box, window.brush_box]
    controls += [window.undo_action, window.redo_action, window.save_button]
    assert not any(c.isEnabled() for c in controls)
    assert window.open_action.isEnabled() and window.paste_action.isEnabled()
    remover.gate.set()
    _finish_removal(window, qapp)
    assert all(a.isEnabled() for a in window._image_actions)
    assert window.angle_box.isEnabled() and window.brush_box.isEnabled()
    assert window.undo_action.isEnabled()
    assert not window.redo_action.isEnabled()


def test_direct_calls_do_nothing_during_a_run(
    window, qapp, tmp_path, remover, out_dir, clipboard, captured_drags
):
    _start_gated_removal(window, remover, tmp_path)
    before = window._edit_state()
    window.quick_save()
    window.copy_image()
    window.start_drag_out()
    window.undo()
    window.reset_edits()
    window.rotate_right()
    window.flip_horizontal()
    window.set_angle(30)
    window.set_fill((255, 0, 0, 255))
    assert window._edit_state() == before
    assert window.angle_box.value() == 0
    assert not out_dir.exists()
    mime = clipboard.mimeData()
    assert mime is None or not mime.hasImage()
    assert captured_drags == []
    remover.gate.set()
    _finish_removal(window, qapp)


def test_mouse_cannot_edit_under_the_overlay(window, qapp, tmp_path, remover, captured_drags):
    _start_gated_removal(window, remover, tmp_path)
    canvas = window.canvas
    overlay = canvas.busy_overlay
    # Real input goes to the topmost widget under the cursor: the overlay.
    for pos in (edge_point(canvas, "right"), canvas._output_screen_rect().center()):
        assert canvas.childAt(pos.toPoint()) is overlay
        mouse_drag(overlay, [pos, pos + QPointF(60, 0)])
    assert canvas.edges == Edges()
    assert captured_drags == []
    assert not canvas.is_dragging
    remover.gate.set()
    _finish_removal(window, qapp)


def test_drag_out_after_a_run_includes_the_removal(
    window, qapp, tmp_path, remover, out_dir, captured_drags
):
    # The reported bug: a drag-out during a run wrote the file without the removal.
    _start_gated_removal(window, remover, tmp_path)
    _drag_out(window)
    assert captured_drags == []
    remover.gate.set()
    _finish_removal(window, qapp)
    _drag_out(window)
    assert len(captured_drags) == 1
    path = captured_drags[0].mimeData().urls()[0].toLocalFile()
    with Image.open(path) as dragged:
        assert dragged.getpixel((50, 100))[3] == 255
        assert dragged.getpixel((350, 100))[3] == 0


def test_removal_is_refused_during_a_drag(window, tmp_path, remover):
    window.load_path(_opaque_image(tmp_path))
    drag_edge(window.canvas, "right", 20, release=False)
    window.remove_background()
    assert not window.is_removing
    assert remover.calls == 0


# --- cancel ------------------------------------------------------------------------------


def test_cancel_button_unlocks_without_a_change(window, qapp, tmp_path, remover):
    _start_gated_removal(window, remover, tmp_path)
    window.canvas.busy_overlay.cancel_button.click()
    assert remover.cancels == 1
    assert not window.is_removing
    assert not window.canvas.is_busy
    assert window.remove_bg_action.isEnabled()
    assert window.statusBar().currentMessage() == app_module.CANCELLED_MESSAGE
    thread_done = remover.gate.wait(5)
    qapp.processEvents()
    assert thread_done
    assert window.canvas.matte is None
    assert not window.history.can_undo


def test_late_result_of_a_cancelled_run_is_ignored(window, qapp, tmp_path, remover, warnings):
    _start_gated_removal(window, remover, tmp_path)
    run = window._removal_run
    window.cancel_removal()
    matte = Image.new("L", window.image.size, 0)
    window._removal_signals.finished.emit(run, window.image, matte)
    window._removal_signals.failed.emit(run, "late failure")
    qapp.processEvents()
    assert window.canvas.matte is None
    assert not window.history.can_undo
    assert warnings == []
    # A new run then works normally.
    remover.gate = None
    window.remove_background()
    _finish_removal(window, qapp)
    assert window.canvas.matte is not None


def test_new_image_during_removal_cancels_it(window, qapp, tmp_path, remover):
    _start_gated_removal(window, remover, tmp_path)
    window.load_path(_save_test_image(tmp_path / "b.png"))
    assert remover.cancels == 1
    assert not window.is_removing
    assert not window.canvas.is_busy
    assert window.remove_bg_action.isEnabled()
    qapp.processEvents()
    assert window.canvas.matte is None
    assert not window.history.can_undo


def test_cancel_during_the_download_stops_it(window, qapp, tmp_path, remover, monkeypatch):
    monkeypatch.setattr(app_module.matting, "has_model", lambda path=None: False)
    reached = threading.Event()
    outcome = []

    def fake_download(dest, progress):
        progress(1, 4)
        reached.set()
        time.sleep(0.2)  # the test cancels meanwhile
        try:
            progress(2, 4)
        except app_module.matting.Cancelled:
            outcome.append("cancelled")
            raise

    monkeypatch.setattr(app_module.matting, "download_model", fake_download)
    window.load_path(_opaque_image(tmp_path))
    window.remove_background()
    thread = window._removal_thread
    assert reached.wait(5)
    window.cancel_removal()
    thread.join(5)
    qapp.processEvents()
    assert outcome == ["cancelled"]
    assert remover.calls == 0
    assert not window.canvas.is_busy


def test_close_cancels_the_run_and_ends_the_child(qapp, tmp_path, monkeypatch):
    win = MainWindow()
    win.show()
    fake = _FakeRemover()
    fake.gate = threading.Event()
    win.remover = fake
    monkeypatch.setattr(app_module.matting, "is_installed", lambda: True)
    monkeypatch.setattr(app_module.matting, "has_model", lambda path=None: True)
    win.load_path(_opaque_image(tmp_path))
    win.remove_background()
    thread = win._removal_thread
    assert win.close()
    assert fake.closed
    assert not win.is_removing
    thread.join(5)
    assert not thread.is_alive()


# --- failure, progress, snapshots --------------------------------------------------------


def test_removal_failure_shows_error_and_unlocks(window, qapp, tmp_path, remover, warnings):
    remover.error = RuntimeError("out of memory")
    window.load_path(_opaque_image(tmp_path))
    window.remove_background()
    _finish_removal(window, qapp)
    assert len(warnings) == 1
    assert "out of memory" in warnings[0][2]
    assert window.canvas.matte is None
    assert not window.canvas.is_busy
    assert window.remove_bg_action.isEnabled()
    assert window.quick_save_action.isEnabled()
    assert not window.history.can_undo


def test_removal_without_packages_explains_install(window, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: shown.append(args))
    monkeypatch.setattr(app_module.matting, "is_installed", lambda: False)
    window.load_path(_opaque_image(tmp_path))
    window.remove_background()
    assert len(shown) == 1
    assert '".[bg]"' in shown[0][2]
    assert not window.is_removing
    assert not window.canvas.is_busy


def test_first_run_downloads_the_model(window, qapp, tmp_path, remover, monkeypatch):
    monkeypatch.setattr(app_module.matting, "has_model", lambda path=None: False)
    downloads = []

    def fake_download(dest, progress):
        downloads.append(dest)
        progress(1, 2)

    monkeypatch.setattr(app_module.matting, "download_model", fake_download)
    window.load_path(_opaque_image(tmp_path))
    window.remove_background()
    _finish_removal(window, qapp)
    assert downloads == [remover.path]
    assert window.canvas.matte is not None


def test_download_progress_shows_on_the_overlay(window, tmp_path, remover):
    _start_gated_removal(window, remover, tmp_path)
    run = window._removal_run
    overlay = window.canvas.busy_overlay
    window._removal_progress(run, 42, 100)
    assert overlay.detail == app_module.DOWNLOADING_DETAIL.format(0.42)
    assert "42%" in overlay.detail
    window._removal_progress(run - 1, 90, 100)  # an old run: ignored
    assert "42%" in overlay.detail
    window._removal_progress(run, 100, 100)
    assert overlay.detail == app_module.LOCKED_DETAIL
    remover.gate.set()


def test_busy_overlay_snapshot(window, qapp, tmp_path, remover, artifacts_dir):
    _start_gated_removal(window, remover, tmp_path)
    window._removal_progress(window._removal_run, 42, 100)
    assert window.grab().save(str(artifacts_dir / "p6_busy_overlay.png"))
    remover.gate.set()
    _finish_removal(window, qapp)


def test_background_removal_snapshot(window, qapp, tmp_path, remover, artifacts_dir):
    window.load_path(_opaque_image(tmp_path))
    window.remove_background()
    _finish_removal(window, qapp)
    assert window.grab().save(str(artifacts_dir / "p5_background_removed.png"))
