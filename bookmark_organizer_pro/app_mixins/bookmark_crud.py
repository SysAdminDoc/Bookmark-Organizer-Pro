"""Bookmark add, edit, open, copy, pin, and delete actions."""

from __future__ import annotations

from tkinter import messagebox
from typing import Dict

from bookmark_organizer_pro.commands import DeleteBookmarksCommand
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.ui.bookmark_workflows import QuickAddDialog
from bookmark_organizer_pro.ui.foundation import pluralize
from bookmark_organizer_pro.ui.widgets import BookmarkEditorDialog
from bookmark_organizer_pro.utils.validators import validate_url


class BookmarkCrudMixin:
    """Manual bookmark lifecycle actions used by the app coordinator."""

    def _add_bookmark(self):
        """Add new bookmark"""
        dialog = QuickAddDialog(
            self.root, self.category_manager.get_sorted_categories(),
            on_add=self._on_bookmark_added
        )
    
    def _on_bookmark_added(self, data: Dict):
        """Handle new bookmark"""
        url = str(data.get("url", "")).strip()
        valid, error = validate_url(url)
        if not valid or not url.startswith(("http://", "https://")):
            self._show_toast(f"Bookmark was not added: {error or 'unsupported URL'}", "error")
            return
        
        bookmark = self.bookmark_manager.add_bookmark_clean(
            url=url,
            title=str(data.get("title") or url).strip(),
            category=str(data.get("category") or "Uncategorized / Needs Review"),
            favicon_path=str(data.get("custom_favicon") or ""),
        )
        if bookmark is None:
            self._show_toast("Bookmark already exists", "info")
            self._set_status("Duplicate bookmark skipped")
            return

        self.favicon_manager.download_async(bookmark.domain, bookmark.id)
        
        self._refresh_all()
        self._set_status(f"Added bookmark: {bookmark.title}")
        self._show_toast("Bookmark added", "success")
    
    def _edit_selected(self):
        """Edit selected bookmark"""
        if self.selected_bookmarks:
            bookmark = self.bookmark_manager.get_bookmark(self.selected_bookmarks[0])
            if bookmark:
                dialog = BookmarkEditorDialog(
                    self.root, bookmark,
                    categories=self.category_manager.get_sorted_categories(),
                    available_tags=self.tag_manager.get_all_tags(),
                    on_save=lambda bm: self._on_bookmark_edited(bm)
                )
    
    def _on_bookmark_edited(self, bookmark: Bookmark):
        """Handle edited bookmark"""
        self.bookmark_manager.update_bookmark(bookmark)
        self._refresh_all()
    
    def _open_selected(self):
        """Open selected bookmarks"""
        for bm_id in self.selected_bookmarks:
            bookmark = self.bookmark_manager.get_bookmark(bm_id)
            if bookmark:
                self._open_bookmark(bookmark)
    
    def _copy_url(self):
        """Copy URLs to clipboard"""
        urls = []
        for bm_id in self.selected_bookmarks:
            bookmark = self.bookmark_manager.get_bookmark(bm_id)
            if bookmark:
                urls.append(bookmark.url)
        
        if urls:
            self.root.clipboard_clear()
            self.root.clipboard_append('\n'.join(urls))
            self._set_status(f"Copied {pluralize(len(urls), 'URL')}")
    
    def _toggle_pin(self):
        """Toggle pin status"""
        changed = 0
        for bm_id in self.selected_bookmarks:
            bookmark = self.bookmark_manager.get_bookmark(bm_id)
            if bookmark:
                bookmark.is_pinned = not bookmark.is_pinned
                self.bookmark_manager.update_bookmark(bookmark)
                changed += 1
        self._refresh_bookmark_list()
        if changed:
            self._set_status(f"Updated pin state for {pluralize(changed, 'bookmark')}")
    
    def _delete_selected(self):
        """Delete selected bookmarks with undo support"""
        if not self.selected_bookmarks:
            return

        count = len(self.selected_bookmarks)

        if count >= 2:
            if not messagebox.askyesno(
                "Delete Bookmarks",
                f"Delete {pluralize(count, 'bookmark')}?\n\nYou can undo this from the Edit menu.",
                parent=self.root
            ):
                return

        cmd = DeleteBookmarksCommand(self.bookmark_manager, list(self.selected_bookmarks))
        self.command_stack.execute(cmd)

        self.selected_bookmarks.clear()
        self._refresh_all()
        self._update_selection_bar()
        self._show_toast(f"Deleted {pluralize(count, 'bookmark')}. Undo is available from Edit.", "info")
