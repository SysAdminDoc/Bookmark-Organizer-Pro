"""Command palette actions for the app coordinator."""

from __future__ import annotations

from bookmark_organizer_pro.i18n import _
from bookmark_organizer_pro.ui.shell_widgets import CommandPalette
from bookmark_organizer_pro.ui.widgets import ThemeSelectorDialog


class CommandPaletteActionsMixin:
    """Keyboard command palette command registry."""

    def _show_command_palette(self, event=None):
        """Open the keyboard command palette."""
        commands = [
            (_("Add Bookmark"), "Ctrl+N", self._add_bookmark),
            (_("Import Bookmarks"), "Ctrl+I", self._show_import_dialog),
            (_("Export Bookmarks"), "Ctrl+S", self._show_export_dialog),
            (_("Backup Now"), "", self._backup_now),
            (_("Refresh"), "F5", self._refresh_all),
            (_("Focus Search"), "Ctrl+F", self._focus_search),
            (_("Clear Search and Filters"), "Esc", self._clear_search),
            (_("Select All Bookmarks"), "Ctrl+A", self._select_all_bookmarks),
            (_("Edit Selected Bookmark"), "Ctrl+E", self._edit_selected),
            (_("Open Selected Bookmark"), "Enter", self._open_selected),
            (_("Open Reader View"), "", self._open_reader_view),
            (_("Delete Selected Bookmarks"), "Del", self._delete_selected),
            (_("Copy URL of Selected"), "", self._copy_url),
            (_("Toggle Pin on Selected"), "", self._toggle_pin),
            (_("Theme Settings"), "", lambda: ThemeSelectorDialog(self.root, self.theme_manager)),
            (_("Full Analytics"), "", self._show_analytics),
            (_("Zoom In"), "Ctrl++", self._zoom_in),
            (_("Zoom Out"), "Ctrl+-", self._zoom_out),
            (_("Check All Links"), "", self._check_all_links),
            (_("Find Duplicates"), "", self._find_duplicates),
            (_("Clean Tracking Parameters"), "", self._clean_urls),
            (_("Open Graph View"), "", self._open_graph_view),
            (_("Manage Categories"), "", self._show_category_manager),
            (_("Flatten All Folders"), "", self._flatten_all_folders),
            (_("Clear All Categories"), "", self._clear_all_categories),
            (_("Clear All Tags"), "", self._clear_all_tags),
            (_("Assistant Settings"), "", self._show_ai_settings),
            (_("Assistant Categorize Selected"), "", self._ai_categorize),
            (_("Suggest Tags"), "", self._ai_suggest_tags),
            (_("Improve Titles"), "", self._ai_improve_titles),
            (_("Organize Selected (Auto-categorize)"), "", self._organize_selected),
            (_("Search Syntax Help"), "", self._show_search_syntax_help),
            (_("Keyboard Shortcuts"), "", self._show_keyboard_shortcuts),
            (_("About"), "", self._show_about_dialog),
        ]
        available = []
        for name, shortcut, callback in commands:
            if callback is not None and (callable(callback) or hasattr(self, callback.__name__ if hasattr(callback, '__name__') else '')):
                available.append((name, shortcut, callback))
        CommandPalette(self.root, available)
        return "break"
