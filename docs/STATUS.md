# Project status

This is the god's-eye view of the project. Rewrite it at the end of every iteration so that it describes the tree as it is. The decision log is append-only.

## Version / last iteration

- Version: 0.1.0
- Last iteration: project setup and iteration guardrails (no app code yet).
- Active plan: [plans/01-prototype.md](plans/01-prototype.md). No milestone started.

## Feature matrix

States: `planned`, `done` (built, automated tests green), `verified` (the user checked it by hand).

| Prototype milestone | State | Notes |
|---|---|---|
| 1. Skeleton window, menu bar, empty-state text | planned | |
| 2. Load + display (drag-and-drop, File > Open, fit, EXIF) | planned | |
| 3. Model + tests (`Edges`, `apply_edges`, clamp) | planned | |
| 4. Edge dragging (hover, cursors, live drag, refit on release) | planned | |
| 5. Export (PNG/JPEG/WebP/BMP) + `test_files.py` | planned | |
| 6. Polish (reset, disabled actions, README) | planned | |

## Module map

| File | Responsibility | Key public names |
|---|---|---|
| `image_lab/__init__.py` | Package marker, version source | `__version__` |
| `tools/check.py` | Gate: ruff check, ruff format check, pytest | `main` |

Planned (from the prototype plan): `__main__.py`, `app.py`, `canvas.py`, `model.py`, `files.py`, `qtimage.py`.

## Test inventory

| File | Covers |
|---|---|
| `tests/conftest.py` | Fixtures: `qapp` (offscreen QApplication), `artifacts_dir` |
| `tests/test_project.py` | Changelog/status match `__version__`; `model.py`/`files.py` Qt-free; module docstrings present |

## Decision log

Append-only. Format: date, decision, reason.

- 2026-09-22: The user writes the plans and Claude implements them. Each iteration follows the protocol in `CLAUDE.md`. Reason: the user asked for this working model.
- 2026-09-22: `pil_to_qimage` lives in its own module `image_lab/qtimage.py`, so `files.py` stays free of Qt imports. Reason: the prototype plan allows this, and it keeps the Qt-free rule easy to enforce with a test.
- 2026-09-22: Geometry helpers (output box, visible rect, clamp) live in `model.py`, and both the canvas preview and the export use them. Reason: preview and export can't disagree.
- 2026-09-22: Headless GUI tests run on the Qt `offscreen` platform using PySide6's QtTest (no new dependency). Reason: the user approved it; it gives evidence for GUI behavior.
- 2026-09-22: `tests/conftest.py` sets `QT_QPA_FONTDIR` to the Windows font folder. Reason: without it the offscreen platform finds no fonts and draws every glyph as a box, so snapshots are useless.
- 2026-09-22: `ruff` added as a dev dependency for lint and format. Reason: the user approved it.
- 2026-09-22: Versioning: `__version__` in `image_lab/__init__.py` is the only source. A feature iteration bumps the minor version, a fix-only iteration bumps the patch, and each iteration is tagged `vX.Y.Z`. Reason: keeps the version, changelog and tags in step.
- 2026-09-22: `docs/PLAN.md` moved to `docs/plans/01-prototype.md`; each later user plan is stored as `docs/plans/NN-slug.md`. Reason: keeps a record of what was asked.

## Deviations from plans

None.

## Open questions

None.

## Known issues

- Tests run only on Python 3.14. The declared floor is 3.10; ruff's `target-version = "py310"` guards syntax but not runtime or API differences.
