"""Feedback, preview, and empty-state widgets for the desktop UI."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from typing import Optional

from bookmark_organizer_pro.models import Bookmark

from .foundation import FONTS, readable_text_on
from .tk_interactions import make_keyboard_activatable
from .widgets import ModernButton, get_theme


# =============================================================================
# Hover Preview (Tooltip with page info)
# =============================================================================
class HoverPreview:
    """Show preview tooltip on bookmark hover"""
    
    def __init__(self, parent: tk.Widget):
        self.parent = parent
        self.tooltip: Optional[tk.Toplevel] = None
        self._after_id = None
        self._delay = 500  # ms before showing tooltip
    
    def show(self, event, bookmark: Bookmark):
        """Schedule showing the preview"""
        self.hide()
        self._after_id = self.parent.after(
            self._delay, 
            lambda: self._create_tooltip(event, bookmark)
        )
    
    def _create_tooltip(self, event, bookmark: Bookmark):
        """Create and show the tooltip"""
        theme = get_theme()
        
        self.tooltip = tk.Toplevel(self.parent)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.configure(bg=theme.bg_dark)
        
        # Position near mouse
        x = event.x_root + 15
        y = event.y_root + 10
        
        # Main frame
        frame = tk.Frame(self.tooltip, bg=theme.bg_dark, padx=12, pady=10)
        frame.pack()
        
        # Title
        title = bookmark.title[:60] + "..." if len(bookmark.title) > 63 else bookmark.title
        tk.Label(
            frame, text=title, bg=theme.bg_dark,
            fg=theme.text_primary, font=("Segoe UI", 10, "bold"),
            wraplength=300, justify=tk.LEFT
        ).pack(anchor="w")
        
        # URL
        tk.Label(
            frame, text=bookmark.url[:50] + "..." if len(bookmark.url) > 53 else bookmark.url,
            bg=theme.bg_dark, fg=theme.text_link, font=FONTS.small()
        ).pack(anchor="w", pady=(5, 0))
        
        # Category and tags
        meta = f"📂 {bookmark.category}"
        if bookmark.tags:
            meta += f"  🏷️ {', '.join(bookmark.tags[:3])}"
        
        tk.Label(
            frame, text=meta, bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.small()
        ).pack(anchor="w", pady=(5, 0))
        
        # Notes preview if available
        if bookmark.notes:
            notes_preview = bookmark.notes[:100] + "..." if len(bookmark.notes) > 100 else bookmark.notes
            tk.Label(
                frame, text=notes_preview, bg=theme.bg_dark,
                fg=theme.text_secondary, font=FONTS.small(),
                wraplength=280, justify=tk.LEFT
            ).pack(anchor="w", pady=(8, 0))
        
        # Stats
        stats_parts = []
        if bookmark.visit_count > 0:
            stats_parts.append(f"👁️ {bookmark.visit_count} visits")
        if bookmark.created_at:
            try:
                created = datetime.fromisoformat(bookmark.created_at.replace('Z', '+00:00'))
                stats_parts.append(f"📅 Added {created.strftime('%Y-%m-%d')}")
            except Exception:
                pass
        
        if stats_parts:
            tk.Label(
                frame, text="  •  ".join(stats_parts), bg=theme.bg_dark,
                fg=theme.text_muted, font=FONTS.tiny()
            ).pack(anchor="w", pady=(5, 0))
        
        # Position tooltip
        self.tooltip.geometry(f"+{x}+{y}")
    
    def hide(self):
        """Hide the tooltip"""
        if self._after_id:
            self.parent.after_cancel(self._after_id)
            self._after_id = None
        
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None


# =============================================================================
# EMPTY STATE - Shown when no bookmarks exist
# =============================================================================
class EmptyState(tk.Frame):
    """First-run empty state with clear, calm next actions."""

    def __init__(self, parent, on_import=None, on_add=None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_primary)
        self._on_import = on_import
        self._on_add = on_add
        self._build(theme)

    def _build(self, theme):
        stage = tk.Frame(self, bg=theme.bg_primary)
        stage.place(relx=0.5, rely=0.5, relwidth=0.9, relheight=0.78, anchor="center")

        left = tk.Frame(stage, bg=theme.bg_primary)
        left.pack(fill=tk.BOTH, expand=True, padx=(32, 0))

        tk.Label(
            left, text="EMPTY LIBRARY", bg=theme.bg_primary,
            fg=theme.accent_primary, font=FONTS.tiny(bold=True)
        ).pack(anchor="w", pady=(10, 14))

        tk.Label(
            left, text="Start With an Import",
            bg=theme.bg_primary, fg=theme.text_primary,
            font=FONTS.custom(30, bold=True), justify=tk.LEFT
        ).pack(anchor="w")

        tk.Label(
            left,
            text=(
                "Bring in a browser export or add one URL. Then review duplicates, "
                "missing tags, weak categories, and broken links from this workspace."
            ),
            bg=theme.bg_primary, fg=theme.text_secondary,
            font=FONTS.custom(12), justify=tk.LEFT, wraplength=620
        ).pack(anchor="w", pady=(18, 28))

        btn_row = tk.Frame(left, bg=theme.bg_primary)
        btn_row.pack(anchor="w")

        import_btn = ModernButton(
            btn_row, text="Import Bookmarks", icon="↓",
            style="primary", command=self._on_import,
            font=FONTS.body(bold=True), padx=22, pady=11
        )
        import_btn.pack(side=tk.LEFT, padx=(0, 10))

        add_btn = ModernButton(
            btn_row, text="Add URL", icon="+",
            command=self._on_add,
            font=FONTS.body(), padx=20, pady=11
        )
        add_btn.pack(side=tk.LEFT)

        runway = tk.Frame(left, bg=theme.bg_primary)
        runway.pack(fill=tk.X, pady=(34, 0))
        for eyebrow, title, body in [
            ("01", "Import", "HTML, JSON, CSV, OPML, and plain URL lists."),
            ("02", "Review", "Find broken links, duplicates, uncategorized items, and gaps."),
            ("03", "Search", "Use domain:, #tags, pinned filters, and command actions."),
        ]:
            row = tk.Frame(runway, bg=theme.bg_primary)
            row.pack(fill=tk.X, pady=7)
            tk.Label(
                row, text=eyebrow, bg=theme.bg_primary,
                fg=theme.accent_primary, font=FONTS.small(bold=True), width=4, anchor="w"
            ).pack(side=tk.LEFT)
            tk.Frame(row, bg=theme.border, width=1, height=34).pack(side=tk.LEFT, padx=(4, 14))
            copy = tk.Frame(row, bg=theme.bg_primary)
            copy.pack(side=tk.LEFT, fill=tk.X, expand=True)
            tk.Label(
                copy, text=title, bg=theme.bg_primary,
                fg=theme.text_primary, font=FONTS.body(bold=True), anchor="w"
            ).pack(anchor="w")
            tk.Label(
                copy, text=body, bg=theme.bg_primary,
                fg=theme.text_secondary, font=FONTS.small(), anchor="w", justify=tk.LEFT,
                wraplength=440
            ).pack(anchor="w", pady=(2, 0))



class FilteredEmptyState(tk.Frame):
    """Empty state shown when search or filters hide every bookmark."""

    def __init__(self, parent, on_clear=None, on_add=None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_primary)
        self._on_clear = on_clear
        self._on_add = on_add
        self._build(theme)

    def _build(self, theme):
        center = tk.Frame(self, bg=theme.bg_primary)
        center.place(relx=0.5, rely=0.42, anchor="center")

        tk.Label(
            center, text="🔎", bg=theme.bg_primary,
            fg=theme.accent_primary, font=("Segoe UI Emoji", 40)
        ).pack(pady=(0, 14))

        tk.Label(
            center, text="No bookmarks match this view",
            bg=theme.bg_primary, fg=theme.text_primary,
            font=FONTS.custom(18, bold=True)
        ).pack(pady=(0, 8))

        tk.Label(
            center,
            text="Broaden the search, choose another filter, or reset the view to return to the full library.",
            bg=theme.bg_primary, fg=theme.text_secondary,
            font=FONTS.body(), justify="center", wraplength=420
        ).pack(pady=(0, 24))

        btn_row = tk.Frame(center, bg=theme.bg_primary)
        btn_row.pack()

        ModernButton(
            btn_row, text="Reset view", style="primary",
            command=self._on_clear, font=FONTS.body(bold=True),
            padx=20, pady=10
        ).pack(side=tk.LEFT, padx=6)

        ModernButton(
            btn_row, text="Add bookmark",
            command=self._on_add, font=FONTS.body(),
            padx=20, pady=10
        ).pack(side=tk.LEFT, padx=6)

        tk.Label(
            center,
            text="Tip: use domain:example.com, is:pinned, is:broken, or #tag in search.",
            bg=theme.bg_primary, fg=theme.text_muted,
            font=FONTS.small(), wraplength=440, justify="center"
        ).pack(pady=(20, 0))


# =============================================================================
# TOAST NOTIFICATION - Non-blocking feedback
# =============================================================================
class ToastNotification(tk.Toplevel):
    """Elegant non-blocking toast notification that auto-dismisses."""

    _active_toasts: list = []

    def __init__(self, parent, message: str, style: str = "info",
                 duration: int = 3500):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", 0.95)
        except Exception:
            pass

        theme = get_theme()

        # Style config
        styles = {
            "success": (theme.accent_success, readable_text_on(theme.accent_success), "✓"),
            "error": (theme.accent_error, readable_text_on(theme.accent_error), "✕"),
            "warning": (theme.accent_warning, readable_text_on(theme.accent_warning), "⚠"),
            "info": (theme.accent_primary, readable_text_on(theme.accent_primary), "ℹ"),
        }
        bg, fg, icon = styles.get(style, styles["info"])

        # Build toast
        frame = tk.Frame(self, bg=bg, padx=1, pady=1)
        frame.pack(fill=tk.BOTH, expand=True)

        inner = tk.Frame(frame, bg=theme.bg_card)
        inner.pack(fill=tk.BOTH, expand=True)

        # Icon strip
        tk.Label(
            inner, text=icon, bg=bg, fg=fg,
            font=FONTS.custom(12, bold=True), padx=12, pady=10
        ).pack(side=tk.LEFT, fill=tk.Y)

        # Message
        tk.Label(
            inner, text=message, bg=theme.bg_card,
            fg=theme.text_primary, font=FONTS.body(),
            padx=14, pady=10, wraplength=350, justify="left"
        ).pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Close button
        close_lbl = tk.Label(
            inner, text="✕", bg=theme.bg_card,
            fg=theme.text_muted, font=FONTS.small(),
            cursor="hand2", padx=10
        )
        close_lbl.pack(side=tk.RIGHT, fill=tk.Y)
        make_keyboard_activatable(close_lbl, self._dismiss)

        # Position: top-right of parent, stacked below existing toasts
        self.update_idletasks()
        pw = parent.winfo_width()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        tw = min(self.winfo_reqwidth(), 420)
        th = self.winfo_reqheight()

        offset_y = sum(t.winfo_height() + 6 for t in ToastNotification._active_toasts
                       if t.winfo_exists())
        x = px + pw - tw - 20
        y = py + 80 + offset_y
        self.geometry(f"{tw}x{th}+{x}+{y}")

        ToastNotification._active_toasts.append(self)

        # Auto-dismiss
        self._after_id = self.after(duration, self._dismiss)

    def _dismiss(self):
        try:
            self.after_cancel(self._after_id)
        except Exception:
            pass
        if self in ToastNotification._active_toasts:
            ToastNotification._active_toasts.remove(self)
        try:
            self.destroy()
        except Exception:
            pass

    @classmethod
    def show(cls, parent, message: str, style: str = "info", duration: int = 3500):
        """Convenience method to show a toast."""
        return cls(parent, message, style, duration)
