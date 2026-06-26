"""Zoom and font-scaling actions for the app coordinator."""

from __future__ import annotations

import tkinter as tk
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
        if event.state & 0x4:
            if event.delta > 0:
                self._zoom_in()
            else:
                self._zoom_out()
            return "break"

    def _apply_zoom(self):
        """Apply zoom to ALL UI elements — fonts, spacing, widget sizes."""
        if self.zoom_label:
            self.zoom_label.configure(text=f"{self.zoom_level}%")

        scale = self.zoom_level / 100.0

        # Scale the global FONTS config (base sizes at 100%)
        FONTS.size_title = max(12, int(18 * scale))
        FONTS.size_subtitle = max(10, int(14 * scale))
        FONTS.size_header = max(10, int(13 * scale))
        FONTS.size_body = max(8, int(11 * scale))
        FONTS.size_small = max(7, int(10 * scale))
        FONTS.size_tiny = max(7, int(9 * scale))

        # Scale treeview
        row_height = max(24, min(84, int(DesignTokens.TREEVIEW_ROW_HEIGHT * scale)))
        style = ttk.Style()
        style.configure("Treeview", rowheight=row_height, font=FONTS.body())
        style.configure("Treeview.Heading", font=FONTS.small(bold=True))
        if hasattr(getattr(self, "tree", None), "apply_zoom"):
            self.tree.apply_zoom(row_height)

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

        # Scale layout dimensions
        self._rescale_layout(scale)

        # Force all widgets to redraw
        if self.root:
            self.root.update_idletasks()

        self._set_status(f"Zoom: {self.zoom_level}%")

    def _rescale_layout(self, scale: float):
        """Resize header, sidebar, status bar, and padding based on zoom scale."""
        # Header height
        max(60, int(76 * scale))
        for child in self.main_container.winfo_children():
            try:
                if child.winfo_height() and child.cget("height"):
                    pass
            except Exception:
                pass

        # Sidebar width  (clamp 200–400)
        sidebar_w = max(200, min(400, int(256 * scale)))
        for child in self.main_container.winfo_children():
            # content frame holds left/right sidebars
            for sub in child.winfo_children():
                try:
                    if sub.cget("width") and int(sub.cget("width")) >= 200:
                        current_w = int(sub.cget("width"))
                        if 230 <= current_w <= 300:
                            sub.configure(width=sidebar_w)
                except (tk.TclError, ValueError):
                    pass

        # Scale button padding by updating all ModernButton instances recursively
        self._rescale_buttons(self.root, scale)

    def _rescale_buttons(self, widget, scale: float):
        """Walk the widget tree and re-pad any ModernButton."""
        from bookmark_organizer_pro.ui.widget_controls import ModernButton
        try:
            for child in widget.winfo_children():
                if isinstance(child, ModernButton):
                    pad_x = max(6, int(14 * scale))
                    pad_y = max(4, int(7 * scale))
                    child.label.configure(padx=pad_x, pady=pad_y)
                self._rescale_buttons(child, scale)
        except Exception:
            pass
