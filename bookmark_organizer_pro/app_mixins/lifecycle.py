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
        try:
            self._refresh_analytics()
        except Exception:
            log.warning("Analytics poll failed", exc_info=True)
        
        # Schedule next poll (30 seconds)
        self._analytics_poll_id = self.root.after(30000, self._poll_analytics)

    def _on_close(self):
        """Handle close"""
        # Cancel polling
        if hasattr(self, '_analytics_poll_id') and self._analytics_poll_id:
            self.root.after_cancel(self._analytics_poll_id)
        if hasattr(self, '_grid_after_id') and self._grid_after_id:
            self.root.after_cancel(self._grid_after_id)
        
        self.favicon_manager.shutdown()
        self.task_runner.shutdown()
        self.root.destroy()
