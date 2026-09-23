# Project status

This is the god's-eye view of the project. Rewrite it at the end of every iteration so that it describes the tree as it is. The decision log is append-only.

## Version / last iteration

- Version: 0.9.0
- Last iteration: plan 02 step B (undo/redo).
- Active plan: [plans/02-save-undo-clipboard-dragout.md](plans/02-save-undo-clipboard-dragout.md). Next: step C (copy/paste). Plan 01 is complete apart from its manual checks.

## Feature matrix

States: `planned`, `done` (built, automated tests green), `verified` (the user checked it by hand).

| Prototype milestone | State | Notes |
|---|---|---|
| 1. Skeleton window, menu bar, empty-state text | done | Headless tests plus an offscreen launch of `python -m image_lab` |
| 2. Load + display (drag-and-drop, File > Open, fit, EXIF) | done | Drop is tested with synthetic Qt events; a real drag from Explorer and a real phone photo still need a manual check |
| 3. Model + tests (`Edges`, `apply_edges`, clamp) | done | Includes the symmetric move needed for Shift-drag |
| 4. Edge dragging (hover, cursors, live drag, refit on release) | done | Includes Shift for a symmetric drag. Needs a manual check of how the drag feels with a real mouse |
| 5. Export (PNG/JPEG/WebP/BMP) + `test_files.py` | done | Export size is checked against the status bar for all four formats. Opening the exports in another viewer is still a manual check |
| 6. Polish (reset, disabled actions, README) | done | Also includes the padding fill-color picker (hex and alpha) |

| Plan 02 feature | State | Notes |
|---|---|---|
| A. Save button (one click to `out/`, arrow for Save As) | done | Needs a manual check of the split-button arrow on the real Windows style |
| B. Undo / redo (Ctrl+Z / Ctrl+Y) | done | |
| C. Copy / paste (Ctrl+C / Ctrl+V) | planned | |
| D. Drag the edited image out | planned | |

## Module map

| File | Responsibility | Key public names |
|---|---|---|
| `image_lab/__init__.py` | Package marker, version source | `__version__` |
| `image_lab/__main__.py` | Entry point, creates QApplication and MainWindow | `main` |
| `image_lab/app.py` | Main window: menus and toolbar with the split Save button (image-only actions disabled until load), status bar, drag-and-drop, open, save and color dialogs, error boxes | `MainWindow` (`load_path`, `save_to`, `quick_save`, `set_fill`, `choose_fill`, `undo`, `redo`, `reset_edges`, `history`), `status_text`, `fill_label`, `dropped_image_path`, `SAVE_FILTERS`, `LOAD_ERRORS`, `COLOR_DIALOG_OPTIONS` |
| `image_lab/canvas.py` | Draws the output box (checkerboard, fill over the padding, visible image part, border, handles); hover, hit testing, edge dragging with frozen view, refit on release | `ImageCanvas` (`set_image`, `reset_edges`, `set_edges`, `set_fill`, `is_dragging`, `editFinished`, `edges`, `fill`, `scale`, `origin`, `hovered_edge`, `edgesChanged`), `hit_edge` |
| `image_lab/files.py` | Pillow loading and saving (Qt-free) | `load_image`, `save_image`, `ensure_extension`, `next_free_path`, `OUT_DIR`, `is_image_path`, `IMAGE_EXTENSIONS`, `SAVE_FORMATS` |
| `image_lab/qtimage.py` | PIL to `QImage` conversion | `pil_to_qimage` |
| `image_lab/history.py` | Undo/redo stack of edit states (Qt-free) | `EditState`, `History` |
| `image_lab/model.py` | Edge model and all output-box geometry (Qt-free) | `Edges`, `output_box`, `output_size`, `visible_rect`, `adjust_edge`, `apply_edges`, `TRANSPARENT`, `SIDES` |
| `tools/check.py` | Gate: ruff check, ruff format check, pytest | `main` |

## Test inventory

