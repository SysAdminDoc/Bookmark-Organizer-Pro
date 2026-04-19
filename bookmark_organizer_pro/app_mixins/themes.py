"""Theme-change actions for the app coordinator."""

from __future__ import annotations

from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.ui.widgets import get_theme


class ThemeActionsMixin:
    """Live theme refresh behavior used by the app coordinator."""

    def _on_theme_change(self, theme_name: str):
        """Handle theme change - apply live"""
        self._apply_theme_live()
        self._set_status(f"Theme changed to {theme_name}")
    
    def _apply_theme_live(self):
        """Apply current theme to all widgets recursively"""
        # Safety check - only proceed if fully initialized
        if not hasattr(self, 'main_container'):
            return
        
        theme = get_theme()
        
        def apply_to_widget(widget, bg_color=None):
            """Recursively apply theme to widget and children"""
            try:
                widget_class = widget.winfo_class()
                
                # Skip certain widget types
                if widget_class in ('Menu', 'Scrollbar'):
                    return
                
                # Determine background color
                if bg_color:
                    widget.configure(bg=bg_color)
                elif widget_class == 'Frame':
                    widget.configure(bg=theme.bg_primary)
                elif widget_class == 'Label':
                    widget.configure(bg=theme.bg_primary, fg=theme.text_primary)
                elif widget_class == 'Entry':
                    widget.configure(bg=theme.bg_secondary, fg=theme.text_primary)
                elif widget_class == 'Listbox':
                    widget.configure(bg=theme.bg_secondary, fg=theme.text_primary)
            except Exception:
                pass
            
            # Apply to children
            for child in widget.winfo_children():
                try:
                    apply_to_widget(child)
                except Exception:
                    pass
        
        # Apply to root
        try:
            self.root.configure(bg=theme.bg_primary)
            apply_to_widget(self.main_container)
        except Exception:
            pass
        
        # Update status bar explicitly
        try:
            self.status_bar.configure(bg=theme.bg_dark)
            self.status_label.configure(bg=theme.bg_dark, fg=theme.text_muted)
        except Exception:
            pass
        
        # Refresh all data displays (this recreates widgets with new theme)
        try:
            self._refresh_category_list()
            self._refresh_bookmark_list()
            self._refresh_analytics()
        except Exception:
            log.warning("Theme refresh failed", exc_info=True)
