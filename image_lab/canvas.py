"""ImageCanvas: the central widget that draws the image and handles edge dragging."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

BACKGROUND = QColor(48, 48, 48)
EMPTY_TEXT_COLOR = QColor(170, 170, 170)
EMPTY_TEXT = "Drop an image here"


class ImageCanvas(QWidget):
    """Custom-painted view of the current image."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), BACKGROUND)
        painter.setPen(EMPTY_TEXT_COLOR)
        painter.drawText(self.rect(), Qt.AlignCenter, EMPTY_TEXT)
