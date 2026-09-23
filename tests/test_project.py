"""Consistency checks that keep versions, docs, and architecture rules in line."""

import ast
import re
from pathlib import Path

import image_lab

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "image_lab"

# Modules that must stay Qt-free so the core logic is testable without a GUI.
QT_FREE_MODULES = ["model.py", "files.py", "history.py"]


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


def _imported_top_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_core_modules_do_not_import_qt():
    for name in QT_FREE_MODULES:
        path = PACKAGE / name
        if path.exists():
            assert "PySide6" not in _imported_top_modules(path), f"{name} imports Qt"


def test_every_module_has_docstring():
    for path in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert ast.get_docstring(tree), f"{path.name} has no module docstring"
