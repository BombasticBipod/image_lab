"""MainWindow: menus, status bar, drag-and-drop, file and color dialogs, and the canvas."""

from pathlib import Path

from PIL import Image, UnidentifiedImageError
from PySide6.QtGui import QAction, QColor, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QColorDialog,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
)

from image_lab.canvas import ImageCanvas
from image_lab.files import (
    IMAGE_EXTENSIONS,
    ensure_extension,
    is_image_path,
    load_image,
    save_image,
)
from image_lab.model import RGBA, TRANSPARENT, Edges, output_size
from image_lab.qtimage import pil_to_qimage

NO_IMAGE_STATUS = "No image"
SAVED_MESSAGE_MS = 5000

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


def status_text(size: tuple[int, int], edges: Edges, fill: RGBA = TRANSPARENT) -> str:
    """Status bar summary: original size, per-side edits, output size, padding fill."""
    ow, oh = output_size(size, edges)
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


class MainWindow(QMainWindow):
    """Top-level window that owns the loaded image, the canvas, and the menu actions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("image_lab")
        self.setAcceptDrops(True)
        self.image: Image.Image | None = None
        self.image_path: Path | None = None
        self.canvas = ImageCanvas(self)
        self.setCentralWidget(self.canvas)
        # A normal (not permanent) status widget, so showMessage() can briefly cover it.
        self.status_label = QLabel(NO_IMAGE_STATUS)
        self.statusBar().addWidget(self.status_label, 1)
        self.canvas.edgesChanged.connect(self._update_status)
        self._build_menus()

    def _action(self, text, slot, shortcut=None) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.triggered.connect(slot)
        return action

    def _build_menus(self):
        self.open_action = self._action("&Open…", self.open_dialog, QKeySequence.Open)
        # The plan asks for Ctrl+S, which is QKeySequence.Save rather than SaveAs.
        self.save_action = self._action("&Save As…", self.save_dialog, QKeySequence.Save)
        self.quit_action = self._action("E&xit", self.close, QKeySequence.Quit)
        self.reset_action = self._action("&Reset", self.canvas.reset_edges, "Ctrl+R")
        self.fill_action = self._action("Padding &Color…", self.choose_fill)
        self.transparent_action = self._action(
            "&Transparent Padding", lambda: self.set_fill(TRANSPARENT)
        )

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addActions([self.open_action, self.save_action])
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self.reset_action)
        edit_menu.addSeparator()
        edit_menu.addActions([self.fill_action, self.transparent_action])

        # Actions that only make sense with an image loaded.
        self._image_actions = [
            self.save_action,
            self.reset_action,
            self.fill_action,
            self.transparent_action,
        ]
        for action in self._image_actions:
            action.setEnabled(False)

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
        self.image = img
        self.image_path = path
        # Convert once here; the canvas reuses this pixmap for every repaint.
        self.canvas.set_image(QPixmap.fromImage(pil_to_qimage(img)))
        self.setWindowTitle(f"{path.name} - image_lab")
        for action in self._image_actions:
            action.setEnabled(True)
        return True

    def save_to(self, path: str | Path) -> bool:
        """Export the current image with its edges and fill. Shows an error box on failure."""
        path = Path(path)
        try:
            save_image(self.image, self.canvas.edges, path, fill=self.canvas.fill)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Could not save image", f"Saving {path} failed.\n\n{exc}")
            return False
        self.statusBar().showMessage(f"Saved to {path}", SAVED_MESSAGE_MS)
        return True

    def save_dialog(self):
        if self.image is None:
            return
        default = self.image_path.with_name(f"{self.image_path.stem}_edited.png")
        first_filter = next(iter(SAVE_FILTERS))
        path, chosen = QFileDialog.getSaveFileName(
            self, "Save As", str(default), ";;".join(SAVE_FILTERS), first_filter
        )
        if path:
            self.save_to(ensure_extension(path, SAVE_FILTERS.get(chosen, ".png")))

    def set_fill(self, fill: RGBA):
        """Set the padding color used by the preview and the export."""
        self.canvas.set_fill(fill)
        self._update_status()

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
                status_text(self.image.size, self.canvas.edges, self.canvas.fill)
            )

    def open_dialog(self):
        start_dir = str(self.image_path.parent) if self.image_path else ""
        path, _ = QFileDialog.getOpenFileName(self, "Open image", start_dir, OPEN_FILTER)
        if path:
            self.load_path(path)

    def dragEnterEvent(self, event):
        if dropped_image_path(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = dropped_image_path(event.mimeData())
        if path:
            event.acceptProposedAction()
            self.load_path(path)
