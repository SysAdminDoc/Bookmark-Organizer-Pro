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
from .components import (
    DragDropImportArea,
    EnhancedProgressBar,
    FaviconStatusDisplay,
    MiniAnalyticsDashboard,
    ScrollableFrame,
    ThemeDropdown,
)
from .density import DENSITY_SETTINGS, DensityManager, DisplayDensity
from .dependencies import DependencyCheckDialog, check_and_install_dependencies
from .drag_drop import CategoryDragDropManager
from .feedback import EmptyState, FilteredEmptyState, HoverPreview, ToastNotification
from .infrastructure import NonBlockingTaskRunner, WindowTransparency
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
from .reports import ReportGenerator
from .secondary_views import (
    KanbanColumn,
    KanbanView,
    ReadingListView,
    TagCloudView,
    TimelineView,
)
from .shell_widgets import (
    BookmarkCard,
    CommandPalette,
    StatusBar,
    StyledDropdownMenu,
    SystemTray,
    ViewMode,
    show_styled_menu,
)
from .style_manager import StyleManager, style_manager
from .system_theme import SystemThemeDetector
from .tk_interactions import make_keyboard_activatable
from .treeview import SortableTreeview
from .view_models import (
    CollectionSummaryViewModel,
    FilterCountsViewModel,
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
    "DragDropImportArea",
    "EnhancedProgressBar",
    "FaviconStatusDisplay",
    "MiniAnalyticsDashboard",
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
    "CategoryDragDropManager",
    "EmptyState",
    "FilteredEmptyState",
    "HoverPreview",
    "ToastNotification",
    "NonBlockingTaskRunner",
    "WindowTransparency",
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
    "ReportGenerator",
    "KanbanColumn",
    "KanbanView",
    "ReadingListView",
    "TagCloudView",
    "TimelineView",
    "BookmarkCard",
    "CommandPalette",
    "StatusBar",
    "StyledDropdownMenu",
    "SystemTray",
    "ViewMode",
    "show_styled_menu",
    "StyleManager",
    "style_manager",
    "SystemThemeDetector",
    "make_keyboard_activatable",
    "SortableTreeview",
    "CollectionSummaryViewModel",
    "FilterCountsViewModel",
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
