"""Main application shell construction for the app coordinator."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from bookmark_organizer_pro.constants import APP_NAME
from bookmark_organizer_pro.i18n import _
from bookmark_organizer_pro.ui.components import DragDropImportArea, ScrollableFrame
from bookmark_organizer_pro.ui.feedback import EmptyState, FilteredEmptyState
from bookmark_organizer_pro.ui.foundation import FONTS, DesignTokens, readable_text_on
from bookmark_organizer_pro.ui.shell_widgets import ViewMode
from bookmark_organizer_pro.ui.tk_interactions import make_keyboard_activatable, route_pointer_to_control
from bookmark_organizer_pro.ui.treeview import BookmarkListWidget
from bookmark_organizer_pro.ui.widget_chat_panel import ChatPanel
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
        """Apply treeview tag colors after style_manager has set base styles."""
        pass
    
    def _create_menu(self):
        """Create menu bar"""
        theme = get_theme()
        
        menubar = tk.Menu(self.root, bg=theme.bg_dark, fg=theme.text_primary,
                         activebackground=theme.selection, borderwidth=0)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary)
        file_menu.add_command(label=_("New Bookmark"), accelerator="Ctrl+N", command=self._add_bookmark)
        file_menu.add_separator()
        file_menu.add_command(label=_("Import…"), accelerator="Ctrl+I", command=self._show_import_dialog)
        file_menu.add_command(label=_("Export…"), accelerator="Ctrl+S", command=self._show_export_dialog)
        file_menu.add_separator()
        file_menu.add_command(label=_("Restore from Backup…"), command=self._show_restore_dialog)
        file_menu.add_separator()
        file_menu.add_command(label=_("Exit"), command=self._on_close)
        menubar.add_cascade(label=_("File"), menu=file_menu)

        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary)
        edit_menu.add_command(label=_("Undo"), accelerator="Ctrl+Z", command=self._undo)
        edit_menu.add_command(label=_("Redo"), accelerator="Ctrl+Y", command=self._redo)
        edit_menu.add_separator()
        edit_menu.add_command(label=_("Select All"), accelerator="Ctrl+A", command=self._select_all_bookmarks)
        menubar.add_cascade(label=_("Edit"), menu=edit_menu)

        # View menu
        view_menu = tk.Menu(menubar, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary)
        view_menu.add_command(label=_("List View"), command=lambda: self._set_view_mode(ViewMode.LIST))
        self._right_rail_var = tk.BooleanVar(value=True)
        view_menu.add_checkbutton(
            label=_("Insights and assistant rail"),
            variable=self._right_rail_var,
            command=self._toggle_right_rail,
        )
        view_menu.add_separator()
        view_menu.add_command(label=_("Command Palette"), accelerator="Ctrl+P", command=self._show_command_palette)
        view_menu.add_separator()
        view_menu.add_command(label=_("Refresh"), accelerator="F5", command=self._refresh_all)
        menubar.add_cascade(label=_("View"), menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary)
        help_menu.add_command(label=_("Search Syntax"), command=self._show_search_syntax_help)
        help_menu.add_command(label=_("Keyboard Shortcuts"), command=self._show_keyboard_shortcuts)
        help_menu.add_separator()
        help_menu.add_command(label=_("About"), command=self._show_about_dialog)
        menubar.add_cascade(label=_("Help"), menu=help_menu)

        self.root.config(menu=menubar)

    def _show_search_syntax_help(self):
        from bookmark_organizer_pro.search import SearchEngine
        get_syntax_help = SearchEngine.get_syntax_help
        win = tk.Toplevel(self.root)
        win.title("Search Syntax")
        win.geometry("520x480")
        win.transient(self.root)
        win.grab_set()
        win.bind("<Escape>", lambda e: win.destroy())
        theme = get_theme()
        text = tk.Text(win, bg=theme.bg_primary, fg=theme.text_primary,
                       font=FONTS.body(), wrap=tk.WORD, padx=12, pady=12,
                       relief=tk.FLAT, highlightthickness=0)
        text.insert(tk.END, get_syntax_help())
        text.configure(state=tk.DISABLED)
        text.pack(fill=tk.BOTH, expand=True)

    def _show_keyboard_shortcuts(self):
        shortcuts = [
            ("Ctrl+N", "New bookmark"),
            ("Ctrl+I", "Import bookmarks"),
            ("Ctrl+S", "Export bookmarks"),
            ("Ctrl+F", "Focus search bar"),
            ("Ctrl+P", "Command palette"),
            ("Ctrl+Z", "Undo"),
            ("Ctrl+Y", "Redo"),
            ("Ctrl+A", "Select all"),
            ("Ctrl++", "Zoom in"),
            ("Ctrl+-", "Zoom out"),
            ("F5", "Refresh"),
            ("Delete", "Delete selected"),
            ("Escape", "Close dialog"),
        ]
        win = tk.Toplevel(self.root)
        win.title("Keyboard Shortcuts")
        win.geometry("400x400")
        win.transient(self.root)
        win.grab_set()
        win.bind("<Escape>", lambda e: win.destroy())
        theme = get_theme()
        win.configure(bg=theme.bg_primary)
        for key, desc in shortcuts:
            row = tk.Frame(win, bg=theme.bg_primary)
            row.pack(fill=tk.X, padx=16, pady=3)
            tk.Label(row, text=key, font=FONTS.body(bold=True), width=12, anchor="w",
                     bg=theme.bg_primary, fg=theme.accent_primary).pack(side=tk.LEFT)
            tk.Label(row, text=desc, font=FONTS.body(), anchor="w",
                     bg=theme.bg_primary, fg=theme.text_primary).pack(side=tk.LEFT)

    def _show_about_dialog(self):
        from bookmark_organizer_pro.ui.about import AboutDialog
        AboutDialog(self.root)

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
        brand = tk.Frame(header, bg=theme.bg_dark, width=294)
        brand.pack(side=tk.LEFT, padx=(18, 12), pady=9, fill=tk.Y)
        brand.pack_propagate(False)
        brand_row = tk.Frame(brand, bg=theme.bg_dark)
        brand_row.pack(anchor="w")
        tk.Label(
            brand_row, text="B", bg=theme.accent_primary,
            fg=readable_text_on(theme.accent_primary),
            font=FONTS.header(bold=True), width=2, padx=3, pady=4
        ).pack(side=tk.LEFT, padx=(0, 9))
        tk.Label(
            brand_row, text=APP_NAME, bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.body(bold=True)
        ).pack(side=tk.LEFT)
        tk.Label(
            brand, text=_("Your library stays on this device"),
            bg=theme.bg_dark, fg=theme.text_secondary,
            font=FONTS.tiny(), anchor="w",
        ).pack(anchor="w", padx=(43, 0), pady=(1, 0))
        
        # Search bar
        search_frame = tk.Frame(
            header, bg=theme.bg_secondary,
            highlightbackground=theme.border_muted,
            highlightthickness=DesignTokens.FOCUS_RING_WIDTH
        )
        search_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 12), pady=13)
        self.search_frame = search_frame

        self._search_icon_label = tk.Label(
            search_frame, text="⌕", bg=theme.bg_secondary,
            fg=theme.text_muted, font=FONTS.small()
        )
        self._search_icon_label.pack(side=tk.LEFT, padx=(12, 6))

        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', self._on_search_change)

        self.search_entry = tk.Entry(
            search_frame, textvariable=self.search_var,
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            font=FONTS.body(), width=22
        )
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=7, padx=5)
        Tooltip(self.search_entry,
               "Search by title, URL, category, or tags.\n"
               "Filters: tag: category: domain: title: url:\n"
               "  content: before: after: is: has: visits:>N\n"
               "Type a prefix (e.g. tag:) for suggestions.")

        # Placeholder text
        self._search_placeholder = "Search your library"
        self._suppress_search_callback = True
        self.search_entry.insert(0, self._search_placeholder)
        self.search_entry.configure(fg=theme.text_muted)
        self._suppress_search_callback = False
        self.search_entry.bind("<FocusIn>", self._on_search_focus_in)
        self.search_entry.bind("<FocusOut>", self._on_search_focus_out)
        
        self.clear_search_btn = tk.Label(
            search_frame, text=_("Clear"), bg=theme.bg_secondary,
            fg=theme.text_muted, font=FONTS.body(), cursor="hand2",
            relief=tk.FLAT
        )
        self.clear_search_btn.pack(side=tk.LEFT, padx=(4, 0))
        self.clear_search_btn.pack_forget()

        make_keyboard_activatable(self.clear_search_btn, self._clear_search)
        self.clear_search_btn.bind("<Enter>", lambda e: self.clear_search_btn.configure(
            fg=theme.accent_error))
        self.clear_search_btn.bind("<Leave>", lambda e: self.clear_search_btn.configure(
            fg=theme.text_muted))
        Tooltip(self.clear_search_btn, _("Clear search and filters"))

        self._nl_search_mode = False
        self._nl_toggle_btn = tk.Label(
            search_frame, text=_("AI"), bg=theme.bg_tertiary,
            fg=theme.accent_secondary, font=FONTS.tiny(bold=True),
            padx=7, pady=3, cursor="hand2",
        )
        self._nl_toggle_btn.pack(side=tk.RIGHT, padx=(4, 4))
        make_keyboard_activatable(self._nl_toggle_btn, self._toggle_nl_search)
        Tooltip(self._nl_toggle_btn, _("Interpret the query as natural language"))

        search_help = tk.Label(
            search_frame, text="?", bg=theme.bg_tertiary,
            fg=theme.text_muted, font=FONTS.tiny(bold=True),
            padx=7, pady=3, cursor="hand2"
        )
        search_help.pack(side=tk.RIGHT, padx=(8, 4))
        make_keyboard_activatable(search_help, self._show_search_syntax_help)
        Tooltip(search_help, _("Show search operators"))
        
        # ===== TOOLBAR BUTTONS =====
        toolbar = tk.Frame(header, bg=theme.bg_dark)
        toolbar.pack(side=tk.RIGHT, padx=(0, 14))
        
        # Add button
        add_btn = ModernButton(
            toolbar, text=_("Add bookmark"), icon="+", style="primary",
            command=self._add_bookmark,
            tooltip=_("Add one bookmark manually"), padx=8, pady=8,
            font=FONTS.tiny(bold=True),
        )
        add_btn.pack(side=tk.LEFT, padx=3)
        
        # Import button
        import_btn = ModernButton(
            toolbar, text=_("Import"), icon="↓",
            command=self._show_import_dialog,
            tooltip=_("Open guided import paths for browsers, services, and files"),
            padx=5, pady=8, font=FONTS.tiny(bold=True),
        )
        import_btn.pack(side=tk.LEFT, padx=3)
        
        # Export button
        export_btn = ModernButton(
            toolbar, text=_("Export"), icon="↑",
            command=self._show_export_dialog,
            tooltip=_("Export bookmarks to HTML, JSON, CSV, or Markdown"),
            padx=5, pady=8, font=FONTS.tiny(bold=True),
        )
        export_btn.pack(side=tk.LEFT, padx=3)
        
        # AI button
        self.ai_btn = ModernButton(
            toolbar, text=_("Assistant"), icon="✦",
            command=self._show_ai_menu,
            tooltip=_("Assistant tools: categorize, tag, summarize, and find semantic duplicates"),
            padx=5, pady=8, font=FONTS.tiny(bold=True),
        )
        self.ai_btn.pack(side=tk.LEFT, padx=3)
        
        # Tools button
        self.tools_btn = ModernButton(
            toolbar, text=_("Tools"), icon="\u2692",
            command=self._show_tools_menu,
            tooltip=_("Tools: Check links, Find duplicates,\nClean URLs, Manage categories, Backup"),
            padx=5, pady=8, font=FONTS.tiny(bold=True),
        )
        self.tools_btn.pack(side=tk.LEFT, padx=3)
        
        # Settings
        settings_btn = ModernButton(
            toolbar, text=_("Settings"), icon="⚙",
            command=self._show_settings_menu,
            tooltip=_("Settings: AI provider, themes, preferences"),
            padx=5, pady=8, font=FONTS.tiny(bold=True),
        )
        settings_btn.pack(side=tk.LEFT, padx=3)
        self.settings_btn = settings_btn

        self.theme_dropdown = None
        
        # ===== CONTENT AREA =====
        content = tk.Frame(self.main_container, bg=theme.bg_primary)
        content.pack(fill=tk.BOTH, expand=True)
        
        # ----- LEFT SIDEBAR (Scrollable) -----
        left_sidebar = tk.Frame(
            content, bg=theme.bg_dark, width=DesignTokens.SIDEBAR_WIDTH,
            highlightbackground=theme.border_muted, highlightthickness=1,
        )
        left_sidebar.pack(side=tk.LEFT, fill=tk.Y)
        left_sidebar.pack_propagate(False)
        
        # Scrollable container for left sidebar
        self.left_scroll = ScrollableFrame(left_sidebar, bg=theme.bg_dark)
        self.left_scroll.pack(fill=tk.BOTH, expand=True)
        
        workspace = tk.Frame(self.left_scroll.inner, bg=theme.bg_dark)
        workspace.pack(fill=tk.X, padx=DesignTokens.PANEL_PAD, pady=(20, 12))
        tk.Label(
            workspace, text=_("WORKSPACE"), bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.tiny(bold=True),
        ).pack(anchor="w", pady=(0, 9))
        workspace_row = tk.Frame(
            workspace, bg=theme.bg_secondary,
            highlightbackground=theme.border_muted, highlightthickness=1,
        )
        workspace_row.pack(fill=tk.X)
        tk.Label(
            workspace_row, text=_("▣  My Workspace"), bg=theme.bg_secondary,
            fg=theme.text_primary, font=FONTS.small(bold=True),
            anchor="w", padx=10, pady=9,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(
            workspace_row, text="⌄", bg=theme.bg_secondary,
            fg=theme.text_muted, font=FONTS.small(), padx=10,
        ).pack(side=tk.RIGHT)

        # Keep the drop target available to callers without giving it permanent
        # visual priority over the library navigation.
        self.import_area = DragDropImportArea(
            self.left_scroll.inner,
            on_files_dropped=self._on_files_dropped,
            on_open_import_center=self._show_import_dialog,
        )
        self.import_area.set_compact(True)
        
        # Quick filters
        filters_frame = tk.Frame(self.left_scroll.inner, bg=theme.bg_dark)
        filters_frame.pack(fill=tk.X, padx=DesignTokens.PANEL_PAD, pady=(0, DesignTokens.SPACE_MD))
        
        tk.Label(
            filters_frame, text=_("LIBRARY"), bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.tiny(bold=True)
        ).pack(anchor="w", pady=(5, 7))
        
        self.filter_buttons = {}
        self.filter_button_parts = {}
        self.active_filter = "All"  # Track active filter
        
        # Filter tooltips
        filter_tooltips = {
            "All": _("Show all bookmarks"),
            "Pinned": _("Show only pinned bookmarks"),
            "Recent": _("Show bookmarks added in the last 7 days"),
            "Broken": _("Show bookmarks with broken links"),
            "Untagged": _("Show bookmarks without any tags"),
        }

        for filter_name, label in [
            ("All", _("▣  All Bookmarks")),
            ("Pinned", _("◆  Pinned")),
            ("Recent", _("◷  Recent")),
            ("Broken", _("⚑  Needs Review")),
            ("Untagged", _("◇  Untagged")),
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
                row, text="0", bg=row["bg"],
                fg=theme.accent_primary if is_active else theme.text_muted,
                font=FONTS.tiny(bold=True),
                cursor="hand2", padx=4, pady=1
            )
            count_lbl.pack(side=tk.RIGHT, padx=(4, 8), pady=6)

            for widget in (row, name_lbl, count_lbl):
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
            make_keyboard_activatable(
                row,
                lambda f=filter_name: self._apply_filter(f),
                accessible_name=_("Filter library: {name}").format(name=filter_name),
            )
            route_pointer_to_control(row, name_lbl, count_lbl)
            row.bind("<FocusIn>", lambda e, f=filter_name: self._set_filter_visual(f, self.active_filter == f, hover=True))
            row.bind("<FocusOut>", lambda e, f=filter_name: self._set_filter_visual(f, self.active_filter == f))
            
            # Add tooltip
            Tooltip(row, filter_tooltips.get(filter_name, ""))
        
        # Categories header
        cat_header = tk.Frame(self.left_scroll.inner, bg=theme.bg_dark)
        cat_header.pack(fill=tk.X, padx=DesignTokens.PANEL_PAD, pady=(16, 7))
        
        tk.Label(
            cat_header, text=_("COLLECTIONS"), bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.tiny(bold=True)
        ).pack(side=tk.LEFT)
        add_collection = tk.Label(
            cat_header, text="+", bg=theme.bg_dark,
            fg=theme.text_secondary, font=FONTS.subtitle(),
            cursor="hand2", padx=5,
        )
        add_collection.pack(side=tk.RIGHT)
        make_keyboard_activatable(add_collection, self._add_new_category_dialog)
        Tooltip(add_collection, _("Create a collection"))
        
        # Categories list
        self.categories_frame = tk.Frame(self.left_scroll.inner, bg=theme.bg_dark)
        self.categories_frame.pack(fill=tk.X, padx=DesignTokens.PANEL_PAD, pady=(0, 12))

        # --- Read Later section (R-67) ---
        rl_header = tk.Frame(self.left_scroll.inner, bg=theme.bg_dark)
        rl_header.pack(fill=tk.X, padx=DesignTokens.PANEL_PAD, pady=(4, 7))
        rl_title = tk.Label(
            rl_header, text=_("READ LATER"), bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.tiny(bold=True), cursor="hand2",
        )
        rl_title.pack(side=tk.LEFT)
        make_keyboard_activatable(rl_title, self._show_read_later_queue)
        Tooltip(rl_title, _("Open Read Later queue"))
        self._rl_count_label = tk.Label(
            rl_header, text="0", bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.tiny(),
        )
        self._rl_count_label.pack(side=tk.RIGHT)
        rl_open = tk.Label(
            rl_header, text=_("Open"), bg=theme.bg_dark,
            fg=theme.accent_primary, font=FONTS.tiny(bold=True), cursor="hand2",
        )
        rl_open.pack(side=tk.RIGHT, padx=(0, 8))
        make_keyboard_activatable(rl_open, self._show_read_later_queue)
        Tooltip(rl_open, _("Open Read Later queue"))

        self._rl_frame = tk.Frame(self.left_scroll.inner, bg=theme.bg_dark)
        self._rl_frame.pack(fill=tk.X, padx=DesignTokens.PANEL_PAD, pady=(0, 12))
        self._rl_empty = tk.Label(
            self._rl_frame, text=_("Nothing queued"),
            bg=theme.bg_dark, fg=theme.text_muted, font=FONTS.small(),
            anchor="w",
        )
        self._rl_empty.pack(fill=tk.X, pady=2)

        # --- Flows section (R-67) ---
        flows_header = tk.Frame(self.left_scroll.inner, bg=theme.bg_dark)
        flows_header.pack(fill=tk.X, padx=DesignTokens.PANEL_PAD, pady=(4, 7))
        tk.Label(
            flows_header, text=_("WORKFLOWS"), bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.tiny(bold=True),
        ).pack(side=tk.LEFT)
        self._flows_count_label = tk.Label(
            flows_header, text="0", bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.tiny(),
        )
        self._flows_count_label.pack(side=tk.RIGHT)

        self._flows_frame = tk.Frame(self.left_scroll.inner, bg=theme.bg_dark)
        self._flows_frame.pack(fill=tk.X, padx=DesignTokens.PANEL_PAD, pady=(0, 20))
        self._flows_empty = tk.Label(
            self._flows_frame, text=_("No active flows"),
            bg=theme.bg_dark, fg=theme.text_muted, font=FONTS.small(),
            anchor="w",
        )
        self._flows_empty.pack(fill=tk.X, pady=2)

        # ----- MAIN CONTENT -----
        self.content_area = tk.Frame(content, bg=theme.bg_primary)
        self.content_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Content header
        self.content_header = tk.Frame(self.content_area, bg=theme.bg_primary)
        self.content_header.pack(fill=tk.X, padx=DesignTokens.CONTENT_PAD_X, pady=(16, 8))

        self.count_label = tk.Label(
            self.content_header, text=_("Your library"), bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.header(bold=True)
        )
        self.count_label.pack(side=tk.LEFT)

        self.view_hint_label = tk.Label(
            self.content_header, text=_("List view"),
            bg=theme.bg_primary, fg=theme.text_muted, font=FONTS.small()
        )
        self.view_hint_label.pack(side=tk.RIGHT)

        self._create_collection_summary()
        
        # List view frame
        self.list_frame = tk.Frame(self.content_area, bg=theme.bg_primary)
        
        # Create virtualized bookmark table - REMOVED "Added" column, added more padding
        columns = ("title", "url", "category", "tags")
        self.tree = BookmarkListWidget(
            self.list_frame, columns=columns, show="tree headings",
            selectmode="extended"
        )
        
        # Configure columns with MORE padding for favicon
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=34, stretch=False, minwidth=34)
        
        self.tree.heading("title", text=_("Title"))
        self.tree.column("title", width=245, minwidth=160)

        self.tree.heading("url", text=_("Domain"))
        self.tree.column("url", width=190, minwidth=150)

        self.tree.heading("category", text=_("Category"))
        self.tree.column("category", width=170, minwidth=130)

        self.tree.heading("tags", text=_("Tags"))
        self.tree.column("tags", width=170, minwidth=130)
        
        # Scrollbars
        tree_scroll_y = None
        tree_scroll_x = None
        if not getattr(self.tree, "uses_internal_scrollbars", False):
            tree_scroll_y = ttk.Scrollbar(self.list_frame, orient="vertical", command=self.tree.yview)
            tree_scroll_x = ttk.Scrollbar(self.list_frame, orient="horizontal", command=self.tree.xview)
            self.tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)
        self.tree.tag_configure("oddrow", background=theme.bg_primary)
        self.tree.tag_configure("evenrow", background=theme.bg_secondary)
        self.tree.tag_configure("broken", foreground=theme.accent_error)
        self.tree.tag_configure("pinned", foreground=theme.accent_warning)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        if tree_scroll_y is not None:
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
            on_add=self._add_bookmark,
            on_organize=self._show_tools_menu,
            on_search=self._focus_search,
        )
        self.filtered_empty_state = FilteredEmptyState(
            self.content_area,
            on_clear=self._clear_search,
            on_add=self._add_bookmark
        )

        # Show list view by default
        self.list_frame.pack(fill=tk.BOTH, expand=True, padx=DesignTokens.CONTENT_PAD_X, pady=(0, DesignTokens.CONTENT_PAD_Y))

        # ----- RIGHT SIDEBAR (Scrollable) - ANALYTICS -----
        right_sidebar = tk.Frame(
            content, bg=theme.bg_dark, width=DesignTokens.RIGHT_SIDEBAR_WIDTH,
            highlightbackground=theme.border_muted, highlightthickness=1,
        )
        right_sidebar.pack(side=tk.RIGHT, fill=tk.Y, before=self.content_area)
        right_sidebar.pack_propagate(False)
        self._right_sidebar = right_sidebar
        self._right_rail_user_hidden = False
        
        # Scrollable container for right sidebar
        self.right_scroll = ScrollableFrame(right_sidebar, bg=theme.bg_dark)
        self.right_scroll.pack(fill=tk.BOTH, expand=True)
        
        # Collection signals lead; the assistant is a contextual follow-up.
        self._create_analytics_panel()

        # Chat Panel (R-60)
        self.chat_panel = ChatPanel(
            self.right_scroll.inner,
            on_ask=self._on_chat_ask,
            on_bookmark_click=self._on_chat_bookmark_click,
        )
        self.chat_panel.pack(fill=tk.X, pady=(DesignTokens.SPACE_SM, DesignTokens.SPACE_MD))
        self.root.bind("<Configure>", self._on_shell_viewport_configure, add="+")
        self.root.after_idle(lambda: self._apply_right_rail_visibility(
            self.root.winfo_width() >= 1400
        ))

    def _apply_right_rail_visibility(self, visible: bool) -> None:
        """Show or hide the fixed rail without constraining the library viewport."""
        rail = getattr(self, "_right_sidebar", None)
        if rail is None:
            return
        if visible:
            if not rail.winfo_manager():
                rail.pack(side=tk.RIGHT, fill=tk.Y, before=self.content_area)
        elif rail.winfo_manager():
            rail.pack_forget()
        if hasattr(self, "_right_rail_var"):
            self._right_rail_var.set(bool(visible))

    def _toggle_right_rail(self) -> None:
        """Honor an explicit View-menu rail preference for the current viewport."""
        visible = bool(self._right_rail_var.get())
        self._right_rail_user_hidden = not visible
        self._apply_right_rail_visibility(visible)

    def _on_shell_viewport_configure(self, event) -> None:
        """Collapse the rail at laptop widths and restore it when room returns."""
        if event.widget is not self.root:
            return
        width = int(event.width)
        if width < 1400:
            self._apply_right_rail_visibility(False)
        elif not getattr(self, "_right_rail_user_hidden", False):
            self._apply_right_rail_visibility(True)

    def _set_content_header_visible(self, visible: bool):
        """Keep list chrome out of the first-run workspace."""
        header = getattr(self, "content_header", None)
        if not header:
            return
        if visible:
            if header.winfo_ismapped():
                return
            options = {
                "fill": tk.X,
                "padx": DesignTokens.CONTENT_PAD_X,
                "pady": (16, 8),
            }
            summary = getattr(self, "collection_summary_frame", None)
            try:
                header.pack(**options, before=summary) if summary else header.pack(**options)
            except tk.TclError:
                header.pack(**options)
        else:
            header.pack_forget()

    # --- Chat panel handlers (R-60) -----------------------------------------

    def _on_chat_ask(self, question: str):
        import threading
        def _do_ask():
            try:
                from bookmark_organizer_pro.services.embeddings import EmbeddingService
                from bookmark_organizer_pro.services.vector_store import VectorStore
                from bookmark_organizer_pro.services.rag_chat import CollectionChat

                if not hasattr(self, "_chat_service") or self._chat_service is None:
                    emb = EmbeddingService()
                    vs = VectorStore(emb)
                    self._chat_service = CollectionChat(self.ai_config, vs)

                turn = self._chat_service.ask(question)
                self._post_to_ui(lambda: self.chat_panel.show_answer(
                    turn.answer, sources=turn.sources,
                ))
            except Exception as exc:
                # Bind the message now: Python unbinds `exc` when the except
                # block exits, but this callback runs later on the UI thread.
                err_text = f"Error: {str(exc)[:100]}"
                self._post_to_ui(lambda: self.chat_panel.show_error(err_text))

        threading.Thread(target=_do_ask, daemon=True).start()

    def _on_chat_bookmark_click(self, bookmark_id: int):
        bm = self.bookmark_manager.get_bookmark(bookmark_id)
        if bm:
            from bookmark_organizer_pro.ui.widget_runtime import _open_external_url
            _open_external_url(bm.url)

    # --- Sidebar refresh helpers (R-67) -------------------------------------

    def _refresh_read_later_sidebar(self):
        from bookmark_organizer_pro.services.read_later import ReadLaterQueue
        theme = get_theme()
        bms = self.bookmark_manager.get_all_bookmarks()
        queue = ReadLaterQueue.list_queue(bms)

        for w in self._rl_frame.winfo_children():
            w.destroy()

        self._rl_count_label.config(text=str(len(queue)))
        if not queue:
            tk.Label(
                self._rl_frame, text=_("Nothing queued"),
                bg=theme.bg_dark, fg=theme.text_muted, font=FONTS.small(),
                anchor="w",
            ).pack(fill=tk.X, pady=2)
            return

        for bm in queue[:8]:
            title = (bm.title or bm.url)[:40]
            row = tk.Label(
                self._rl_frame, text=f"  {title}",
                bg=theme.bg_dark, fg=theme.text_secondary, font=FONTS.small(),
                cursor="hand2", anchor="w",
            )
            row.pack(fill=tk.X, pady=1)
            make_keyboard_activatable(
                row,
                lambda b=bm: self._select_bookmark_by_id(b.id),
                accessible_name=_("Open Read Later bookmark: {title}").format(title=title),
            )
            row.bind("<Enter>", lambda e, w=row: w.configure(bg=theme.bg_hover, fg=theme.text_primary))
            row.bind("<Leave>", lambda e, w=row: w.configure(bg=theme.bg_dark, fg=theme.text_secondary))

    def _refresh_flows_sidebar(self):
        from bookmark_organizer_pro.services.flows import FlowManager
        theme = get_theme()
        fm = FlowManager()
        flows = fm.list_flows()

        for w in self._flows_frame.winfo_children():
            w.destroy()

        self._flows_count_label.config(text=str(len(flows)))
        if not flows:
            tk.Label(
                self._flows_frame, text=_("No active flows"),
                bg=theme.bg_dark, fg=theme.text_muted, font=FONTS.small(),
                anchor="w",
            ).pack(fill=tk.X, pady=2)
            return

        for flow in flows[:8]:
            label = f"  {flow.icon or '📋'} {flow.name}"[:40]
            row = tk.Label(
                self._flows_frame, text=label,
                bg=theme.bg_dark, fg=theme.text_secondary, font=FONTS.small(),
                cursor="hand2", anchor="w",
            )
            row.pack(fill=tk.X, pady=1)
            row.bind("<Enter>", lambda e, w=row: w.configure(bg=theme.bg_hover, fg=theme.text_primary))
            row.bind("<Leave>", lambda e, w=row: w.configure(bg=theme.bg_dark, fg=theme.text_secondary))

    def _select_bookmark_by_id(self, bookmark_id: int):
        item_id = str(bookmark_id)
        if item_id in self.tree.get_children():
            self.tree.selection_set(item_id)
            self.tree.see(item_id)
            self.tree.focus(item_id)
