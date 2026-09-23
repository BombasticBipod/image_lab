"""MainWindow: menus, status bar, and the canvas."""

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMainWindow

from image_lab.canvas import ImageCanvas


class MainWindow(QMainWindow):
    """Top-level window that owns the canvas and the menu actions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("image_lab")
        self.canvas = ImageCanvas(self)
        self.setCentralWidget(self.canvas)
        self._build_menus()

    def _build_menus(self):
        file_menu = self.menuBar().addMenu("&File")
        self.quit_action = QAction("E&xit", self)
        self.quit_action.setShortcut(QKeySequence.Quit)
        self.quit_action.triggered.connect(self.close)
        file_menu.addAction(self.quit_action)

        self.menuBar().addMenu("&Edit")
