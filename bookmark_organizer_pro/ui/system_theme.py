"""System dark/light mode detection utilities."""

from __future__ import annotations

import subprocess
from typing import Any, Callable, Optional

from bookmark_organizer_pro.constants import IS_LINUX, IS_MAC, IS_WINDOWS


class SystemThemeDetector:
    """Detect and optionally monitor the operating system color scheme."""

    def __init__(
        self,
        on_theme_change: Optional[Callable[[bool], None]] = None,
        check_interval_ms: int = 5000,
    ):
        self.on_theme_change = on_theme_change
        self._last_is_dark: Optional[bool] = None
        self._running = False
        self._root: Optional[Any] = None
        self._check_interval_ms = max(1000, int(check_interval_ms or 5000))

    def get_system_theme_is_dark(self) -> bool:
        """Return True when the OS appears to prefer dark mode."""
        if IS_WINDOWS:
            return self._check_windows_dark_mode()
        if IS_MAC:
            return self._check_macos_dark_mode()
        if IS_LINUX:
            return self._check_linux_dark_mode()
        return True

    def _check_windows_dark_mode(self) -> bool:
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            try:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            finally:
                winreg.CloseKey(key)
            return value == 0
        except Exception:
            return True

    def _check_macos_dark_mode(self) -> bool:
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                timeout=1.5,
                check=False,
            )
            return "dark" in result.stdout.lower()
        except Exception:
            return True

    def _check_linux_dark_mode(self) -> bool:
        try:
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                capture_output=True,
                text=True,
                timeout=1.5,
                check=False,
            )
            return "dark" in result.stdout.lower()
        except Exception:
            return True

    def start_monitoring(self, root: Any) -> None:
        """Start monitoring for system theme changes using a Tk-like root."""
        self._root = root
        self._running = True
        self._check_theme()

    def stop_monitoring(self) -> None:
        """Stop monitoring for theme changes."""
        self._running = False

    def _check_theme(self) -> None:
        if not self._running or self._root is None:
            return

        is_dark = self.get_system_theme_is_dark()
        if self._last_is_dark is not None and is_dark != self._last_is_dark:
            if self.on_theme_change:
                self.on_theme_change(is_dark)

        self._last_is_dark = is_dark
        if self._running:
            self._root.after(self._check_interval_ms, self._check_theme)
