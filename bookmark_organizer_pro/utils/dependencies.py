"""Dependency discovery and installation helpers."""

from __future__ import annotations

import importlib
import subprocess
import sys
from typing import Callable, Dict, List, Optional, Tuple

from ..logging_config import log


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
        "pystray": {
            "import_name": "pystray",
            "required": False,
            "description": "System tray integration",
        },
    }

    def __init__(self):
        self.missing_required: List[str] = []
        self.missing_optional: List[str] = []
        self.installed: Dict[str, bool] = {}
        self.install_errors: Dict[str, str] = {}

    def _package_info(self, package: str) -> Optional[dict]:
        return self.REQUIRED_PACKAGES.get(package) or self.OPTIONAL_PACKAGES.get(package)

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

        log.info(f"Installing package: {package}")
        if progress_callback:
            progress_callback(f"Installing {package}...")

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", package, "--quiet"],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                log.info(f"Successfully installed {package}")
                self.installed[package] = True
                return True

            error_msg = result.stderr or "Unknown error"
            log.error(f"Failed to install {package}: {error_msg}")
            self.install_errors[package] = error_msg
            return False
        except subprocess.TimeoutExpired:
            log.error(f"Timeout installing {package}")
            self.install_errors[package] = "Installation timed out"
            return False
        except Exception as e:
            log.error(f"Error installing {package}: {e}")
            self.install_errors[package] = str(e)
            return False

    def install_all_missing(self, progress_callback: Optional[Callable] = None) -> bool:
        """Install all known missing dependencies."""
        all_missing = self.missing_required + self.missing_optional
        success = True

        for index, package in enumerate(all_missing):
            if progress_callback:
                progress_callback(f"Installing {package} ({index + 1}/{len(all_missing)})...")

            if not self.install_package(package) and package in self.missing_required:
                success = False

        return success
