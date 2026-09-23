"""Headless tests for MainWindow."""

import pytest
from PIL import Image
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QImage, QMouseEvent
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
from image_lab.model import Edges

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


def _drag_edge(canvas, side, image_px):
    """Drag `side` outward by `image_px` image pixels with synthetic mouse events."""
    r = canvas._output_screen_rect()
    start, direction = {
        "left": (QPointF(r.left(), r.center().y()), QPointF(-1, 0)),
        "right": (QPointF(r.right(), r.center().y()), QPointF(1, 0)),
        "top": (QPointF(r.center().x(), r.top()), QPointF(0, -1)),
        "bottom": (QPointF(r.center().x(), r.bottom()), QPointF(0, 1)),
    }[side]
    end = start + direction * (image_px * canvas.scale)
    for kind, pos, button, buttons in [
        (QEvent.MouseMove, start, Qt.NoButton, Qt.NoButton),
        (QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton),
        (QEvent.MouseMove, end, Qt.NoButton, Qt.LeftButton),
        (QEvent.MouseButtonRelease, end, Qt.LeftButton, Qt.NoButton),
    ]:
        event = QMouseEvent(kind, pos, canvas.mapToGlobal(pos), button, buttons, Qt.NoModifier)
        QApplication.sendEvent(canvas, event)


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
    assert text == (
        "Original 1920×1080  |  L +40  T 0  R -120  B +40  |  Output 1840×1120  |  Fill transparent"
    )


def test_status_bar_tracks_image_and_edges(window, tmp_path):
    assert window.status_label.text() == NO_IMAGE_STATUS
    window.load_path(_save_test_image(tmp_path / "s.png", size=(400, 200)))
    assert window.status_label.text() == status_text((400, 200), Edges())

    # Drag the right edge outward; the status bar follows the canvas edges.
    _drag_edge(window.canvas, "right", 50)
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
    _drag_edge(window.canvas, "bottom", 30)
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
        window.save_as_action,
        window.reset_action,
        window.fill_action,
        window.transparent_action,
    ]
    assert not any(a.isEnabled() for a in actions)
    assert window.open_action.isEnabled()
    window.load_path(_save_test_image(tmp_path / "a.png"))
    assert all(a.isEnabled() for a in actions)


def test_reset_restores_zero_edges_and_refits(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    origin_before = window.canvas.origin
    _drag_edge(window.canvas, "left", 80)
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

    _drag_edge(window.canvas, "top", 20)
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
    _drag_edge(window.canvas, "left", 60)
    _drag_edge(window.canvas, "bottom", 40)
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
    _drag_edge(window.canvas, "left", 25)
    assert not out_dir.exists()  # created on first save

    window.save_button.click()
    window.quick_save_action.trigger()
    first, second = out_dir / "cat_edited.png", out_dir / "cat_edited_2.png"
    assert first.exists() and second.exists()
    with Image.open(first) as img:
        assert img.size == (425, 200)
    assert window.statusBar().currentMessage() == f"Saved to {second}"


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
    assert window.undo_action.shortcut().toString() == "Ctrl+Z"
    # QKeySequence.Redo on Windows is Ctrl+Y (with Ctrl+Shift+Z as an alternate).
    assert "Ctrl+Y" in [k.toString() for k in window.redo_action.shortcuts()]


def test_undo_redo_drags(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    assert not window.undo_action.isEnabled()
    _drag_edge(window.canvas, "right", 40)
    _drag_edge(window.canvas, "top", -30)
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
    r = canvas._output_screen_rect()
    start = QPointF(r.right(), r.center().y())
    # Many moves while the button is held, then one release.
    events = [(QEvent.MouseMove, start, Qt.NoButton, Qt.NoButton)]
    events.append((QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton))
    for step in range(1, 6):
        events.append((QEvent.MouseMove, start + QPointF(step * 10, 0), Qt.NoButton, Qt.LeftButton))
    events.append((QEvent.MouseButtonRelease, start + QPointF(50, 0), Qt.LeftButton, Qt.NoButton))
    for kind, pos, button, buttons in events:
        event = QMouseEvent(kind, pos, canvas.mapToGlobal(pos), button, buttons, Qt.NoModifier)
        QApplication.sendEvent(canvas, event)
    assert canvas.edges.right > 0
    window.undo_action.trigger()
    assert canvas.edges == Edges()


def test_drag_without_change_adds_no_step(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png"))
    _drag_edge(window.canvas, "left", 0)
    assert not window.undo_action.isEnabled()


def test_undo_reset_and_fill(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png"))
    _drag_edge(window.canvas, "left", 20)
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
    _drag_edge(window.canvas, "left", 20)
    window.undo_action.trigger()
    assert window.redo_action.isEnabled()
    _drag_edge(window.canvas, "bottom", 10)
    assert not window.redo_action.isEnabled()


def test_load_clears_history(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png"))
    _drag_edge(window.canvas, "left", 20)
    window.load_path(_save_test_image(tmp_path / "b.png"))
    assert not window.undo_action.isEnabled()
    window.undo_action.trigger()
    assert window.canvas.edges == Edges()


def test_undo_ignored_during_drag(window, tmp_path):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    _drag_edge(window.canvas, "left", 20)
    canvas = window.canvas
    r = canvas._output_screen_rect()
    start = QPointF(r.right(), r.center().y())
    for kind, pos, button, buttons in [
        (QEvent.MouseMove, start, Qt.NoButton, Qt.NoButton),
        (QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton),
        (QEvent.MouseMove, start + QPointF(15, 0), Qt.NoButton, Qt.LeftButton),
    ]:
        event = QMouseEvent(kind, pos, canvas.mapToGlobal(pos), button, buttons, Qt.NoModifier)
        QApplication.sendEvent(canvas, event)
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
    _drag_edge(window.canvas, "left", 30)
    window.copy_action.trigger()

    mime = clipboard.mimeData()
    qimg = QImage(mime.imageData())
    assert (qimg.width(), qimg.height()) == (430, 200)
    # The PNG data keeps the transparent padding.
    from io import BytesIO

    png = Image.open(BytesIO(mime.data("image/png").data()))
    assert png.size == (430, 200)
    assert png.convert("RGBA").getpixel((0, 100))[3] == 0
    assert window.statusBar().currentMessage() == "Copied 430×200 image"


def test_paste_image_data_replaces_image(window, tmp_path, clipboard, out_dir):
    window.load_path(_save_test_image(tmp_path / "a.png"))
    _drag_edge(window.canvas, "left", 30)
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


def test_copy_then_paste_round_trip(window, tmp_path, clipboard):
    window.load_path(_save_test_image(tmp_path / "a.png", size=(400, 200)))
    _drag_edge(window.canvas, "bottom", 50)
    window.copy_action.trigger()
    window.paste_action.trigger()
    assert window.image.size == (400, 250)
    assert window.image.getpixel((10, 240))[3] == 0
