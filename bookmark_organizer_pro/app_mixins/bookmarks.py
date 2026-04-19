"""Bookmark list rendering and favicon update actions for the app coordinator."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime, timedelta
from typing import Dict, List

from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.ui.feedback import ToastNotification
from bookmark_organizer_pro.ui.foundation import DesignTokens, display_or_fallback, pluralize, truncate_middle
from bookmark_organizer_pro.ui.shell_widgets import ViewMode
from bookmark_organizer_pro.ui.widgets import get_theme


class BookmarkViewMixin:
    """Bookmark filtering, list rendering, and favicon UI update behavior."""

    def _refresh_bookmark_list(self):
        """Refresh bookmark display with advanced filtering"""
        if not hasattr(self, 'tree') or not self.tree:
            return
        
        # Get base bookmarks - always start from all bookmarks for quick filters
        if self.current_category:
            bookmarks = self.bookmark_manager.get_bookmarks_by_category(self.current_category)
        else:
            bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        query = self.search_query.strip() if hasattr(self, 'search_query') and self.search_query else ""

        # Apply quick filter (takes priority over search)
        quick_filter = getattr(self, 'quick_filter', None)
        if quick_filter:
            if quick_filter == "pinned":
                bookmarks = [bm for bm in bookmarks if bm.is_pinned]
            elif quick_filter == "broken":
                bookmarks = [bm for bm in bookmarks if not bm.is_valid]
            elif quick_filter == "recent":
                week_ago = (datetime.now() - timedelta(days=7)).isoformat()
                # Handle bookmarks with empty or invalid created_at
                bookmarks = [bm for bm in bookmarks if bm.created_at and bm.created_at >= week_ago]
            elif quick_filter == "untagged":
                bookmarks = [bm for bm in bookmarks if not bm.tags and not bm.ai_tags]
        else:
            # Apply search query only if no quick filter
            if query:
                try:
                    bookmarks = self.bookmark_manager.search_bookmarks(
                        query, category=self.current_category
                    )
                except Exception:
                    query_lower = query.lower()
                    bookmarks = [
                        bm for bm in bookmarks
                        if query_lower in bm.title.lower() or
                        query_lower in bm.url.lower() or
                        query_lower in (bm.category or "").lower() or
                        query_lower in ' '.join(bm.tags).lower()
                    ]
        
        if query:
            bookmarks.sort(key=lambda b: not b.is_pinned)
        else:
            bookmarks.sort(key=lambda b: (not b.is_pinned, b.title.lower()))

        if self.count_label:
            n = len(bookmarks)
            total = len(self.bookmark_manager.bookmarks)
            if total == 0:
                self.count_label.configure(text="Library")
                if getattr(self, 'view_hint_label', None):
                    self.view_hint_label.configure(text="Ready to import")
            elif n != total:
                self.count_label.configure(text=f"{pluralize(n, 'bookmark')} Shown")
                if getattr(self, 'view_hint_label', None):
                    self.view_hint_label.configure(text="Filtered view")
            else:
                self.count_label.configure(text=pluralize(n, "Bookmark"))
                if getattr(self, 'view_hint_label', None):
                    self.view_hint_label.configure(text="List view")

        self._refresh_filter_counts()
        total_bookmarks = len(self.bookmark_manager.get_all_bookmarks())
        self._set_collection_summary_visible(total_bookmarks > 0)
        if total_bookmarks > 0:
            self._refresh_collection_summary(
                visible_count=len(bookmarks),
                total_count=total_bookmarks,
                query=query,
                quick_filter=quick_filter or ""
            )

        # Toggle empty state vs list view
        if hasattr(self, 'empty_state'):
            is_filtered_view = bool(query or quick_filter or self.current_category)
            self.empty_state.pack_forget()
            if hasattr(self, 'filtered_empty_state'):
                self.filtered_empty_state.pack_forget()

            if len(bookmarks) == 0 and total_bookmarks == 0:
                self.list_frame.pack_forget()
                self.empty_state.pack(fill=tk.BOTH, expand=True)
            elif len(bookmarks) == 0 and is_filtered_view and hasattr(self, 'filtered_empty_state'):
                self.list_frame.pack_forget()
                self.filtered_empty_state.pack(fill=tk.BOTH, expand=True)
            else:
                self.list_frame.pack(
                    fill=tk.BOTH, expand=True,
                    padx=DesignTokens.CONTENT_PAD_X,
                    pady=(0, DesignTokens.CONTENT_PAD_Y)
                )

        if self.view_mode == ViewMode.LIST:
            self._populate_list_view(bookmarks)
        else:
            self._populate_grid_view(bookmarks)

    def _show_toast(self, message: str, style: str = "info"):
        """Show a non-blocking toast notification."""
        ToastNotification.show(self.root, message, style)

    def _populate_list_view(self, bookmarks: List[Bookmark]):
        """Populate treeview with bookmarks"""
        theme = get_theme()
        self.tree.tag_configure("oddrow", background=theme.bg_primary, foreground=theme.text_primary)
        self.tree.tag_configure("evenrow", background=theme.bg_secondary, foreground=theme.text_primary)
        self.tree.tag_configure("broken", foreground=theme.accent_error)
        self.tree.tag_configure("archived", foreground=theme.text_muted)
        previous_selection = set(getattr(self, 'selected_bookmarks', []))
        restored_selection = []

        for item in self.tree.get_children():
            self.tree.delete(item)
        
        self._tree_items: Dict[int, str] = {}
        self._tree_domains: Dict[str, List[str]] = {}
        
        for index, bm in enumerate(bookmarks):
            # Build a calm, scannable row summary with important status first.
            status_parts = []
            if bm.is_pinned:
                status_parts.append("★")
            if bm.ai_confidence > 0:
                status_parts.append("AI")
            if not bm.is_valid:
                status_parts.append("Needs review")
            if bm.is_archived:
                status_parts.append("Archived")

            prefix = " · ".join(status_parts)
            title_text = display_or_fallback(bm.title, "Untitled bookmark")
            title = f"{prefix} · {title_text}" if prefix else title_text
            
            # Keep rows scan-friendly: show one primary tag plus a count.
            if bm.tags:
                tags_str = f"#{bm.tags[0]}"
                remaining = len(bm.tags) + len(bm.ai_tags) - 1
            elif bm.ai_tags:
                tags_str = f"AI #{bm.ai_tags[0]}"
                remaining = len(bm.ai_tags) - 1
            else:
                tags_str = "—"
                remaining = 0
            if remaining > 0:
                tags_str += f" +{remaining}"

            category = truncate_middle(display_or_fallback(bm.category, "Uncategorized"), 28)
            url_display = display_or_fallback(bm.domain, "Unknown domain")
            tags_str = truncate_middle(tags_str, 26)

            row_tags = ["evenrow" if index % 2 else "oddrow"]
            if not bm.is_valid:
                row_tags.append("broken")
            elif bm.is_archived:
                row_tags.append("archived")
            
            item_id = self.tree.insert(
                "", "end",
                iid=str(bm.id),
                text="  ",  # Padding space
                values=(title, url_display, category, tags_str),
                tags=tuple(row_tags)
            )
            if bm.id in previous_selection:
                restored_selection.append(item_id)
            
            self._tree_items[bm.id] = item_id
            
            if bm.domain not in self._tree_domains:
                self._tree_domains[bm.domain] = []
            self._tree_domains[bm.domain].append(item_id)
            
            # Set favicon if cached
            favicon_path = self.favicon_manager.get_cached(bm.domain)
            if favicon_path:
                self.tree.set_favicon(item_id, favicon_path)

        if restored_selection:
            self.tree.selection_set(restored_selection)
            self.selected_bookmarks = [int(item) for item in restored_selection]
        else:
            self.selected_bookmarks = []
        self._update_status_counts()
        self._update_selection_bar()
    
    def _populate_grid_view(self, bookmarks: List[Bookmark]):
        """Grid view disabled - using list view only"""
        pass  # Grid view removed - list view with zoom is now used
    
    def _load_next_grid_batch(self):
        """Grid view disabled - this is a stub"""
        pass
    
    def _on_favicon_progress(self, completed: int, total: int, current: str):
        """Favicon progress callback - thread-safe"""
        self.root.after(0, lambda: self.favicon_status.update_status(completed, total, current))
    
    def _on_favicon_ready_threadsafe(self, domain: str, filepath: str, bookmark_id: int):
        """Favicon ready callback - schedules UI update on main thread"""
        self.root.after(0, lambda: self._update_favicon_in_tree(domain, filepath))
    
    def _update_favicon_in_tree(self, domain: str, filepath: str):
        """Update favicon in treeview (runs on main thread)"""
        if hasattr(self, '_tree_domains') and domain in self._tree_domains:
            for item_id in self._tree_domains[domain]:
                try:
                    self.tree.set_favicon(item_id, filepath)
                except Exception:
                    pass
    
    def _set_view_mode(self, mode: ViewMode):
        """View mode - now only list view is supported"""
        self.view_mode = ViewMode.LIST
        self._refresh_bookmark_list()

