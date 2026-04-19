"""Runtime hooks shared by extracted legacy widgets."""

from __future__ import annotations

import tkinter as tk
import webbrowser
from typing import Callable

from bookmark_organizer_pro.utils.runtime import open_external_url

from .theme import ThemeColors

_theme_provider: Callable[[], ThemeColors] = ThemeColors
_window_chrome_provider: Callable[[tk.Toplevel], None] = lambda window: None


def set_widget_theme_provider(provider: Callable[[], ThemeColors]):
    """Configure the current theme provider used by extracted legacy widgets."""
    global _theme_provider
    if callable(provider):
        _theme_provider = provider


def set_widget_window_chrome_provider(provider: Callable[[tk.Toplevel], None]):
    """Configure platform window styling for extracted dialogs."""
    global _window_chrome_provider
    if callable(provider):
        _window_chrome_provider = provider


def get_theme() -> ThemeColors:
    """Return current widget colors, falling back to default theme colors."""
    try:
        return _theme_provider()
    except Exception:
        return ThemeColors()


def apply_window_chrome(window: tk.Toplevel):
    """Apply optional platform window styling without coupling UI modules to main."""
    try:
        _window_chrome_provider(window)
    except Exception:
        pass


def _open_external_url(url: str) -> bool:
    """Open external URLs through the shared runtime helper."""
    return open_external_url(url, opener=webbrowser.open)
