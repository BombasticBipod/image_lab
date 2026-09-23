"""Shared pytest fixtures.

Qt must use the offscreen platform so GUI tests run headless. The environment
variable has to be set before any PySide6 module is imported, hence module level.
"""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# The offscreen platform finds no fonts on Windows and draws text as boxes
# unless it is pointed at the system font folder.
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ["WINDIR"], "Fonts"))

ARTIFACTS_DIR = Path(__file__).parent / "_artifacts"


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole test session."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def artifacts_dir() -> Path:
    """Folder for screenshots written by GUI tests (git-ignored)."""
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    return ARTIFACTS_DIR
