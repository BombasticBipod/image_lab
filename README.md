# image_lab

Small desktop app for preprocessing images. Drop an image on the window, drag any edge outward to pad or inward to crop, then export.

Status: prototype in progress. See [docs/STATUS.md](docs/STATUS.md) for current state and [docs/plans/](docs/plans/) for the plans. Changes are listed in [CHANGELOG.md](CHANGELOG.md).

## Setup (Windows)

Use a Windows Python install, not WSL (drag-and-drop from File Explorer does not work reliably under WSLg).

```powershell
py -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

## Run

```powershell
.venv/Scripts/python -m image_lab
```

## Check (lint, format, tests)

```powershell
.venv/Scripts/python tools/check.py
```

GUI tests run headless on Qt's offscreen platform; no window opens.
