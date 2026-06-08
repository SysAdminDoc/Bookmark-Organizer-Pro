"""Application lifecycle and status actions for the app coordinator."""

from __future__ import annotations

import tkinter as tk

from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.ui.foundation import pluralize


class LifecycleActionsMixin:
    """Startup data load, status bar, polling, undo/redo, and close handlers."""

    def _load_and_display_data(self):
        """Load bookmarks and display - non-blocking"""
        self._refresh_category_list()
        self._refresh_bookmark_list()
        self._refresh_analytics()
        
        # Queue favicon downloads
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        self.favicon_manager.queue_bookmarks(bookmarks)
        
        if bookmarks:
            self._set_status(f"Loaded {pluralize(len(bookmarks), 'bookmark')}")
        else:
            self._set_status("Library ready")

    def _post_to_ui(self, callback):
        """Schedule a callback on the Tk main thread from a worker thread.

        Safe during/after shutdown: does nothing once the app is closing or the
        root is gone, and swallows the TclError that ``root.after()`` raises on a
        destroyed interpreter. Returns the after-id, or None if not scheduled.
        """
        if getattr(self, "_closing", False):
            return None
        try:
            if not self.root.winfo_exists():
                return None
            return self.root.after(0, callback)
        except Exception:
            return None

    def _undo(self):
        """Undo"""
        if self.command_stack.undo():
            self._refresh_all()
    
    def _redo(self):
        """Redo"""
        if self.command_stack.redo():
            self._refresh_all()
    
    def _refresh_all(self):
        """Refresh all displays"""
        self._refresh_category_list()
        self._refresh_bookmark_list()
        self._refresh_analytics()
        if hasattr(self, "_refresh_read_later_sidebar"):
            try:
                self._refresh_read_later_sidebar()
            except Exception:
                pass
        if hasattr(self, "_refresh_flows_sidebar"):
            try:
                self._refresh_flows_sidebar()
            except Exception:
                pass
    
    def _set_status(self, message: str):
        """Set status message and update counts"""
        if self.status_label:
            try:
                self.status_label.configure(text=message)
            except Exception:
                pass
        # Update counts whenever status changes
        self._update_status_counts()
    
    def _show_status_progress(self, show: bool = True):
        """Show or hide progress indicator in status bar"""
        if hasattr(self, 'status_progress'):
            try:
                if show:
                    self.status_progress.pack(side=tk.LEFT, padx=(8, 0))
                    self.status_progress.start(10)
                else:
                    self.status_progress.stop()
                    self.status_progress.pack_forget()
            except Exception:
                pass
    
    def _update_status_counts(self):
        """Update item counts in status bar"""
        try:
            if hasattr(self, 'status_total_label') and self.status_total_label:
                total = len(self.bookmark_manager.get_all_bookmarks())
                self.status_total_label.configure(text=pluralize(total, "bookmark"))
            
            if hasattr(self, 'status_selected_label') and self.status_selected_label:
                selected = len(self.selected_bookmarks) if hasattr(self, 'selected_bookmarks') else 0
                if selected > 0:
                    self.status_selected_label.configure(text=f"{selected} selected")
                else:
                    self.status_selected_label.configure(text="")
        except Exception:
            pass
    
    def _try_enable_window_dnd(self):
        """Drag-drop requires tkinterdnd2 which may not be installed"""
        # Native drag-drop requires tkinterdnd2
        # Users can still use the browse button or import menu
        pass
    
    def _start_analytics_polling(self):
        """Start periodic analytics refresh"""
        self._analytics_poll_id = None
        self._poll_analytics()
    
    def _poll_analytics(self):
        """Poll and refresh analytics periodically"""
        if getattr(self, "_closing", False):
            return
        try:
            self._refresh_analytics()
        except Exception:
            log.warning("Analytics poll failed", exc_info=True)

        # Schedule next poll (30 seconds) unless the app is shutting down.
        if not getattr(self, "_closing", False):
            self._analytics_poll_id = self.root.after(30000, self._poll_analytics)

    def _cycle_focus_section(self):
        """Cycle keyboard focus between search, sidebar, and bookmark list (F6)."""
        targets = []
        if hasattr(self, "search_entry") and self.search_entry:
            targets.append(self.search_entry)
        if hasattr(self, "filter_buttons"):
            first_filter = list(self.filter_buttons.values())
            if first_filter:
                targets.append(first_filter[0])
        if hasattr(self, "tree") and self.tree:
            targets.append(self.tree)
        if hasattr(self, "chat_panel") and self.chat_panel:
            targets.append(self.chat_panel._entry)
        if not targets:
            return "break"
        try:
            current = self.root.focus_get()
            idx = -1
            for i, t in enumerate(targets):
                if current is t or (hasattr(current, "master") and current.master is t):
                    idx = i
                    break
            next_idx = (idx + 1) % len(targets)
            targets[next_idx].focus_set()
        except Exception:
            if targets:
                targets[0].focus_set()
        return "break"

    def _on_close(self):
        """Handle close — stop timers and background work before tearing down."""
        # Signal background workers/poll loops to stop scheduling UI callbacks;
        # firing root.after() after destroy() raises TclError on worker threads.
        self._closing = True

        # Cancel any pending after() timers so none fire on a destroyed root.
        for attr in ("_analytics_poll_id", "_grid_after_id", "_search_after"):
            after_id = getattr(self, attr, None)
            if after_id:
                try:
                    self.root.after_cancel(after_id)
                except Exception:
                    pass

        for manager in (getattr(self, "favicon_manager", None),
                        getattr(self, "task_runner", None)):
            if manager is not None:
                try:
                    manager.shutdown()
                except Exception:
                    log.debug("Error during shutdown", exc_info=True)

        try:
            self.root.destroy()
        except Exception:
            pass
