"""Standard-library-only dependency preflight for every application entry point."""

from __future__ import annotations

import ctypes
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable, Iterable, Mapping, Sequence, TextIO


MANIFEST_SCHEMA = "bookmark-organizer-pro/bootstrap-dependencies"
MANIFEST_VERSION = 1
MANIFEST_RELATIVE_PATH = Path("bookmark_organizer_pro") / "bootstrap_dependencies.json"
COMPLETE_RELEASE_URL = "https://github.com/SysAdminDoc/Bookmark-Organizer-Pro/releases/latest"


class BootstrapManifestError(RuntimeError):
    """Raised when the generated dependency manifest is absent or malformed."""


def is_frozen_runtime() -> bool:
    """Return whether this process is running from a frozen application bundle."""
    return bool(
        getattr(sys, "frozen", False)
        or hasattr(sys, "_MEIPASS")
        or globals().get("__compiled__") is not None
    )


def manifest_path() -> Path:
    """Return the generated manifest path for source, wheel, or frozen layouts."""
    if hasattr(sys, "_MEIPASS"):
        root = Path(sys._MEIPASS)
    elif globals().get("__compiled__") is not None:
        root = Path(__file__).resolve().parent
    elif getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
    else:
        root = Path(__file__).resolve().parent
    return root / MANIFEST_RELATIVE_PATH


def load_manifest(path: str | Path | None = None) -> dict:
    """Load and validate the generated bootstrap manifest using only stdlib."""
    target = Path(path) if path is not None else manifest_path()
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BootstrapManifestError(f"Cannot read dependency manifest at {target}: {exc}") from exc
    if not isinstance(document, dict):
        raise BootstrapManifestError("Dependency manifest must be a JSON object")
    if document.get("schema") != MANIFEST_SCHEMA or document.get("version") != MANIFEST_VERSION:
        raise BootstrapManifestError("Dependency manifest schema or version is unsupported")
    dependencies = document.get("dependencies")
    if not isinstance(dependencies, list) or not dependencies:
        raise BootstrapManifestError("Dependency manifest has no required dependencies")
    for entry in dependencies:
        if not isinstance(entry, dict):
            raise BootstrapManifestError("Dependency manifest entries must be JSON objects")
        if not all(str(entry.get(key) or "").strip() for key in ("distribution", "import_name", "requirement")):
            raise BootstrapManifestError("Dependency manifest entry is incomplete")
    return document


def find_missing_imports(
    dependencies: Iterable[Mapping[str, object]],
    *,
    find_spec: Callable[[str], object | None] = importlib.util.find_spec,
) -> tuple[str, ...]:
    """Return every required import that cannot be resolved without importing it."""
    missing: list[str] = []
    for entry in dependencies:
        import_name = str(entry["import_name"])
        try:
            available = find_spec(import_name) is not None
        except (AttributeError, ImportError, ModuleNotFoundError, ValueError):
            available = False
        if not available:
            missing.append(import_name)
    return tuple(missing)


def source_reinstall_command(
    *,
    executable: str | None = None,
    source_root: str | Path | None = None,
    project_version: str | None = None,
) -> str:
    """Return a copyable reinstall command bound to this interpreter and install layout."""
    interpreter = str(executable or sys.executable)
    root = Path(source_root) if source_root is not None else Path(__file__).resolve().parent
    if (root / "pyproject.toml").is_file():
        install_target = str(root)
    else:
        version = str(project_version or "").strip()
        install_target = "bookmark-organizer-pro" + (f"=={version}" if version else "")
    arguments = [interpreter, "-m", "pip", "install", "--upgrade", "--force-reinstall", install_target]
    if os.name == "nt":
        return subprocess.list2cmdline(arguments)
    import shlex

    return shlex.join(arguments)


def repair_message(
    missing_imports: Sequence[str],
    *,
    frozen: bool | None = None,
    executable: str | None = None,
    source_root: str | Path | None = None,
) -> str:
    """Return deterministic recovery guidance without running an installer."""
    missing = ", ".join(missing_imports) if missing_imports else "unknown"
    if is_frozen_runtime() if frozen is None else frozen:
        return (
            f"Bookmark Organizer Pro is missing required component imports: {missing}.\n\n"
            "This packaged build cannot add components at runtime. Reinstall the complete signed "
            f"release from:\n{COMPLETE_RELEASE_URL}"
        )
    try:
        project_version = str(load_manifest().get("project_version") or "")
    except BootstrapManifestError:
        project_version = ""
    command = source_reinstall_command(
        executable=executable,
        source_root=source_root,
        project_version=project_version,
    )
    return (
        f"Bookmark Organizer Pro is missing required dependency imports: {missing}.\n\n"
        "Close the application, then reinstall into this exact Python environment:\n"
        f"{command}"
    )


def _emit_failure(message: str, *, stream: TextIO | None = None, frozen: bool | None = None) -> None:
    output = stream if stream is not None else getattr(sys, "stderr", None)
    if output is not None:
        output.write(message.rstrip() + "\n")
        output.flush()
        return
    if (is_frozen_runtime() if frozen is None else frozen) and os.name == "nt":
        ctypes.windll.user32.MessageBoxW(0, message, "Bookmark Organizer Pro", 0x10)


def preflight_or_exit(
    *,
    path: str | Path | None = None,
    find_spec: Callable[[str], object | None] = importlib.util.find_spec,
    frozen: bool | None = None,
    stream: TextIO | None = None,
) -> None:
    """Exit with actionable guidance before any application package is imported."""
    try:
        manifest = load_manifest(path)
    except BootstrapManifestError as exc:
        message = repair_message((), frozen=frozen) + f"\n\nDependency manifest error: {exc}"
        _emit_failure(message, stream=stream, frozen=frozen)
        raise SystemExit(2) from None
    missing = find_missing_imports(manifest["dependencies"], find_spec=find_spec)
    if not missing:
        return
    _emit_failure(repair_message(missing, frozen=frozen), stream=stream, frozen=frozen)
    raise SystemExit(2)
