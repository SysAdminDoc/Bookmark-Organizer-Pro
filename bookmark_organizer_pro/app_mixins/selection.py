"""Selection, opening, and context-menu actions for the app coordinator."""

from __future__ import annotations

import tkinter as tk
import webbrowser
from datetime import datetime

from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.ui.foundation import pluralize
from bookmark_organizer_pro.ui.widgets import get_theme
from bookmark_organizer_pro.utils.runtime import open_external_url


def _open_external_url(url: str) -> bool:
    """Open external URLs through the shared runtime helper."""
    return open_external_url(url, opener=webbrowser.open)


class SelectionActionsMixin:
    """Selection state, bookmark opening, and row context-menu behavior."""

    def _select_all_bookmarks(self):
        """Select all bookmarks in view (Ctrl+A)"""
        all_items = self.tree.get_children()
        self.tree.selection_set(all_items)
        self.selected_bookmarks = [int(item) for item in all_items]
        self._update_selection_bar()
        self._set_status(f"Selected {len(all_items)} bookmarks")
        return "break"  # Prevent default behavior

    def _on_selection_change(self, event):
        """Handle tree selection change"""
        self.selected_bookmarks = [int(item) for item in self.tree.selection()]
        self._update_status_counts()
        self._update_selection_bar()
        if self.selected_bookmarks:
            self._set_status(f"{pluralize(len(self.selected_bookmarks), 'bookmark')} selected")
    
    def _on_item_double_click(self, event):
        """Handle double-click"""
        item = self.tree.identify_row(event.y)
        if item:
            bookmark = self.bookmark_manager.get_bookmark(int(item))
            if bookmark:
                self._open_bookmark(bookmark)
    
    def _on_bookmark_click(self, bookmark: Bookmark):
        """Handle bookmark click"""
        pass
    
    def _open_bookmark(self, bookmark: Bookmark):
        """Open bookmark in browser"""
        if _open_external_url(bookmark.url):
            bookmark.visit_count += 1
            bookmark.last_visited = datetime.now().isoformat()
            self.bookmark_manager.update_bookmark(bookmark)

    def _show_context_menu(self, event):
        """Show context menu with Send To and Search Domain options"""
        theme = get_theme()
        item = self.tree.identify_row(event.y)
        if not item:
            return
        
        # Select item if not already selected
        if item not in self.tree.selection():
            self.tree.selection_set(item)
        
        # Update selected_bookmarks list
        self.selected_bookmarks = [int(i) for i in self.tree.selection()]
        
        # Get selected bookmark for domain search
        first_bookmark = None
        if self.selected_bookmarks:
            first_bookmark = self.bookmark_manager.get_bookmark(self.selected_bookmarks[0])
        
        menu = tk.Menu(self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                      activebackground=theme.bg_hover, activeforeground=theme.text_primary)
        menu.add_command(label="  Open in Browser", command=self._open_selected)
        menu.add_command(label="  Edit Bookmark", command=self._edit_selected)
        menu.add_separator()
        
        # Search Domain option
        if first_bookmark and first_bookmark.domain:
            menu.add_command(
                label=f"  Filter by Domain ({first_bookmark.domain})",
                command=lambda: self._filter_by_domain(first_bookmark.domain)
            )
        
        # Send To submenu with all categories
        send_to_menu = tk.Menu(menu, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                              activebackground=theme.bg_hover, activeforeground=theme.text_primary)
        
        categories = self.category_manager.get_sorted_categories()
        for cat in categories:
            send_to_menu.add_command(
                label=cat,
                command=lambda c=cat: self._send_to_category(c)
            )
        
        menu.add_cascade(label="  Move to Category", menu=send_to_menu)
        menu.add_separator()
        menu.add_command(label="  Copy URL", command=self._copy_url)
        menu.add_command(label="  Toggle Pin", command=self._toggle_pin)
        menu.add_command(label="  Custom Favicon…", command=self._show_custom_favicon_dialog)
        menu.add_separator()
        
        # AI Tools submenu
        ai_menu = tk.Menu(menu, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                         activebackground=theme.bg_hover, activeforeground=theme.text_primary)
        ai_menu.add_command(label="AI Categorize", command=self._ai_categorize)
        ai_menu.add_command(label="Suggest Tags", command=self._ai_suggest_tags)
        ai_menu.add_command(label="Summarize", command=self._ai_summarize)
        ai_menu.add_command(label="Improve Titles", command=self._ai_improve_titles)
        menu.add_cascade(label="  AI Tools", menu=ai_menu)
        
        menu.add_separator()
        menu.add_command(label="  Mark as Needs Review", command=self._mark_as_broken)
        menu.add_command(label="  Delete", command=self._delete_selected)
        
        menu.tk_popup(event.x_root, event.y_root)
    
    def _send_to_category(self, category: str):
        """Send selected bookmarks to a category"""
        if not self.selected_bookmarks:
            return
        
        count = 0
        for bm_id in self.selected_bookmarks:
            bookmark = self.bookmark_manager.get_bookmark(bm_id)
            if bookmark:
                bookmark.category = category
                self.bookmark_manager.update_bookmark(bookmark)
                count += 1
        
        self._refresh_all()
        self._set_status(f"Moved {count} bookmark(s) to '{category}'")
    
    def _mark_as_broken(self):
        """Mark selected bookmarks as broken"""
        if not self.selected_bookmarks:
            return
        
        for bm_id in self.selected_bookmarks:
            bookmark = self.bookmark_manager.get_bookmark(bm_id)
            if bookmark:
                bookmark.is_valid = False
                bookmark.notes = (bookmark.notes or "") + "\n[Marked as potentially broken]"
                self.bookmark_manager.update_bookmark(bookmark)
        
        self._refresh_bookmark_list()
        self._set_status(f"Marked {len(self.selected_bookmarks)} bookmark(s) as broken")

