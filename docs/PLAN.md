# image_lab — Prototype Plan

## Goal

A small desktop app for preprocessing images. For this prototype the user can:

1. Drag an image file from File Explorer onto the window.
2. See it displayed centered in the window.
3. Drag any of the 4 edges outward to **pad** that side, or inward to **crop** that side.
4. Save/export the result.

Anything not on this list (undo, rotate, resize, batch mode, zoom tools) is out of scope for now. Keep the code simple and readable, since we will build on it.

## Tech choices

| Piece | Choice | Why |
|---|---|---|
| Language | Python 3.10+ | Team standard |
| GUI | **PySide6** (Qt 6, LGPL) | Mature, first-class drag-and-drop, custom painting, file dialogs. Official Qt binding. |
| Image I/O + export | **Pillow** | Loading, EXIF orientation, the actual crop/pad, saving |
| Tests | pytest | For the pure image logic |

Install:

```
pip install PySide6 Pillow pytest
```

**Environment note:** run the app with a **Windows** Python install (a venv in the project folder is fine), not inside WSL. Dragging files from Windows File Explorer into a Linux GUI app running under WSLg does not work reliably. The code can still live anywhere you like; only the interpreter that launches the GUI matters.

## Project layout

```
image_lab/
  pyproject.toml
  README.md
  image_lab/
    __init__.py
    __main__.py      # entry point: python -m image_lab
    app.py           # MainWindow: menus, status bar, drag-and-drop, save dialog
    canvas.py        # ImageCanvas widget: drawing + edge-drag interaction
    model.py         # Edges dataclass + apply_edges() (pure Pillow, no Qt)
    files.py         # load_image(), save_image(), pil_to_qimage()
  tests/
    test_model.py
    test_files.py
```

Rule of thumb: **`model.py` and `files.py` must not import Qt** (except `pil_to_qimage`, which can live in its own tiny section or file). That keeps the core logic testable without a GUI.

## Core concept: the edge model

Store the edit as four integers, in **original image pixels**:

```python
@dataclass
class Edges:
    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0
```

- Positive value = pad that side by N pixels.
- Negative value = crop that side by N pixels.
- Zero = unchanged.

Everything else derives from one "output box" in original-image coordinates:

```
x0 = -left
y0 = -top
x1 = width  + right
y1 = height + bottom
output size = (x1 - x0, y1 - y0)
```

Constraint: the output must be at least 1×1, i.e. `width + left + right >= 1` and `height + top + bottom >= 1`. Enforce this with clamping during drags, not by throwing errors.

The original image is **never modified**. We only change `Edges`, and apply them once at export time. Reset = set edges back to zero.

### `apply_edges(img, edges, fill) -> Image`

Pure Pillow, no Qt:

1. Compute the output box as above.
2. Create a new image of the output size in the right mode (see "Pad fill" below) filled with `fill`.
3. Compute the part of the original that is still visible (the intersection of `(0, 0, w, h)` with the output box). If crops remove everything on an axis, the constraint above prevents that.
4. `img.crop(visible_rect)` and paste it into the new image at `(visible_rect.left - x0, visible_rect.top - y0)`.
5. Return the new image.

### Pad fill

- Prototype default: **transparent** padding. Work in `RGBA` (convert on load if the image has no alpha).
- On export to a format without alpha (JPEG, BMP), flatten onto **white** before saving.
- A fill-color picker is a nice-to-have, not required.

## Loading (drag and drop)

In `MainWindow` (or the canvas):

- `setAcceptDrops(True)`.
- `dragEnterEvent`: accept only if `mimeData().hasUrls()` and the first URL is a local file with an image extension (`.png .jpg .jpeg .bmp .gif .webp .tif .tiff`).
- `dropEvent`: take the first file, call `files.load_image(path)`.

`load_image(path)`:

1. `Image.open(path)`, then `img.load()` so the file handle isn't held open.
2. `ImageOps.exif_transpose(img)` — **important**, otherwise phone photos show sideways.
3. For animated GIFs, just use the first frame.
4. Convert to `RGBA`.
5. On failure (`UnidentifiedImageError`, `OSError`) show a `QMessageBox` with a friendly message; don't crash.

Also add **File > Open…** (Ctrl+O) using `QFileDialog` as a fallback. It's cheap and useful for testing.

Dropping a new image replaces the current one and resets edges.

### Pillow → Qt conversion

```python
def pil_to_qimage(img):
    img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, 4 * img.width, QImage.Format_RGBA8888)
    return qimg.copy()  # copy so Qt owns the memory, not the temporary bytes
```

Convert the original **once** on load and keep a `QPixmap`. Don't re-convert on every mouse move.

## Display (the canvas)

