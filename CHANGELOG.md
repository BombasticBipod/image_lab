# Changelog

All notable changes to this project are recorded here. Newest first.
The top entry must match `image_lab.__version__` (enforced by `tests/test_project.py`).

## 0.3.0 - 2026-09-22

Prototype milestone 2: load and display.

### Added
- Load images by dragging from File Explorer or with File > Open… (Ctrl+O). Accepted extensions: png, jpg, jpeg, bmp, gif, webp, tif, tiff.
- `files.load_image`: returns upright RGBA; applies EXIF orientation; animated GIFs use the first frame.
- `qtimage.pil_to_qimage`: converts once per load; the canvas keeps the resulting `QPixmap`.
- The canvas centers the image, scales it to fit within 80% of the widget (never enlarges it), refits on resize, and shows a checkerboard behind transparent pixels.
- Unreadable files show a warning box, and the current image is kept.
- Tests: `tests/test_files.py` (loading), `tests/test_qtimage.py`, more GUI tests in `tests/test_app.py`.

## 0.2.0 - 2026-09-22

Prototype milestone 1: skeleton.

### Added
- `python -m image_lab` opens a window with File and Edit menus, and File > Exit (Ctrl+Q).
- `ImageCanvas` shows centered "Drop an image here" text on a dark background.
- Headless GUI tests in `tests/test_app.py`.

## 0.1.0 - 2026-09-22

### Added
- Project setup: `pyproject.toml` (PySide6, Pillow; dev: pytest, ruff), README, `.gitignore`, `.gitattributes`.
- Prototype plan in `docs/plans/01-prototype.md`.
- Iteration guardrails: `CLAUDE.md` protocol, `docs/STATUS.md` project state, this changelog.
- Gate script `tools/check.py` (ruff check, ruff format check, pytest).
- Headless Qt test setup in `tests/conftest.py` (offscreen platform with Windows fonts, `qapp` and `artifacts_dir` fixtures).
- Consistency tests in `tests/test_project.py`: version matches changelog and status, core modules stay Qt-free, every module has a docstring.
