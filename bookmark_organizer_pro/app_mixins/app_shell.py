"""Main application shell construction for the app coordinator."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from bookmark_organizer_pro.constants import APP_NAME
from bookmark_organizer_pro.ui.components import DragDropImportArea, ScrollableFrame, ThemeDropdown
from bookmark_organizer_pro.ui.feedback import EmptyState, FilteredEmptyState
from bookmark_organizer_pro.ui.foundation import FONTS, DesignTokens, readable_text_on
from bookmark_organizer_pro.ui.shell_widgets import ViewMode
from bookmark_organizer_pro.ui.tk_interactions import make_keyboard_activatable
from bookmark_organizer_pro.ui.treeview import SortableTreeview
from bookmark_organizer_pro.ui.widgets import ModernButton, Tooltip, get_theme


class AppShellMixin:
    """Search focus, menu, style, and primary layout construction."""

    def _focus_search(self, event=None):
        """Focus the search entry and select all text"""
        if hasattr(self, 'search_entry') and self.search_entry:
            self.search_entry.focus_set()
            self.search_entry.select_range(0, tk.END)
        return "break"
    
    def _setup_styles(self):
        """Configure ttk styles"""
        theme = get_theme()
        style = ttk.Style()
        
        try:
            style.theme_use('clam')
        except Exception:
            pass
        
        style.configure(
            "Treeview",
            background=theme.bg_primary,
            foreground=theme.text_primary,
            fieldbackground=theme.bg_primary,
            borderwidth=0,
            rowheight=DesignTokens.TREEVIEW_ROW_HEIGHT,
            font=FONTS.body()
        )
        
        style.configure(
            "Treeview.Heading",
            background=theme.bg_secondary,
            foreground=theme.text_secondary,
            borderwidth=0,
            relief=tk.FLAT,
            font=FONTS.small(bold=True)
        )
        
        style.map(
            "Treeview",
            background=[("selected", theme.selection), ("focus", theme.bg_hover)],
            foreground=[("selected", theme.text_primary)]
        )
    
    def _create_menu(self):
        """Create menu bar"""
        theme = get_theme()
        
        menubar = tk.Menu(self.root, bg=theme.bg_dark, fg=theme.text_primary,
                         activebackground=theme.selection, borderwidth=0)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary)
        file_menu.add_command(label="New Bookmark", accelerator="Ctrl+N", command=self._add_bookmark)
        file_menu.add_separator()
        file_menu.add_command(label="Import…", accelerator="Ctrl+I", command=self._show_import_dialog)
        file_menu.add_command(label="Export…", accelerator="Ctrl+S", command=self._show_export_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary)
        edit_menu.add_command(label="Undo", accelerator="Ctrl+Z", command=self._undo)
        edit_menu.add_command(label="Redo", accelerator="Ctrl+Y", command=self._redo)
        edit_menu.add_separator()
        edit_menu.add_command(label="Select All", accelerator="Ctrl+A", command=self._select_all_bookmarks)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary)
        view_menu.add_command(label="List View", command=lambda: self._set_view_mode(ViewMode.LIST))
        view_menu.add_separator()
        view_menu.add_command(label="Command Palette", accelerator="Ctrl+P", command=self._show_command_palette)
        view_menu.add_separator()
        view_menu.add_command(label="Refresh", accelerator="F5", command=self._refresh_all)
        menubar.add_cascade(label="View", menu=view_menu)
        
        self.root.config(menu=menubar)
    
    def _create_main_layout(self):
        """Create main application layout"""
        theme = get_theme()
        
        # Main container
        self.main_container = tk.Frame(self.root, bg=theme.bg_primary)
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        # ===== HEADER / TOOLBAR =====
        header = tk.Frame(
            self.main_container, bg=theme.bg_dark, height=DesignTokens.HEADER_HEIGHT,
            highlightbackground=theme.border_muted, highlightthickness=1
        )
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        # Brand block
        brand = tk.Frame(header, bg=theme.bg_dark)
        brand.pack(side=tk.LEFT, padx=(24, 18), pady=12)
        brand_row = tk.Frame(brand, bg=theme.bg_dark)
        brand_row.pack(anchor="w")
        tk.Label(
            brand_row, text="B", bg=theme.accent_primary,
            fg=readable_text_on(theme.accent_primary),
            font=FONTS.header(bold=True), width=2, padx=3, pady=3
        ).pack(side=tk.LEFT, padx=(0, 9))
        tk.Label(
            brand_row, text=APP_NAME, bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.title(bold=True)
        ).pack(side=tk.LEFT)
        tk.Label(
            brand, text="Library workspace for saved links",
            bg=theme.bg_dark, fg=theme.text_secondary, font=FONTS.small()
        ).pack(anchor="w", pady=(2, 0))
        
        # Search bar
        search_frame = tk.Frame(
            header, bg=theme.bg_secondary,
            highlightbackground=theme.border_muted,
            highlightthickness=DesignTokens.FOCUS_RING_WIDTH
        )
        search_frame.pack(side=tk.LEFT, padx=(0, 18), fill=tk.X, expand=True, pady=14)
        self.search_frame = search_frame
        
        tk.Label(
            search_frame, text="Search", bg=theme.bg_secondary,
            fg=theme.text_muted, font=FONTS.tiny(bold=True)
        ).pack(side=tk.LEFT, padx=(12, 4))
        
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', self._on_search_change)
        
        self.search_entry = tk.Entry(
            search_frame, textvariable=self.search_var,
            bg=theme.bg_secondary, fg=theme.text_muted,
            insertbackground=theme.text_primary, bd=0,
            font=FONTS.body(), width=35
        )
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=9, padx=5)
        Tooltip(self.search_entry, "Search bookmarks by title, URL, category, or tags.\nSpecial filters: is:pinned, is:broken, is:recent, is:untagged, domain:xyz")

        # Placeholder text
        self._search_placeholder = "Search links, domain:, #tag, or is:pinned…"
        self._suppress_search_callback = True
        self.search_entry.insert(0, self._search_placeholder)
        self._suppress_search_callback = False
        self.search_entry.bind("<FocusIn>", self._on_search_focus_in)
        self.search_entry.bind("<FocusOut>", self._on_search_focus_out)
        
        # Clear search button (X) - more visible styling
        self.clear_search_btn = tk.Label(
            search_frame, text="  ✕  ", bg=theme.bg_tertiary,
            fg=theme.text_secondary, font=FONTS.body(bold=True), cursor="hand2",
            relief=tk.FLAT, padx=4, pady=2
        )
        self.clear_search_btn.pack(side=tk.LEFT, padx=(5, 0))
        self.clear_search_btn.pack_forget()
        
        make_keyboard_activatable(self.clear_search_btn, self._clear_search)
        self.clear_search_btn.bind("<Enter>", lambda e: self.clear_search_btn.configure(
            bg=theme.accent_error, fg="white"))
        self.clear_search_btn.bind("<Leave>", lambda e: self.clear_search_btn.configure(
            bg=theme.bg_tertiary, fg=theme.text_secondary))
        Tooltip(self.clear_search_btn, "Clear Search")

        search_shortcut = tk.Label(
            search_frame, text="Ctrl+F", bg=theme.bg_tertiary,
            fg=theme.text_muted, font=FONTS.tiny(bold=True),
            padx=8, pady=3
        )
        search_shortcut.pack(side=tk.RIGHT, padx=(8, 10))
        
        # ===== TOOLBAR BUTTONS =====
        toolbar = tk.Frame(header, bg=theme.bg_dark)
        toolbar.pack(side=tk.RIGHT, padx=(0, 18))
        
        # Add button
        add_btn = ModernButton(
            toolbar, text="New", icon="+", style="primary",
            command=self._add_bookmark,
            tooltip="Add a new bookmark manually"
        )
        add_btn.pack(side=tk.LEFT, padx=3)
        
        # Import button
        import_btn = ModernButton(
            toolbar, text="Import", icon="↓",
            command=self._show_import_dialog,
            tooltip="Import bookmarks from HTML, JSON, CSV, or OPML files"
        )
        import_btn.pack(side=tk.LEFT, padx=3)
        
        # Export button
        export_btn = ModernButton(
            toolbar, text="Export", icon="↑",
            command=self._show_export_dialog,
            tooltip="Export bookmarks to HTML, JSON, CSV, or Markdown"
        )
        export_btn.pack(side=tk.LEFT, padx=3)
        
        # Separator
        tk.Frame(toolbar, bg=theme.border_muted, width=1, height=30).pack(side=tk.LEFT, padx=8)
        
        # AI button
        self.ai_btn = ModernButton(
            toolbar, text="AI",
            command=self._show_ai_menu,
            tooltip="AI-powered tools: Auto-categorize, Generate tags,\nSummarize, Find semantic duplicates"
        )
        self.ai_btn.pack(side=tk.LEFT, padx=3)
        
        # Tools button
        self.tools_btn = ModernButton(
            toolbar, text="Tools",
            command=self._show_tools_menu,
            tooltip="Tools: Check links, Find duplicates,\nClean URLs, Manage categories, Backup"
        )
        self.tools_btn.pack(side=tk.LEFT, padx=3)
        
        # Separator
        tk.Frame(toolbar, bg=theme.border_muted, width=1, height=30).pack(side=tk.LEFT, padx=8)
        
        # Theme dropdown
        self.theme_dropdown = ThemeDropdown(
            toolbar, self.theme_manager,
            on_change=lambda t: self._on_theme_change(t)
        )
        self.theme_dropdown.pack(side=tk.LEFT, padx=3)
        Tooltip(self.theme_dropdown, "Change application theme/color scheme")
        
        # Zoom controls
        tk.Frame(toolbar, bg=theme.border_muted, width=1, height=30).pack(side=tk.LEFT, padx=8)
        
        zoom_frame = tk.Frame(toolbar, bg=theme.bg_dark)
        zoom_frame.pack(side=tk.LEFT, padx=3)
        
        self.zoom_level = 115  # Default slightly larger for high-DPI readability
        self.zoom_min = 75
        self.zoom_max = 200
        
        zoom_out_btn = ModernButton(
            zoom_frame, text="−", command=self._zoom_out,
            tooltip="Zoom Out (Ctrl+Scroll Down)"
        )
        zoom_out_btn.pack(side=tk.LEFT, padx=1)
        
        self.zoom_label = tk.Label(
            zoom_frame, text="100%", bg=theme.bg_secondary,
            fg=theme.text_primary, font=FONTS.small(), width=5, padx=5, pady=4
        )
        self.zoom_label.pack(side=tk.LEFT, padx=2)
        Tooltip(self.zoom_label, "Current zoom level - Use Ctrl+Scroll to zoom")
        
        zoom_in_btn = ModernButton(
            zoom_frame, text="+", command=self._zoom_in,
            tooltip="Zoom In (Ctrl+Scroll Up)"
        )
        zoom_in_btn.pack(side=tk.LEFT, padx=1)
        
        # ===== CONTENT AREA =====
        content = tk.Frame(self.main_container, bg=theme.bg_primary)
        content.pack(fill=tk.BOTH, expand=True)
        
        # ----- LEFT SIDEBAR (Scrollable) -----
        left_sidebar = tk.Frame(content, bg=theme.bg_dark, width=DesignTokens.SIDEBAR_WIDTH)
        left_sidebar.pack(side=tk.LEFT, fill=tk.Y)
        left_sidebar.pack_propagate(False)
        
        # Scrollable container for left sidebar
        self.left_scroll = ScrollableFrame(left_sidebar, bg=theme.bg_dark)
        self.left_scroll.pack(fill=tk.BOTH, expand=True)
        
        # Enhanced drag-drop import area
        self.import_area = DragDropImportArea(
            self.left_scroll.inner, on_files_dropped=self._on_files_dropped
        )
        self.import_area.pack(fill=tk.X, padx=DesignTokens.PANEL_PAD, pady=DesignTokens.PANEL_PAD)
        self.import_area.set_compact(True)
        
        # Quick filters
        filters_frame = tk.Frame(self.left_scroll.inner, bg=theme.bg_dark)
        filters_frame.pack(fill=tk.X, padx=DesignTokens.PANEL_PAD, pady=(0, DesignTokens.SPACE_MD))
        
        tk.Label(
            filters_frame, text="VIEWS", bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.tiny(bold=True)
        ).pack(anchor="w", pady=(5, 7))
        
        self.filter_buttons = {}
        self.filter_button_parts = {}
        self.active_filter = "All"  # Track active filter
        
        # Filter tooltips
        filter_tooltips = {
            "All": "Show all bookmarks",
            "Pinned": "Show only pinned bookmarks",
            "Recent": "Show bookmarks added in the last 7 days",
            "Broken": "Show bookmarks with broken links",
            "Untagged": "Show bookmarks without any tags"
        }
        
        for filter_name, label in [
            ("All", "All Links"),
            ("Pinned", "Pinned"),
            ("Recent", "Recent"),
            ("Broken", "Needs Review"),
            ("Untagged", "Untagged"),
        ]:
            is_active = (filter_name == "All")  # All is active by default
            row = tk.Frame(
                filters_frame,
                bg=theme.selection if is_active else theme.bg_dark,
                cursor="hand2", highlightthickness=1,
                highlightbackground=theme.border_muted if is_active else theme.bg_dark
            )
            row.pack(fill=tk.X, pady=2)
            name_lbl = tk.Label(
                row, text=label,
                bg=row["bg"], fg=theme.text_primary,
                font=FONTS.body(), cursor="hand2",
                anchor="w", padx=10, pady=6
            )
            name_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            count_lbl = tk.Label(
                row, text="0", bg=theme.bg_tertiary if is_active else theme.bg_primary,
                fg=theme.text_secondary, font=FONTS.tiny(bold=True),
                cursor="hand2", padx=7, pady=1
            )
            count_lbl.pack(side=tk.RIGHT, padx=(4, 8), pady=6)

            for widget in (row, name_lbl, count_lbl):
                widget.bind("<Button-1>", lambda e, f=filter_name: self._apply_filter(f))

                def on_enter(e, f=filter_name):
                    if self.active_filter != f:
                        self._set_filter_visual(f, False, hover=True)

                def on_leave(e, f=filter_name):
                    if self.active_filter != f:
                        self._set_filter_visual(f, False)

                widget.bind("<Enter>", on_enter)
                widget.bind("<Leave>", on_leave)

            self.filter_buttons[filter_name] = row
            self.filter_button_parts[filter_name] = (row, name_lbl, count_lbl)
            make_keyboard_activatable(row, lambda f=filter_name: self._apply_filter(f))
            row.bind("<FocusIn>", lambda e, f=filter_name: self._set_filter_visual(f, self.active_filter == f, hover=True))
            row.bind("<FocusOut>", lambda e, f=filter_name: self._set_filter_visual(f, self.active_filter == f))
            
            # Add tooltip
            Tooltip(row, filter_tooltips.get(filter_name, ""))
        
        # Categories header
        cat_header = tk.Frame(self.left_scroll.inner, bg=theme.bg_dark)
        cat_header.pack(fill=tk.X, padx=DesignTokens.PANEL_PAD, pady=(16, 7))
        
        tk.Label(
            cat_header, text="CATEGORIES", bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.tiny(bold=True)
        ).pack(side=tk.LEFT)
        
        # Categories list
        self.categories_frame = tk.Frame(self.left_scroll.inner, bg=theme.bg_dark)
        self.categories_frame.pack(fill=tk.X, padx=DesignTokens.PANEL_PAD, pady=(0, 20))
        
        # ----- MAIN CONTENT -----
        self.content_area = tk.Frame(content, bg=theme.bg_primary)
        self.content_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Content header
        content_header = tk.Frame(self.content_area, bg=theme.bg_primary)
        content_header.pack(fill=tk.X, padx=DesignTokens.CONTENT_PAD_X, pady=(16, 8))
        
        self.count_label = tk.Label(
            content_header, text="Library", bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.header(bold=True)
        )
        self.count_label.pack(side=tk.LEFT)

        self.view_hint_label = tk.Label(
            content_header, text="List view",
            bg=theme.bg_primary, fg=theme.text_muted, font=FONTS.small()
        )
        self.view_hint_label.pack(side=tk.RIGHT)

        self._create_collection_summary()
        
        # List view frame
        self.list_frame = tk.Frame(self.content_area, bg=theme.bg_primary)
        
        # Create sortable treeview - REMOVED "Added" column, added more padding
        columns = ("title", "url", "category", "tags")
        self.tree = SortableTreeview(
            self.list_frame, columns=columns, show="tree headings",
            selectmode="extended"
        )
        
        # Configure columns with MORE padding for favicon
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=34, stretch=False, minwidth=34)
        
        self.tree.heading("title", text="Title")
        self.tree.column("title", width=245, minwidth=160)
        
        self.tree.heading("url", text="Domain")
        self.tree.column("url", width=190, minwidth=150)
        
        self.tree.heading("category", text="Category")
        self.tree.column("category", width=170, minwidth=130)
        
        self.tree.heading("tags", text="Tags")
        self.tree.column("tags", width=170, minwidth=130)
        
        # Scrollbars
        tree_scroll_y = ttk.Scrollbar(self.list_frame, orient="vertical", command=self.tree.yview)
        tree_scroll_x = ttk.Scrollbar(self.list_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)
        self.tree.tag_configure("oddrow", background=theme.bg_primary)
        self.tree.tag_configure("evenrow", background=theme.bg_secondary)
        self.tree.tag_configure("broken", foreground=theme.accent_error)
        self.tree.tag_configure("pinned", foreground=theme.text_primary)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Tree bindings
        self.tree.bind("<Double-1>", self._on_item_double_click)
        self.tree.bind("<Return>", lambda e: self._open_selected())
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<<TreeviewSelect>>", self._on_selection_change)
        
        # Ctrl+Scroll zoom binding
        self.tree.bind("<Control-MouseWheel>", self._on_mousewheel_zoom)
        self.list_frame.bind("<Control-MouseWheel>", self._on_mousewheel_zoom)

        self._create_selection_bar()

        # Empty state (shown when no bookmarks exist)
        self.empty_state = EmptyState(
            self.content_area,
            on_import=self._show_import_dialog,
            on_add=self._add_bookmark
        )
        self.filtered_empty_state = FilteredEmptyState(
            self.content_area,
            on_clear=self._clear_search,
            on_add=self._add_bookmark
        )

        # Show list view by default
        self.list_frame.pack(fill=tk.BOTH, expand=True, padx=DesignTokens.CONTENT_PAD_X, pady=(0, DesignTokens.CONTENT_PAD_Y))

        # ----- RIGHT SIDEBAR (Scrollable) - ANALYTICS -----
        right_sidebar = tk.Frame(content, bg=theme.bg_dark, width=DesignTokens.RIGHT_SIDEBAR_WIDTH)
        right_sidebar.pack(side=tk.RIGHT, fill=tk.Y, before=self.content_area)
        right_sidebar.pack_propagate(False)
        
        # Scrollable container for right sidebar
        self.right_scroll = ScrollableFrame(right_sidebar, bg=theme.bg_dark)
        self.right_scroll.pack(fill=tk.BOTH, expand=True)
        
        # Analytics Dashboard
        self._create_analytics_panel()

