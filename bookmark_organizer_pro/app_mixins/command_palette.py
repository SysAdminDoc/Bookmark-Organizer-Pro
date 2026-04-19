"""Command palette actions for the app coordinator."""

from __future__ import annotations

from bookmark_organizer_pro.ui.shell_widgets import CommandPalette
from bookmark_organizer_pro.ui.widgets import ThemeSelectorDialog


class CommandPaletteActionsMixin:
    """Keyboard command palette command registry."""

    def _show_command_palette(self, event=None):
        """Open the keyboard command palette."""
        commands = [
            ("Add Bookmark", "Ctrl+N", self._add_bookmark),
            ("Import Bookmarks", "Ctrl+I", self._show_import_dialog),
            ("Export Bookmarks", "Ctrl+S", self._show_export_dialog),
            ("Focus Search", "Ctrl+F", self._focus_search),
            ("Clear Search and Filters", "Esc", self._clear_search),
            ("Select All Bookmarks", "Ctrl+A", self._select_all_bookmarks),
            ("Edit Selected Bookmark", "Ctrl+E", self._edit_selected),
            ("Open Selected Bookmark", "Enter", self._open_selected),
            ("Check All Links", "", self._check_all_links),
            ("Find Duplicates", "", self._find_duplicates),
            ("Clean Tracking Parameters", "", self._clean_urls),
            ("Manage Categories", "", self._show_category_manager),
            ("Full Analytics", "", self._show_analytics),
            ("Theme Settings", "", lambda: ThemeSelectorDialog(self.root, self.theme_manager)),
            ("AI Settings", "", self._show_ai_settings),
            ("AI Categorize Selected", "", self._ai_categorize),
            ("AI Suggest Tags", "", self._ai_suggest_tags),
            ("Backup Now", "", self._backup_now),
            ("Refresh", "F5", self._refresh_all),
        ]
        CommandPalette(self.root, commands)
        return "break"
