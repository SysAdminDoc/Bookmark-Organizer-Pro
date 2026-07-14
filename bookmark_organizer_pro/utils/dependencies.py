"""Dependency discovery and installation helpers."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import subprocess
import sys
import threading
from typing import Callable, Dict, List, Optional, Tuple

from ..logging_config import log


FROZEN_REPAIR_GUIDANCE = (
    "This packaged build cannot install Python components at runtime. "
    "Reinstall Bookmark Organizer Pro from the complete release package."
)


@dataclass(frozen=True)
class DependencyInstallReport:
    """Terminal state for one bounded dependency-install session."""

    success: bool
    cancelled: bool = False
    installed: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()

    def summary(self) -> str:
        changed = ", ".join(self.installed) if self.installed else "none"
        if self.cancelled:
            return f"Cancelled. Installed before cancellation: {changed}."
        if self.failed:
            return f"Installed: {changed}. Failed: {', '.join(self.failed)}."
        return f"Installation complete. Installed: {changed}."


def is_frozen_runtime() -> bool:
    """Return whether Python is running from a frozen application bundle."""
    return bool(getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS"))


class DependencyManager:
    """Manage optional and required runtime package dependencies."""

    REQUIRED_PACKAGES = {
        "beautifulsoup4": {
            "import_name": "bs4",
            "required": True,
            "description": "HTML parsing for bookmark import",
        },
        "requests": {
            "import_name": "requests",
            "required": True,
            "description": "HTTP requests for favicon download",
        },
    }

    OPTIONAL_PACKAGES = {
        "Pillow": {
            "import_name": "PIL",
            "required": False,
            "description": "Image processing for favicons",
        },
    }

    def __init__(self):
        self.missing_required: List[str] = []
        self.missing_optional: List[str] = []
        self.installed: Dict[str, bool] = {}
        self.install_errors: Dict[str, str] = {}
        self.last_install_report = DependencyInstallReport(success=False)
        self._cancel_install = threading.Event()
        self._install_session_lock = threading.Lock()
        self._process_lock = threading.Lock()
        self._active_process: subprocess.Popen | None = None

    def _package_info(self, package: str) -> Optional[dict]:
        return self.REQUIRED_PACKAGES.get(package) or self.OPTIONAL_PACKAGES.get(package)

    @property
    def runtime_install_supported(self) -> bool:
        """Return whether this interpreter can safely invoke ``python -m pip``."""
        return not is_frozen_runtime()

    def repair_guidance(self, package: str | None = None) -> str:
        """Return deterministic recovery guidance for an incomplete frozen build."""
        if package:
            return f"Missing packaged component: {package}. {FROZEN_REPAIR_GUIDANCE}"
        return FROZEN_REPAIR_GUIDANCE

    def check_all(self) -> Tuple[bool, List[str], List[str]]:
        """Check all dependencies and return required/optional missing lists."""
        self.missing_required = []
        self.missing_optional = []

        for package, info in self.REQUIRED_PACKAGES.items():
            installed = self._is_installed(info["import_name"])
            self.installed[package] = installed
            if not installed:
                self.missing_required.append(package)

        for package, info in self.OPTIONAL_PACKAGES.items():
            installed = self._is_installed(info["import_name"])
            self.installed[package] = installed
            if not installed:
                self.missing_optional.append(package)

        return len(self.missing_required) == 0, self.missing_required, self.missing_optional

    def _is_installed(self, import_name: str) -> bool:
        """Return True when an importable package is available."""
        try:
            importlib.import_module(import_name)
            return True
        except ImportError:
            return False

    def install_package(self, package: str, progress_callback: Optional[Callable] = None) -> bool:
        """Install a known package with pip."""
        if not self._package_info(package):
            message = f"Unknown dependency: {package}"
            log.error(message)
            self.install_errors[package] = message
            return False

        if not self.runtime_install_supported:
            message = self.repair_guidance(package)
            log.error(message)
            self.install_errors[package] = message
            if progress_callback:
                progress_callback(message)
            return False

        log.info(f"Installing package: {package}")
        if progress_callback:
            progress_callback(f"Installing {package}...")

        if self._cancel_install.is_set():
            self.install_errors[package] = "Installation cancelled"
            return False

        process = None
        try:
            process = subprocess.Popen(
                [sys.executable, "-m", "pip", "install", package, "--quiet"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            with self._process_lock:
                self._active_process = process
                cancel_now = self._cancel_install.is_set()
            if cancel_now:
                process.terminate()
            stdout, stderr = process.communicate(timeout=120)

            if process.returncode == 0:
                log.info(f"Successfully installed {package}")
                self.installed[package] = True
                return True

            if self._cancel_install.is_set():
                self.install_errors[package] = "Installation cancelled"
                return False
            error_msg = stderr or stdout or "Unknown error"
            log.error(f"Failed to install {package}: {error_msg}")
            self.install_errors[package] = error_msg
            return False
        except subprocess.TimeoutExpired:
            if process is not None:
                self._stop_process(process)
            log.error(f"Timeout installing {package}")
            self.install_errors[package] = "Installation timed out"
            return False
        except Exception as e:
            log.error(f"Error installing {package}: {e}")
            self.install_errors[package] = str(e)
            return False
        finally:
            with self._process_lock:
                if self._active_process is process:
                    self._active_process = None

    @staticmethod
    def _stop_process(process: subprocess.Popen, wait_timeout: float = 3.0) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=wait_timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=wait_timeout)
        except Exception as exc:
            log.warning(f"Could not stop dependency installer cleanly: {exc}")

    def cancel_installation(self) -> bool:
        """Request cancellation and synchronously stop the active pip process."""
        self._cancel_install.set()
        with self._process_lock:
            process = self._active_process
        if process is not None:
            self._stop_process(process)
        return True

    def install_all_missing(self, progress_callback: Optional[Callable] = None) -> bool:
        """Install all known missing dependencies."""
        all_missing = self.missing_required + self.missing_optional
        if not self._install_session_lock.acquire(blocking=False):
            self.last_install_report = DependencyInstallReport(
                success=False, failed=tuple(all_missing)
            )
            return False
        self._cancel_install.clear()
        installed: list[str] = []
        failed: list[str] = []
        skipped: list[str] = []
        try:
            for index, package in enumerate(all_missing):
                if self._cancel_install.is_set():
                    skipped.extend(all_missing[index:])
                    break
                if progress_callback:
                    progress_callback(f"Installing {package} ({index + 1}/{len(all_missing)})...")

                package_ok = self.install_package(package)
                if package_ok:
                    installed.append(package)
                elif not self._cancel_install.is_set():
                    failed.append(package)
                if self._cancel_install.is_set():
                    skipped.extend(all_missing[index + 1:])
                    break

            cancelled = self._cancel_install.is_set()
            required_failed = any(package in self.missing_required for package in failed)
            success = not cancelled and not required_failed
            self.last_install_report = DependencyInstallReport(
                success=success,
                cancelled=cancelled,
                installed=tuple(installed),
                failed=tuple(failed),
                skipped=tuple(skipped),
            )
            return success
        finally:
            self._install_session_lock.release()
