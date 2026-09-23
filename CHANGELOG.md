# Changelog

All notable changes to this project are recorded here. Newest first.
The top entry must match `image_lab.__version__` (enforced by `tests/test_project.py`).

## 0.9.0 - 2026-09-22

Plan 02, step B: undo and redo.

### Added
- Edit > Undo (Ctrl+Z) and Edit > Redo (Ctrl+Y; Ctrl+Shift+Z also works). They cover edge drags (one step per drag), Reset, and padding-color changes. Loading an image starts a new history.
- `image_lab/history.py` (Qt-free): `EditState(edges, fill)` and `History` (push, undo, redo, reset).
- `ImageCanvas.editFinished` (emitted once per drag that changed the edges), `set_edges`, and `is_dragging`.
- Undo and redo do nothing while an edge is being dragged.
- Tests: `tests/test_history.py`; undo and redo tests in `tests/test_app.py`.

## 0.8.0 - 2026-09-22

Plan 02, step A: on-screen Save button and `out/` folder.

### Added
- Toolbar with a split **Save** button. A click saves at once to `out/<stem>_edited.png` in the project folder. If that name is taken, it saves as `_2`, `_3`, and so on; it never overwrites. The arrow opens Save As….
- File > Save (Ctrl+S). The `out/` folder is created on first use and is git-ignored.
- `files.OUT_DIR` and `files.next_free_path`.
- Tests: split-button wiring, shortcuts, numbered quick saves, disabled state, toolbar snapshot, `next_free_path`.

### Changed
- Save As… is now Ctrl+Shift+S (it was Ctrl+S), and its dialog starts in `out/` instead of the original's folder.

## 0.7.0 - 2026-09-22

Prototype milestone 6: polish. This completes the prototype plan.

### Added
- Edit > Reset (Ctrl+R) sets all edges back to zero and refits the view.
- Edit > Padding Color… uses Qt's color dialog, which accepts hex input and has an alpha control. Edit > Transparent Padding goes back to the default. The fill shows in the preview and in exports, and only covers padding.
- The status bar also shows the fill: `Fill transparent`, `#RRGGBB`, or `#RRGGBBAA` when partly transparent.
- Save As, Reset and the padding actions are disabled until an image is loaded.
- README: setup, run, usage table, and check command.
- Tests: reset, disabled states, fill picker (set, cancel, clear, export, persistence), the hex field in the color dialog, and a fill snapshot.

### Changed
- The status line has an extra `|  Fill …` section at the end.
- The fill color is kept across Reset and when a new image is loaded.

## 0.6.0 - 2026-09-22

Prototype milestone 5: export.

### Added
- File > Save As… (Ctrl+S) exports PNG, JPEG, WebP or BMP. It is disabled until an image is loaded.
- The default file name is `<stem>_edited.png` in the original's folder. If no supported extension is typed, the selected filter's extension is added. A typed supported extension takes precedence over the selected filter.
- `files.save_image(img, edges, path, fill=TRANSPARENT)`: applies the edges and flattens onto white for JPEG and BMP. JPEG uses quality 95.
- A successful save shows "Saved to …" in the status bar for 5 s. A failure shows an error box.
- Tests: save tests in `tests/test_files.py` (PNG round trip, JPEG and BMP white flattening, WebP alpha, fill color, unsupported extension, source untouched); dialog, extension handling and export-size checks in `tests/test_app.py`.

## 0.5.0 - 2026-09-22

Prototype milestone 4: edge dragging.

### Added
- Drag any edge of the output box outward to pad or inward to crop. Changes show live.
- Hovering an edge highlights its handle and shows a resize cursor.
- Hold Shift while dragging to move the opposite edge by the same amount (symmetric pad or crop).
- The view stays fixed during a drag and refits when the mouse is released. A resize during a drag doesn't refit either.
- Crops are clamped, so at least 1 original pixel stays visible on each axis.
- Status bar: `Original W×H  |  L … T … R … B …  |  Output W×H`, or "No image".
- The canvas draws the output box over a checkerboard, with a 1 px border and four edge handles. Both preview and export use `model.output_box` and `model.visible_rect`.
- Tests: `tests/test_canvas.py` (hit testing, hover, dragging each side, frozen view, screen-to-image scaling, clamping, Shift, snapshots); status-bar tests in `tests/test_app.py`.

## 0.4.0 - 2026-09-22

Prototype milestone 3: edge model.

### Added
- `image_lab/model.py` (Qt-free):
  - `Edges`: frozen dataclass; positive pads, negative crops.
  - `output_box`, `output_size`, `visible_rect`: the only implementation of the output-box math.
  - `adjust_edge`: moves one side, or with `symmetric` both opposite sides, and clamps so at least 1 original pixel stays visible on each axis.
  - `apply_edges`: builds the result image, with transparent padding by default or a given `fill`.
- `tests/test_model.py`: geometry, zero edges, pad and crop on each side, mixed edits, fill color, clamping, symmetric moves.

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
