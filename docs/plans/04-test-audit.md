# Plan 04: test audit fixes

The user's instruction, word for word: "Lets make these changes."

It approves the proposal at the end of the test audit Claude ran on v0.14.0, reproduced here as the spec:

Make this a fix-only iteration, **0.14.1**, following the full protocol:

- Fix items 1–6:
  1. `test_core_modules_do_not_import_qt` only checks the top-level import name, so an indirect Qt import (for example `files.py` importing `image_lab.qtimage`) passes, and a renamed module passes without checking anything. Import each module in a subprocess and assert no `PySide6` module was loaded.
  2. `tests/conftest.py` uses `os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")`, so a preset variable opens real windows. Force offscreen.
  3. `test_save_does_not_modify_source` only checks the size, not the pixels.
  4. `test_bad_file_shows_error_and_keeps_state` only runs with no image loaded; keeping the current image after a failed load is never tested.
  5. `test_image_actions_disabled_until_loaded` leaves out the copy, quick save, paint and brush actions.
  6. `test_every_module_has_docstring` only scans `image_lab/`, but CLAUDE.md says every module.
- Add the untested-behavior tests:
  - Reset during a drag is ignored.
  - The angle box during a drag snaps back to the current angle.
  - Corrupt clipboard PNG data falls back to the bitmap.
  - Drag-out when the save fails starts no drag.
  - `out/` cannot be created: error box.
  - Dropping a non-local URL (such as `http://…`) is ignored.
  - `leaveEvent`: hides the brush circle and clears the hover.
  - Mouse input with the wrong button, or on an empty canvas.
  - `DecompressionBombError` handling in `LOAD_ERRORS`.
- Add the two invariant tests:
  - Invariant 6: `canvas._pixmap` stays the same object across a turn, a free angle, undo and repaint.
  - Invariant 4: a brute-force loop over small sizes, sides and amounts for `adjust_edge` and `clamp_edges`, proving at least 1 pixel stays visible and that clamping twice changes nothing.
- Move the mouse helpers into `conftest.py`.
- Log the dead canvas methods (`ImageCanvas.reset_edges`, `set_edges`) and the untested `__main__` as open questions and leave the code alone.
