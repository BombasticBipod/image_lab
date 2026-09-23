# image_lab

Small desktop app for preprocessing images. Drop an image on the window, drag any edge outward to pad or inward to crop, then export.

Status: prototype in progress. See [docs/PLAN.md](docs/PLAN.md) for scope and milestones.

## Setup (Windows)

Use a Windows Python install, not WSL (drag-and-drop from File Explorer does not work reliably under WSLg).

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

## Run

```powershell
python -m image_lab
```

## Test

```powershell
pytest
```
