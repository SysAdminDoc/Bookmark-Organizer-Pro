"""Bookmark list rendering and favicon update actions for the app coordinator."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime, timedelta
from typing import Dict, List

from bookmark_organizer_pro.i18n import _
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.ui.feedback import ToastNotification
from bookmark_organizer_pro.ui.foundation import DesignTokens, display_or_fallback, truncate_middle
from bookmark_organizer_pro.ui.shell_widgets import ViewMode
from bookmark_organizer_pro.ui.widgets import get_theme


def _relative_added(value: str, now: datetime | None = None) -> str:
    """Return a compact date label for the library table."""
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.replace(tzinfo=None)
    except (TypeError, ValueError):
        return "—"
    now = now or datetime.now()
    delta = max(0, (now.date() - parsed.date()).days)
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Yesterday"
    if delta < 7:
        return f"{delta} days ago"
    return parsed.strftime("%b %d, %Y")


def _bookmark_status(bookmark: Bookmark) -> str:
    """Describe a bookmark state without relying on color alone."""
    if not bookmark.is_valid:
        return "● Needs review"
    if bookmark.read_later:
        return "● Read later"
    if bookmark.visit_count:
        return "● Read"
    return "● Unread"


def _saved_cell(value: str, now: datetime | None = None) -> str:
    """Return a two-line saved date that stays readable in a dense row."""
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.replace(tzinfo=None)
    except (TypeError, ValueError):
        return "—"
    now = now or datetime.now()
    age_in_days = max(0, (now.date() - parsed.date()).days)
    if age_in_days < 7:
        return f"{_relative_added(value, now)}\n{parsed.strftime('%b %d')}"
    return f"{parsed.strftime('%b %d')}\n{parsed.strftime('%Y')}"


def _saved_sort_value(value: str) -> datetime | None:
    """Parse the source timestamp once for typed table ordering."""
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed


def _status_sort_value(bookmark: Bookmark) -> int:
    """Return the explicit product order for bookmark status groups."""
    if not bookmark.is_valid:
        return 0
    if bookmark.read_later:
        return 1
    if not bookmark.visit_count:
        return 2
    return 3


class BookmarkViewMixin:
    """Bookmark filtering, list rendering, and favicon UI update behavior."""

    def _refresh_bookmark_list(self):
        """Refresh bookmark display with advanced filtering"""
        if not hasattr(self, 'tree') or not self.tree:
            return
        set_semantic_state = getattr(self.tree, "set_semantic_state", None)
        if set_semantic_state is not None:
            set_semantic_state("loading", _("Loading bookmarks"))
            self._refresh_table_semantic_status()
        
        # Get base bookmarks - always start from all bookmarks for quick filters
        if self.current_category:
            bookmarks = self.bookmark_manager.get_bookmarks_by_category(self.current_category)
        else:
            bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        query = self.search_query.strip() if hasattr(self, 'search_query') and self.search_query else ""
        search_has_error = False

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
                if getattr(self, '_nl_search_mode', False):
                    bookmarks = self._nl_search_sync(query, bookmarks)
                    if hasattr(self, "_set_search_validation"):
                        self._set_search_validation([])
                else:
                    bookmarks = self.bookmark_manager.search_bookmarks(
                        query, category=self.current_category
                    )
                    diagnostics = self.bookmark_manager.search_engine.last_diagnostics
                    search_has_error = bool(diagnostics)
                    if hasattr(self, "_set_search_validation"):
                        self._set_search_validation(diagnostics)
            elif hasattr(self, "_set_search_validation"):
                self._set_search_validation([])
        
        if query:
            bookmarks.sort(key=lambda b: not b.is_pinned)
        else:
            bookmarks.sort(key=lambda b: (not b.is_pinned, b.title.lower()))

        if self.count_label and not bookmarks and not self.bookmark_manager.bookmarks:
            self.count_label.configure(text=_("Library"))
            if getattr(self, 'library_context_label', None):
                self.library_context_label.configure(text=_("Ready for your first save"))
            if getattr(self, 'view_hint_label', None):
                self.view_hint_label.configure(text=_("Local and ready"))

        self._refresh_filter_counts()
        total_bookmarks = len(self.bookmark_manager.get_all_bookmarks())
        self._table_visible_total = len(bookmarks)
        self._table_library_total = total_bookmarks
        self._set_collection_summary_visible(total_bookmarks > 0)
        self._set_content_header_visible(total_bookmarks > 0)
        if total_bookmarks > 0:
            self._refresh_collection_summary(
                visible_count=len(bookmarks),
                total_count=total_bookmarks,
                query=query,
                quick_filter=quick_filter or ""
            )
        if getattr(self, "collection_filter_btn", None):
            self.collection_filter_btn.set_text(self.current_category or "All collections")
        if getattr(self, "tag_filter_btn", None):
            tag_label = "All tags"
            if query.lower().startswith("tag:"):
                tag_label = f"#{query.split(':', 1)[1]}"
            self.tag_filter_btn.set_text(tag_label)
        if getattr(self, "type_filter_btn", None):
            type_labels = {
                "pinned": "Pinned", "recent": "Inbox",
                "broken": "Needs review", "untagged": "Untagged",
            }
            self.type_filter_btn.set_text(type_labels.get(quick_filter, "All types"))

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

        if set_semantic_state is not None:
            if search_has_error:
                set_semantic_state(
                    "error",
                    _("Search query has errors; no results are shown."),
                )
            elif not bookmarks:
                set_semantic_state(
                    "empty",
                    (
                        _("No bookmarks match the current view.")
                        if total_bookmarks
                        else _("Your bookmark library is empty.")
                    ),
                )
            else:
                set_semantic_state(
                    "ready",
                    _("{count} bookmarks in the current view.").format(
                        count=len(bookmarks),
                    ),
                )
        self._populate_list_view(bookmarks)

    def _show_toast(self, message: str, style: str = "info"):
        """Show a non-blocking toast notification."""
        ToastNotification.show(self.root, message, style)

    def _populate_list_view(self, bookmarks: List[Bookmark]):
        """Populate the virtualized bookmark table with bookmarks."""
        theme = get_theme()
        self.tree.tag_configure("oddrow", background=theme.bg_primary, foreground=theme.text_primary)
        self.tree.tag_configure("evenrow", background=theme.bg_secondary, foreground=theme.text_primary)
        self.tree.tag_configure("broken", foreground=theme.accent_error)
        self.tree.tag_configure("archived", foreground=theme.text_muted)
        previous_selection = set(getattr(self, 'selected_bookmarks', []))
        restored_selection = []
        
        self._tree_items: Dict[int, str] = {}
        self._tree_domains: Dict[str, List[str]] = {}
        row_specs = []
        favicon_updates = []
        
        for index, bm in enumerate(bookmarks):
            # Build calm two-line cells and keep state/favorite controls in their
            # own predictable columns.
            title_text = display_or_fallback(bm.title, "Untitled bookmark")
            subtitle = truncate_middle(
                display_or_fallback(bm.description or bm.notes, bm.url), 72,
            )
            title = f"{truncate_middle(title_text, 54)}\n{subtitle}"
            
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

            category = truncate_middle(display_or_fallback(bm.category, "Uncategorized"), 22)
            organization = f"{category}\n{truncate_middle(tags_str, 28)}"
            added = _saved_cell(bm.created_at)
            status = _bookmark_status(bm)
            favorite = _("Yes") if bm.is_pinned else _("No")
            site = truncate_middle(
                display_or_fallback(bm.domain, _("Unknown site")),
                14,
            )

            row_tags = ["evenrow" if index % 2 else "oddrow"]
            if not bm.is_valid:
                row_tags.append("broken")
            elif bm.is_archived:
                row_tags.append("archived")
            
            item_id = str(bm.id)
            row_specs.append({
                "iid": item_id,
                "text": site,
                "values": (title, organization, added, status, favorite),
                "tags": tuple(row_tags),
                "sort_values": {
                    "#0": bm.domain,
                    "title": bm.title,
                    "organization": bm.category,
                    "saved": _saved_sort_value(bm.created_at),
                    "status": _status_sort_value(bm),
                    "favorite": bool(bm.is_pinned),
                },
            })
            if bm.id in previous_selection:
                restored_selection.append(item_id)
            
            self._tree_items[bm.id] = item_id
            
            if bm.domain not in self._tree_domains:
                self._tree_domains[bm.domain] = []
            self._tree_domains[bm.domain].append(item_id)
            
            # Set favicon if cached
            favicon_path = self.favicon_manager.get_cached(bm.domain)
            if favicon_path:
                favicon_updates.append((item_id, favicon_path))

        if hasattr(self.tree, "set_bookmark_rows"):
            self.tree.set_bookmark_rows(row_specs)
        else:
            for item in self.tree.get_children():
                self.tree.delete(item)
            for row in row_specs:
                self.tree.insert(
                    "", "end",
                    iid=row["iid"],
                    text=row["text"],
                    values=row["values"],
                    tags=row["tags"],
                )
                if hasattr(self.tree, "set_sort_values"):
                    self.tree.set_sort_values(row["iid"], row["sort_values"])
        for item_id, favicon_path in favicon_updates:
            self.tree.set_favicon(item_id, favicon_path)

        if restored_selection:
            try:
                self.tree.selection_set(restored_selection, emit=False)
            except TypeError:
                self.tree.selection_set(restored_selection)
            self.selected_bookmarks = [int(item) for item in restored_selection]
        else:
            if hasattr(self.tree, "selection_clear"):
                self.tree.selection_clear()
            self.selected_bookmarks = []
        self._update_status_counts()
        self._update_selection_bar()
        if hasattr(self, "_update_right_rail_selection"):
            self._update_right_rail_selection()
        # Refresh after the row model and restored selection are committed so
        # assistive status text describes the current table, not the previous
        # render that was still present during the loading transition.
        if hasattr(self, "_refresh_table_semantic_status"):
            self._refresh_table_semantic_status()

    def _refresh_table_semantic_status(self, _event=None):
        """Publish visible row, selection, state, sort, and action context."""
        label = getattr(self, "library_footer_label", None)
        snapshotter = getattr(getattr(self, "tree", None), "semantic_snapshot", None)
        if label is None or snapshotter is None:
            return
        snapshot = snapshotter()
        state = snapshot.get("state", "ready")
        message = str(snapshot.get("message", ""))
        if state != "ready":
            label.configure(text=message)
            return

        visible = int(getattr(self, "_table_visible_total", len(snapshot["rows"])))
        total = int(getattr(self, "_table_library_total", visible))
        parts = [
            _("{visible} of {total} bookmarks").format(
                visible=visible,
                total=total,
            )
        ]
        selected_rows = [row for row in snapshot["rows"] if row["selected"]]
        if len(selected_rows) == 1:
            row = selected_rows[0]
            parts.append(
                _("row {position} of {total} selected").format(
                    position=row["position"],
                    total=row["set_size"],
                )
            )
        elif selected_rows:
            parts.append(
                _("{count} rows selected").format(count=len(selected_rows))
            )

        sorted_header = next(
            (
                header for header in snapshot["headers"]
                if header.get("sort") in {"ascending", "descending"}
            ),
            None,
        )
        if sorted_header is not None:
            direction = (
                _("descending")
                if sorted_header["sort"] == "descending"
                else _("ascending")
            )
            parts.append(
                _("Sorted: {column} {direction}").format(
                    column=sorted_header["label"],
                    direction=direction,
                )
            )
        label.configure(text=" · ".join(parts))
    
    def _on_favicon_progress(self, completed: int, total: int, current: str):
        """Favicon progress callback - thread-safe"""
        self._post_to_ui(lambda: self.favicon_status.update_status(completed, total, current))
    
    def _on_favicon_ready_threadsafe(self, domain: str, filepath: str, bookmark_id: int):
        """Favicon ready callback - schedules UI update on main thread"""
        self._post_to_ui(lambda: self._update_favicon_in_tree(domain, filepath))
    
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