| File | Covers |
|---|---|
| `tests/conftest.py` | Fixtures: `qapp` (offscreen QApplication), `artifacts_dir` |
| `tests/test_project.py` | Changelog/status match `__version__`; `model.py`/`files.py`/`history.py` Qt-free; module docstrings present |
| `tests/test_app.py` | GUI: menus, empty state, clean close, load centering and fit, no upscaling, refit on resize, error box on a bad file, drag-enter filtering, drop, open dialog, status-bar format and tracking during a drag, Save enabled state, save-dialog default name and filters, export size equal to the status bar in each format, save error box, image-only actions disabled until load, Reset, `fill_label`, fill picker (set, cancel, clear, export, kept across reset and load), hex field in the color dialog, fill snapshot, Save split button, save shortcuts, numbered quick saves into `out/` (redirected to a temp folder by an autouse fixture), toolbar snapshot, undo/redo of drags, Reset and fill, one step per drag, no step for an unchanged drag, redo cleared by a new edit, history cleared on load, undo ignored mid-drag |
| `tests/test_canvas.py` | `hit_edge` cases; GUI: hover and cursors, pad and crop on each side, frozen view with refit on release, no refit on resize mid-drag, screen-to-image scaling, crop clamp, Shift symmetric, press off-edge, signal, new image resets edges, snapshots |
| `tests/test_files.py` | Loading: RGBA conversion, transparency, JPEG, EXIF orientation, first GIF frame, bad and missing files. Saving: `ensure_extension`, PNG round trip, JPEG and BMP white flattening, WebP alpha, fill color, unsupported extension, source untouched; `next_free_path` |
| `tests/test_history.py` | `History`: empty state, round trip, redo cleared by push, duplicate pushes ignored, fill as its own step, reset |
| `tests/test_model.py` | Geometry helpers; `apply_edges` with zero edges, pad and crop on each side, mixed edits, fill color, RGB input; `adjust_edge` clamping (including opposite crop and opposite pad) and symmetric moves |
| `tests/test_qtimage.py` | `pil_to_qimage` size, pixels, alpha, memory ownership |

## Decision log

Append-only. Format: date, decision, reason.