Build `ImageCanvas` as a custom `QWidget` with `paintEvent` and mouse event handlers. (Avoid `QGraphicsView` for now; it's more machinery than we need.)

### Screen transform

Keep two values: `scale` (screen px per image px) and `origin` (screen position of image coordinate 0,0).

```
screen_x = origin_x + scale * image_x
image_x  = (screen_x - origin_x) / scale
```

**Fit:** leave margin around the image so there is room to drag edges outward to pad.

```
scale = min(0.8 * widget_w / out_w, 0.8 * widget_h / out_h, 1.0)
origin chosen so the output box is centered in the widget
```

Recompute fit on load, on window resize, on reset, and **when a drag ends**. **Do not** refit during a drag, or the image will jump around under the cursor.

### Painting (in order)

1. Neutral background (dark gray).
2. Output box: fill with a checkerboard (signals "transparent padding").
3. Visible part of the original: `painter.drawPixmap(target_rect, pixmap, source_rect)`, where `source_rect` is the visible rect from `apply_edges` step 3 and `target_rect` is that rect mapped to screen.
4. A 1px border around the output box.
5. Four edge handles: a small rectangle at the midpoint of each side. Highlight the one under the cursor.

Enable `QPainter.SmoothPixmapTransform` when scaled down.

The preview is drawn with Qt from the same `Edges` model; Pillow's `apply_edges` is used for export. Because both derive from the same output-box math, they will match. Add a debug check if you want: the export size must equal the size shown in the status bar.

## Edge dragging

- `setMouseTracking(True)` so hover works without a button held.
- **Hit test:** the cursor is "on" an edge if it's within ~8 screen px of that side's line and within the side's extent. Corners: pick whichever edge is closer; corner-drag is out of scope.
- **Cursor:** `Qt.SizeHorCursor` for left/right, `Qt.SizeVerCursor` for top/bottom, normal arrow otherwise.
- **Press:** record which edge, the mouse position, and the starting `Edges`. Freeze `scale` and `origin`.
- **Move:** `d = round((mouse - press_pos) / scale)` in image px, then:

  | Edge | New value |
  |---|---|
  | left | `start.left - dx` |
  | right | `start.right + dx` |
  | top | `start.top - dy` |
  | bottom | `start.bottom + dy` |

  Clamp so the output stays ≥ 1×1. Then `update()` to repaint and emit a signal (e.g. `edgesChanged`) so the window can update the status bar.
- **Release:** clear drag state, refit, repaint.

Optional nice-to-have: hold **Shift** to apply the same change to the opposite edge (symmetric pad/crop).

## Status bar

Always show: original size, current edges, output size. Example:

```
Original 1920×1080  |  L +40  T 0  R -120  B +40  |  Output 1840×1160
```

## Saving / export

**File > Save As…** (Ctrl+S), disabled until an image is loaded.

- `QFileDialog.getSaveFileName` with filters for PNG, JPEG, WebP, BMP.
- Default filename: `<original_stem>_edited.png` in the original's folder.
- If the user types no extension, add the one for the selected filter.

`save_image(img, edges, path)`:

1. `out = apply_edges(img, edges, fill=(0, 0, 0, 0))`
2. If the format has no alpha (JPEG, BMP): paste onto a white `RGB` image using the alpha as mask.
3. JPEG: `quality=95`. PNG: default settings.
4. Save. On error show a `QMessageBox`.

Show a brief "Saved to …" message in the status bar on success.

## Other small actions

- **Edit > Reset** (Ctrl+R): edges back to zero.
- Empty state: when no image is loaded, the canvas shows centered text "Drop an image here".

## Tests (`tests/test_model.py`)

Test `apply_edges` with small synthetic images (e.g. a 10×6 image with distinct colored pixels), no GUI needed:

- All-zero edges returns an identical image.
- Pad each side individually: correct size, original pixels at the right offset, pad pixels transparent.
- Crop each side individually: correct size and correct pixels kept.
- Mixed pad on one side + crop on another.
- Clamp helper: a crop that would make width 0 gets clamped to width 1.

`tests/test_files.py`:

- Round-trip save/load for PNG keeps size and transparency.
- JPEG save of an image with transparent padding produces white in those pixels and no error.
- `load_image` applies EXIF orientation (build a tiny test image with an orientation tag set).

## Milestones

Work in this order and get each one working before the next. Commit after each.

1. **Skeleton.** `python -m image_lab` opens an empty window with a menu bar and the "Drop an image here" text.
   *Done when:* the window opens and closes cleanly.
2. **Load + display.** Drag-and-drop and File > Open load an image; it is centered and scaled to fit; resizing the window refits.
   *Done when:* JPEG/PNG load, a sideways phone photo displays upright, a non-image file shows an error box.
3. **Model + tests.** `Edges`, `apply_edges`, clamp helper, and `tests/test_model.py` all passing.
   *Done when:* `pytest` is green.
4. **Edge dragging.** Hover highlights and cursors, dragging pads/crops live, status bar updates, refit on release.
   *Done when:* all four sides can be padded and cropped, the image can't be cropped to nothing, nothing jumps mid-drag.
5. **Export.** Save As in PNG/JPEG/WebP/BMP, plus `tests/test_files.py`.
   *Done when:* exported file size matches the status bar output size and opens correctly in another viewer.
6. **Polish.** Reset, disabled menu items when nothing is loaded, README with setup/run instructions.

## Things to ask about rather than guess

- Anything that seems to need a new dependency.
- If performance is poor on very large images (e.g. > 50 MP); we can add a downscaled preview pixmap.
- Any change to the edge model, since future features will build on it.
