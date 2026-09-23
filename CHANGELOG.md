# Changelog

All notable changes to this project are recorded here. Newest first.
The top entry must match `image_lab.__version__` (enforced by `tests/test_project.py`).

## 0.1.0 - 2026-09-22

### Added
- Project setup: `pyproject.toml` (PySide6, Pillow; dev: pytest, ruff), README, `.gitignore`, `.gitattributes`.
- Prototype plan in `docs/plans/01-prototype.md`.
- Iteration guardrails: `CLAUDE.md` protocol, `docs/STATUS.md` project state, this changelog.
- Gate script `tools/check.py` (ruff check, ruff format check, pytest).
- Headless Qt test setup in `tests/conftest.py` (offscreen platform with Windows fonts, `qapp` and `artifacts_dir` fixtures).
- Consistency tests in `tests/test_project.py`: version matches changelog and status, core modules stay Qt-free, every module has a docstring.
