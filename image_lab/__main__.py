"""Entry point: `python -m image_lab` opens the main window."""

import sys

from PySide6.QtWidgets import QApplication

from image_lab.app import MainWindow


def main() -> int:
    """Start the Qt event loop with one main window; return the exit code."""
    app = QApplication(sys.argv)
    app.setApplicationName("image_lab")
    window = MainWindow()
    window.resize(1000, 700)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
