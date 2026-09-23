# CLAUDE.md

Guidance for Claude Code in this repository. This file holds rules and protocol and changes rarely. Current project state lives in [docs/STATUS.md](docs/STATUS.md).

## Project

`image_lab` is a small PySide6 + Pillow desktop app for preprocessing images. The user drops an image on the window, drags its edges outward to pad or inward to crop, and exports the result.

- [docs/STATUS.md](docs/STATUS.md): the god's-eye view. It covers version, feature states, module map, test inventory, decision log, deviations, open questions and known issues. Read it first in every session.
- [docs/plans/](docs/plans/): every plan the user has given, stored word for word as `NN-slug.md`. The highest-numbered plan in progress is the active spec.
- [CHANGELOG.md](CHANGELOG.md): what shipped in each version.

## Roles

The user writes the plans. Claude implements them.

- The active plan is the spec. Do not add features, refactors or "improvements" the plan did not ask for.
- If a plan is ambiguous, conflicts with an invariant below, or conflicts with an entry in the STATUS decision log, stop and ask before writing code.
- Anything outside scope that is worth doing goes into STATUS under "Open questions" for the user to decide.

## Environment and commands

Windows 11, Windows Python 3.14 via `py`. Do not run the GUI under WSL: dragging files from Explorer into WSLg apps does not work reliably. The venv is `.venv/` in the project root (git-ignored). The forward-slash paths below work in both PowerShell and Git Bash.

| Task | Command |
|---|---|
| Create venv | `py -m venv .venv` |
| Install (editable, with dev tools) | `.venv/Scripts/python -m pip install -e ".[dev]"` |
| **Gate** (ruff check, ruff format check, pytest) | `.venv/Scripts/python tools/check.py` |
| Auto-format | `.venv/Scripts/python -m ruff format .` |
| Run the app | `.venv/Scripts/python -m image_lab` |
| One test | `.venv/Scripts/python -m pytest tests/test_model.py::test_name -q` |

The declared Python floor is 3.10. Ruff's `target-version = "py310"` flags newer syntax, so do not use 3.11+ features (for example `except*`, `typing.Self`, `tomllib`).

Quote `".[dev]"`: PowerShell otherwise misparses the brackets.

## Invariants

Changing any of these needs the user's explicit approval and an entry in the STATUS decision log.

1. `model.py` and `files.py` never import Qt. `pil_to_qimage` lives in its own module, `qtimage.py`. `tests/test_project.py` enforces this.
2. An edit is `Edges(left, top, right, bottom)` in original-image pixels. Positive means pad, negative means crop. The original image is never modified; edges are applied once, at export.
3. Output box: `x0 = -left`, `y0 = -top`, `x1 = w + right`, `y1 = h + bottom`. The geometry helpers in `model.py` (output box, visible rect, clamp) are the only implementation of this math, and both the canvas preview and the export call them.
4. The output is always at least 1x1. Enforce this by clamping during drags, never by raising.
5. Images are held as RGBA and padding is transparent. Flatten onto white only when saving to a format without alpha (JPEG, BMP).
6. The PIL image is converted to a `QPixmap` once per load, never per repaint.
7. The canvas refits on load, resize, reset and drag release. Never refit during a drag.
8. `ImageCanvas` is a plain `QWidget` with custom painting. Do not use `QGraphicsView`.
9. Ask before adding any dependency beyond PySide6, Pillow, pytest and ruff.

## Iteration protocol

Follow this protocol in full, every iteration.

### Start

1. Read `docs/STATUS.md`.
2. Run `git status`. If the tree is not clean, stop and report what is uncommitted; do not discard it.
3. Run `git log --oneline -5` to confirm where the last iteration ended.
4. Run the gate. It must pass before any change; if it fails, report that first.
5. Save the user's new plan word for word as `docs/plans/NN-slug.md`, with the next number.
6. Read the plan against STATUS and the invariants. List every ambiguity or conflict and ask about them before coding.

### Build

- Work in small steps and run the gate often, not just at the end.
- Write or update tests together with the code, not afterwards.
- If something must deviate from the plan, record it in STATUS under "Deviations from plans" with the reason. Prefer asking over deviating.

### Finish

Every item is required. Do not report an iteration as done with any item open.

1. The gate passes.
2. Every behavior change has a test: pure tests for logic, headless GUI tests for window and canvas behavior.
3. Review docstrings and comments against `git diff`. Fix any that describe old behavior, and remove any that are no longer needed.
4. `__version__` is bumped and `CHANGELOG.md` has a matching top entry (see Versioning).
5. `docs/STATUS.md` is rewritten to match the tree. That means version, feature states, module map, test inventory, new decisions, deviations, open questions and known issues.
6. `README.md` is updated if setup, run steps or user-facing behavior changed.
7. Make one commit for the iteration, then tag it `vX.Y.Z`.

### Report

End each iteration with a short report containing:

- What shipped, mapped to the plan's items.
- Evidence: the gate result, plus which GUI snapshots in `tests/_artifacts/` were opened and what they showed.
- A manual-check list for the user: things headless tests cannot prove, such as a real drag from Explorer, how edge dragging feels, and cursor shapes.
- Open questions.

### Stop and ask when

- The same failure persists after two real attempts at a fix.
- The plan conflicts with an invariant or a logged decision.
- A new dependency seems necessary.
- Performance on large images (over about 50 MP) needs a design change, such as a downscaled preview.
- A change would modify the `Edges` model or its sign convention.

## Versioning

- `image_lab/__init__.py` `__version__` is the single source. `pyproject.toml` reads it dynamically.
- Pre-1.0: an iteration that adds or changes features bumps the minor version (0.2.0, 0.3.0). A fix-only iteration bumps the patch (0.2.1).
- The top `## X.Y.Z - YYYY-MM-DD` entry in `CHANGELOG.md` must equal `__version__`, and STATUS must contain `Version: X.Y.Z`. `tests/test_project.py` enforces both.
- Each iteration's commit is tagged `vX.Y.Z`.
- After a version bump, the editable install picks up the new version on import. `pip show` shows it only after reinstalling.

## Code and comment style

- Every module starts with a docstring that states its responsibility (enforced by a test). Public functions and classes get a short docstring.
- Comments explain why, not what. Use them for non-obvious decisions, Qt quirks and coordinate-system conversions.
- A behavior change updates its docstrings and comments in the same commit.
- No commented-out code. No `TODO` in code unless STATUS has a matching open question.
- Keep code simple and readable, because later iterations build on it. No speculative abstractions and no unrequested configurability.
- Ruff formatting is authoritative; do not hand-format against it.

## Testing

- Pure logic (`model.py`, `files.py`): build small synthetic images in code (for example a 10x6 image with distinct pixel colors). Do not commit binary fixtures unless no alternative exists.
- GUI behavior: mark tests `@pytest.mark.gui` and use the `qapp` fixture from `tests/conftest.py`, which forces `QT_QPA_PLATFORM=offscreen`. Drive input with `PySide6.QtTest.QTest` or by sending events directly. Assert on model state and status-bar text, not on pixels.
- Visual evidence: GUI tests may save `widget.grab()` PNGs into the `artifacts_dir` fixture (`tests/_artifacts/`, git-ignored). Open them with the Read tool and look at them before claiming a visual result.
- Headless tests do not prove real OS drag-and-drop from Explorer, the offscreen platform may differ slightly from the Windows platform plugin, and they do not show how the drag feels. Always list these for manual checking in the report.

## Git

- Default branch `main`. One commit per iteration plus a `vX.Y.Z` tag, unless the user asks for finer commits.
- Never rewrite published history, force-push, or skip hooks.
