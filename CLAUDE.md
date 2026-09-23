# CLAUDE.md

Guidance for Claude Code in this repository.

## Project

`image_lab` is a small PySide6 + Pillow desktop app for preprocessing images. The prototype scope: drag an image in, drag its four edges to pad (outward) or crop (inward), export. The full spec and milestone list live in [docs/PLAN.md](docs/PLAN.md). Read it before starting a milestone; it is the source of truth for behavior.

Out of scope for the prototype: undo, rotate, resize, batch mode, zoom tools. Do not add them unasked.

## Environment

- Windows 11, Windows Python (3.14 installed via `py`). Do not run the GUI under WSL.
- Venv lives at `.venv/` in the project root (git-ignored).
- Setup: `py -m venv .venv` then `.venv\Scripts\python -m pip install -e .[dev]`
- Run app: `.venv\Scripts\python -m image_lab`
- Run tests: `.venv\Scripts\python -m pytest`
- Single test: `.venv\Scripts\python -m pytest tests/test_model.py::test_name -q`

The GUI cannot be verified from tests alone. For milestones that change UI behavior, say what needs manual checking (drag-and-drop from Explorer, edge dragging, cursors) rather than claiming it works.

## Architecture

```
image_lab/
  __main__.py   entry point (python -m image_lab); defines main()
  app.py        MainWindow: menus, status bar, drag-and-drop, file dialogs
  canvas.py     ImageCanvas(QWidget): paintEvent, hit testing, edge dragging
  model.py      Edges dataclass, apply_edges(), clamp helper. Pure Pillow.
  files.py      load_image(), save_image(). Pure Pillow.
tests/          pytest, no GUI
```

Hard rules:

- `model.py` and `files.py` must not import Qt. `pil_to_qimage` is the only Qt-touching conversion helper; keep it isolated (own small module or clearly separated section) so the core stays testable headless.
- The original image is never modified. All edits are an `Edges(left, top, right, bottom)` in original-image pixels: positive = pad, negative = crop. Export applies edges once via `apply_edges`.
- Output box: `x0=-left, y0=-top, x1=w+right, y1=h+bottom`. Preview (Qt) and export (Pillow) both derive from this same math. Keep them in sync.
- Output must stay at least 1x1. Enforce by clamping during drags, never by raising.
- Work in RGBA. Pad is transparent. Flatten onto white only when saving to JPEG/BMP.
- Convert PIL to QPixmap once on load, not per repaint.
- Canvas refits on load, resize, reset, and drag release. Never refit mid-drag.
- `ImageCanvas` is a plain `QWidget` with custom painting. No `QGraphicsView`.

## Workflow

- Work milestone by milestone in the order in PLAN.md. Finish and verify one before starting the next.
- Commit after each milestone, on its own commit, with a clear message.
- Ask before: adding any dependency beyond PySide6/Pillow/pytest, changing the `Edges` model or its sign convention, or adding a downscaled-preview path for huge images.
- Keep code simple and readable; later features build on it. Match existing style; no speculative abstractions.
- Write tests for pure logic (`model.py`, `files.py`) using small synthetic images built in code. Do not commit binary fixtures unless unavoidable.
