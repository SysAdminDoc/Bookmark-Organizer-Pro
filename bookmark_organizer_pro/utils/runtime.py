"""Runtime helpers shared by the desktop app and tests."""

import concurrent.futures
import json
import os
import shutil
import sys
import tempfile
import webbrowser
from pathlib import Path
from typing import Callable, Optional

from ..constants import APP_DIR
from ..logging_config import log
from .validators import validate_url


ERROR_MESSAGES = {
    "FileNotFoundError": "The file could not be found. Please check the path and try again.",
    "PermissionError": "Permission denied. Please check file permissions or run as administrator.",
    "JSONDecodeError": "The file contains invalid data. It may be corrupted or not in the expected format.",
    "ConnectionError": "Could not connect to the server. Please check your internet connection.",
    "TimeoutError": "The operation timed out. Please try again later.",
    "ValueError": "Invalid value provided. Please check your input.",
    "MemoryError": "Not enough memory to complete this operation. Try closing other applications.",
    "OSError": "An operating system error occurred. Please check disk space and permissions.",
}


def atomic_json_write(filepath: Path, data, indent: int = 2) -> None:
    """Write JSON atomically via temp file + os.replace."""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=filepath.parent, suffix=".tmp", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=indent, ensure_ascii=False)
        os.replace(temp_path, filepath)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def csv_safe_cell(value) -> str:
    """Return a spreadsheet-safe CSV cell string."""
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def open_external_url(url: str, opener: Optional[Callable[[str], bool]] = None) -> bool:
    """Open a user/bookmark URL only after scheme-level validation."""
    url = str(url or "").strip()
    valid, error = validate_url(url)
    if not valid:
        log.warning(f"Blocked opening invalid URL '{url[:80]}': {error}")
        return False
    opener = opener or webbrowser.open
    return bool(opener(url))


def get_user_friendly_error(exception: Exception) -> str:
    """Get a user-friendly error message for an exception."""
    exc_type = type(exception).__name__
    if exc_type in ERROR_MESSAGES:
        return ERROR_MESSAGES[exc_type]

    error_str = str(exception).lower()
    if "permission" in error_str:
        return ERROR_MESSAGES["PermissionError"]
    if "timeout" in error_str:
        return ERROR_MESSAGES["TimeoutError"]
    if "connect" in error_str or "network" in error_str:
        return ERROR_MESSAGES["ConnectionError"]
    if "memory" in error_str:
        return ERROR_MESSAGES["MemoryError"]
    if "not found" in error_str or "no such file" in error_str:
        return ERROR_MESSAGES["FileNotFoundError"]

    msg = str(exception)
    if len(msg) > 200:
        msg = msg[:200] + "..."
    return f"An error occurred: {msg}"


class ResourceManager:
    """Context manager for safe resource cleanup."""

    def __init__(self):
        self._resources = []

    def register(self, resource, cleanup_func=None):
        """Register a resource for cleanup."""
        self._resources.append((resource, cleanup_func))
        return resource

    def cleanup(self) -> None:
        """Clean up all registered resources."""
        for resource, cleanup_func in reversed(self._resources):
            try:
                if cleanup_func:
                    cleanup_func(resource)
                elif hasattr(resource, "close"):
                    resource.close()
                elif hasattr(resource, "destroy"):
                    resource.destroy()
            except Exception as e:
                log.warning(f"Resource cleanup error: {e}")
        self._resources.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False


def validate_environment():
    """Validate the runtime environment at startup."""
    warnings = []

    if sys.version_info < (3, 8):
        warnings.append(f"Python 3.8+ recommended (running {sys.version})")

    if not APP_DIR.exists():
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            warnings.append(f"Could not create data directory: {e}")

    try:
        test_file = APP_DIR / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
    except Exception as e:
        warnings.append(f"Data directory not writable: {e}")

    try:
        _, _, free = shutil.disk_usage(APP_DIR)
        if free < 100 * 1024 * 1024:
            warnings.append(f"Low disk space: {free // (1024 * 1024)}MB free")
    except Exception:
        pass

    is_valid = len([warning for warning in warnings if "not writable" in warning]) == 0
    return is_valid, warnings


def run_with_timeout(func, timeout_seconds: float, default=None):
    """Run a no-argument function with a timeout."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            log.warning(f"Function timed out after {timeout_seconds}s")
            return default
        except Exception as e:
            log.error(f"Function error: {e}")
            return default
