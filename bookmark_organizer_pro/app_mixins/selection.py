"""Selection, opening, and context-menu actions for the app coordinator."""

from __future__ import annotations

import tkinter as tk
import webbrowser
from datetime import datetime

from bookmark_organizer_pro.i18n import _, format_message
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.snapshot import open_snapshot_file
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
        if hasattr(self, "_update_right_rail_selection"):
            self._update_right_rail_selection()
        if hasattr(self, "_refresh_table_semantic_status"):
            self._refresh_table_semantic_status()
        self._set_status(format_message("Selected {count} bookmarks", count=len(all_items)))
        return "break"  # Prevent default behavior

    def _on_selection_change(self, event):
        """Handle tree selection change"""
        self.selected_bookmarks = [int(item) for item in self.tree.selection()]
        self._update_status_counts()
        self._update_selection_bar()
        if hasattr(self, "_update_right_rail_selection"):
            self._update_right_rail_selection()
        if hasattr(self, "_refresh_table_semantic_status"):
            self._refresh_table_semantic_status()
        if self.selected_bookmarks:
            self._set_status(format_message(
                "{bookmarks} selected",
                bookmarks=pluralize(len(self.selected_bookmarks), "bookmark"),
            ))
    
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

    def _open_offline_copy(self, bookmark: Bookmark):
        """Verify and open a selected bookmark's local snapshot."""
        opened, detail = open_snapshot_file(bookmark)
        if opened:
            self._set_status(
                _("Opened offline copy for {title}").format(
                    title=bookmark.title[:60],
                )
            )
            return
        self._set_status(detail)
        if hasattr(self, "_toast"):
            self._toast(detail, "error")

    def _show_context_menu(self, event=None):
        """Show the row action/sort menu for pointer or keyboard invocation."""
        theme = get_theme()
        item = ""
        if event is not None and getattr(event, "num", None) == 3:
            item = self.tree.identify_row(event.y)
        if not item:
            selected = self.tree.selection()
            item = str(selected[0]) if selected else str(self.tree.focus() or "")
        if not item:
            return "break"
        
        # Select item if not already selected
        if item not in self.tree.selection():
            self.tree.selection_set(item)
        
        # Update selected_bookmarks list
        self.selected_bookmarks = [int(i) for i in self.tree.selection()]
        self._update_selection_bar()
        if hasattr(self, "_update_right_rail_selection"):
            self._update_right_rail_selection()
        
        # Get selected bookmark for domain search
        first_bookmark = None
        if self.selected_bookmarks:
            first_bookmark = self.bookmark_manager.get_bookmark(self.selected_bookmarks[0])
        
        menu = tk.Menu(self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                      activebackground=theme.bg_hover, activeforeground=theme.text_primary)
        menu.add_command(label=_("Open in Browser"), command=self._open_selected)
        if first_bookmark and first_bookmark.snapshot_path:
            menu.add_command(
                label=_("Open Offline Copy"),
                command=lambda: self._open_offline_copy(first_bookmark),
            )
        menu.add_command(label=_("Reader View"), command=self._open_reader_view)
        menu.add_command(label=_("Edit Bookmark"), command=self._edit_selected)
        menu.add_separator()

        sort_menu = tk.Menu(
            menu,
            tearoff=0,
            bg=theme.bg_secondary,
            fg=theme.text_primary,
            activebackground=theme.bg_hover,
            activeforeground=theme.text_primary,
        )
        for label, column in (
            (_("Site"), "#0"),
            (_("Title"), "title"),
            (_("Collection / Tags"), "organization"),
            (_("Saved"), "saved"),
            (_("Status"), "status"),
            (_("Pinned"), "favorite"),
        ):
            sort_menu.add_command(
                label=label,
                command=lambda value=column: self.tree.sort_by_column(value),
            )
        menu.add_cascade(label=_("Sort by"), menu=sort_menu)
        menu.add_separator()
        
        # Search Domain option
        if first_bookmark and first_bookmark.domain:
            menu.add_command(
                label=format_message('Filter by Domain ({value_0})', value_0=first_bookmark.domain),
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
        
        menu.add_cascade(label=_("Move to Category"), menu=send_to_menu)
        menu.add_separator()
        menu.add_command(label=_("Copy URL"), command=self._copy_url)
        menu.add_command(label=_("Toggle Pin"), command=self._toggle_pin)
        menu.add_command(label=_("Set Custom Favicon…"), command=self._show_custom_favicon_dialog)
        menu.add_separator()
        
        # AI Tools submenu
        ai_menu = tk.Menu(menu, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                         activebackground=theme.bg_hover, activeforeground=theme.text_primary)
        ai_menu.add_command(label=_("AI Categorize"), command=self._ai_categorize)
        ai_menu.add_command(label=_("Suggest Tags"), command=self._ai_suggest_tags)
        ai_menu.add_command(label=_("Summarize"), command=self._ai_summarize)
        ai_menu.add_command(label=_("Improve Titles"), command=self._ai_improve_titles)
        menu.add_cascade(label=_("Assistant Tools"), menu=ai_menu)

        menu.add_separator()
        menu.add_command(label=_("Mark as Needs Review"), command=self._mark_as_broken)
        menu.add_command(label=_("Delete"), command=self._delete_selected)

        if event is not None and getattr(event, "num", None) == 3:
            x_root, y_root = event.x_root, event.y_root
        else:
            x_root = self.tree.winfo_rootx() + 48
            y_root = self.tree.winfo_rooty() + 72
        menu.tk_popup(x_root, y_root)
        return "break"
    
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
        self._set_status(format_message(
            "Moved {count} bookmark(s) to '{category}'", count=count, category=category,
        ))
    
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
        self._set_status(format_message(
            "Marked {count} bookmark(s) as broken", count=len(self.selected_bookmarks),
        ))
