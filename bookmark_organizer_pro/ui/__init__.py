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
from .about import AboutDialog
from .bookmark_workflows import (
    BookmarkDetailPanel,
    BulkTagEditorDialog,
    EmojiPicker,
    QuickAddDialog,
    SelectiveExportDialog,
    SmartFiltersPanel,
)
from .cleanup_review import (
    CleanupReviewDialog,
    CleanupReviewGroup,
    build_hybrid_duplicate_review_groups,
    build_tag_lint_review_groups,
    build_url_duplicate_review_groups,
)
from .components import (
    DragDropImportArea,
    EnhancedProgressBar,
    FaviconStatusDisplay,
    ScrollableFrame,
    ThemeDropdown,
)
from .density import DENSITY_SETTINGS, DensityManager, DisplayDensity
from .dependencies import DependencyCheckDialog, check_and_install_dependencies
from .feedback import EmptyState, FilteredEmptyState, HoverPreview, ToastNotification
from .infrastructure import NonBlockingTaskRunner, WindowTransparency
from .import_center import ImportCenterDialog, ImportSource, build_import_sources
from .management_dialogs import CategoryManagementDialog, CustomFaviconDialog
from .navigation import ClipboardMonitor, SearchHighlighter, VimNavigator
from .quick_add import (
    DEFAULT_CATEGORY,
    FAVICON_PLACEHOLDER,
    TITLE_PLACEHOLDER,
    QuickAddPayload,
    pick_default_category,
    prepare_quick_add_payload,
)
from .read_later_queue import ReadLaterQueueDialog, ReadLaterQueueRow, build_read_later_rows
from .graph_view import GraphViewDialog
from .reader_view import ReaderViewDialog, text_index_offset
from .reports import ReportGenerator
from .shell_widgets import (
    CommandPalette,
    StatusBar,
    StyledDropdownMenu,
    ViewMode,
    show_styled_menu,
)
from .style_manager import StyleManager, style_manager
from .system_theme import SystemThemeDetector
from .tk_interactions import make_keyboard_activatable
from .treeview import BookmarkListWidget, SortableTreeview, TKSHEET_AVAILABLE, VirtualBookmarkSheet
from .view_models import (
    CollectionPulseViewModel,
    CollectionSummaryViewModel,
    FilterCountsViewModel,
    build_collection_pulse,
    build_collection_summary,
    build_filter_counts,
)
from .theme import ThemeColors, ThemeInfo, ThemeManager
from .widgets import (
    AnalyticsDashboard,
    BookmarkEditorDialog,
    ModernButton,
    ModernSearch,
    TagEditor,
    TagWidget,
    ThemeCreatorDialog,
    ThemeSelectorDialog,
    ThemedWidget,
    Tooltip,
    create_tooltip,
    set_widget_theme_provider,
    set_widget_window_chrome_provider,
)

__all__ = [
    "FONTS",
    "DesignTokens",
    "FontConfig",
    "AboutDialog",
    "BookmarkDetailPanel",
    "BulkTagEditorDialog",
    "EmojiPicker",
    "QuickAddDialog",
    "SelectiveExportDialog",
    "SmartFiltersPanel",
    "CleanupReviewDialog",
    "CleanupReviewGroup",
    "build_hybrid_duplicate_review_groups",
    "build_tag_lint_review_groups",
    "build_url_duplicate_review_groups",
    "DragDropImportArea",
    "EnhancedProgressBar",
    "FaviconStatusDisplay",
    "ScrollableFrame",
    "ThemeDropdown",
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
    "EmptyState",
    "FilteredEmptyState",
    "HoverPreview",
    "ToastNotification",
    "NonBlockingTaskRunner",
    "WindowTransparency",
    "ImportCenterDialog",
    "ImportSource",
    "build_import_sources",
    "CategoryManagementDialog",
    "CustomFaviconDialog",
    "ClipboardMonitor",
    "SearchHighlighter",
    "VimNavigator",
    "DEFAULT_CATEGORY",
    "FAVICON_PLACEHOLDER",
    "TITLE_PLACEHOLDER",
    "QuickAddPayload",
    "pick_default_category",
    "prepare_quick_add_payload",
    "ReadLaterQueueDialog",
    "ReadLaterQueueRow",
    "build_read_later_rows",
    "GraphViewDialog",
    "ReaderViewDialog",
    "text_index_offset",
    "ReportGenerator",
    "CommandPalette",
    "StatusBar",
    "StyledDropdownMenu",
    "ViewMode",
    "show_styled_menu",
    "StyleManager",
    "style_manager",
    "SystemThemeDetector",
    "make_keyboard_activatable",
    "BookmarkListWidget",
    "SortableTreeview",
    "TKSHEET_AVAILABLE",
    "VirtualBookmarkSheet",
    "CollectionSummaryViewModel",
    "CollectionPulseViewModel",
    "FilterCountsViewModel",
    "build_collection_pulse",
    "build_collection_summary",
    "build_filter_counts",
    "ThemeColors",
    "ThemeInfo",
    "ThemeManager",
    "AnalyticsDashboard",
    "BookmarkEditorDialog",
    "ModernButton",
    "ModernSearch",
    "TagEditor",
    "TagWidget",
    "ThemeCreatorDialog",
    "ThemeSelectorDialog",
    "ThemedWidget",
    "Tooltip",
    "create_tooltip",
    "set_widget_theme_provider",
    "set_widget_window_chrome_provider",
]
