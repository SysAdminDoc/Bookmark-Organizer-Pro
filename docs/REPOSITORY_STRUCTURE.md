# Repository Structure

Bookmark Organizer Pro is organized around a Tkinter desktop entry point backed
by a modular Python package.

## Durable Project Files

| Path | Purpose |
| --- | --- |
| `main.py` | Desktop application entry point and Tkinter UI wiring. |
| `bookmark_organizer_pro/` | Reusable backend package: models, import/export, search, storage, AI, URL utilities, and UI support modules. |
| `tests/` | Regression tests for core behavior and edge cases. |
| `assets/` | Source-controlled visual assets, including the app icons and README screenshot. |
| `packaging/` | PyInstaller build specification and Windows version metadata. |
| `scripts/` | Local build and cleanup helpers. |
| `.github/workflows/` | CI build automation for tagged releases. |

## Generated Local Output

These paths are intentionally ignored and can be deleted at any time:

| Path | Source |
| --- | --- |
| `build/` | PyInstaller intermediate build output. |
| `dist/` | PyInstaller executable output. |
| `.pytest_cache/` | Pytest cache. |
| `__pycache__/` | Python bytecode cache. |

## Build Commands

Run builds from the repository root:

```bash
pyinstaller packaging/bookmark_organizer.spec --clean --noconfirm
```

Or use the wrapper scripts:

```batch
scripts\build_windows.bat
```

```bash
./scripts/build_unix.sh
```

## Cleanup Command

Remove generated local artifacts after tests or builds:

```bash
python scripts/clean_workspace.py
```
