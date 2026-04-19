"""Compatibility exports for reusable themed Tk widgets.

The legacy ``ui.widgets`` module used to contain every widget implementation.
The implementations now live in focused modules, while this facade preserves
existing imports from ``bookmark_organizer_pro.ui.widgets``.
"""

from __future__ import annotations

from .widget_runtime import (
    _open_external_url,
    apply_window_chrome,
    get_theme,
    set_widget_theme_provider,
    set_widget_window_chrome_provider,
)
from .widget_controls import (
    ModernButton,
    ModernSearch,
    TagEditor,
    TagWidget,
    ThemedWidget,
    Tooltip,
    create_tooltip,
)
from .widget_grid import GridView
from .widget_dashboard_panel import DashboardPanel
from .widget_tray import SystemTrayManager
from .widget_lists import BookmarkListView, CategorySidebar
from .widget_theme_dialogs import ThemeCreatorDialog, ThemeSelectorDialog
from .widget_analytics import AnalyticsDashboard
from .widget_bookmark_editor import BookmarkEditorDialog

__all__ = [
    "AnalyticsDashboard",
    "BookmarkEditorDialog",
    "BookmarkListView",
    "CategorySidebar",
    "DashboardPanel",
    "GridView",
    "ModernButton",
    "ModernSearch",
    "SystemTrayManager",
    "TagEditor",
    "TagWidget",
    "ThemeCreatorDialog",
    "ThemeSelectorDialog",
    "ThemedWidget",
    "Tooltip",
    "_open_external_url",
    "apply_window_chrome",
    "create_tooltip",
    "get_theme",
    "set_widget_theme_provider",
    "set_widget_window_chrome_provider",
]
