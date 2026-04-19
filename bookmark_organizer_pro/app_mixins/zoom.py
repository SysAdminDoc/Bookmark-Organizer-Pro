"""Zoom and font-scaling actions for the app coordinator."""

from __future__ import annotations

import tkinter.font as tkfont
from tkinter import ttk

from bookmark_organizer_pro.ui.foundation import FONTS, DesignTokens


class ZoomActionsMixin:
    """Application zoom controls backed by the shared font token system."""

    def _zoom_in(self):
        """Increase zoom level"""
        if self.zoom_level < self.zoom_max:
            self.zoom_level = min(self.zoom_level + 15, self.zoom_max)
            self._apply_zoom()
    
    def _zoom_out(self):
        """Decrease zoom level"""
        if self.zoom_level > self.zoom_min:
            self.zoom_level = max(self.zoom_level - 15, self.zoom_min)
            self._apply_zoom()
    
    def _on_mousewheel_zoom(self, event):
        """Handle Ctrl+Scroll for zoom"""
        # Check if Ctrl is pressed
        if event.state & 0x4:  # Control key modifier
            if event.delta > 0:
                self._zoom_in()
            else:
                self._zoom_out()
            return "break"  # Prevent normal scrolling
    
    def _apply_zoom(self):
        """Apply zoom to ALL UI text via the global FONTS system"""
        # Update zoom label
        if self.zoom_label:
            self.zoom_label.configure(text=f"{self.zoom_level}%")

        scale = self.zoom_level / 100.0

        # Scale the global FONTS config (base sizes at 100%)
        FONTS.size_title = max(12, int(16 * scale))
        FONTS.size_header = max(10, int(12 * scale))
        FONTS.size_body = max(8, int(10 * scale))
        FONTS.size_small = max(7, int(9 * scale))
        FONTS.size_tiny = max(7, int(8 * scale))

        # Update treeview (has its own style system)
        row_height = max(24, min(84, int(DesignTokens.TREEVIEW_ROW_HEIGHT * scale)))
        style = ttk.Style()
        style.configure("Treeview", rowheight=row_height, font=FONTS.body())
        style.configure("Treeview.Heading", font=FONTS.small(bold=True))

        # Update ALL tk default fonts so every widget picks up the change
        for font_name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            try:
                f = tkfont.nametofont(font_name)
                f.configure(family=FONTS.family, size=FONTS.size_body)
            except Exception:
                pass
        try:
            tkfont.nametofont("TkHeadingFont").configure(
                family=FONTS.family, size=FONTS.size_small, weight="bold"
            )
        except Exception:
            pass

        # Force all widgets to redraw
        if self.root:
            self.root.update_idletasks()

        self._set_status(f"Zoom: {self.zoom_level}%")
