# Project status

This is the god's-eye view of the project. Rewrite it at the end of every iteration so that it describes the tree as it is. The decision log is append-only.

## Version / last iteration

- Version: 0.2.0
- Last iteration: prototype milestone 1 (skeleton).
- Active plan: [plans/01-prototype.md](plans/01-prototype.md), with the user-approved additions listed in the decision log. Next: milestone 2.

## Feature matrix

States: `planned`, `done` (built, automated tests green), `verified` (the user checked it by hand).

| Prototype milestone | State | Notes |
|---|---|---|
| 1. Skeleton window, menu bar, empty-state text | done | Headless tests plus an offscreen launch of `python -m image_lab` |
| 2. Load + display (drag-and-drop, File > Open, fit, EXIF) | planned | |
| 3. Model + tests (`Edges`, `apply_edges`, clamp) | planned | |
| 4. Edge dragging (hover, cursors, live drag, refit on release) | planned | |
| 5. Export (PNG/JPEG/WebP/BMP) + `test_files.py` | planned | |
| 6. Polish (reset, disabled actions, README) | planned | |

## Module map

| File | Responsibility | Key public names |
|---|---|---|
| `image_lab/__init__.py` | Package marker, version source | `__version__` |
| `image_lab/__main__.py` | Entry point, creates QApplication and MainWindow | `main` |
| `image_lab/app.py` | Main window: menus | `MainWindow` |
| `image_lab/canvas.py` | Central widget; currently only the empty state | `ImageCanvas` |
| `tools/check.py` | Gate: ruff check, ruff format check, pytest | `main` |

Planned (from the prototype plan): `model.py`, `files.py`, `qtimage.py`.

## Test inventory

| File | Covers |
|---|---|
| `tests/conftest.py` | Fixtures: `qapp` (offscreen QApplication), `artifacts_dir` |
| `tests/test_project.py` | Changelog/status match `__version__`; `model.py`/`files.py` Qt-free; module docstrings present |
| `tests/test_app.py` | GUI: window title and menus, empty-state snapshot, clean close |

## Decision log

Append-only. Format: date, decision, reason.

- 2026-09-22: The user writes the plans and Claude implements them. Each iteration follows the protocol in `CLAUDE.md`. Reason: the user asked for this working model.
- 2026-09-22: `pil_to_qimage` lives in its own module `image_lab/qtimage.py`, so `files.py` stays free of Qt imports. Reason: the prototype plan allows this, and it keeps the Qt-free rule easy to enforce with a test.
- 2026-09-22: Geometry helpers (output box, visible rect, clamp) live in `model.py`, and both the canvas preview and the export use them. Reason: preview and export can't disagree.
- 2026-09-22: Headless GUI tests run on the Qt `offscreen` platform using PySide6's QtTest (no new dependency). Reason: the user approved it; it gives evidence for GUI behavior.
- 2026-09-22: `tests/conftest.py` sets `QT_QPA_FONTDIR` to the Windows font folder. Reason: without it the offscreen platform finds no fonts and draws every glyph as a box, so snapshots are useless.
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
