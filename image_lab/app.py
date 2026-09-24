"""MainWindow: menus, toolbar, status bar, drag-and-drop, file and color dialogs, the canvas,
and background removal on a worker thread."""

import threading
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from PySide6.QtCore import QMimeData, QObject, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDrag, QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDoubleSpinBox,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSpinBox,
    QStyle,
    QToolButton,
)

from image_lab import matting
from image_lab.canvas import ImageCanvas
from image_lab.files import (
    IMAGE_EXTENSIONS,
    OUT_DIR,
    ensure_extension,
    is_image_path,
    load_image,
    next_free_path,
    png_bytes,
    save_image,
)
from image_lab.history import EditState, History
from image_lab.model import (
    IDENTITY,
    RGBA,
    TRANSPARENT,
    Edges,
    Matte,
    Transform,
    clamp_edges,
    flip_edges_h,
    flip_edges_v,
    flipped_h,
    flipped_v,
    output_size,
    render,
    rotate_edges,
    rotated,
    transformed_size,
)
from image_lab.qtimage import pil_to_qimage, qimage_to_pil

NO_IMAGE_STATUS = "No image"
EXPORT_SUFFIX = "_edited"
PASTED_NAME = "pasted"
NO_CLIPBOARD_IMAGE = "Clipboard has no image"
PNG_MIME = "image/png"
DRAG_THUMBNAIL_PX = 128
SAVED_MESSAGE_MS = 5000
ANGLE_STEP = 0.1
ANGLE_DECIMALS = 1
BRUSH_MAX = 1000
# [ and ] change the brush size by this factor (and by at least 1 px).
BRUSH_STEP_FACTOR = 1.25
REMOVING_MESSAGE = "Removing background…"
LOCKED_DETAIL = "The image is locked until this finishes."
DOWNLOADING_DETAIL = "Downloading the model (first use only): {:.0%}"
REMOVED_MESSAGE = "Background removed"
CANCELLED_MESSAGE = "Background removal cancelled"
NOT_INSTALLED_TEXT = (
    "Background removal needs the optional packages. Install them with:\n\n"
    '.venv/Scripts/python -m pip install -e ".[bg]"'
)

OPEN_FILTER = "Images (" + " ".join(f"*{ext}" for ext in IMAGE_EXTENSIONS) + ");;All files (*)"

# Save dialog filters and the extension added when the user types none.
SAVE_FILTERS = {
    "PNG (*.png)": ".png",
    "JPEG (*.jpg *.jpeg)": ".jpg",
    "WebP (*.webp)": ".webp",
    "BMP (*.bmp)": ".bmp",
}

# Errors Pillow raises for unreadable, unsupported, or absurdly large files.
LOAD_ERRORS = (UnidentifiedImageError, OSError, Image.DecompressionBombError)

# Qt's own dialog (not the OS one) so the hex ("HTML") field and alpha control are
# always available.
COLOR_DIALOG_OPTIONS = QColorDialog.ShowAlphaChannel | QColorDialog.DontUseNativeDialog


def _signed(value: int) -> str:
    return f"{value:+d}" if value else "0"


def fill_label(fill: RGBA) -> str:
    """Fill color as text: 'transparent', '#RRGGBB', or '#RRGGBBAA' when partly transparent."""
    r, g, b, a = fill
    if a == 0:
        return "transparent"
    text = f"#{r:02X}{g:02X}{b:02X}"
    return text if a == 255 else f"{text}{a:02X}"


def status_text(
    size: tuple[int, int], edges: Edges, fill: RGBA = TRANSPARENT, transform: Transform = IDENTITY
) -> str:
    """Status bar summary: original size, per-side edits, output size, padding fill."""
    ow, oh = output_size(transformed_size(size, transform), edges)
    return (
        f"Original {size[0]}×{size[1]}  |  "
        f"L {_signed(edges.left)}  T {_signed(edges.top)}  "
        f"R {_signed(edges.right)}  B {_signed(edges.bottom)}  |  "
        f"Output {ow}×{oh}  |  Fill {fill_label(fill)}"
    )


