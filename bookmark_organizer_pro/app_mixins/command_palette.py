"""Command palette actions for the app coordinator."""

from __future__ import annotations

from bookmark_organizer_pro.ui.shell_widgets import CommandPalette
from bookmark_organizer_pro.ui.widgets import ThemeSelectorDialog


class CommandPaletteActionsMixin:
    """Keyboard command palette command registry."""

    def _show_command_palette(self, event=None):
        """Open the keyboard command palette."""
        commands = [
            # File
            ("Add Bookmark", "Ctrl+N", self._add_bookmark),
            ("Import Bookmarks", "Ctrl+I", self._show_import_dialog),
            ("Export Bookmarks", "Ctrl+S", self._show_export_dialog),
            ("Backup Now", "", self._backup_now),
            ("Refresh", "F5", self._refresh_all),

            # Edit
            ("Focus Search", "Ctrl+F", self._focus_search),
            ("Clear Search and Filters", "Esc", self._clear_search),
            ("Select All Bookmarks", "Ctrl+A", self._select_all_bookmarks),
            ("Edit Selected Bookmark", "Ctrl+E", self._edit_selected),
            ("Open Selected Bookmark", "Enter", self._open_selected),
            ("Open Reader View", "", self._open_reader_view),
            ("Delete Selected Bookmarks", "Del", self._delete_selected),
            ("Copy URL of Selected", "", self._copy_url),
            ("Toggle Pin on Selected", "", self._toggle_pin),

            # View
            ("Theme Settings", "", lambda: ThemeSelectorDialog(self.root, self.theme_manager)),
            ("Full Analytics", "", self._show_analytics),
            ("Zoom In", "Ctrl++", self._zoom_in),
            ("Zoom Out", "Ctrl+-", self._zoom_out),

            # Tools
            ("Check All Links", "", self._check_all_links),
            ("Find Duplicates", "", self._find_duplicates),
            ("Clean Tracking Parameters", "", self._clean_urls),
            ("Manage Categories", "", self._show_category_manager),
            ("Flatten All Folders", "", self._flatten_all_folders),
            ("Clear All Categories", "", self._clear_all_categories),
            ("Clear All Tags", "", self._clear_all_tags),

            # AI
            ("AI Settings", "", self._show_ai_settings),
            ("AI Categorize Selected", "", self._ai_categorize),
            ("AI Suggest Tags", "", self._ai_suggest_tags),
            ("AI Improve Titles", "", self._ai_improve_titles),

            # Bulk
            ("Organize Selected (Auto-categorize)", "", self._organize_selected),

            # Help
            ("Search Syntax Help", "", self._show_search_syntax_help),
            ("Keyboard Shortcuts", "", self._show_keyboard_shortcuts),
            ("About", "", self._show_about_dialog),
        ]
        available = []
        for name, shortcut, callback in commands:
            if callback is not None and (callable(callback) or hasattr(self, callback.__name__ if hasattr(callback, '__name__') else '')):
                available.append((name, shortcut, callback))
        CommandPalette(self.root, available)
        return "break"
