"""Feedback, preview, and empty-state widgets for the desktop UI."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from typing import Optional

from bookmark_organizer_pro.i18n import _
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
        self.tooltip.configure(bg=theme.border_muted)
        try:
            self.tooltip.attributes("-topmost", True)
            self.tooltip.attributes("-alpha", 0.97)
        except Exception:
            pass

        x = event.x_root + 15
        y = event.y_root + 10

        frame = tk.Frame(self.tooltip, bg=theme.bg_dark, padx=12, pady=10)
        frame.pack(padx=1, pady=1)
        
        # Title
        title = bookmark.title[:60] + "..." if len(bookmark.title) > 63 else bookmark.title
        tk.Label(
            frame, text=title, bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.body(bold=True),
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
    """First-run workspace that teaches the product without a tour."""

    def __init__(self, parent, on_import=None, on_add=None,
                 on_organize=None, on_search=None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_primary)
        self._on_import = on_import
        self._on_add = on_add
        self._on_organize = on_organize
        self._on_search = on_search
        self._compact_layout = False
        self._build(theme)
        self.bind("<Configure>", self._on_viewport_configure, add="+")

    def _build(self, theme):
        stage = tk.Frame(self, bg=theme.bg_primary)
        stage.pack(fill=tk.BOTH, expand=True, padx=48, pady=(28, 24))
        self._stage = stage

        self._eyebrow = tk.Label(
            stage, text=_("YOUR LIBRARY"), bg=theme.bg_primary,
            fg=theme.accent_primary, font=FONTS.tiny(bold=True)
        )
        self._eyebrow.pack(anchor="w", pady=(0, 13))

        tk.Label(
            stage, text=_("Build a library worth returning to"),
            bg=theme.bg_primary, fg=theme.text_primary,
            font=FONTS.display(), justify=tk.LEFT
        ).pack(anchor="w")

        self._intro = tk.Label(
            stage,
            text=(
                "Import your existing bookmarks or add new ones. We'll help you clean up, "
                "organize, and rediscover what matters."
            ),
            bg=theme.bg_primary, fg=theme.text_secondary,
            font=FONTS.body(), justify=tk.LEFT, wraplength=690
        )
        self._intro.pack(anchor="w", pady=(15, 24))

        btn_row = tk.Frame(stage, bg=theme.bg_primary)
        btn_row.pack(anchor="w")

        import_btn = ModernButton(
            btn_row, text=_("Import bookmarks"), icon="⇩",
            style="primary", command=self._on_import,
            font=FONTS.body(bold=True), padx=22, pady=11,
            tooltip=_("Import from a browser, service, or bookmark file"),
        )
        import_btn.pack(side=tk.LEFT, padx=(0, 10))

        add_btn = ModernButton(
            btn_row, text=_("Add one link"), icon="∞",
            command=self._on_add,
            font=FONTS.body(), padx=20, pady=11,
            tooltip=_("Save one bookmark manually"),
        )
        add_btn.pack(side=tk.LEFT)

        self._divider = tk.Frame(stage, bg=theme.border_muted, height=1)
        self._divider.pack(fill=tk.X, pady=(24, 20))

        self._quick_heading = tk.Label(
            stage, text=_("Quick start"), bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.subtitle(bold=True),
        )
        self._quick_heading.pack(anchor="w", pady=(0, 12))

        cards = tk.Frame(stage, bg=theme.bg_primary)
        cards.pack(fill=tk.X)
        self._cards = cards
        for column in range(3):
            cards.grid_columnconfigure(column, weight=1, uniform="quick-start")

        card_specs = (
            ("⇩", "Capture", "Import from your browser or file to bring everything into one place.",
             "Import bookmarks  →", theme.accent_primary, self._on_import),
            ("▦", "Organize", "Find duplicates, fix tags, and group bookmarks into collections.",
             "Start organizing  →", theme.accent_secondary, self._on_organize),
            ("⌕", "Rediscover", "Search with filters, tags, and saved views that surface what you need.",
             "Go to search  →", theme.accent_purple, self._on_search),
        )
        for column, spec in enumerate(card_specs):
            self._create_quick_start_card(cards, theme, column, *spec)

        self._recent_heading = tk.Label(
            stage, text=_("Recent activity"), bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.subtitle(bold=True),
        )
        self._recent_heading.pack(anchor="w", pady=(24, 10))

        activity = tk.Frame(
            stage, bg=theme.bg_dark,
            highlightbackground=theme.border_muted, highlightthickness=1,
        )
        activity.pack(fill=tk.X)
        self._recent_activity = activity
        tk.Label(
            activity, text="↻", bg=theme.bg_tertiary,
            fg=theme.text_secondary, font=FONTS.title(), width=3, pady=8,
        ).pack(side=tk.LEFT, padx=16, pady=14)
        activity_copy = tk.Frame(activity, bg=theme.bg_dark)
        activity_copy.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=14)
        tk.Label(
            activity_copy, text=_("No recent activity yet"), bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.body(bold=True), anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            activity_copy, text=_("Your imports, edits, and searches will appear here."),
            bg=theme.bg_dark, fg=theme.text_secondary,
            font=FONTS.small(), anchor="w",
        ).pack(fill=tk.X, pady=(3, 0))

    def _on_viewport_configure(self, event) -> None:
        """Compact first-run spacing when the root is at laptop height."""
        compact = int(event.height) < 680
        if compact == self._compact_layout:
            return
        self._compact_layout = compact
        if compact:
            self._stage.pack_configure(padx=32, pady=(12, 12))
            self._eyebrow.pack_configure(pady=(0, 6))
            self._intro.pack_configure(pady=(8, 12))
            self._divider.pack_configure(pady=(12, 10))
            self._quick_heading.pack_configure(pady=(0, 6))
            self._recent_heading.pack_forget()
            self._recent_activity.pack_forget()
            return
        self._stage.pack_configure(padx=48, pady=(28, 24))
        self._eyebrow.pack_configure(pady=(0, 13))
        self._intro.pack_configure(pady=(15, 24))
        self._divider.pack_configure(pady=(24, 20))
        self._quick_heading.pack_configure(pady=(0, 12))
        self._recent_heading.pack(anchor="w", pady=(24, 10), after=self._cards)
        self._recent_activity.pack(fill=tk.X, after=self._recent_heading)

    @staticmethod
    def _create_quick_start_card(parent, theme, column, icon, title, body,
                                 action_text, accent, command):
        card = tk.Frame(
            parent, bg=theme.bg_card, cursor="hand2" if command else "arrow",
            highlightbackground=theme.card_border, highlightthickness=1,
        )
        card.grid(
            row=0, column=column, sticky="nsew",
            padx=(0 if column == 0 else 5, 0 if column == 2 else 5),
        )
        tk.Label(
            card, text=icon, bg=theme.bg_card, fg=accent,
            font=FONTS.custom(26), anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(15, 8))
        tk.Label(
            card, text=title, bg=theme.bg_card, fg=theme.text_primary,
            font=FONTS.subtitle(bold=True), anchor="w",
        ).pack(fill=tk.X, padx=16)
        tk.Label(
            card, text=body, bg=theme.bg_card, fg=theme.text_secondary,
            font=FONTS.small(), anchor="nw", justify=tk.LEFT, wraplength=205,
        ).pack(fill=tk.X, expand=True, padx=16, pady=(6, 10))
        action = tk.Label(
            card, text=action_text, bg=theme.bg_card, fg=accent,
            font=FONTS.small(bold=True), anchor="w",
            cursor="hand2" if command else "arrow",
        )
        action.pack(fill=tk.X, padx=16, pady=(0, 14))
        if command:
            make_keyboard_activatable(card, command)
            for child in card.winfo_children():
                child.configure(cursor="hand2")
                child.bind("<Button-1>", lambda _event, callback=command: callback())



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
            center, text=_("No bookmarks match this view"),
            bg=theme.bg_primary, fg=theme.text_primary,
            font=FONTS.title(bold=True)
        ).pack(pady=(0, 8))

        tk.Label(
            center,
            text=_("Broaden the search, choose another filter, or reset the view to return to the full library."),
            bg=theme.bg_primary, fg=theme.text_secondary,
            font=FONTS.body(), justify="center", wraplength=420
        ).pack(pady=(0, 24))

        btn_row = tk.Frame(center, bg=theme.bg_primary)
        btn_row.pack()

        ModernButton(
            btn_row, text=_("Reset view"), style="primary",
            command=self._on_clear, font=FONTS.body(bold=True),
            padx=20, pady=10
        ).pack(side=tk.LEFT, padx=6)

        ModernButton(
            btn_row, text=_("Add bookmark"),
            command=self._on_add, font=FONTS.body(),
            padx=20, pady=10
        ).pack(side=tk.LEFT, padx=6)

        tk.Label(
            center,
            text=_("Try domain:example.com, is:pinned, is:broken, or #tag in search."),
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
            "warning": (theme.accent_warning, readable_text_on(theme.accent_warning), "!"),
            "info": (theme.accent_primary, readable_text_on(theme.accent_primary), "i"),
        }
        bg, fg, icon = styles.get(style, styles["info"])

        frame = tk.Frame(self, bg=theme.border_muted, padx=1, pady=1)
        frame.pack(fill=tk.BOTH, expand=True)

        inner = tk.Frame(frame, bg=theme.bg_card)
        inner.pack(fill=tk.BOTH, expand=True)

        # Accent bar (3px left edge)
        tk.Frame(inner, bg=bg, width=3).pack(side=tk.LEFT, fill=tk.Y)

        # Icon
        tk.Label(
            inner, text=icon, bg=theme.bg_card, fg=bg,
            font=FONTS.body(bold=True), padx=10, pady=10
        ).pack(side=tk.LEFT)

        # Message
        tk.Label(
            inner, text=message, bg=theme.bg_card,
            fg=theme.text_primary, font=FONTS.body(),
            pady=10, wraplength=340, justify="left"
        ).pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 14))

        close_lbl = tk.Label(
            inner, text="✕", bg=theme.bg_card,
            fg=theme.text_muted, font=FONTS.small(),
            cursor="hand2", padx=8
        )
        close_lbl.pack(side=tk.RIGHT, fill=tk.Y)
        close_lbl.bind("<Enter>", lambda e: close_lbl.configure(fg=theme.text_primary))
        close_lbl.bind("<Leave>", lambda e: close_lbl.configure(fg=theme.text_muted))
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
        self._reposition_toasts()

    @classmethod
    def _reposition_toasts(cls):
        """Keep visible toasts neatly stacked after one closes."""
        visible = [toast for toast in cls._active_toasts if toast.winfo_exists()]
        offset_y = 0
        for toast in visible:
            try:
                parent = toast.master
                parent.update_idletasks()
                width = min(toast.winfo_reqwidth(), 420)
                height = toast.winfo_height() or toast.winfo_reqheight()
                x = parent.winfo_rootx() + parent.winfo_width() - width - 20
                y = parent.winfo_rooty() + 80 + offset_y
                toast.geometry(f"{width}x{height}+{x}+{y}")
                offset_y += height + 6
            except Exception:
                continue

    @classmethod
    def show(cls, parent, message: str, style: str = "info", duration: int = 3500):
        """Convenience method to show a toast."""
        return cls(parent, message, style, duration)
