# Project status

This is the god's-eye view of the project. Rewrite it at the end of every iteration so that it describes the tree as it is. The decision log is append-only.

## Version / last iteration

- Version: 0.5.0
- Last iteration: prototype milestone 4 (edge dragging, Shift symmetric, status bar).
- Active plan: [plans/01-prototype.md](plans/01-prototype.md), with the user-approved additions listed in the decision log. Next: milestone 5.

## Feature matrix

States: `planned`, `done` (built, automated tests green), `verified` (the user checked it by hand).

| Prototype milestone | State | Notes |
|---|---|---|
| 1. Skeleton window, menu bar, empty-state text | done | Headless tests plus an offscreen launch of `python -m image_lab` |
| 2. Load + display (drag-and-drop, File > Open, fit, EXIF) | done | Drop is tested with synthetic Qt events; a real drag from Explorer and a real phone photo still need a manual check |
| 3. Model + tests (`Edges`, `apply_edges`, clamp) | done | Includes the symmetric move needed for Shift-drag |
| 4. Edge dragging (hover, cursors, live drag, refit on release) | done | Includes Shift for a symmetric drag. Needs a manual check of how the drag feels with a real mouse |
| 5. Export (PNG/JPEG/WebP/BMP) + `test_files.py` | planned | |
| 6. Polish (reset, disabled actions, README) | planned | |

## Module map

| File | Responsibility | Key public names |
|---|---|---|
| `image_lab/__init__.py` | Package marker, version source | `__version__` |
| `image_lab/__main__.py` | Entry point, creates QApplication and MainWindow | `main` |
| `image_lab/app.py` | Main window: menus, status bar, drag-and-drop, open dialog, load error box | `MainWindow`, `status_text`, `dropped_image_path`, `LOAD_ERRORS` |
| `image_lab/canvas.py` | Draws the output box (checkerboard, visible image part, border, handles); hover, hit testing, edge dragging with frozen view, refit on release | `ImageCanvas` (`set_image`, `edges`, `scale`, `origin`, `hovered_edge`, `edgesChanged`), `hit_edge` |
| `image_lab/files.py` | Pillow loading (Qt-free) | `load_image`, `is_image_path`, `IMAGE_EXTENSIONS` |
| `image_lab/qtimage.py` | PIL to `QImage` conversion | `pil_to_qimage` |
| `image_lab/model.py` | Edge model and all output-box geometry (Qt-free) | `Edges`, `output_box`, `output_size`, `visible_rect`, `adjust_edge`, `apply_edges`, `TRANSPARENT`, `SIDES` |
| `tools/check.py` | Gate: ruff check, ruff format check, pytest | `main` |

## Test inventory

| File | Covers |
|---|---|
| `tests/conftest.py` | Fixtures: `qapp` (offscreen QApplication), `artifacts_dir` |
| `tests/test_project.py` | Changelog/status match `__version__`; `model.py`/`files.py` Qt-free; module docstrings present |
| `tests/test_app.py` | GUI: menus, empty state, clean close, load centering and fit, no upscaling, refit on resize, error box on a bad file, drag-enter filtering, drop, open dialog, status-bar format and tracking during a drag |
| `tests/test_canvas.py` | `hit_edge` cases; GUI: hover and cursors, pad and crop on each side, frozen view with refit on release, no refit on resize mid-drag, screen-to-image scaling, crop clamp, Shift symmetric, press off-edge, signal, new image resets edges, snapshots |
| `tests/test_files.py` | Loading: RGBA conversion, transparency, JPEG, EXIF orientation, first GIF frame, bad and missing files |
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
- 2026-09-22: `ruff` added as a dev dependency for lint and format. Reason: the user approved it.
- 2026-09-22: Versioning: `__version__` in `image_lab/__init__.py` is the only source. A feature iteration bumps the minor version, a fix-only iteration bumps the patch, and each iteration is tagged `vX.Y.Z`. Reason: keeps the version, changelog and tags in step.
- 2026-09-22: The user approved two of the plan's optional extras for this plan: Shift for a symmetric drag (milestone 4), and a padding fill-color picker that accepts hex input (milestone 6). Reason: the user's answer at the start of the plan.
- 2026-09-22: Each prototype milestone is its own mini-iteration with a minor version bump, changelog entry, STATUS update and tag (M1 = 0.2.0 through M6 = 0.7.0). Reason: the user chose this; it keeps every commit consistent.
- 2026-09-22: `docs/PLAN.md` moved to `docs/plans/01-prototype.md`; each later user plan is stored as `docs/plans/NN-slug.md`. Reason: keeps a record of what was asked.

## Deviations from plans

- 01-prototype: File > Exit (Ctrl+Q) was added so the File menu isn't empty in milestone 1. It's a standard action with no other effect.

## Open questions

None.

## Known issues

- Tests run only on Python 3.14. The declared floor is 3.10; ruff's `target-version = "py310"` guards syntax but not runtime or API differences.
