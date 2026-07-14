"""GUI chat panel for conversational RAG over bookmark collections."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from bookmark_organizer_pro.i18n import _, format_message

from .foundation import FONTS, DesignTokens, readable_text_on
from .tk_interactions import bind_scoped_mousewheel, make_keyboard_activatable
from .widget_controls import ModernButton, ThemedWidget
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
        self._history = []
        self._build(theme)

    def _build(self, theme):
        header = tk.Frame(self, bg=theme.bg_dark)
        header.pack(fill=tk.X, padx=DesignTokens.PANEL_PAD,
                    pady=(10, 4))

        tk.Label(
            header, text=_("Ask your library"), bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.subtitle(bold=True),
        ).pack(side=tk.LEFT)

        self._clear_btn = tk.Label(
            header, text=_("Clear"), bg=theme.bg_dark, fg=theme.text_muted,
            font=FONTS.tiny(), cursor="hand2",
        )
        self._clear_btn.pack(side=tk.RIGHT)
        make_keyboard_activatable(self._clear_btn, self.clear_conversation)
        self._clear_btn.pack_forget()

        self._messages_frame = tk.Frame(self, bg=theme.bg_dark, height=54)
        self._messages_frame.pack(fill=tk.X, padx=DesignTokens.PANEL_PAD)
        self._messages_frame.pack_propagate(False)

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
        self._messages_window = self._messages_canvas.create_window(
            (0, 0), window=self._messages_inner, anchor="nw",
        )
        self._messages_canvas.bind(
            "<Configure>",
            lambda event: self._messages_canvas.itemconfigure(
                self._messages_window, width=max(1, event.width)
            ),
        )
        self._messages_canvas.configure(yscrollcommand=self._messages_scrollbar.set)
        self._messages_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._show_welcome(theme)

        self._wheel_binding = bind_scoped_mousewheel(
            self._messages_canvas,
            lambda units, _event: self._messages_canvas.yview_scroll(units, "units"),
        )

        # Input area
        input_frame = tk.Frame(self, bg=theme.bg_dark)
        input_frame.pack(fill=tk.X, padx=DesignTokens.PANEL_PAD,
                         pady=(6, 10))

        input_row = tk.Frame(input_frame, bg=theme.border_muted)
        input_row.pack(fill=tk.X)

        self._entry = tk.Entry(
            input_row, bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0, font=FONTS.body(),
            highlightthickness=1, highlightbackground=theme.border_muted,
            highlightcolor=theme.accent_primary,
        )
        self._entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, ipadx=8)
        self._entry.insert(0, _("Type your question..."))
        self._entry.config(fg=theme.text_muted)

        self._entry.bind("<FocusIn>", self._on_focus_in)
        self._entry.bind("<FocusOut>", self._on_focus_out)
        self._entry.bind("<Return>", self._on_submit)

        ModernButton(
            input_row, text=_("Ask"), command=self._on_submit,
            padx=9, pady=7, tooltip=_("Ask the local assistant"),
        ).pack(side=tk.RIGHT)

        suggestions = tk.Frame(input_frame, bg=theme.bg_dark)
        suggestions.pack(fill=tk.X, pady=(8, 0))
        for text, question in (
            (_("Duplicates"), _("Which bookmarks look like duplicates?")),
            (_("Untagged"), _("Which bookmarks still need tags?")),
            (_("Rediscover"), _("What useful bookmark should I revisit?")),
        ):
            ModernButton(
                suggestions, text=text,
                command=lambda prompt=question: self._submit_prompt(prompt),
                font=FONTS.tiny(), padx=6, pady=5,
            ).pack(side=tk.LEFT, padx=(0, 5))

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
            font=FONTS.small(), wraplength=300, justify=tk.LEFT,
            anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            self._welcome_frame,
            text=_("Answers cite matching bookmarks when the local search index is available."),
            bg=theme.bg_dark, fg=theme.text_muted,
            font=FONTS.tiny(), wraplength=300, justify=tk.LEFT,
            anchor="w",
        ).pack(fill=tk.X, pady=(6, 0))

    def _hide_welcome(self):
        if self._welcome_frame and self._welcome_frame.winfo_exists():
            self._welcome_frame.destroy()
        self._welcome_frame = None

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
            self._entry.insert(0, _("Type your question..."))
            self._entry.config(fg=theme.text_muted)
            self._placeholder_active = True

    def _submit_prompt(self, question: str):
        if str(self._entry.cget("state")) == str(tk.DISABLED):
            return
        self._entry.delete(0, tk.END)
        self._entry.insert(0, question)
        self._entry.config(fg=get_theme().text_primary)
        self._placeholder_active = False
        self._on_submit()

    def _on_submit(self, event=None):
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

    def _add_message(self, role: str, text: str, sources=None, *, record: bool = True):
        theme = get_theme()
        is_user = role == "user"
        if record:
            self._history.append((role, text, list(sources or [])))
        self._hide_welcome()
        if not self._clear_btn.winfo_ismapped():
            self._clear_btn.pack(side=tk.RIGHT)
        self._messages_frame.configure(height=184)
        if not self._messages_scrollbar.winfo_ismapped():
            self._messages_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

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
                    bubble, text=format_message('  [{value_0}]', value_0=title),
                    bg=bubble["bg"],
                    fg=theme.accent_primary if not is_user else readable_text_on(theme.accent_primary),
                    font=FONTS.tiny(), cursor="hand2", anchor="w",
                )
                src_label.pack(fill=tk.X)
                if bm_id and self._on_bookmark_click:
                    make_keyboard_activatable(
                        src_label,
                        lambda bid=bm_id: self._on_bookmark_click(bid),
                        accessible_name=_("Open cited bookmark: {title}").format(title=title),
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
        self._history.clear()
        self._clear_btn.pack_forget()
        self._messages_frame.configure(height=54)
        self._messages_scrollbar.pack_forget()
        self._show_welcome()

    def export_state(self):
        """Return portable conversation state for live theme rebuilds."""
        entry_text = "" if self._placeholder_active else self._entry.get()
        return {
            "history": list(self._history),
            "status": self._status_label.cget("text"),
            "entry_text": entry_text,
            "entry_state": str(self._entry.cget("state")),
        }

    def restore_state(self, state):
        """Restore conversation state after a live theme rebuild."""
        if not isinstance(state, dict):
            return
        for widget in self._messages_inner.winfo_children():
            widget.destroy()
        self._history.clear()
        history = list(state.get("history") or [])
        if history:
            for role, text, sources in history:
                self._add_message(role, text, sources=sources, record=True)
        else:
            self._show_welcome()
        self._status_label.config(text=str(state.get("status") or ""))
        entry_text = str(state.get("entry_text") or "")
        if entry_text:
            self._entry.delete(0, tk.END)
            self._entry.insert(0, entry_text)
            self._entry.config(fg=get_theme().text_primary)
            self._placeholder_active = False
        if state.get("entry_state") == str(tk.DISABLED):
            self._entry.config(state=tk.DISABLED)
