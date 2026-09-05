"""Main application shell construction for the app coordinator."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from bookmark_organizer_pro.constants import APP_NAME
from bookmark_organizer_pro.i18n import _, format_message, pgettext
from bookmark_organizer_pro.services.ai_operation import (
    AIBudgetExceeded,
    AICancellationToken,
    AIOperationCancelled,
)
from bookmark_organizer_pro.services.processing_timeline import (
    ProcessingTimelineEvent,
    ProcessingTimelineService,
    sanitize_processing_error,
)
from bookmark_organizer_pro.ui.components import DragDropImportArea, ScrollableFrame
from bookmark_organizer_pro.ui.feedback import EmptyState, FilteredEmptyState
from bookmark_organizer_pro.ui.foundation import FONTS, DesignTokens, readable_text_on
from bookmark_organizer_pro.ui.shell_widgets import ViewMode
from bookmark_organizer_pro.ui.tk_interactions import make_keyboard_activatable, route_pointer_to_control
from bookmark_organizer_pro.ui.treeview import BookmarkListWidget
from bookmark_organizer_pro.ui.widget_chat_panel import ChatPanel
from bookmark_organizer_pro.ui.workflow_detail_panel import BookmarkDetailPanel
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
        file_menu.add_command(label=_("Trash…"), command=self._show_trash)
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
            label=_("Focus rail"),
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
        win.title(_("Search Syntax"))
        win.geometry("520x480")
        win.transient(self.root)
        win.grab_set()
        win.focus_set()
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
            ("Ctrl+K", "Focus search bar"),
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
        win.title(_("Keyboard Shortcuts"))
        win.geometry("400x400")
        win.transient(self.root)
        win.grab_set()
        win.focus_set()
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
        brand.pack(side=tk.LEFT, padx=(18, 12), pady=5, fill=tk.Y)
        brand.pack_propagate(False)
        brand_row = tk.Frame(brand, bg=theme.bg_dark)
        brand_row.pack(anchor="w")
        tk.Label(
            brand_row, text=_("B"), bg=theme.accent_primary,
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
            search_frame, text=_("⌕"), bg=theme.bg_secondary,
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
               "  content: before: after: is: has: visits:>N regex:\n"
               "Type a prefix (e.g. tag:) for suggestions.")

        # Placeholder text
        self._search_placeholder = _("Search your library")
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

        search_shortcut = tk.Label(
            search_frame, text=_("Ctrl+K"), bg=theme.bg_secondary,
            fg=theme.text_muted, font=FONTS.tiny(),
            padx=7, pady=3, cursor="hand2",
        )
        search_shortcut.pack(side=tk.RIGHT, padx=(8, 4))
        make_keyboard_activatable(search_shortcut, self._focus_search)
        Tooltip(search_shortcut, _("Focus library search"))
        
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
        
        # Secondary destinations share one predictable menu so the command bar
        # remains usable at the supported 1280 px laptop width.
        self.more_btn = ModernButton(
            toolbar, text=_("More"), icon="⋮",
            command=self._show_shell_actions_menu,
            tooltip=_("Export, assistant, tools, and settings"),
            padx=7, pady=8, font=FONTS.tiny(bold=True),
        )
        self.more_btn.pack(side=tk.LEFT, padx=3)
        # Compatibility handles used by theme/menu refresh paths.
        self.ai_btn = self.more_btn
        self.tools_btn = self.more_btn
        self.settings_btn = self.more_btn

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
        filters_frame.pack(fill=tk.X, padx=DesignTokens.PANEL_PAD, pady=(20, DesignTokens.SPACE_MD))
        
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
            "In Progress": _("Show bookmarks currently in progress"),
        }

        for filter_name, label in [
            ("All", _("⌂  My Library")),
            ("Pinned", _("◆  Pinned")),
            ("Recent", _("▱  Inbox")),
            ("Broken", _("⚑  Needs Review")),
            ("Untagged", _("◇  Untagged")),
            ("In Progress", _("▣  In Progress")),
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
                row, text=_("0"), bg=row["bg"],
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
            cat_header, text=_("+"), bg=theme.bg_dark,
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
            rl_header, text=_("0"), bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.tiny(),
        )
        self._rl_count_label.pack(side=tk.RIGHT)
        rl_open = tk.Label(
            rl_header, text=pgettext("read-later", "Open"), bg=theme.bg_dark,
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
            flows_header, text=_("0"), bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.tiny(),
        )
        self._flows_count_label.pack(side=tk.RIGHT)

        self._flows_frame = tk.Frame(self.left_scroll.inner, bg=theme.bg_dark)
        self._flows_frame.pack(fill=tk.X, padx=DesignTokens.PANEL_PAD, pady=(0, 20))
        self._render_empty_workflows(theme)

        # A persistent local-save footer keeps the privacy/trust state visible
        # even when the global status bar is reporting a transient operation.
        self.left_scroll.pack_forget()
        sidebar_footer = tk.Frame(
            left_sidebar, bg=theme.bg_dark,
            highlightbackground=theme.border_muted, highlightthickness=1,
        )
        sidebar_footer.pack(side=tk.BOTTOM, fill=tk.X)
        self.sidebar_status_label = tk.Label(
            sidebar_footer, text=_("●  Saved locally"), bg=theme.bg_dark,
            fg=theme.accent_success, font=FONTS.tiny(), anchor="w",
        )
        self.sidebar_status_label.pack(side=tk.LEFT, padx=(14, 6), pady=10)
        tk.Label(
            sidebar_footer, text=_("Library.db"), bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.tiny(),
        ).pack(side=tk.LEFT, padx=(0, 4))
        sidebar_settings = tk.Label(
            sidebar_footer, text=_("⚙"), bg=theme.bg_dark,
            fg=theme.text_secondary, font=FONTS.body(), cursor="hand2", padx=12,
        )
        sidebar_settings.pack(side=tk.RIGHT, pady=5)
        make_keyboard_activatable(sidebar_settings, self._show_settings_menu)
        Tooltip(sidebar_settings, _("Open settings"))
        self.left_scroll.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # ----- MAIN CONTENT -----
        self.content_area = tk.Frame(content, bg=theme.bg_primary)
        self.content_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Content header: collection context on the left, freshness and view
        # controls on the right. This replaces the older oversized overview card.
        self.content_header = tk.Frame(self.content_area, bg=theme.bg_primary)
        self.content_header.pack(fill=tk.X, padx=DesignTokens.CONTENT_PAD_X, pady=(22, 12))

        header_copy = tk.Frame(self.content_header, bg=theme.bg_primary)
        header_copy.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.count_label = tk.Label(
            header_copy, text=_("Library"), bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.title(bold=True), anchor="w",
        )
        self.count_label.pack(fill=tk.X)
        self.library_context_label = tk.Label(
            header_copy, text=_("Ready for your next save"), bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.small(), anchor="w",
        )
        self.library_context_label.pack(fill=tk.X, pady=(5, 0))

        # Kept as a lightweight state target for refresh paths; display controls
        # live beside the query filters where their scope is unambiguous.
        self.view_hint_label = tk.Label(
            self.content_header, text=_("Updated just now"),
            bg=theme.bg_primary, fg=theme.text_muted, font=FONTS.tiny(),
        )

        self._create_collection_summary()
        
        # List view frame
        self.list_frame = tk.Frame(self.content_area, bg=theme.bg_primary)
        
        # Mockup-aligned table: category context is folded into the tag cell so
        # time and state remain visible without horizontal scrolling.
        columns = ("title", "organization", "saved", "status", "favorite")
        self.tree = BookmarkListWidget(
            self.list_frame, columns=columns, show="tree headings",
            selectmode="extended"
        )
        
        # Every cell has a named column in both the virtual and native table.
        # This prevents the former one-letter and star cells from appearing as
        # unexplained glyphs when site-icon fetching is disabled.
        self.tree.heading("#0", text=_("Site"))
        self.tree.column("#0", width=180, stretch=False, minwidth=130)
        
        self.tree.heading("title", text=_("Title"))
        self.tree.column("title", width=280, minwidth=210)

        self.tree.heading("organization", text=_("Collection / Tags"))
        self.tree.column("organization", width=160, minwidth=135)

        self.tree.heading("saved", text=_("Saved"))
        self.tree.column("saved", width=92, minwidth=82)

        self.tree.heading("status", text=_("Status"))
        self.tree.column("status", width=108, minwidth=98)

        self.tree.heading("favorite", text=_("Pinned"))
        self.tree.column("favorite", width=70, stretch=False, minwidth=64)
        
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

        table_footer = tk.Frame(
            self.list_frame, bg=theme.bg_primary,
            highlightbackground=theme.border_muted, highlightthickness=1,
        )
        table_footer.pack(side=tk.BOTTOM, fill=tk.X)
        self.library_footer_label = tk.Label(
            table_footer, text=_("Showing bookmarks in this view"),
            bg=theme.bg_primary, fg=theme.text_muted,
            font=FONTS.tiny(), anchor="w",
        )
        self.library_actions_label = tk.Label(
            table_footer,
            text=_("Keyboard: Enter · Space · Shift+F10"),
            bg=theme.bg_primary, fg=theme.text_muted,
            font=FONTS.tiny(), anchor="e",
        )
        self.library_actions_label.pack(side=tk.RIGHT, padx=10, pady=8)
        Tooltip(
            self.library_actions_label,
            _(
                "Enter opens. Space toggles Pinned. "
                "Shift+F10 opens actions and sorting."
            ),
        )
        self.library_footer_label.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
            padx=10,
            pady=8,
        )

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        if tree_scroll_y is not None:
            tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Tree bindings
        self.tree.bind("<Double-1>", self._on_item_double_click)
        self.tree.bind("<Return>", lambda e: self._open_selected())
        self.tree.bind("<space>", self._toggle_pin_from_keyboard)
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<Shift-F10>", self._show_context_menu)
        self.tree.bind("<KeyPress-Menu>", self._show_context_menu)
        self.tree.bind("<ButtonRelease-1>", self._on_library_table_release, add="+")
        self.tree.bind("<<TreeviewSelect>>", self._on_selection_change)
        self.tree.bind("<<TreeviewSort>>", self._refresh_table_semantic_status)
        
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

        # ----- RIGHT SIDEBAR (Scrollable) - CONTEXTUAL FOCUS -----
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
        
        self._create_right_rail_header()
        self._right_rail_focus = tk.Frame(self.right_scroll.inner, bg=theme.bg_dark)
        self._right_rail_assistant = tk.Frame(self.right_scroll.inner, bg=theme.bg_dark)

        # The assistant remains available as an explicit destination without
        # competing with the selected bookmark or the viewport at startup.
        self.chat_panel = None

        self.bookmark_inspector = BookmarkDetailPanel(
            self._right_rail_focus,
            on_edit=lambda _bookmark: self._edit_selected(),
            on_open=self._open_bookmark,
            on_open_offline=self._open_offline_copy,
            on_delete=lambda _bookmark: self._delete_selected(),
            on_close=lambda: self._set_right_rail_user_visibility(False),
            on_retry_processing=self._retry_processing_event,
            on_remove_processing=self._remove_processing_event,
        )
        self.bookmark_inspector.pack(fill=tk.BOTH, expand=True)
        self._set_right_rail_mode("focus")
        self.root.bind("<Configure>", self._on_shell_viewport_configure, add="+")
        self.root.after_idle(lambda: self._apply_right_rail_visibility(
            self.root.winfo_width() >= 1400
        ))

    def _show_shell_actions_menu(self):
        """Consolidate secondary destinations into one laptop-safe menu."""
        theme = get_theme()
        menu = tk.Menu(
            self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
            activebackground=theme.selection, activeforeground=theme.text_primary,
            borderwidth=0,
        )
        menu.add_command(label=_("Export bookmarks…"), command=self._show_export_dialog)
        menu.add_command(label=_("Ask your library"), command=self._show_right_rail_assistant)
        menu.add_command(label=_("Assistant tools…"), command=self._show_ai_menu)
        menu.add_command(label=_("Library tools"), command=self._show_tools_menu)
        menu.add_separator()
        menu.add_command(label=_("Settings"), command=self._show_settings_menu)
        button = self.more_btn
        menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height() + 3)

    def _create_right_rail_header(self):
        """Create a compact contextual heading for the focus rail."""
        theme = get_theme()
        header = tk.Frame(
            self.right_scroll.inner, bg=theme.bg_dark,
            highlightbackground=theme.border_muted, highlightthickness=0,
        )
        header.pack(fill=tk.X, padx=DesignTokens.PANEL_PAD, pady=(15, 8))
        tk.Label(
            header, text=_("✦"), bg=theme.bg_dark,
            fg=theme.accent_primary, font=FONTS.subtitle(),
        ).pack(side=tk.LEFT, padx=(0, 9))
        copy = tk.Frame(header, bg=theme.bg_dark)
        copy.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._right_rail_title_label = tk.Label(
            copy, text=_("Focus"), bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.subtitle(bold=True), anchor="w",
        )
        self._right_rail_title_label.pack(fill=tk.X)
        self._right_rail_subtitle_label = tk.Label(
            copy, text=_("Details and next action"), bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.tiny(), anchor="w",
        )
        self._right_rail_subtitle_label.pack(fill=tk.X, pady=(2, 0))
        close = tk.Label(
            header, text=_("×"), bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.subtitle(),
            cursor="hand2", padx=7, pady=4,
        )
        close.pack(side=tk.RIGHT)
        make_keyboard_activatable(
            close,
            lambda: self._set_right_rail_user_visibility(False),
            accessible_name=_("Close focus rail"),
        )
        Tooltip(close, _("Close focus rail"))
        tk.Frame(
            self.right_scroll.inner, bg=theme.border_muted, height=1,
        ).pack(fill=tk.X, padx=DesignTokens.PANEL_PAD, pady=(0, 4))

    def _set_right_rail_mode(self, mode: str):
        """Switch between contextual focus and the optional assistant."""
        focus = getattr(self, "_right_rail_focus", None)
        assistant = getattr(self, "_right_rail_assistant", None)
        if focus is None or assistant is None:
            return
        mode = "assistant" if mode == "assistant" else "focus"
        if mode == "assistant":
            self._ensure_chat_panel()
        focus.pack_forget()
        assistant.pack_forget()
        target = assistant if mode == "assistant" else focus
        target.pack(fill=tk.BOTH, expand=True)
        title = _("Ask your library") if mode == "assistant" else _("Focus")
        subtitle = (
            _("Answers grounded in your saved sources")
            if mode == "assistant"
            else _("Details and next action")
        )
        self._right_rail_title_label.configure(text=title)
        self._right_rail_subtitle_label.configure(text=subtitle)
        self._right_rail_active_mode = mode

    def _ensure_chat_panel(self):
        """Create the assistant only when the user opens that destination."""
        panel = getattr(self, "chat_panel", None)
        if panel is not None:
            return panel
        panel = ChatPanel(
            self._right_rail_assistant,
            on_ask=self._on_chat_ask,
            on_bookmark_click=self._on_chat_bookmark_click,
            on_cancel=self._on_chat_cancel,
        )
        panel.pack(fill=tk.X, pady=(DesignTokens.SPACE_SM, DesignTokens.SPACE_MD))
        self.chat_panel = panel
        return panel

    def _set_right_rail_tab(self, tab_name: str):
        """Compatibility bridge for callers using the previous tab contract."""
        self._set_right_rail_mode("focus" if tab_name == "selected" else "assistant")

    def _show_right_rail_assistant(self):
        """Reveal the assistant as a deliberate, reversible rail mode."""
        self._set_right_rail_user_visibility(True)
        self._set_right_rail_mode("assistant")
        entry = getattr(getattr(self, "chat_panel", None), "_entry", None)
        if entry is not None:
            self.root.after_idle(entry.focus_set)

    def _update_right_rail_selection(self):
        """Turn a single row selection into an immediately useful inspector."""
        inspector = getattr(self, "bookmark_inspector", None)
        if inspector is None:
            return
        selected_ids = list(getattr(self, "selected_bookmarks", []) or [])
        if len(selected_ids) != 1:
            inspector.clear(
                _("Select one bookmark to inspect")
                if not selected_ids
                else _("Select a single bookmark to inspect its details")
            )
            return
        bookmark = self.bookmark_manager.get_bookmark(selected_ids[0])
        if bookmark is None:
            inspector.clear(_("This bookmark is no longer available"))
            return
        inspector.show_bookmark(bookmark)
        self._set_right_rail_mode("focus")
        if (
            self.root.winfo_width() >= 1400
            and not getattr(self, "_right_rail_user_hidden", False)
        ):
            self._apply_right_rail_visibility(True)

    def _retry_processing_event(
        self,
        bookmark,
        event: ProcessingTimelineEvent,
    ) -> None:
        """Retry one bounded local processing step from the focus rail."""
        current = self.bookmark_manager.get_bookmark(getattr(bookmark, "id", None))
        if current is None:
            return
        operation = str(event.operation or "local processing").replace("_", " ")
        self._set_status(format_message("Retrying {operation}…", operation=operation))

        import threading

        def worker() -> None:
            try:
                succeeded, detail = self._perform_processing_retry(current, event)
            except Exception as exc:
                succeeded = False
                detail = sanitize_processing_error(exc)
            self._post_to_ui(
                lambda: self._finish_processing_action(
                    current, succeeded, detail, retry=True,
                )
            )

        threading.Thread(target=worker, daemon=True).start()

    def _remove_processing_event(
        self,
        bookmark,
        event: ProcessingTimelineEvent,
    ) -> None:
        """Remove one derived artifact while retaining its bookmark row."""
        current = self.bookmark_manager.get_bookmark(getattr(bookmark, "id", None))
        if current is None:
            return
        self._set_status(format_message(
            "Removing {operation}…",
            operation=str(event.operation or "derived artifact").replace("_", " "),
        ))

        import threading

        def worker() -> None:
            vector_store = None
            try:
                if event.operation == "embedding":
                    from bookmark_organizer_pro.services.embeddings import EmbeddingService
                    from bookmark_organizer_pro.services.vector_store import VectorStore

                    embedder = EmbeddingService(model_name=current.embedding_model or None)
                    vector_store = VectorStore(
                        embedder,
                        source_digest_resolver=lambda bookmark_id: self._bookmark_source_digest(bookmark_id),
                    )
                succeeded, detail = ProcessingTimelineService().remove_derived_artifact(
                    current, event, vector_store=vector_store,
                )
            except Exception as exc:
                succeeded = False
                detail = sanitize_processing_error(exc)
            self._post_to_ui(
                lambda: self._finish_processing_action(
                    current, succeeded, detail, retry=False,
                )
            )

        threading.Thread(target=worker, daemon=True).start()

    def _perform_processing_retry(self, bookmark, event: ProcessingTimelineEvent) -> tuple[bool, str]:
        """Dispatch retry actions without exposing source data in the result."""
        operation = str(event.operation or "").strip().lower()
        if operation == "snapshot":
            from bookmark_organizer_pro.services.snapshot import SnapshotArchiver

            succeeded, _detail = SnapshotArchiver().snapshot(bookmark)
            return succeeded, _("Offline snapshot captured") if succeeded else _("Offline snapshot failed")
        if operation in {"ingest", "extraction"}:
            from bookmark_organizer_pro.services.ingest import ContentIngestor

            result = ContentIngestor().ingest_bookmark(bookmark)
            if result.success:
                result.apply_to(bookmark)
                return True, _("Content extraction completed")
            return False, sanitize_processing_error(result.error or "Content extraction failed")
        if operation == "metadata":
            from bookmark_organizer_pro.utils.metadata import fetch_page_metadata

            metadata = fetch_page_metadata(bookmark.url)
            changed = False
            for field in ("title", "description", "favicon_url"):
                value = str(metadata.get(field) or "").strip()
                if value and getattr(bookmark, field, "") != value:
                    setattr(bookmark, field, value)
                    changed = True
            return changed, _("Metadata refreshed") if changed else _("Metadata was unavailable")
        if operation == "link_check":
            from bookmark_organizer_pro.link_checker import LinkChecker
            from bookmark_organizer_pro.services.dead_link_scanner import apply_check_verdict

            valid, status = LinkChecker(max_workers=1)._check_url(bookmark)
            if not apply_check_verdict(bookmark, valid, status):
                return True, format_message(
                    "Host is rate limiting us ({status}); the link was left unchanged",
                    status=status or 0,
                )
            return True, format_message("Link check completed ({status})", status=status or 0)
        if operation == "youtube_transcript":
            from bookmark_organizer_pro.services.youtube_transcript import YouTubeTranscriptService

            result = YouTubeTranscriptService().capture(
                bookmark, language=event.language or "en",
            )
            if result.success:
                YouTubeTranscriptService().apply(bookmark, result)
                return True, _("YouTube transcript captured")
            return False, sanitize_processing_error(result.error or "Transcript capture failed")
        if operation == "embedding":
            from bookmark_organizer_pro.services.embeddings import EmbeddingService
            from bookmark_organizer_pro.services.vector_store import VectorStore

            embedder = EmbeddingService(model_name=bookmark.embedding_model or None)
            vector_store = VectorStore(
                embedder,
                source_digest_resolver=lambda bookmark_id: self._bookmark_source_digest(bookmark_id),
            )
            source = EmbeddingService.bookmark_source_text(bookmark)
            chunks = embedder.chunk_text(source)
            rows = vector_store.upsert_bookmark(int(bookmark.id), chunks)
            if rows:
                bookmark.embedding_model = embedder.resolved_model_name
                bookmark.embedding_dim = embedder.dim
                return True, _("Search index updated")
            return False, _("Search index could not be updated")
        return False, _("This processing step cannot be retried")

    def _finish_processing_action(
        self,
        bookmark,
        succeeded: bool,
        detail: str,
        *,
        retry: bool,
    ) -> None:
        """Persist a completed action and refresh the selected-bookmark rail."""
        if succeeded:
            try:
                self.bookmark_manager.update_bookmark(bookmark)
            except Exception as exc:
                succeeded = False
                detail = sanitize_processing_error(exc)
        self._refresh_all()
        self._update_right_rail_selection()
        verb = _("Retry complete") if retry else _("Artifact removal complete")
        if succeeded:
            self._set_status(format_message("{verb}: {detail}", verb=verb, detail=detail))
            self._show_toast(detail, "success")
        else:
            self._set_status(format_message("Processing action failed: {detail}", detail=detail))
            self._show_toast(detail, "error")

    def _bookmark_source_digest(self, bookmark_id: int):
        from bookmark_organizer_pro.services.embeddings import EmbeddingService

        bookmark = self.bookmark_manager.get_bookmark(bookmark_id)
        return EmbeddingService.bookmark_source_digest(bookmark) if bookmark else None

    def _on_library_table_release(self, event):
        """Make the trailing star a direct, discoverable pin control."""
        column_at_event = getattr(self.tree, "column_at_event", None)
        if column_at_event is None or column_at_event(event) != "favorite":
            return None
        item_id = self.tree.identify_row(event)
        if not item_id:
            return "break"
        self.root.after_idle(lambda value=str(item_id): self._toggle_pin_from_row(value))
        return "break"

    def _toggle_pin_from_row(self, item_id: str):
        """Select one rendered row and toggle its persisted pin state."""
        if item_id not in self.tree.get_children():
            return
        try:
            self.tree.selection_set(item_id, emit=False)
        except TypeError:
            self.tree.selection_set(item_id)
        self.selected_bookmarks = [int(item_id)]
        self._toggle_pin()

    def _toggle_pin_from_keyboard(self, _event=None):
        """Expose the direct Pinned-column operation without a pointer."""
        if not self.tree.selection():
            return "break"
        self._toggle_pin()
        return "break"

    def _show_library_view_menu(self):
        """Open a compact view menu anchored to the visible view-options control."""
        theme = get_theme()
        menu = tk.Menu(
            self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
            activebackground=theme.selection, activeforeground=theme.text_primary,
            borderwidth=0,
        )
        menu.add_command(label=_("Refresh library"), command=self._refresh_all)
        menu.add_command(label=_("Show focus rail"), command=lambda: self._set_right_rail_user_visibility(True))
        menu.add_command(label=_("Hide focus rail"), command=lambda: self._set_right_rail_user_visibility(False))
        menu.add_command(label=_("Ask your library"), command=self._show_right_rail_assistant)
        menu.add_separator()
        menu.add_command(label=_("Theme and display settings"), command=self._show_settings_menu)
        button = self.view_options_btn
        menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height() + 3)

    def _show_library_collection_menu(self):
        """Filter the current library by a live collection list."""
        theme = get_theme()
        menu = tk.Menu(
            self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
            activebackground=theme.selection, activeforeground=theme.text_primary,
            borderwidth=0,
        )
        menu.add_command(label=_("All collections"), command=lambda: self._select_category(""))
        counts = self.bookmark_manager.get_category_counts()
        active = sorted((name for name, count in counts.items() if count), key=str.lower)
        if active:
            menu.add_separator()
        for category in active[:20]:
            menu.add_command(
                label=format_message('{value_0}  ·  {value_1}', value_0=category, value_1=counts.get(category, 0)),
                command=lambda value=category: self._select_category(value),
            )
        button = self.collection_filter_btn
        menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height() + 3)

    def _show_library_tag_menu(self):
        """Apply a search-backed tag filter from the library toolbar."""
        theme = get_theme()
        menu = tk.Menu(
            self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
            activebackground=theme.selection, activeforeground=theme.text_primary,
            borderwidth=0,
        )
        menu.add_command(label=_("All tags"), command=self._clear_search)
        counts = {}
        for bookmark in self.bookmark_manager.get_all_bookmarks():
            for tag in (*bookmark.tags, *bookmark.ai_tags):
                counts[tag] = counts.get(tag, 0) + 1
        if counts:
            menu.add_separator()
        for tag, count in sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))[:20]:
            menu.add_command(
                label=format_message('#{value_0}  ·  {value_1}', value_0=tag, value_1=count),
                command=lambda value=tag: self._set_library_search(f"tag:{value}"),
            )
        button = self.tag_filter_btn
        menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height() + 3)

    def _show_library_type_menu(self):
        """Expose the highest-value saved views without another persistent row."""
        theme = get_theme()
        menu = tk.Menu(
            self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
            activebackground=theme.selection, activeforeground=theme.text_primary,
            borderwidth=0,
        )
        for label, filter_name in (
            (_("All types"), "All"), (_("Pinned"), "Pinned"),
            (_("Recent"), "Recent"), (_("Needs review"), "Broken"),
            (_("Untagged"), "Untagged"),
        ):
            menu.add_command(label=label, command=lambda value=filter_name: self._apply_filter(value))
        button = self.type_filter_btn
        menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height() + 3)

    def _set_library_search(self, query: str):
        """Set a structured query through the shared search contract."""
        self._suppress_search_callback = True
        self.search_var.set(str(query or ""))
        self.search_entry.configure(fg=get_theme().text_primary)
        self._suppress_search_callback = False
        self.search_query = str(query or "")
        self.quick_filter = None
        self.current_category = None
        self._refresh_bookmark_list()

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

    def _set_right_rail_user_visibility(self, visible: bool) -> None:
        """Persist a direct user choice independently of responsive collapse."""
        self._right_rail_user_hidden = not bool(visible)
        self._apply_right_rail_visibility(bool(visible))

    def _toggle_right_rail(self) -> None:
        """Honor an explicit View-menu rail preference for the current viewport."""
        visible = bool(self._right_rail_var.get())
        self._set_right_rail_user_visibility(visible)

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
                "pady": (22, 12),
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
        token = AICancellationToken()
        self._chat_cancel_token = token
        panel = self.chat_panel

        def _do_ask():
            try:
                from bookmark_organizer_pro.services.embeddings import EmbeddingService
                from bookmark_organizer_pro.services.rag_chat import CollectionChat
                from bookmark_organizer_pro.services.vector_store import VectorStore

                if not hasattr(self, "_chat_service") or self._chat_service is None:
                    emb = EmbeddingService()
                    def _source_digest(bookmark_id: int):
                        bookmark = self.bookmark_manager.get_bookmark(bookmark_id)
                        if bookmark is None:
                            return None
                        return EmbeddingService.bookmark_source_digest(bookmark)

                    vs = VectorStore(
                        emb,
                        source_digest_resolver=_source_digest,
                    )
                    self._chat_service = CollectionChat(self.ai_config, vs)

                turn = self._chat_service.ask(question, cancel_token=token)
                self._post_to_ui(lambda: panel.show_answer(
                    turn.answer, sources=turn.sources,
                ))
            except AIOperationCancelled:
                self._post_to_ui(panel.show_stopped)
            except AIBudgetExceeded as exc:
                err_text = f"Stopped: {str(exc)[:160]}"
                self._post_to_ui(lambda: panel.show_error(err_text))
            except Exception as exc:
                # Bind the message now: Python unbinds `exc` when the except
                # block exits, but this callback runs later on the UI thread.
                err_text = f"Error: {str(exc)[:100]}"
                self._post_to_ui(lambda: panel.show_error(err_text))

        threading.Thread(target=_do_ask, daemon=True).start()

    def _on_chat_cancel(self):
        token = getattr(self, "_chat_cancel_token", None)
        if token is not None:
            token.cancel()

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
                self._rl_frame, text=format_message('  {value_0}', value_0=title),
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
            self._render_empty_workflows(theme)
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

    def _render_empty_workflows(self, theme):
        """Keep the secondary workflow empty state quiet and compact."""
        empty = tk.Frame(self._flows_frame, bg=theme.bg_dark)
        empty.pack(fill=tk.X, pady=(2, 0))
        tk.Label(
            empty, text=_("No active workflows"), bg=theme.bg_dark,
            fg=theme.text_secondary, font=FONTS.small(), anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            empty, text=_("Research trails appear here when you start one."),
            bg=theme.bg_dark, fg=theme.text_muted, font=FONTS.tiny(),
            justify=tk.LEFT, anchor="w", wraplength=190,
        ).pack(fill=tk.X, pady=(3, 0))

    def _select_bookmark_by_id(self, bookmark_id: int):
        item_id = str(bookmark_id)
        if item_id in self.tree.get_children():
            self.tree.selection_set(item_id)
            self.tree.see(item_id)
            self.tree.focus(item_id)