- 2026-09-22: The user writes the plans and Claude implements them. Each iteration follows the protocol in `CLAUDE.md`. Reason: the user asked for this working model.
- 2026-09-22: `pil_to_qimage` lives in its own module `image_lab/qtimage.py`, so `files.py` stays free of Qt imports. Reason: the prototype plan allows this, and it keeps the Qt-free rule easy to enforce with a test.
- 2026-09-22: Geometry helpers (output box, visible rect, clamp) live in `model.py`, and both the canvas preview and the export use them. Reason: preview and export can't disagree.
- 2026-09-22: Headless GUI tests run on the Qt `offscreen` platform using PySide6's QtTest (no new dependency). Reason: the user approved it; it gives evidence for GUI behavior.
- 2026-09-22: `tests/conftest.py` sets `QT_QPA_FONTDIR` to the Windows font folder. Reason: without it the offscreen platform finds no fonts and draws every glyph as a box, so snapshots are useless.
- 2026-09-22: `load_image` raises and `MainWindow.load_path` shows the error box, so `files.py` stays Qt-free. Load errors caught: `UnidentifiedImageError`, `OSError`, `DecompressionBombError`. Reason: invariant 1.
- 2026-09-22: Drag-and-drop is handled on `MainWindow`, not the canvas. Reason: the plan allows either, and the window owns loading.
- 2026-09-22: The clamp rule keeps at least 1 original pixel visible on each axis (`w + min(left,0) + min(right,0) >= 1`), not just a 1x1 output. Reason: the plan's rule alone allows cropping the whole image away while padding the opposite side (for example, left = -w and right = +5 gives an all-padding output). The plan says the image must not be croppable to nothing. The stricter rule still implies output >= 1x1. `Edges` itself is unchanged.
- 2026-09-22: Drag math lives in `model.adjust_edge(size, start, side, amount, symmetric)`, where `amount` means outward movement in image pixels. The canvas only converts screen movement into that amount. Reason: the drag and clamp logic can be tested without a GUI.
- 2026-09-22: The status-bar text is `status_text(size, edges)` in `app.py`. The plan's example line says "Output 1840×1160", but the correct height for those edges is 1080 + 0 + 40 = 1120; the code and tests use the correct math. Reason: the example had an arithmetic slip.
- 2026-09-22: `save_image` takes an optional `fill` argument (default transparent), in addition to the plan's `(img, edges, path)`. Reason: the approved fill-color picker needs it; existing callers are unaffected.
- 2026-09-22: Save-path rules: a typed supported extension (png, jpg, jpeg, webp, bmp) sets the format even if another filter is selected. Otherwise the selected filter's extension is appended ("my.photo" becomes "my.photo.webp"). WebP uses Pillow's default settings. Reason: the plan only covers the no-extension case; this is the least surprising way to extend it.
- 2026-09-22: `ruff` added as a dev dependency for lint and format. Reason: the user approved it.
- 2026-09-22: Versioning: `__version__` in `image_lab/__init__.py` is the only source. A feature iteration bumps the minor version, a fix-only iteration bumps the patch, and each iteration is tagged `vX.Y.Z`. Reason: keeps the version, changelog and tags in step.
- 2026-09-22: The user approved two of the plan's optional extras for this plan: Shift for a symmetric drag (milestone 4), and a padding fill-color picker that accepts hex input (milestone 6). Reason: the user's answer at the start of the plan.
- 2026-09-22: Each prototype milestone is its own mini-iteration with a minor version bump, changelog entry, STATUS update and tag (M1 = 0.2.0 through M6 = 0.7.0). Reason: the user chose this; it keeps every commit consistent.
- 2026-09-22: `docs/PLAN.md` moved to `docs/plans/01-prototype.md`; each later user plan is stored as `docs/plans/NN-slug.md`. Reason: keeps a record of what was asked.
- 2026-09-22: The padding fill is view state on `ImageCanvas` (`fill`), not part of `Edges`. It is kept across Reset and when a new image loads, and it covers only the padding: export pastes the image over the fill, and the preview subtracts the image area before painting the fill. CLAUDE.md invariant 5 was reworded to match. Reason: the user approved the fill picker; keeping it out of `Edges` leaves the edge model unchanged.
- 2026-09-22: Hex input for the fill comes from Qt's own `QColorDialog` (`DontUseNativeDialog` plus `ShowAlphaChannel`). Its "HTML" field accepts `#RRGGBB`, and alpha is a separate control. The status bar shows `#RRGGBB`, or `#RRGGBBAA` in CSS order when the fill is partly transparent. Reason: this meets the hex request without adding a custom dialog.
- 2026-09-22: The status line has a `|  Fill …` section after the plan's three sections. Reason: the fill affects the export, so it should be visible.

- 2026-09-22: Plan 02 is done in four steps, each with its own minor version (A 0.8.0, B 0.9.0, C 0.10.0, D 0.11.0). Reason: same approach the user chose for plan 01.
- 2026-09-22: `OUT_DIR` is `<project>/out`, derived from the package location (`image_lab/files.py`). It is git-ignored and created on first use. Reason: the user asked for "a folder called out in the image_lab directory"; the install is editable, so the package location gives the project folder.
- 2026-09-22: Ctrl+S is now one-click Save and Ctrl+Shift+S is Save As…. The Save As dialog starts in `out/`. Reason: the user asked for a one-click save defaulting to `out/`; these are the standard Windows shortcuts. This replaces plan 01's Ctrl+S for Save As and its "original's folder" default.
- 2026-09-22: Quick save never overwrites. It numbers the name instead (`_2`, `_3`, …). Reason: one click with no dialog must not destroy earlier exports.

- 2026-09-22: Undo history lives in `MainWindow` as a `History` of `EditState(edges, fill)`. One drag is one step (via `ImageCanvas.editFinished`). Reset and fill changes are steps too. Loading an image resets the history, with the current fill as its first state. Reason: the user chose "edits only"; a Qt-free history can be tested without a GUI.

## Deviations from plans

- 01-prototype: File > Exit (Ctrl+Q) was added so the File menu isn't empty in milestone 1. It's a standard action with no other effect.

## Open questions

- Manual checks still owed by the user before the prototype counts as `verified`: a real drag from File Explorer; a real sideways phone photo; how edge dragging feels, including cursors and Shift; exported files opening correctly in another viewer; the color dialog's hex field on the real Windows platform.

## Known issues

- Tests run only on Python 3.14. The declared floor is 3.10; ruff's `target-version = "py310"` guards syntax but not runtime or API differences.
