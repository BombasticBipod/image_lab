"""Consistency checks that keep versions, docs, and architecture rules in line."""

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

import image_lab

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "image_lab"

# Modules that must stay Qt-free so the core logic is testable without a GUI.
QT_FREE_MODULES = ["model", "files", "history", "matting"]


def _changelog_versions() -> list[str]:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    return re.findall(r"^## \[?(\d+\.\d+\.\d+)\]?", text, flags=re.MULTILINE)


def test_changelog_top_entry_matches_version():
    versions = _changelog_versions()
    assert versions, "CHANGELOG.md has no '## X.Y.Z' entries"
    assert versions[0] == image_lab.__version__


def test_status_names_current_version():
    status = (ROOT / "docs" / "STATUS.md").read_text(encoding="utf-8")
    assert f"Version: {image_lab.__version__}" in status


@pytest.mark.parametrize("name", QT_FREE_MODULES)
def test_core_modules_do_not_import_qt(name):
    # A fresh interpreter, so Qt loaded by other tests doesn't hide an import, and
    # indirect imports (through another image_lab module) are caught too.
    code = (
        f"import sys, image_lab.{name}; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] == 'PySide6'))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]", f"image_lab.{name} imports Qt"


def _python_files() -> list[Path]:
    """Every Python module in the project: the package, the tests and the tools."""
    return sorted(
        path for folder in ("image_lab", "tests", "tools") for path in (ROOT / folder).glob("*.py")
    )


def test_every_module_has_docstring():
    files = _python_files()
    assert PACKAGE / "model.py" in files
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert ast.get_docstring(tree), f"{path.relative_to(ROOT)} has no module docstring"
