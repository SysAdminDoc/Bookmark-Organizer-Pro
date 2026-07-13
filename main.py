#!/usr/bin/env python3
"""
Bookmark Organizer Pro - Ultimate Edition
==========================================
A powerful, modern bookmark manager with:
- Modular architecture: backend in `bookmark_organizer_pro` package
- Multi-theme system with 10+ built-in themes
- Nested category hierarchy
- Full tagging system
- Grid/Card and List views
- Advanced search syntax
- Analytics dashboard
- Enhanced favicon caching
- Professional UI with DPI awareness
"""

import multiprocessing
import sys

multiprocessing.freeze_support()

BOOTSTRAP_APP_NAME = "Bookmark Organizer Pro"
BOOTSTRAP_APP_VERSION = "6.11.3"

if __name__ == "__main__" and any(arg in {"--version", "-V"} for arg in sys.argv[1:]):
    stdout = getattr(sys, "stdout", None)
    if stdout is not None:
        try:
            stdout.write(f"{BOOTSTRAP_APP_NAME} v{BOOTSTRAP_APP_VERSION}\n")
            stdout.flush()
        except Exception:
            pass
    raise SystemExit(0)

import webbrowser

from bookmark_organizer_pro.constants import APP_NAME, APP_VERSION
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.ui.widget_runtime import set_widget_window_chrome_provider
from bookmark_organizer_pro.utils.runtime import csv_safe_cell, open_external_url

# =============================================================================
# Public compatibility imports
# main.py remains a launcher plus legacy facade for tests and external callers.
# =============================================================================
from bookmark_organizer_pro import *  # noqa: F403 - legacy main.py export surface
from bookmark_organizer_pro.ui import *  # noqa: F403 - legacy UI export surface
from bookmark_organizer_pro.theme_runtime import BUILT_IN_THEMES, get_theme, get_theme_manager  # noqa: F401

log.info(f"Starting {APP_NAME} v{APP_VERSION}")


_csv_safe_cell = csv_safe_cell


def _open_external_url(url: str) -> bool:
    """Backward-compatible wrapper around the shared URL opener."""
    return open_external_url(url, opener=webbrowser.open)


from bookmark_organizer_pro import desktop_bootstrap as _desktop_bootstrap
from bookmark_organizer_pro.desktop_bootstrap import (
    APP_ICON_BASE64,  # noqa: F401
    ASSETS_DIR,  # noqa: F401
    BUNDLE_ROOT,  # noqa: F401
    SOURCE_ROOT,  # noqa: F401
    get_embedded_icon,  # noqa: F401
    set_dark_title_bar,
    set_window_icon,  # noqa: F401
    setup_dpi_awareness,  # noqa: F401
)


def _sync_dependency_globals():
    """Mirror optional dependency state for legacy main.py consumers."""
    global BeautifulSoup, requests, HAS_PIL, Image, ImageTk, ImageDraw, ImageFont
    BeautifulSoup = _desktop_bootstrap.BeautifulSoup
    requests = _desktop_bootstrap.requests
    HAS_PIL = _desktop_bootstrap.HAS_PIL
    Image = _desktop_bootstrap.Image
    ImageTk = _desktop_bootstrap.ImageTk
    ImageDraw = _desktop_bootstrap.ImageDraw
    ImageFont = _desktop_bootstrap.ImageFont


def import_dependencies():
    """Import optional desktop dependencies and keep legacy globals in sync."""
    _desktop_bootstrap.import_dependencies()
    _sync_dependency_globals()


_sync_dependency_globals()
set_widget_window_chrome_provider(set_dark_title_bar)


from bookmark_organizer_pro.app import FinalBookmarkOrganizerApp  # noqa: F401
from bookmark_organizer_pro.launcher import main as _launcher_main


# =============================================================================
# FINAL MAIN ENTRY POINT
# =============================================================================
def main():
    """Run the package launcher."""
    return _launcher_main()

if __name__ == "__main__":
    main()
