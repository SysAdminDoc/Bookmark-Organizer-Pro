"""Theme-change actions for the app coordinator."""

from __future__ import annotations

from bookmark_organizer_pro.ui.widgets import apply_window_chrome, get_theme


class ThemeActionsMixin:
    """Live theme refresh behavior used by the app coordinator."""

    def _on_theme_change(self, theme_name: str):
        """Handle theme change - apply live"""
        self._apply_theme_live()
        self._set_status(f"Theme changed to {theme_name}")
    
    def _apply_theme_live(self):
        """Rebuild the themed shell so every native Tk surface repaints."""
        if not hasattr(self, 'main_container'):
            return

        theme = get_theme()
        status_text = "Ready"
        try:
            status_text = self.status_label.cget("text") or status_text
        except Exception:
            pass

        query = ""
        try:
            if self.search_entry.get() != self._search_placeholder:
                query = self.search_entry.get()
        except Exception:
            pass

        active_filter = getattr(self, "active_filter", "All")
        quick_filter = getattr(self, "quick_filter", None)
        current_category = getattr(self, "current_category", None)
        selected_ids = list(getattr(self, "selected_bookmarks", []) or [])
        chat_state = None
        try:
            chat_state = self.chat_panel.export_state()
        except Exception:
            pass
        scroll_positions = {}
        for name in ("left_scroll", "right_scroll"):
            try:
                scroll_positions[name] = getattr(self, name).canvas.yview()[0]
            except Exception:
                pass

        for name in ("main_container", "status_bar"):
            widget = getattr(self, name, None)
            try:
                if widget and widget.winfo_exists():
                    widget.destroy()
            except Exception:
                pass

        self._last_analytics_stats = None
        self.root.configure(bg=theme.bg_primary)
        apply_window_chrome(self.root)
        self._create_menu()
        self._create_main_layout()
        self._create_status_bar()
        self.active_filter = active_filter
        self.quick_filter = quick_filter
        self.current_category = current_category

        if query:
            self._suppress_search_callback = True
            self.search_entry.delete(0, "end")
            self.search_entry.insert(0, query)
            self.search_entry.configure(fg=theme.text_primary)
            self.search_query = query
            self._suppress_search_callback = False

        self._refresh_all()
        for filter_name in self.filter_buttons:
            self._set_filter_visual(filter_name, filter_name == active_filter)
        valid_selection = [
            str(bookmark_id) for bookmark_id in selected_ids
            if str(bookmark_id) in self.tree.get_children("")
        ]
        if valid_selection:
            self.tree.selection_set(valid_selection)
            self.tree.focus(valid_selection[0])
            self.tree.see(valid_selection[0])
        try:
            self.chat_panel.restore_state(chat_state)
        except Exception:
            pass
        for name, position in scroll_positions.items():
            try:
                getattr(self, name).canvas.yview_moveto(position)
            except Exception:
                pass
        self.status_label.configure(text=status_text)
        self._update_status_counts()
