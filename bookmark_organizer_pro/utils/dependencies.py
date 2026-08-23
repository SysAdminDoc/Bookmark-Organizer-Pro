"""Dependency discovery and installation helpers."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from typing import Callable, Dict, List, Optional, Tuple

from bootstrap_dependencies import is_frozen_runtime, load_manifest, repair_message

from ..logging_config import log


def _required_packages() -> dict[str, dict]:
    return {
        str(entry["distribution"]): {
            "import_name": str(entry["import_name"]),
            "required": True,
            "description": f"Required runtime component ({entry['requirement']})",
        }
        for entry in load_manifest()["dependencies"]
    }


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


class DependencyManager:
    """Report runtime package status and deterministic external repair guidance."""

    REQUIRED_PACKAGES = _required_packages()
    OPTIONAL_PACKAGES: dict[str, dict] = {}

    def __init__(self):
        self.missing_required: List[str] = []
        self.missing_optional: List[str] = []
        self.installed: Dict[str, bool] = {}
        self.install_errors: Dict[str, str] = {}
        self.last_install_report = DependencyInstallReport(success=False)

    def _package_info(self, package: str) -> Optional[dict]:
        canonical = str(package).lower()
        return (
            self.REQUIRED_PACKAGES.get(package)
            or self.OPTIONAL_PACKAGES.get(package)
            or self.REQUIRED_PACKAGES.get(canonical)
            or self.OPTIONAL_PACKAGES.get(canonical)
        )

    @property
    def runtime_install_supported(self) -> bool:
        """Runtime installers are forbidden for both source and frozen builds."""
        return False

    def repair_guidance(self, package: str | None = None) -> str:
        """Return deterministic recovery guidance for the current environment."""
        missing = []
        if package:
            info = self._package_info(package)
            missing.append(str(info["import_name"]) if info else package)
        else:
            for name in self.missing_required:
                info = self._package_info(name)
                missing.append(str(info["import_name"]) if info else name)
        return repair_message(missing, frozen=is_frozen_runtime())

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
        """Return True when a package can be resolved without importing it."""
        try:
            return importlib.util.find_spec(import_name) is not None
        except (AttributeError, ImportError, ModuleNotFoundError, ValueError):
            return False

    def install_package(self, package: str, progress_callback: Optional[Callable] = None) -> bool:
        """Refuse runtime installation and return copyable external guidance."""
        if not self._package_info(package):
            message = f"Unknown dependency: {package}"
            log.error(message)
            self.install_errors[package] = message
            return False

        message = self.repair_guidance(package)
        log.error(message)
        self.install_errors[package] = message
        if progress_callback:
            progress_callback(message)
        return False

    def cancel_installation(self) -> bool:
        """Compatibility no-op because no runtime installer can start."""
        return True

    def install_all_missing(self, progress_callback: Optional[Callable] = None) -> bool:
        """Refuse runtime mutation while preserving the compatibility result API."""
        missing = tuple(self.missing_required + self.missing_optional)
        message = self.repair_guidance()
        if progress_callback:
            progress_callback(message)
        self.last_install_report = DependencyInstallReport(success=False, failed=missing)
        return False
