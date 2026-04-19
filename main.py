#!/usr/bin/env python3
"""
Bookmark Organizer Pro - Ultimate Edition v5.2.2
=================================================
A powerful, modern bookmark manager with:
- Modular architecture: backend in `bookmark_organizer_pro` package
- Multi-theme system with 10+ built-in themes
- Nested category hierarchy
- Full tagging system
- Grid/Card and List views
- Advanced search syntax
- Analytics dashboard
- System tray integration
- Enhanced favicon caching
- Professional UI with DPI awareness

Version 5.2.2 - April 2026
"""

import webbrowser

# =============================================================================
# Public compatibility imports
# main.py remains a launcher plus legacy facade for tests and external callers.
# =============================================================================
from bookmark_organizer_pro import *  # noqa: F403 - legacy main.py export surface
from bookmark_organizer_pro.ui import *  # noqa: F403 - legacy UI export surface
from bookmark_organizer_pro.theme_runtime import BUILT_IN_THEMES, get_theme, get_theme_manager

log.info(f"Starting {APP_NAME} v{APP_VERSION}")


_csv_safe_cell = csv_safe_cell


def _open_external_url(url: str) -> bool:
    """Backward-compatible wrapper around the shared URL opener."""
    return open_external_url(url, opener=webbrowser.open)


from bookmark_organizer_pro import desktop_bootstrap as _desktop_bootstrap
from bookmark_organizer_pro.desktop_bootstrap import (
    APP_ICON_BASE64,
    ASSETS_DIR,
    BUNDLE_ROOT,
    SOURCE_ROOT,
    get_embedded_icon,
    set_dark_title_bar,
    set_window_icon,
    setup_dpi_awareness,
)


def _sync_dependency_globals():
    """Mirror optional dependency state for legacy main.py consumers."""
    global BeautifulSoup, requests, HAS_PIL, HAS_TRAY, Image, ImageTk, ImageDraw, ImageFont, pystray, TrayItem
    BeautifulSoup = _desktop_bootstrap.BeautifulSoup
    requests = _desktop_bootstrap.requests
    HAS_PIL = _desktop_bootstrap.HAS_PIL
    HAS_TRAY = _desktop_bootstrap.HAS_TRAY
    Image = _desktop_bootstrap.Image
    ImageTk = _desktop_bootstrap.ImageTk
    ImageDraw = _desktop_bootstrap.ImageDraw
    ImageFont = _desktop_bootstrap.ImageFont
    pystray = _desktop_bootstrap.pystray
    TrayItem = _desktop_bootstrap.TrayItem


def import_dependencies():
    """Import optional desktop dependencies and keep legacy globals in sync."""
    _desktop_bootstrap.import_dependencies()
    _sync_dependency_globals()


_sync_dependency_globals()
set_widget_window_chrome_provider(set_dark_title_bar)


from bookmark_organizer_pro.app import FinalBookmarkOrganizerApp
from bookmark_organizer_pro.launcher import main as _launcher_main


# =============================================================================
# FINAL MAIN ENTRY POINT
# =============================================================================
def main():
    """Run the package launcher."""
    return _launcher_main()

if __name__ == "__main__":
    main()