def dropped_image_path(mime) -> str | None:
    """Local path of the first dropped URL if it looks like an image, else None."""
    if not mime.hasUrls():
        return None
    url = mime.urls()[0]
    if not url.isLocalFile():
        return None
    path = url.toLocalFile()
    return path if is_image_path(path) else None


class _RemovalSignals(QObject):
    """Carries background-removal results from the worker thread to the GUI thread.
    The receivers live in the GUI thread, so Qt queues these signals across threads.
    Each signal carries its run number, so results of a cancelled run are ignored."""

    progress = Signal(int, int, int)  # (run, bytes done, bytes total)
    finished = Signal(int, object, object)  # (run, source image, matte image)
    failed = Signal(int, str)  # (run, message)
    cancelled = Signal(int)  # (run)


class MainWindow(QMainWindow):
    """Top-level window that owns the loaded image, the canvas, and the menu actions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("image_lab")
        self.setAcceptDrops(True)
        self.image: Image.Image | None = None
        # Source file, or None for a pasted image; image_name is the stem used for exports.
        self.image_path: Path | None = None
        self.image_name = ""
        self.history = History()
        # (image, edit state, file) of the last drag-out export, reused while unchanged.
        self._drag_export: tuple[Image.Image, EditState, Path] | None = None
        self.canvas = ImageCanvas(self)
        self.setCentralWidget(self.canvas)
        # A normal (not permanent) status widget, so showMessage() can briefly cover it.
        self.status_label = QLabel(NO_IMAGE_STATUS)
        self.statusBar().addWidget(self.status_label, 1)
        self.canvas.edgesChanged.connect(self._update_status)
        self.canvas.edgesChanged.connect(self._sync_angle_box)
        self.canvas.editFinished.connect(self._record_edit)
        self.canvas.dragOutRequested.connect(self.start_drag_out)
        self.canvas.strokeFinished.connect(self._record_edit)
        # One remover for the window's lifetime; its child process keeps the model loaded.
        self.remover = matting.ProcessRemover()
        self._removal_thread: threading.Thread | None = None
        # Number of the current run, and the flag that tells its thread to stop.
        self._removal_run = 0
        self._removal_stop: threading.Event | None = None
        # Set at the very start of closeEvent, before cancel_removal() runs, so the
        # worker thread never emits into a window that may already be gone.
        self._closing = False
        self.canvas.cancelRequested.connect(self.cancel_removal)
        self._removal_signals = _RemovalSignals(self)
        self._removal_signals.progress.connect(self._removal_progress)
        self._removal_signals.finished.connect(self._removal_finished)
        self._removal_signals.failed.connect(self._removal_failed)
        self._removal_signals.cancelled.connect(self._removal_cancelled)
        self._build_menus()
        self._build_toolbar()

    def _action(self, text, slot, shortcut=None) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.triggered.connect(slot)
        return action

    def _build_menus(self):
        self.open_action = self._action("&Open…", self.open_dialog, QKeySequence.Open)
        self.quick_save_action = self._action("&Save", self.quick_save, QKeySequence.Save)
        self.save_as_action = self._action("Save &As…", self.save_dialog, QKeySequence.SaveAs)
        self.quit_action = self._action("E&xit", self.close, QKeySequence.Quit)
        self.undo_action = self._action("&Undo", self.undo, QKeySequence.Undo)
        self.redo_action = self._action("&Redo", self.redo, QKeySequence.Redo)
        self.copy_action = self._action("&Copy Image", self.copy_image, QKeySequence.Copy)
        self.paste_action = self._action("&Paste Image", self.paste_image, QKeySequence.Paste)
        self.reset_action = self._action("&Reset", self.reset_edits, "Ctrl+R")
        self.fill_action = self._action("Padding &Color…", self.choose_fill)
        self.transparent_action = self._action(
            "&Transparent Padding", lambda: self.set_fill(TRANSPARENT)
        )
        # Ctrl+R is already Reset, so the turns use the bracket keys.
        self.rotate_left_action = self._action("Rotate &Left", self.rotate_left, "Ctrl+[")
        self.rotate_right_action = self._action("Rotate &Right", self.rotate_right, "Ctrl+]")
        self.flip_h_action = self._action("Flip &Horizontal", self.flip_horizontal)
        self.flip_v_action = self._action("Flip &Vertical", self.flip_vertical)
        self._orient_actions = [
            self.rotate_left_action,
            self.rotate_right_action,
            self.flip_h_action,
            self.flip_v_action,
        ]
        self.paint_action = self._action("&Paint Transparency", self.set_paint_mode, "B")
        self.paint_action.setCheckable(True)
        self.paint_action.setToolTip(
            "Paint mode (B): left-drag erases to transparent, right-drag restores"
        )
        self.brush_smaller_action = self._action("Smaller Brush", self.brush_smaller, "[")
        self.brush_larger_action = self._action("Larger Brush", self.brush_larger, "]")
        self.remove_bg_action = self._action("Remove &Background", self.remove_background)
        self.remove_bg_action.setToolTip(
            "Make the background transparent (the restore brush brings parts back)"
        )

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addActions([self.open_action, self.quick_save_action, self.save_as_action])
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addActions([self.undo_action, self.redo_action])
        edit_menu.addSeparator()
        edit_menu.addActions([self.copy_action, self.paste_action])
        edit_menu.addSeparator()
        edit_menu.addAction(self.reset_action)
        edit_menu.addSeparator()
        edit_menu.addActions([self.fill_action, self.transparent_action])

        image_menu = self.menuBar().addMenu("&Image")
        image_menu.addActions(self._orient_actions)
        image_menu.addSeparator()
        image_menu.addAction(self.remove_bg_action)
        image_menu.addSeparator()
        image_menu.addActions(
            [self.paint_action, self.brush_smaller_action, self.brush_larger_action]
        )

        # Actions and controls that only make sense with an image loaded.
        self._image_controls = [
            self.quick_save_action,
            self.save_as_action,
            self.copy_action,
            self.reset_action,
            self.fill_action,
            self.transparent_action,
            *self._orient_actions,
            self.remove_bg_action,
            self.paint_action,
            self.brush_smaller_action,
            self.brush_larger_action,
        ]
        for action in self._image_controls:
            action.setEnabled(False)
        self._update_undo_actions()

    def _build_toolbar(self):
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        # Split button: the main part saves in one click, the arrow offers Save As.
        self.save_button = QToolButton(self)
        self.save_button.setPopupMode(QToolButton.MenuButtonPopup)
        self.save_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        # The button shows its default action's icon, so the icon goes on the action.
        self.quick_save_action.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.save_button.setDefaultAction(self.quick_save_action)
        self.save_button.setToolTip("Save to the out folder (Ctrl+S). Arrow: Save As…")
        menu = QMenu(self.save_button)
        menu.addAction(self.save_as_action)
        self.save_button.setMenu(menu)
        toolbar.addWidget(self.save_button)
        toolbar.addSeparator()
        toolbar.addActions(self._orient_actions)
        toolbar.addWidget(QLabel(" Angle "))
        self.angle_box = QDoubleSpinBox(self)
        self.angle_box.setRange(-180, 180)
        self.angle_box.setDecimals(ANGLE_DECIMALS)
        self.angle_box.setSingleStep(ANGLE_STEP)
        self.angle_box.setSuffix("°")
        self.angle_box.setToolTip("Clockwise rotation in degrees")
        # Apply typed values on Enter or focus loss, not per keystroke; arrow steps apply
        # at once.
        self.angle_box.setKeyboardTracking(False)
        self.angle_box.valueChanged.connect(self.set_angle)
        self.angle_box.setEnabled(False)
        self._image_controls.append(self.angle_box)
        toolbar.addWidget(self.angle_box)
        toolbar.addSeparator()
        toolbar.addAction(self.paint_action)
        toolbar.addWidget(QLabel(" Brush "))
        self.brush_box = QSpinBox(self)
        self.brush_box.setRange(1, BRUSH_MAX)
        self.brush_box.setSuffix(" px")
        self.brush_box.setToolTip("Brush diameter in image pixels ([ and ] change it)")
        self.brush_box.setValue(self.canvas.brush_size)
        self.brush_box.valueChanged.connect(self.canvas.set_brush_size)
        toolbar.addWidget(self.brush_box)

    def _export_stem(self) -> str:
        """Base name for exports: `<image name>_edited` (file stem, or "pasted")."""
        return f"{self.image_name}{EXPORT_SUFFIX}"

    def load_path(self, path: str | Path) -> bool:
        """Load an image file, replacing the current one. Shows an error box on failure."""
        path = Path(path)
        try:
            img = load_image(path)
        except LOAD_ERRORS as exc:
            QMessageBox.warning(
                self, "Could not open image", f"{path.name} could not be opened.\n\n{exc}"
            )
            return False
        self._show_image(img, path, path.stem, path.name)
        return True

    def _show_image(self, img: Image.Image, path: Path | None, name: str, title: str):
        """Make `img` the current image (from a file or the clipboard) with fresh edits."""
        # A removal still running belongs to the previous image.
        self.cancel_removal()
        self.image = img
        self.image_path = path
        self.image_name = name
        # Convert once here; the canvas reuses this pixmap for every repaint.
        self.canvas.set_image(QPixmap.fromImage(pil_to_qimage(img)))
        # A new image starts a new history; the fill carries over as its first state.
        self.history.reset(self._edit_state())
        self._update_undo_actions()
        self.setWindowTitle(f"{title} - image_lab")
        for action in self._image_controls:
            action.setEnabled(True)

    def save_to(self, path: str | Path) -> bool:
        """Export the current image with all its edits. Shows an error box on failure."""
        path = Path(path)
        try:
            save_image(
                self.image,
                self.canvas.edges,
                path,
                fill=self.canvas.fill,
                transform=self.canvas.transform,
                strokes=self.canvas.strokes,
                matte=self.canvas.matte,
            )
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Could not save image", f"Saving {path} failed.\n\n{exc}")
            return False
        self.statusBar().showMessage(f"Saved to {path}", SAVED_MESSAGE_MS)
        return True

    def quick_save(self):
        """Save as PNG into the out folder under the next free name; never overwrites."""
        if self._locked:
            return
        path = self._next_out_path()
        if path is not None:
            self.save_to(path)

    def _next_out_path(self) -> Path | None:
        """Next free `<stem>_edited.png` in the out folder (created if needed); None on error."""
        try:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Could not save image", f"Cannot create {OUT_DIR}.\n\n{exc}")
            return None
        return next_free_path(OUT_DIR, self._export_stem(), ".png")

    def save_dialog(self):
        if self._locked:
            return
        # The dialog starts in the out folder; it may not exist yet, which is fine.
        default = OUT_DIR / f"{self._export_stem()}.png"
        first_filter = next(iter(SAVE_FILTERS))
        path, chosen = QFileDialog.getSaveFileName(
            self, "Save As", str(default), ";;".join(SAVE_FILTERS), first_filter
        )
        if path:
            self.save_to(ensure_extension(path, SAVE_FILTERS.get(chosen, ".png")))

    # --- clipboard ---------------------------------------------------------------

    def edited_image(self) -> Image.Image:
        """The current image with all edits applied, exactly as it would be saved as PNG."""
        c = self.canvas
        return render(self.image, c.edges, c.fill, c.transform, c.strokes, c.matte)

    def copy_image(self):
        """Put the edited image on the clipboard as both a bitmap and PNG data."""
        if self._locked:
            return
        out = self.edited_image()
        mime = QMimeData()
        mime.setImageData(pil_to_qimage(out))
        # Many apps read the plain bitmap, which drops alpha on Windows; PNG keeps it.
        mime.setData(PNG_MIME, png_bytes(out))
        QApplication.clipboard().setMimeData(mime)
        self.statusBar().showMessage(f"Copied {out.width}×{out.height} image", SAVED_MESSAGE_MS)

    def paste_image(self):
        """Replace the current image with a copied image file or image data."""
        mime = QApplication.clipboard().mimeData()
        path = dropped_image_path(mime) if mime is not None else None
        if path:
            self.load_path(path)
            return
        img = self._clipboard_pixels(mime)
        if img is None:
            self.statusBar().showMessage(NO_CLIPBOARD_IMAGE, SAVED_MESSAGE_MS)
            return
        self._show_image(img, None, PASTED_NAME, PASTED_NAME)

    def _clipboard_pixels(self, mime) -> Image.Image | None:
        if mime is None:
            return None
        # Prefer PNG data: it keeps transparency, which the plain bitmap may lose.
        if mime.hasFormat(PNG_MIME):
            try:
                return load_image(BytesIO(mime.data(PNG_MIME).data()))
            except LOAD_ERRORS:
                pass
        if mime.hasImage():
            qimg = QImage(mime.imageData())
            if not qimg.isNull():
                return qimage_to_pil(qimg)
        return None

    # --- drag out -----------------------------------------------------------------

    def export_for_drag(self) -> Path | None:
        """Write the edited image as PNG into the out folder for dragging; None on failure.

        Reuses the previous drag file while the image and its edits are unchanged,
        so repeated drags don't fill the out folder with copies.
        """
        state = self._edit_state()
        last = self._drag_export
        if last and last[0] is self.image and last[1] == state and last[2].exists():
            return last[2]
        path = self._next_out_path()
        if path is None or not self.save_to(path):
            return None
        self._drag_export = (self.image, state, path)
        return path

    def start_drag_out(self):
        """Drag the edited image out as a PNG file (plus bitmap data for apps that want it)."""
        if self._locked:
            return
        path = self.export_for_drag()
        if path is None:
            return
        # `path` is a PNG of the exact current render (export_for_drag guarantees it);
        # load it instead of re-running the Pillow render a second time.
        qimg = QImage(str(path))
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path))])
        mime.setImageData(qimg)
        drag = QDrag(self.canvas)
        drag.setMimeData(mime)
        thumb = QPixmap.fromImage(qimg).scaled(
            DRAG_THUMBNAIL_PX, DRAG_THUMBNAIL_PX, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        drag.setPixmap(thumb)
        self._exec_drag(drag)

    def _exec_drag(self, drag: QDrag):
        # Separate method so tests can replace it: QDrag.exec blocks until the drop.
        drag.exec(Qt.CopyAction)

    # --- edits and undo/redo ----------------------------------------------------

    def _edit_state(self) -> EditState:
        c = self.canvas
        return EditState(c.edges, c.fill, c.transform, c.strokes, c.matte)

    def _record_edit(self):
        """Add the state on screen to the history (after a drag, stroke, reset, turn, flip,
        fill or background removal)."""
        self.history.push(self._edit_state())
        self._update_undo_actions()

    def _update_undo_actions(self):
        self.undo_action.setEnabled(self.history.can_undo and not self.is_removing)
        self.redo_action.setEnabled(self.history.can_redo and not self.is_removing)

    def _apply_state(self, state: EditState | None):
        if state is None:
            return
        self.canvas.set_fill(state.fill)
        self.canvas.set_strokes(state.strokes)
        self.canvas.set_matte(state.matte)
        # Emits edgesChanged, which updates the status.
        self.canvas.set_transform(state.transform, state.edges)
        self._update_undo_actions()

    def undo(self):
        # Mid-drag the canvas owns the edges; undo would fight the mouse.
        if self._can_edit:
            self._apply_state(self.history.undo())

    def redo(self):
        if self._can_edit:
            self._apply_state(self.history.redo())

    def reset_edits(self):
        """Undo all edges, orientation changes, paint and background removal in one step.
        The padding fill stays."""
        if not self._can_edit:
            return
        self.canvas.set_strokes(())
        self.canvas.set_matte(None)
        self.canvas.set_transform(IDENTITY, Edges())
        self._record_edit()

    def _orient(self, transform_op, edges_op):
        """Turn or flip the view; the edges move with it, so the output is turned too."""
        if not self._can_edit:
            return
        self.canvas.set_transform(transform_op(self.canvas.transform), edges_op(self.canvas.edges))
        self._record_edit()

    def set_angle(self, degrees: float):
        """Rotate the view to `degrees` clockwise, keeping any mirror.

        The view image changes size, so crops too deep for it are reduced.
        """
        if not self._can_edit:
            self._sync_angle_box()
            return
        transform = Transform(degrees, self.canvas.transform.mirror)
        if transform == self.canvas.transform:
            return
        size = transformed_size(self.image.size, transform)
        self.canvas.set_transform(transform, clamp_edges(size, self.canvas.edges))
        self._record_edit()

    def _sync_angle_box(self):
        # Show the current angle without feeding it back into set_angle.
        self.angle_box.blockSignals(True)
        self.angle_box.setValue(self.canvas.transform.angle)
        self.angle_box.blockSignals(False)

    def set_paint_mode(self, on: bool):
        """Switch the canvas between editing edges and painting transparency."""
        self.canvas.set_paint_mode(on)
        # The canvas refuses mid-stroke or mid-drag, so show what it actually did.
        self.paint_action.setChecked(self.canvas.paint_mode)

    def brush_smaller(self):
        if not self._can_edit:
            return
        size = self.brush_box.value()
        self.brush_box.setValue(min(size - 1, round(size / BRUSH_STEP_FACTOR)))

    def brush_larger(self):
        if not self._can_edit:
            return
        size = self.brush_box.value()
        self.brush_box.setValue(max(size + 1, round(size * BRUSH_STEP_FACTOR)))

    # --- background removal -----------------------------------------------------

    @property
    def is_removing(self) -> bool:
        """True while background removal (or the model download) runs."""
        return self._removal_thread is not None

    @property
    def _locked(self) -> bool:
        """True when edits and exports are unavailable: no image, or a removal running."""
        return self.image is None or self.is_removing

    @property
    def _can_edit(self) -> bool:
        """True when an edit can run now: an image is loaded, no removal is running, and
        no drag or paint stroke is in progress."""
        return not self._locked and not self.canvas.is_dragging

    def _set_locked(self, locked: bool):
        """Lock or unlock the image for background removal: the overlay covers the
        canvas, and every edit and export is off until the run ends or is cancelled."""
        enabled = not locked and self.image is not None
        for action in self._image_controls:
            action.setEnabled(enabled)
        self.brush_box.setEnabled(not locked)
        self._update_undo_actions()
        if locked:
            self.canvas.show_busy(REMOVING_MESSAGE, LOCKED_DETAIL)
        else:
            self.canvas.hide_busy()

    def remove_background(self):
        """Make the background transparent, as one undoable edit. The model runs in a
        child process so the window stays responsive; the first run downloads it.
        The image is locked until the run ends or is cancelled."""
        if not self._can_edit:
            return
        if not matting.is_installed():
            QMessageBox.information(self, "Background removal", NOT_INSTALLED_TEXT)
            return
        self._removal_run += 1
        self._removal_stop = threading.Event()
        self._removal_thread = threading.Thread(
            target=self._run_removal,
            args=(self._removal_run, self.image, self._removal_stop),
            daemon=True,
        )
        self._set_locked(True)
        self._removal_thread.start()

    def _run_removal(self, run: int, img: Image.Image, stop: threading.Event):
        # Worker thread: no widgets here, only signals back to the GUI thread. A stop
        # (Cancel or a new image) reports back with `cancelled`, so the image unlocks
        # only once this thread's own cleanup (including ProcessRemover.predict's) has
        # actually finished. While the window is closing, nothing is emitted at all,
        # because the window may already be gone.
        signals = self._removal_signals

        def progress(done: int, total: int):
            if stop.is_set():
                raise matting.Cancelled()
            signals.progress.emit(run, done, total)

        try:
            if not matting.has_model(self.remover.path):
                matting.download_model(self.remover.path, progress)
            if stop.is_set():
                if not self._closing:
                    signals.cancelled.emit(run)
                return
            matte = self.remover.predict(img)
        except matting.Cancelled:
            if not self._closing:
                signals.cancelled.emit(run)
            return
        except Exception as exc:
            # Network, disk and onnxruntime errors all end up here; report any of them
            # rather than let the thread die silently.
            if not stop.is_set():
                signals.failed.emit(run, str(exc) or type(exc).__name__)
        else:
            if not stop.is_set():
                signals.finished.emit(run, img, matte)

    def _is_current_run(self, run: int) -> bool:
        return self.is_removing and run == self._removal_run

    def _removal_progress(self, run: int, done: int, total: int):
        if not self._is_current_run(run):
            return
        detail = DOWNLOADING_DETAIL.format(done / total) if done < total else LOCKED_DETAIL
        self.canvas.show_busy(REMOVING_MESSAGE, detail)

    def _removal_finished(self, run: int, img: Image.Image, matte: Image.Image):
        if not self._is_current_run(run):
            return
        self._end_removal()
        self.canvas.set_matte(Matte(matte))
        self._record_edit()
        self.statusBar().showMessage(REMOVED_MESSAGE, SAVED_MESSAGE_MS)

    def _removal_failed(self, run: int, message: str):
        if not self._is_current_run(run):
            return
        self._end_removal()
        QMessageBox.warning(self, "Background removal failed", message)

    def _removal_cancelled(self, run: int):
        if self._is_current_run(run):
            self._end_removal()

    def cancel_removal(self):
        """Stop a running removal; the image unlocks once the worker thread confirms it
        stopped (its own cleanup, including the child process, may still be winding
        down, so unlocking any earlier could let a second run start onto the same
        still-live process or download)."""
        if not self.is_removing:
            return
        self._removal_stop.set()
        self.remover.cancel()
        self.statusBar().showMessage(CANCELLED_MESSAGE, SAVED_MESSAGE_MS)

    def _end_removal(self):
        self._removal_thread = None
        self._removal_stop = None
        self._set_locked(False)

    def closeEvent(self, event):
        # Set before cancel_removal(), so _run_removal's cancelled signal (queued back
        # to this window) is never emitted once the window may already be gone.
        self._closing = True
        # Stop the model's child process too; otherwise it would outlive the window.
        self.cancel_removal()
        self.remover.close()
        super().closeEvent(event)

    def rotate_left(self):
        self._orient(lambda t: rotated(t, -90), lambda e: rotate_edges(e, clockwise=False))

    def rotate_right(self):
        self._orient(lambda t: rotated(t, 90), lambda e: rotate_edges(e, clockwise=True))

    def flip_horizontal(self):
        self._orient(flipped_h, flip_edges_h)

    def flip_vertical(self):
        self._orient(flipped_v, flip_edges_v)

    def set_fill(self, fill: RGBA):
        """Set the padding color used by the preview and the export."""
        if self.is_removing:
            return
        self.canvas.set_fill(fill)
        self._update_status()
        self._record_edit()

    def choose_fill(self):
        """Pick a padding color; the dialog accepts hex (#RRGGBB) and has an alpha control."""
        current = self.canvas.fill
        # Start from white when the fill is transparent, so the dialog isn't invisible black.
        initial = QColor(*current) if current[3] > 0 else QColor(255, 255, 255)
        color = QColorDialog.getColor(initial, self, "Padding color", COLOR_DIALOG_OPTIONS)
        if color.isValid():
            self.set_fill(color.getRgb())

    def _update_status(self):
        if self.image is None:
            self.status_label.setText(NO_IMAGE_STATUS)
        else:
            self.status_label.setText(
                status_text(
                    self.image.size, self.canvas.edges, self.canvas.fill, self.canvas.transform
                )
            )

    def open_dialog(self):
        start_dir = str(self.image_path.parent) if self.image_path else ""
        path, _ = QFileDialog.getOpenFileName(self, "Open image", start_dir, OPEN_FILTER)
        if path:
            self.load_path(path)

    def _is_own_drag(self, event) -> bool:
        # Our own drag-out passing over the window must not reload the image.
        return event.source() is self.canvas

    def dragEnterEvent(self, event):
        if not self._is_own_drag(event) and dropped_image_path(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if self._is_own_drag(event):
            event.ignore()
            return
        path = dropped_image_path(event.mimeData())
        if path:
            event.acceptProposedAction()
            self.load_path(path)
