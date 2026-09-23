"""MainWindow: menus, status bar, drag-and-drop, file dialogs, and the canvas."""

from pathlib import Path

from PIL import Image, UnidentifiedImageError
from PySide6.QtGui import QAction, QKeySequence, QPixmap
from PySide6.QtWidgets import QFileDialog, QLabel, QMainWindow, QMessageBox

from image_lab.canvas import ImageCanvas
from image_lab.files import IMAGE_EXTENSIONS, is_image_path, load_image
from image_lab.model import Edges, output_size
from image_lab.qtimage import pil_to_qimage

NO_IMAGE_STATUS = "No image"

OPEN_FILTER = "Images (" + " ".join(f"*{ext}" for ext in IMAGE_EXTENSIONS) + ");;All files (*)"

# Errors Pillow raises for unreadable, unsupported, or absurdly large files.
LOAD_ERRORS = (UnidentifiedImageError, OSError, Image.DecompressionBombError)


def _signed(value: int) -> str:
    return f"{value:+d}" if value else "0"


def status_text(size: tuple[int, int], edges: Edges) -> str:
    """Status bar summary: original size, per-side edits, output size."""
    ow, oh = output_size(size, edges)
    return (
        f"Original {size[0]}×{size[1]}  |  "
        f"L {_signed(edges.left)}  T {_signed(edges.top)}  "
        f"R {_signed(edges.right)}  B {_signed(edges.bottom)}  |  "
        f"Output {ow}×{oh}"
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

    def _build_menus(self):
        file_menu = self.menuBar().addMenu("&File")
        self.open_action = QAction("&Open…", self)
        self.open_action.setShortcut(QKeySequence.Open)
        self.open_action.triggered.connect(self.open_dialog)
        file_menu.addAction(self.open_action)

        file_menu.addSeparator()
        self.quit_action = QAction("E&xit", self)
        self.quit_action.setShortcut(QKeySequence.Quit)
        self.quit_action.triggered.connect(self.close)
        file_menu.addAction(self.quit_action)

        self.menuBar().addMenu("&Edit")

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
        return True

    def _update_status(self):
        if self.image is None:
            self.status_label.setText(NO_IMAGE_STATUS)
        else:
            self.status_label.setText(status_text(self.image.size, self.canvas.edges))

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
