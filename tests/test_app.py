"""Headless tests for MainWindow."""

import pytest

from image_lab.app import MainWindow

pytestmark = pytest.mark.gui


@pytest.fixture
def window(qapp):
    win = MainWindow()
    win.resize(800, 600)
    win.show()
    qapp.processEvents()
    yield win
    win.close()


def _menu_titles(win):
    return [action.text() for action in win.menuBar().actions()]


def test_window_opens_with_menus(window):
    assert window.windowTitle() == "image_lab"
    assert _menu_titles(window) == ["&File", "&Edit"]


def test_empty_state_snapshot(window, artifacts_dir):
    assert window.grab().save(str(artifacts_dir / "m1_empty_window.png"))


def test_window_closes_cleanly(qapp):
    win = MainWindow()
    win.show()
    qapp.processEvents()
    assert win.close()
