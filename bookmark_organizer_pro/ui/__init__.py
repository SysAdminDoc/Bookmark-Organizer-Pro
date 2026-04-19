"""UI architecture primitives for Bookmark Organizer Pro.

This package is intentionally toolkit-light. Keep reusable product-facing
formatting, design tokens, and view-model builders here so Tkinter widgets do
not own application copy, display math, or visual constants.
"""

from .foundation import (
    FONTS,
    DesignTokens,
    FontConfig,
    display_or_fallback,
    format_compact_count,
    get_system_font,
    pluralize,
    readable_text_on,
    truncate_middle,
)
from .density import DENSITY_SETTINGS, DensityManager, DisplayDensity
from .dependencies import DependencyCheckDialog, check_and_install_dependencies
from .quick_add import (
    DEFAULT_CATEGORY,
    FAVICON_PLACEHOLDER,
    TITLE_PLACEHOLDER,
    QuickAddPayload,
    pick_default_category,
    prepare_quick_add_payload,
)
from .reports import ReportGenerator
from .system_theme import SystemThemeDetector
from .tk_interactions import make_keyboard_activatable
from .view_models import (
    CollectionSummaryViewModel,
    FilterCountsViewModel,
    build_collection_summary,
    build_filter_counts,
)
from .theme import ThemeColors, ThemeInfo, ThemeManager

__all__ = [
    "FONTS",
    "DesignTokens",
    "FontConfig",
    "display_or_fallback",
    "format_compact_count",
    "get_system_font",
    "pluralize",
    "readable_text_on",
    "truncate_middle",
    "DENSITY_SETTINGS",
    "DensityManager",
    "DisplayDensity",
    "DependencyCheckDialog",
    "check_and_install_dependencies",
    "DEFAULT_CATEGORY",
    "FAVICON_PLACEHOLDER",
    "TITLE_PLACEHOLDER",
    "QuickAddPayload",
    "pick_default_category",
    "prepare_quick_add_payload",
    "ReportGenerator",
    "SystemThemeDetector",
    "make_keyboard_activatable",
    "CollectionSummaryViewModel",
    "FilterCountsViewModel",
    "build_collection_summary",
    "build_filter_counts",
    "ThemeColors",
    "ThemeInfo",
    "ThemeManager",
]
