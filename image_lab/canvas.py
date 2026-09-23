"""ImageCanvas: the central widget that draws the image and handles edge dragging."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

BACKGROUND = QColor(48, 48, 48)
EMPTY_TEXT_COLOR = QColor(170, 170, 170)
EMPTY_TEXT = "Drop an image here"
CHECKER_LIGHT = QColor(204, 204, 204)
CHECKER_DARK = QColor(153, 153, 153)
CHECKER_CELL = 8

# Fraction of the widget the image may fill; the rest is room to drag edges outward.
FIT_FRACTION = 0.8


def _checker_brush() -> QBrush:
    tile = QPixmap(2 * CHECKER_CELL, 2 * CHECKER_CELL)
    tile.fill(CHECKER_LIGHT)
    painter = QPainter(tile)
    painter.fillRect(0, 0, CHECKER_CELL, CHECKER_CELL, CHECKER_DARK)
    painter.fillRect(CHECKER_CELL, CHECKER_CELL, CHECKER_CELL, CHECKER_CELL, CHECKER_DARK)
    painter.end()
    return QBrush(tile)


class ImageCanvas(QWidget):
    """Custom-painted view of the current image.

    The view is a uniform scale plus an origin:
    screen = origin + scale * image_pixel.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self._pixmap: QPixmap | None = None
        self._scale = 1.0
        self._origin = QPointF(0, 0)
        self._checker = _checker_brush()

    @property
    def scale(self) -> float:
        """Screen pixels per image pixel."""
        return self._scale

    @property
    def origin(self) -> QPointF:
        """Screen position of image pixel (0, 0)."""
        return QPointF(self._origin)

    def has_image(self) -> bool:
        return self._pixmap is not None

    def set_image(self, pixmap: QPixmap):
        """Show a new image. The pixmap is converted once by the caller and reused."""
        self._pixmap = pixmap
        self._fit()
        self.update()

    def _fit(self):
        """Scale down (never up) and center the image in the widget."""
        if self._pixmap is None:
            return
        w, h = self._pixmap.width(), self._pixmap.height()
        self._scale = min(FIT_FRACTION * self.width() / w, FIT_FRACTION * self.height() / h, 1.0)
        self._origin = QPointF(
            (self.width() - self._scale * w) / 2, (self.height() - self._scale * h) / 2
        )

    def resizeEvent(self, event):
        self._fit()
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), BACKGROUND)
        if self._pixmap is None:
            painter.setPen(EMPTY_TEXT_COLOR)
            painter.drawText(self.rect(), Qt.AlignCenter, EMPTY_TEXT)
            return

        w, h = self._pixmap.width(), self._pixmap.height()
        target = QRectF(self._origin.x(), self._origin.y(), self._scale * w, self._scale * h)
        # The checkerboard shows through wherever the image is transparent.
        painter.fillRect(target, self._checker)
        if self._scale < 1.0:
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawPixmap(target, self._pixmap, QRectF(0, 0, w, h))
