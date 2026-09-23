# Plan 06: background removal busy overlay, image lock, model in a child process

This plan was drafted by Claude from the user's request and approved by the user. The request, the user's answers and the approved draft are recorded here word for word.

## Request

> Do a full runthrough on the codebase and take it all in. It has changed since you have seen it. Then propose a plan to fix this issue:
>
> Applying remove background is not applying until after the image is dragged out of the window. At which point the background is removed only on the version still in the editor.

## Answers

- Does the editor update on its own after about a minute? "Not sure".
- First run only, or every time? "Not sure".
- While a removal runs, what should Save, Copy and drag-out do? "Disable them, but we need to explain or indicate this to the user somehow."
- Fix the window freezes in this plan too? "Include it".
- Feedback on the first draft: "The status bar is fine, but we can do much better for the user to indicate that work is being done. It should occupy/overlay the image display if the image is frozen to any edit or access."
- Lock editing too, or only exports? "Lock everything."
- Cancel button on the overlay? "Yes, add Cancel (Recommended)".

## Approved plan

### Context

The user's report: after Image > Remove Background, the removal doesn't seem to apply until the image is dragged out of the window. When it does appear, only the editor has it; the dragged-out file keeps its background.

What I found (v0.15.0, `e433f35`, gate green):
- **The result does arrive without any input.** I ran the real BiRefNet model in the real Windows event loop with no mouse input. The matte reached `canvas.set_matte` on the GUI thread 30 ms after `predict` returned, about 45 s after the click, and the canvas repainted with it.
- **Race with drag-out.** `start_drag_out` writes the PNG at once (`export_for_drag` in [app.py](image_lab/app.py)), then enters `QDrag.exec`, a nested event loop. If the removal finishes during the drag, it lands in the editor, but the file was already written without it. This matches the report exactly. Save, Save As and Copy have the same race.
- **The feedback is weak.** The only sign of a run is a status-bar `showMessage`. Any later message replaces it, for example "Saved to …" from a drag-out, which then clears after 5 s. A 45 s run looks as if nothing is happening.
- **The GUI freezes during a run.** A 100 ms GUI timer, measured during a real run, stalled for 4.8 s, 6.2 s, 3.0 s and smaller gaps, about 15 s in total. onnxruntime holds Python's GIL while it creates its session. Clicks made during a freeze all land afterwards.

User decisions:
- While a removal runs, **lock the image completely**: no edits and no exports.
- An **overlay on the image display** shows that work is in progress. The status bar alone is not enough.
- The overlay has a **Cancel** button.
- **Run the model in a separate process** so the window never freezes.

Version **0.16.0**: minor, because behavior changes. Save this plan word for word as `docs/plans/06-removal-busy-overlay.md`, with the user's request and answers.

### Step A: busy overlay and image lock

**Overlay** (`canvas.py`): a new `BusyOverlay(QWidget)`, a child of `ImageCanvas`. It is resized to cover the whole canvas in `resizeEvent` and is hidden when idle.
- **Drawing.**
  - A translucent dark veil (for example `QColor(0, 0, 0, 150)`) over the whole display, so the image is visibly dimmed and frozen.
  - A spinner in the center, driven by a `QTimer` at about 30 fps. It runs only while the overlay is shown, and it repaints only the overlay.
  - A title, "Removing background…".
  - A subtitle, "The image is locked until this finishes."
  - A progress line during the first-use download: "Downloading model (first use only): 42%".
- **Cancel.** A `QPushButton` "Cancel" below the text.
- **Input.** The overlay takes all mouse input, so nothing reaches the canvas underneath.
- **Canvas API.** `ImageCanvas.show_busy(title, detail="")`, `ImageCanvas.hide_busy()`, `ImageCanvas.is_busy`, and a signal `ImageCanvas.cancelRequested`.
- **Invariant 6.** The spinner repaints only the overlay widget. The canvas's own `paintEvent` still draws the cached pixmap, so no conversion happens per frame.

**Lock** (`app.py`). Add a helper `_set_locked(on)`, called by `remove_background` and `_end_removal`.
- **What locks.** All `_image_actions`, `angle_box`, `brush_box`, `undo_action` and `redo_action` are disabled.
- **What stays available.**
  - Open, Paste, Exit and drops stay enabled. Loading a new image cancels the run first (see Cancel below).
  - A second Remove Background is impossible, because its action is in `_image_actions`.
- **Direct calls.** `undo`, `redo`, `reset_edits`, `_orient`, `set_angle`, `set_fill`, `quick_save`, `save_dialog`, `copy_image` and `start_drag_out` also return early while `is_removing`, which covers shortcuts and direct calls.
- **Unlock.** `_update_undo_actions` and the enabled states are restored exactly on unlock.
- **No run during a drag.** `remove_background` refuses to start while `canvas.is_dragging`. A result can then never arrive mid-drag, so the `QTimer` retry path in `_removal_finished` (and `RETRY_MS`) is removed.
- **Status bar.** It keeps its short "Background removed" message at the end. Progress moves to the overlay.

**Cancel**
- **Run ids.** Each run gets a run id (`self._removal_run += 1`). The worker thread's signals carry it: `progress(run, done, total)`, `finished(run, img, matte)`, `failed(run, message)`. The GUI ignores any signal whose run is not the current run. This replaces the `img is self.image` check, and also covers a new image being loaded.
- **What Cancel does** (overlay button, or a new image loaded):
  - sets a `threading.Event` for the run;
  - calls `self.remover.cancel()`, which terminates the child process;
  - bumps the run id;
  - unlocks at once, with no change to the image.
- **During the download**, the progress callback raises `matting.Cancelled` when the event is set. `download_model`'s existing `finally` removes the `.part` file.

