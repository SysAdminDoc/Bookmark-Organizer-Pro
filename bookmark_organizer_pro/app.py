"""Tk application coordinator for Bookmark Organizer Pro."""

from __future__ import annotations

import tkinter as tk
from typing import List, Optional

from bookmark_organizer_pro.ai import AIConfigManager
from bookmark_organizer_pro.app_mixins import (
    AiActionsMixin,
    AppShellMixin,
    BookmarkCrudMixin,
    BookmarkViewMixin,
    CategoryActionsMixin,
    CommandPaletteActionsMixin,
    DashboardActionsMixin,
    FilterActionsMixin,
    ImportExportMixin,
    LifecycleActionsMixin,
    SelectionActionsMixin,
    ThemeActionsMixin,
    ToolsActionsMixin,
    ZoomActionsMixin,
)
from bookmark_organizer_pro.commands import CommandStack
from bookmark_organizer_pro.constants import APP_NAME, APP_VERSION
from bookmark_organizer_pro.core import CategoryManager
from bookmark_organizer_pro.managers import BookmarkManager, TagManager
from bookmark_organizer_pro.services import HighSpeedFaviconManager
from bookmark_organizer_pro.theme_runtime import get_theme, get_theme_manager
from bookmark_organizer_pro.ui.infrastructure import NonBlockingTaskRunner
from bookmark_organizer_pro.ui.shell_widgets import ViewMode
from bookmark_organizer_pro.ui.widgets import ThemedWidget, apply_window_chrome


# =============================================================================
# FINAL ENHANCED BOOKMARK ORGANIZER APP
# =============================================================================


class FinalBookmarkOrganizerApp(
    CategoryActionsMixin,
    FilterActionsMixin,
    BookmarkViewMixin,
    SelectionActionsMixin,
    BookmarkCrudMixin,
    ImportExportMixin,
    ToolsActionsMixin,
    ZoomActionsMixin,
    ThemeActionsMixin,
    LifecycleActionsMixin,
    AiActionsMixin,
    DashboardActionsMixin,
    CommandPaletteActionsMixin,
    AppShellMixin,
    ThemedWidget,
):
    """
        Main application class with full feature set.
        
        The primary application window containing all UI components
        and coordinating all application functionality.
        
        Layout:
            - Header: Logo, search bar, toolbar buttons
            - Left Sidebar: Categories, quick filters
            - Main Content: Bookmark list/grid
            - Right Sidebar: Analytics dashboard
            - Status Bar: Status, counts, progress
        
        Attributes:
            root: Tk root window
            theme_manager: ThemeManager instance
            bookmark_manager: BookmarkManager instance
            category_manager: CategoryManager instance
            tag_manager: TagManager instance
            ai_config: AIConfigManager instance
            favicon_manager: FaviconManager instance
            command_stack: CommandStack for undo/redo
        
        Key Methods:
            _add_bookmark(): Add new bookmark
            _edit_bookmark(id): Edit existing bookmark
            _delete_selected(): Delete selected bookmarks
            _import_bookmarks(): Import from file
            _show_export_dialog(): Export to file
            _refresh_bookmark_list(): Refresh display
            _search(query): Perform search
            _show_settings(): Open settings dialog
        
        Keyboard Shortcuts:
            Ctrl+N: New bookmark
            Ctrl+F: Focus search
            Ctrl+I: Import
            Ctrl+S: Export
            Ctrl+Z: Undo
            Ctrl+Y: Redo
            Delete: Delete selected
            F5: Refresh
        """
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.theme_manager = get_theme_manager()
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("1500x950")
        self.root.minsize(1100, 700)
        
        theme = get_theme()
        self.root.configure(bg=theme.bg_primary)
        
        apply_window_chrome(self.root)
        
        # Initialize managers
        self.category_manager = CategoryManager()
        self.tag_manager = TagManager()
        self.bookmark_manager = BookmarkManager(self.category_manager, self.tag_manager)
        self.favicon_manager = HighSpeedFaviconManager(max_workers=15)  # Fast concurrent downloads
        self.task_runner = NonBlockingTaskRunner(root)
        self.command_stack = CommandStack()
        self.ai_config = AIConfigManager()  # AI settings
        
        # State
        self.view_mode = ViewMode.LIST
        self.current_category: Optional[str] = None
        self.search_query: str = ""
        self.selected_bookmarks: List[int] = []
        
        # Placeholder attributes (set before UI is built to prevent errors)
        self.status_label = None
        self.analytics_frame = None
        self.categories_frame = None
        self.tree = None
        self.grid_canvas = None
        self.grid_inner = None
        self.grid_frame = None
        self.main_container = None
        self.filter_buttons = {}
        self.filter_button_parts = {}
        self.count_label = None
        self.collection_summary_frame = None
        self.summary_metric_labels = {}
        self.summary_title_label = None
        self.summary_detail_label = None
        self.selection_bar = None
        self.selection_count_label = None
        self.zoom_label = None
        self.search_var = None
        self.search_entry = None
        self._search_after = None
        self.active_filter = "All"
        self.quick_filter = None  # "pinned", "recent", "broken", "untagged" or None
        self._suppress_search_callback = False  # Flag to prevent search callback during programmatic changes
        
        # Setup favicon callbacks
        self.favicon_manager.set_progress_callback(self._on_favicon_progress)
        self.favicon_manager.set_favicon_ready_callback(self._on_favicon_ready_threadsafe)
        
        # Build UI
        self._setup_styles()
        self._create_menu()
        self._create_main_layout()
        self._create_status_bar()
        
        # Apply initial zoom (scales all fonts for readability)
        self._apply_zoom()

        # Load data
        self._load_and_display_data()
        
        # Keyboard shortcuts - comprehensive set
        self.root.bind("<Control-f>", lambda e: self._focus_search())
        self.root.bind("<Control-l>", lambda e: self._focus_search())  # Also Ctrl+L
        self.root.bind("<Control-n>", lambda e: self._add_bookmark())
        self.root.bind("<Control-i>", lambda e: self._show_import_dialog())
        self.root.bind("<Control-o>", lambda e: self._show_import_dialog())  # Also Ctrl+O
        self.root.bind("<Control-a>", lambda e: self._select_all_bookmarks())
        self.root.bind("<Control-z>", lambda e: self._undo())
        self.root.bind("<Control-y>", lambda e: self._redo())
        self.root.bind("<Control-s>", lambda e: self._show_export_dialog())
        self.root.bind("<Control-e>", lambda e: self._edit_selected())
        self.root.bind("<Control-p>", lambda e: self._show_command_palette())
        self.root.bind("<Escape>", lambda e: self._clear_search())
        self.root.bind("<F5>", lambda e: self._refresh_all())
        self.root.bind("<Delete>", lambda e: self._delete_selected())
    
        # Window events
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Try to enable window-wide drag-drop
        self._try_enable_window_dnd()

        # Start analytics polling (update every 30 seconds)
        self._start_analytics_polling()

