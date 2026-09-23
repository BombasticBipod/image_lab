# Changelog

All notable changes to this project are recorded here. Newest first.
The top entry must match `image_lab.__version__` (enforced by `tests/test_project.py`).

## 0.15.0 - 2026-09-23

Plan 05: background removal to alpha.

### Added
- Image > Remove Background: a BiRefNet model (the MIT-licensed ONNX export `onnx-community/BiRefNet-ONNX`, pinned to one revision) predicts a soft alpha matte for the original image, and the background becomes transparent. Its RGB is kept under alpha 0, the same as painted pixels. It is one undo step, and Reset clears it.
- The model runs on a worker thread, so the window stays responsive. The status bar shows progress, and the action is disabled while a run is in progress. A result for an image that has since been replaced is discarded, and a result that arrives during an edge drag or stroke waits for it to end.
- The first run downloads the model (973 MB) with the standard library into `%LOCALAPPDATA%\image_lab\models\`. The download goes to a `.part` file that is renamed only when complete.
- onnxruntime tries DirectML (GPU) first. If the GPU fails, for example by running out of memory on a 4 GB card, it falls back to the CPU and stays there.
- The paint brush works on top of the removal: right-drag brings removed background back, and left-drag removes more.
- New optional extra `bg` (`onnxruntime-directml`, `numpy`). Without it the action explains how to install it.
- New Qt-free module `image_lab/matting.py` with tests (`tests/test_matting.py`), plus model, history, files and GUI tests for the matte. An opt-in test runs the real model when `IMAGE_LAB_MODEL_TESTS=1` is set.

### Changed
- Export order is now: background matte, paint mask, orientation, edges (`model.render`). CLAUDE.md invariants 1, 2 and 9 were updated with the user's one-time approval for this plan.

## 0.14.1 - 2026-09-23

Plan 04: fixes from a full test audit. Tests only; the app's behavior is unchanged.

### Fixed
- The Qt-free check now imports `model`, `files` and `history` in a fresh interpreter and fails if any `PySide6` module was loaded. Before, it only read each file's top-level import names, so an indirect Qt import (through another `image_lab` module) passed, and a renamed module passed without being checked.
- `tests/conftest.py` now forces `QT_QPA_PLATFORM=offscreen` instead of only setting a default, so a value left in the shell can't make the GUI tests open real windows.
- The module docstring check now covers `tests/` and `tools/` as well as the package.
- `test_save_does_not_modify_source` compares the source's pixels, not just its size, with every kind of edit applied.
- `test_image_actions_disabled_until_loaded` now covers every image-only action (quick save, copy, paint, brush size) and the Save button.

### Added
- Tests: a failed load keeps the current image and its edits; `DecompressionBombError` shows the error box; non-local URLs are neither accepted nor loaded when dropped; an error box when `out/` can't be created; Reset and the angle box are ignored during a drag and record no undo step; corrupt clipboard PNG data falls back to the bitmap; a drag-out whose save fails starts no drag.
- Tests for the canvas: leaving the widget clears the hover and hides the brush circle, but keeps the edge being dragged; right and middle buttons don't drag edges, drag the image out or paint; releasing another button doesn't end a drag or a stroke; mouse input on an empty canvas does nothing.
- Invariant tests: the pixmap from load is reused through turns, flips, free angles, drags, paint, undo, Reset and repaints (invariant 6); exhaustive checks on small images that `adjust_edge` and `clamp_edges` always keep a visible pixel, only reduce crops as much as needed, and give the same result when applied twice (invariant 4).

### Changed
- The synthetic mouse helpers (`send_mouse`, `mouse_drag`, `edge_point`, `drag_edge`) now live in `tests/conftest.py`, replacing six copies across `tests/test_app.py` and `tests/test_canvas.py`.

## 0.14.0 - 2026-09-22

Plan 03, step C: paint to transparency. This completes plan 03.

### Added
- Image > Paint Transparency (B), also on the toolbar: in paint mode, left-drag erases pixels to transparent and right-drag restores them. The brush is hard and round; the toolbar **Brush** box sets its diameter in image pixels, and `[` and `]` shrink or grow it. A circle shows the brush under the cursor.
- The preview shows painted pixels at 50% transparency. The export makes them fully transparent and keeps their original RGB, for inpainting tools that read it. JPEG and BMP flatten them onto white like other transparent pixels.
- Strokes are stored in original-image pixels, so they stay on the same pixels through turns, flips and free angles. Each stroke is one undo step; Reset and loading a new image clear them.
- `model.Stroke`, `render_mask`, `apply_mask`; `render` and `save_image` take `strokes`; `EditState.strokes`; `qtimage.mask_to_qimage`; `ImageCanvas` paint mode (`set_paint_mode`, `set_brush_size`, `set_strokes`, `strokeFinished`); `MainWindow.set_paint_mode`, `brush_smaller`, `brush_larger`.
- Tests: mask drawing, restore order, RGB and partial alpha kept, mask before orientation and through a free angle in `tests/test_model.py`; painted PNG and BMP in `tests/test_files.py`; a stroke undo step in `tests/test_history.py`; paint mode, strokes, restore, painting after a turn, disabled edges and drag-out, undo, Reset, load, save and a snapshot in `tests/test_app.py`.

### Changed
- In paint mode the edge handles are hidden and edge dragging and drag-out are off.
- Reset and undo are ignored while a stroke is in progress, like during an edge drag.

## 0.13.0 - 2026-09-22

Plan 03, step B: free-angle rotation.

### Added
- Toolbar **Angle** box: clockwise rotation from -180° to 180° in 0.1° steps. A typed value applies on Enter or when the box loses focus; the arrows apply each step. Every change is one undo step, and the box follows turns, flips, undo, Reset and loading.
- Free angles resample bicubically. The corners the rotation uncovers are transparent, and the padding fill does not cover them.
- `model.clamp_edges`: when the view image changes size, crops too deep for it are reduced so at least one pixel stays visible. `MainWindow.set_angle`.
- Tests: free-angle sizes, Pillow's affine convention against the exact transposes, corners, RGB kept under transparency, fill versus corners and `clamp_edges` in `tests/test_model.py`; the angle box in `tests/test_app.py`.

### Changed
- `model.apply_transform` resamples the color and alpha channels separately, because Pillow's RGBA resampling blackens the RGB under fully transparent pixels.

## 0.12.0 - 2026-09-22

Plan 03, step A: rotate by 90° and flip.

### Added
- Image menu and toolbar: Rotate Left (Ctrl+[), Rotate Right (Ctrl+]), Flip Horizontal, Flip Vertical. They act on what is on screen, and the edge edits turn with the image, so the output is turned or flipped as a whole.
- Turns and flips are undo steps. A newly loaded image starts upright.
- `model.Transform` (mirror plus clockwise angle) with `rotated`, `flipped_h`, `flipped_v`, `transformed_size`, `affine`, `invert`, `map_point`, `view_to_source`, `apply_transform`, `rotate_edges`, `flip_edges_h`, `flip_edges_v`, and `render`, the single export path (orientation, then edges and fill).
- `ImageCanvas.transform` and `set_transform`; `EditState.transform`; `save_image` and `status_text` take a `transform`.
- Tests: orientation math and pixels in `tests/test_model.py`, an orientation undo step in `tests/test_history.py`, a turned save in `tests/test_files.py`, and actions, exports, edges, undo, Reset and snapshots in `tests/test_app.py`.

### Changed
- Edges are measured in pixels of the turned or flipped image. The status bar's output size follows the turned image.
- Edit > Reset also sets the image upright (`MainWindow.reset_edges` is now `reset_edits`).
- The preview draws the loaded pixmap through the model's orientation matrix, so no pixmap is rebuilt per turn.

## 0.11.0 - 2026-09-22

Plan 02, step D: drag the edited image out. This completes plan 02.

### Added
- Press inside the image (away from the edge handles) and drag to take the edited image out of the window. The image is dragged as a PNG file in `out/` (`<stem>_edited.png`, next free name), with bitmap data attached for apps that want pixels. The file is reused for later drags while the image, edges and fill are unchanged.
- Hovering inside the image shows an open-hand cursor.
- `ImageCanvas.dragOutRequested`; `MainWindow.export_for_drag` and `start_drag_out`.
- The window ignores drops of its own drag-out, so the image doesn't reload itself.
- Tests: drag-out threshold, edge versus interior press, and the interior cursor in `tests/test_canvas.py`; drag content, file reuse and ignoring its own drop in `tests/test_app.py`.

### Changed
- Quick save and drag-out share `MainWindow._next_out_path`.

## 0.10.0 - 2026-09-22

Plan 02, step C: copy and paste.

### Added
- Edit > Copy Image (Ctrl+C) puts the edited image (edges and fill applied) on the clipboard, as a bitmap and as PNG data. Apps that read the PNG data keep the transparency.
- Edit > Paste Image (Ctrl+V) pastes an image file copied in Explorer, or image data such as a screenshot. It prefers PNG data, which keeps transparency. The pasted image replaces the current one with fresh edges and history. It is named "pasted", so the Save button writes `pasted_edited.png`. With no image on the clipboard, the status bar says so and nothing changes.
- `qtimage.qimage_to_pil`, `files.png_bytes`. `files.load_image` also accepts a binary stream.
- Tests: conversions (alpha, padded rows), PNG bytes, and copy/paste in `tests/test_app.py`.

### Changed
- `MainWindow.load_path` now shares `_show_image` with paste. The export stem comes from `MainWindow.image_name`.

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