### Step B: model in a separate process (matting.py, app.py)

- **New Qt-free class `matting.ProcessRemover`.** It has the same `predict(img) -> matte` interface as `Remover`, plus `cancel()` and `close()`, which both terminate the child.
  - **The child.** On the first `predict` it starts one persistent child process (spawn context, `daemon=True`) running a top-level `matting.serve(conn, path, factory)` loop. The loop builds `factory(path)` (default `Remover`) once, then answers each request with `("ok", matte)` or `("error", message)`. The model loads once per child, and the GPU-to-CPU fallback stays inside the child's `Remover`.
  - **No freeze.** `predict` sends the image and blocks on `conn.recv()`. That call releases the GIL, so the GUI thread keeps running while the child does all the onnxruntime work.
  - **Errors.** An error reply raises `RuntimeError(message)`. If the child dies (`EOFError` or `BrokenPipeError`), `predict` raises `matting.Cancelled` when the stop came from `cancel()`, and otherwise `RuntimeError("Background removal stopped unexpectedly")`. The next `predict` starts a new child; after a Cancel the model reloads, which takes about 13 s.
- **`matting.Cancelled`** is a new exception. `_run_removal` catches it and emits nothing.
- **`MainWindow`** uses `matting.ProcessRemover()`. The existing worker thread stays: it downloads if needed, then calls `self.remover.predict`.
- **`MainWindow.closeEvent`** sets `self._closing`, cancels any run and calls `self.remover.close()`. `_run_removal` emits nothing once `_closing` is set. This also fixes the known issue where a `RuntimeError` is printed when the app closes mid-run.
- **`Remover`** itself is unchanged.
- **No new dependency**: `multiprocessing` is in the standard library.

### Step C: cleanup the user approved earlier (it was waiting on plan 05)

- Remove the unused `ImageCanvas.reset_edges` and `set_edges`.
- Add a test that runs `python -m image_lab` offscreen in a subprocess. It swaps in a `QApplication` subclass whose `exec` records the shown `MainWindow` (title, visibility) through `QTimer.singleShot(0, …)`, then quits. The test asserts exit code 0.
- Delete `tests/_artifacts/probe.png`.

### Tests (write them with the code)

- **`tests/test_app.py`.** The `_FakeRemover` fixture gets no-op `cancel()` and `close()`. While a run is gated:
  - The overlay is visible and covers the canvas.
  - All image actions, the angle box, the brush box, undo and redo are disabled.
  - Direct calls change nothing and write nothing: `quick_save`, `copy_image`, `undo`, `reset_edits`, `rotate_right`, `set_angle`, and a drag-out.
  - Mouse drags on the canvas change no edges and add no strokes.
- **Regression test for the reported bug.** After `_finish_removal`: everything is unlocked, the overlay is hidden, and a drag-out's file contains the matte (right half alpha 0).
- **Cancel.**
  - The overlay button unlocks the image with no matte, adds no undo step, and calls `remover.cancel()`.
  - A late `finished` signal from the cancelled run is ignored.
  - Loading a new image during a run cancels it.
  - A cancel during the download raises `Cancelled` and leaves no `.part` file.
- **Other states.**
  - A failed run unlocks the image and hides the overlay.
  - Download progress shows a percentage on the overlay.
  - `remove_background` is refused mid-drag.
  - `closeEvent` cancels the run and closes the remover.
  - Snapshot of the overlay in `tests/_artifacts/`.
- **`tests/test_canvas.py`.** `show_busy` and `hide_busy`; the overlay follows canvas resizes; mouse input is blocked while busy; the Cancel button emits `cancelRequested`; the spinner timer runs only while the overlay is shown.
- **`tests/test_matting.py`**, run through a real spawned child with a picklable top-level fake factory:
  - `predict` returns the child's matte, and the child's PID differs from the parent's.
  - The model is built once across two calls.
  - An error reply raises.
  - `cancel()` during a slow fake raises `Cancelled`, and the next call recovers.
  - A killed child raises `RuntimeError`.
  - `close()` ends the process.
- **`tests/test_project.py`**: the `__main__` launch test (Step C).

### Files

- `image_lab/canvas.py`: `BusyOverlay`, `show_busy`, `hide_busy`, `is_busy`, `cancelRequested`; remove the two dead methods.
- `image_lab/app.py`: lock, run ids, Cancel, early returns, `closeEvent`, `ProcessRemover`, retry path removed.
- `image_lab/matting.py`: `serve`, `ProcessRemover`, `Cancelled`, cancel check in the download.
- Tests as listed above.
- **Docs.**
  - `docs/plans/06-…md`.
  - CHANGELOG 0.16.0.
  - STATUS: feature row, module map, test inventory, decisions (image locked during removal with an overlay; the model runs in a child process; run ids), and known issues (drop the `RuntimeError` at close).
  - README: the overlay, the lock and Cancel.
  - `__version__`.

### Verification

1. Gate: `.venv/Scripts/python tools/check.py`.
2. Mutation checks: drop the lock, ignore the run id, or run `predict` in-process, and confirm the new tests fail.
3. Real run, the same way as the measurements above: the real model in the real Windows event loop with a 100 ms GUI timer. Expect no gap over about 0.3 s (was 6.2 s), and the matte applied on its own. Then a real Cancel mid-run: the child ends and the image unlocks at once.
4. Open the overlay snapshot and the after-removal snapshot in `tests/_artifacts/`.
5. Manual checks for the user:
   - Run Remove Background on a real photo: the overlay dims the image, the spinner turns smoothly and the window stays responsive.
   - Edits, Save, Copy and drag-out are all unavailable during the run.
   - Cancel works.
   - After it finishes, drag the image out and check that the file is transparent.
   - Close the app mid-run: it should exit at once with no console error.
