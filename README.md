# image_lab

Small desktop app for preprocessing images. Drop an image on the window, drag any edge outward to pad or inward to crop, then export.

Current state is in [docs/STATUS.md](docs/STATUS.md), plans are in [docs/plans/](docs/plans/), and changes are in [CHANGELOG.md](CHANGELOG.md).

## Setup (Windows)

Use a Windows Python install (3.10 or newer), not WSL. Dragging files from File Explorer into apps running under WSLg does not work reliably.

```powershell
py -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

## Run

```powershell
.venv/Scripts/python -m image_lab
```

## Use

| Action | How |
|---|---|
| Open an image | Drag it from File Explorer onto the window, or File > Open… (Ctrl+O) |
| Pad a side | Drag that edge outward. The handle at the middle of each edge lights up on hover |
| Crop a side | Drag that edge inward. At least 1 pixel of the image always stays |
| Pad or crop both opposite sides | Hold Shift while dragging |
| Padding color | Edit > Padding Color… (the dialog takes hex such as `#FF8000` and has an alpha control), or Edit > Transparent Padding |
| Copy / paste | Ctrl+C copies the edited image (PNG data keeps transparency). Ctrl+V pastes an image or an image file copied in Explorer, replacing the current image |
| Undo / redo | Ctrl+Z / Ctrl+Y (Edit menu). Covers edge drags, Reset and padding color; a newly loaded image starts fresh |
| Remove all edge changes | Edit > Reset (Ctrl+R) |
| Save | Toolbar **Save** button or Ctrl+S: writes `out/<name>_edited.png` in the project folder, adding `_2`, `_3`, … instead of overwriting |
| Save in another format or place | Arrow next to the Save button, or File > Save As… (Ctrl+Shift+S): PNG, JPEG, WebP or BMP. JPEG and BMP have no transparency, so transparent areas become white |

The status bar shows the original size, the change on each side (`+` pads, `-` crops), the output size and the padding color. The original file is never modified.

## Check (lint, format, tests)

```powershell
.venv/Scripts/python tools/check.py
```

GUI tests run headless on Qt's offscreen platform; no window opens. Test snapshots are written to `tests/_artifacts/`.
