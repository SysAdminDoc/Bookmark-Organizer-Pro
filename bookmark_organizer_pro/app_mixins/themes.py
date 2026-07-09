"""Theme-change actions for the app coordinator."""

from __future__ import annotations

from bookmark_organizer_pro.ui.widgets import get_theme


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

        for name in ("main_container", "status_bar"):
            widget = getattr(self, name, None)
            try:
                if widget and widget.winfo_exists():
                    widget.destroy()
            except Exception:
                pass

        self._last_analytics_stats = None
        self.root.configure(bg=theme.bg_primary)
        self._create_menu()
        self._create_main_layout()
        self._create_status_bar()

        if query:
            self._suppress_search_callback = True
            self.search_entry.delete(0, "end")
            self.search_entry.insert(0, query)
            self.search_entry.configure(fg=theme.text_primary)
            self.search_query = query
            self._suppress_search_callback = False

        self._refresh_all()
        self.status_label.configure(text=status_text)
        self._update_status_counts()
