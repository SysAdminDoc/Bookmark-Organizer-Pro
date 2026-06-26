"""GUI chat panel for conversational RAG over bookmark collections."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from bookmark_organizer_pro.i18n import _

from .foundation import FONTS, DesignTokens, readable_text_on
from .widget_controls import ThemedWidget
from .widget_runtime import get_theme


class ChatPanel(tk.Frame, ThemedWidget):
    """Collapsible sidebar panel for RAG chat over bookmarks.

    Provides a conversation UI backed by CollectionChat.ask().
    """

    def __init__(self, parent, on_ask: Callable[[str], None] = None,
                 on_bookmark_click: Callable[[int], None] = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_dark)
        self._on_ask = on_ask
        self._on_bookmark_click = on_bookmark_click
        self._build(theme)

    def _build(self, theme):
        header = tk.Frame(self, bg=theme.bg_dark)
        header.pack(fill=tk.X, padx=DesignTokens.PANEL_PAD,
                    pady=(DesignTokens.PANEL_PAD, DesignTokens.SPACE_SM))

        tk.Label(
            header, text=_("ASK YOUR LIBRARY"), bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.tiny(bold=True),
        ).pack(side=tk.LEFT)

        self._clear_btn = tk.Label(
            header, text=_("Clear"), bg=theme.bg_dark, fg=theme.text_muted,
            font=FONTS.tiny(), cursor="hand2",
        )
        self._clear_btn.pack(side=tk.RIGHT)
        self._clear_btn.bind("<Button-1>", lambda e: self.clear_conversation())

        self._messages_frame = tk.Frame(self, bg=theme.bg_dark)
        self._messages_frame.pack(fill=tk.BOTH, expand=True,
                                  padx=DesignTokens.PANEL_PAD)

        self._messages_canvas = tk.Canvas(
            self._messages_frame, bg=theme.bg_dark, highlightthickness=0,
        )
        self._messages_scrollbar = ttk.Scrollbar(
            self._messages_frame, orient=tk.VERTICAL,
            command=self._messages_canvas.yview,
        )
        self._messages_inner = tk.Frame(self._messages_canvas, bg=theme.bg_dark)
        self._welcome_frame = None

        self._messages_inner.bind(
            "<Configure>",
            lambda e: self._messages_canvas.configure(
                scrollregion=self._messages_canvas.bbox("all")
            ),
        )
        self._messages_canvas.create_window(
            (0, 0), window=self._messages_inner, anchor="nw",
        )
        self._messages_canvas.configure(yscrollcommand=self._messages_scrollbar.set)
        self._messages_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._messages_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._show_welcome(theme)

        # Bind mousewheel for scrolling
        self._messages_canvas.bind("<Enter>", self._bind_mousewheel)
        self._messages_canvas.bind("<Leave>", self._unbind_mousewheel)

        # Input area
        input_frame = tk.Frame(self, bg=theme.bg_dark)
        input_frame.pack(fill=tk.X, padx=DesignTokens.PANEL_PAD,
                         pady=(DesignTokens.SPACE_SM, DesignTokens.PANEL_PAD))

        self._entry = tk.Entry(
            input_frame, bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0, font=FONTS.body(),
            highlightthickness=1, highlightbackground=theme.border_muted,
            highlightcolor=theme.accent_primary,
        )
        self._entry.pack(fill=tk.X, ipady=8, ipadx=8)
        self._entry.insert(0, _("Ask about your bookmarks..."))
        self._entry.config(fg=theme.text_muted)

        self._entry.bind("<FocusIn>", self._on_focus_in)
        self._entry.bind("<FocusOut>", self._on_focus_out)
        self._entry.bind("<Return>", self._on_submit)

        self._status_label = tk.Label(
            input_frame, text="", bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.tiny(), anchor="w",
        )
        self._status_label.pack(fill=tk.X, pady=(4, 0))

        self._placeholder_active = True

    def _show_welcome(self, theme=None):
        """Render the calm empty state shown before the first question."""
        theme = theme or get_theme()
        if self._welcome_frame and self._welcome_frame.winfo_exists():
            return
        self._welcome_frame = tk.Frame(self._messages_inner, bg=theme.bg_dark)
        self._welcome_frame.pack(fill=tk.X, pady=(4, DesignTokens.SPACE_MD))
        tk.Label(
            self._welcome_frame,
            text=_("Ask about saved links, themes, projects, or old research."),
            bg=theme.bg_dark, fg=theme.text_secondary,
            font=FONTS.small(), wraplength=230, justify=tk.LEFT,
            anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            self._welcome_frame,
            text=_("Answers cite matching bookmarks when the local search index is available."),
            bg=theme.bg_dark, fg=theme.text_muted,
            font=FONTS.tiny(), wraplength=230, justify=tk.LEFT,
            anchor="w",
        ).pack(fill=tk.X, pady=(6, 0))

    def _hide_welcome(self):
        if self._welcome_frame and self._welcome_frame.winfo_exists():
            self._welcome_frame.destroy()
        self._welcome_frame = None

    def _bind_mousewheel(self, event):
        self._messages_canvas.bind(
            "<MouseWheel>",
            lambda e: self._messages_canvas.yview_scroll(
                int(-1 * (e.delta / 120)), "units"
            ),
        )

    def _unbind_mousewheel(self, event):
        self._messages_canvas.unbind("<MouseWheel>")

    def _on_focus_in(self, event):
        theme = get_theme()
        self._entry.configure(highlightbackground=theme.accent_primary)
        if self._placeholder_active:
            self._entry.delete(0, tk.END)
            self._entry.config(fg=theme.text_primary)
            self._placeholder_active = False

    def _on_focus_out(self, event):
        theme = get_theme()
        self._entry.configure(highlightbackground=theme.border_muted)
        if not self._entry.get().strip():
            self._entry.insert(0, _("Ask about your bookmarks..."))
            self._entry.config(fg=theme.text_muted)
            self._placeholder_active = True

    def _on_submit(self, event):
        question = self._entry.get().strip()
        if not question or self._placeholder_active:
            return "break"
        self._entry.delete(0, tk.END)
        self._add_message("user", question)
        self._status_label.config(text=_("Searching your library..."), fg=get_theme().accent_primary)
        self._entry.config(state=tk.DISABLED)
        if self._on_ask:
            self._on_ask(question)
        return "break"

    def _add_message(self, role: str, text: str, sources=None):
        theme = get_theme()
        is_user = role == "user"
        self._hide_welcome()

        bubble = tk.Frame(
            self._messages_inner,
            bg=theme.accent_primary if is_user else theme.bg_secondary,
            padx=10, pady=8,
        )
        bubble.pack(
            fill=tk.X, pady=(0, DesignTokens.SPACE_SM),
            anchor="e" if is_user else "w",
        )

        fg = readable_text_on(theme.accent_primary) if is_user else theme.text_primary
        tk.Label(
            bubble, text=_("You") if is_user else _("BOP"),
            bg=bubble["bg"], fg=fg, font=FONTS.tiny(bold=True),
            anchor="w",
        ).pack(fill=tk.X)

        msg_label = tk.Label(
            bubble, text=text, bg=bubble["bg"], fg=fg,
            font=FONTS.body(), wraplength=220, justify=tk.LEFT, anchor="w",
        )
        msg_label.pack(fill=tk.X, pady=(2, 0))

        if sources:
            for src in sources[:5]:
                bm_id = src.get("bookmark_id")
                title = src.get("title", src.get("url", ""))[:60]
                src_label = tk.Label(
                    bubble, text=f"  [{title}]",
                    bg=bubble["bg"],
                    fg=theme.accent_primary if not is_user else readable_text_on(theme.accent_primary),
                    font=FONTS.tiny(), cursor="hand2", anchor="w",
                )
                src_label.pack(fill=tk.X)
                if bm_id and self._on_bookmark_click:
                    src_label.bind(
                        "<Button-1>",
                        lambda e, bid=bm_id: self._on_bookmark_click(bid),
                    )

        self._messages_canvas.update_idletasks()
        self._messages_canvas.yview_moveto(1.0)

    def show_answer(self, answer: str, sources: list = None):
        self._entry.config(state=tk.NORMAL)
        self._status_label.config(text="", fg=get_theme().text_muted)
        self._add_message("assistant", answer, sources=sources)

    def show_error(self, message: str):
        self._entry.config(state=tk.NORMAL)
        self._status_label.config(text=message, fg=get_theme().accent_error)

    def clear_conversation(self):
        for widget in self._messages_inner.winfo_children():
            widget.destroy()
        self._status_label.config(text="")
        self._show_welcome()
