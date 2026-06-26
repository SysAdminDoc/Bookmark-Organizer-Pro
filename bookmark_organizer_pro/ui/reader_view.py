"""Desktop reader dialog with highlight and note editing."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List

from bookmark_organizer_pro.i18n import _
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.reader_annotations import (
    HIGHLIGHT_COLORS,
    ReaderAnnotationStore,
    ReaderHighlight,
    export_bookmark_highlights,
    read_extracted_text,
)

from .foundation import FONTS, readable_text_on
from .widgets import get_theme


def text_index_offset(text_widget: tk.Text, index: str) -> int:
    """Return the zero-based character offset for a Tk text index."""
    count = text_widget.count("1.0", index, "chars")
    return int(count[0]) if count else 0


class ReaderViewDialog(tk.Toplevel):
    """Read extracted bookmark text and manage persisted highlights."""

    def __init__(self, parent, bookmark: Bookmark, store: ReaderAnnotationStore | None = None):
        theme = get_theme()
        super().__init__(parent)
        self.bookmark = bookmark
        self.store = store or ReaderAnnotationStore()
        self.text_content = read_extracted_text(bookmark)
        self.highlight_ids: List[str] = []

        self.title(_("Reader — {title}").format(title=bookmark.title))
        self.geometry("920x700")
        self.minsize(720, 520)
        self.configure(bg=theme.bg_primary)
        self.transient(parent)

        self._build()
        self._load_highlights()
        self.bind("<Escape>", lambda _event: self.destroy())
        self.after(50, self.text.focus_set)

    def _build(self) -> None:
        theme = get_theme()

        header = tk.Frame(self, bg=theme.bg_secondary)
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text=self.bookmark.title or self.bookmark.url,
            bg=theme.bg_secondary,
            fg=theme.text_primary,
            font=FONTS.header(bold=True),
            anchor="w",
            padx=16,
            pady=12,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(
            header,
            text=_("Export"),
            command=self._export_highlights,
            bg=theme.accent_primary,
            fg=readable_text_on(theme.accent_primary),
            activebackground=theme.accent_primary,
            activeforeground=readable_text_on(theme.accent_primary),
            relief=tk.FLAT,
            padx=12,
            pady=6,
            cursor="hand2",
        ).pack(side=tk.RIGHT, padx=(0, 12), pady=8)

        body = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg=theme.bg_primary, sashwidth=4)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        text_frame = tk.Frame(body, bg=theme.bg_primary)
        self.text = tk.Text(
            text_frame,
            wrap=tk.WORD,
            bg=theme.bg_primary,
            fg=theme.text_primary,
            insertbackground=theme.text_primary,
            selectbackground=theme.selection,
            selectforeground=theme.text_primary,
            relief=tk.FLAT,
            padx=14,
            pady=14,
            font=FONTS.body(),
        )
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.insert("1.0", self.text_content or _("No extracted text available."))
        self.text.configure(state=tk.DISABLED)
        body.add(text_frame, minsize=420)

        side = tk.Frame(body, bg=theme.bg_secondary, padx=12, pady=12)
        body.add(side, minsize=260)

        tk.Label(
            side,
            text=_("Highlights"),
            bg=theme.bg_secondary,
            fg=theme.text_primary,
            font=FONTS.body(bold=True),
            anchor="w",
        ).pack(fill=tk.X)

        self.highlight_list = tk.Listbox(
            side,
            bg=theme.bg_primary,
            fg=theme.text_primary,
            selectbackground=theme.selection,
            selectforeground=theme.text_primary,
            relief=tk.FLAT,
            height=10,
            font=FONTS.small(),
        )
        self.highlight_list.pack(fill=tk.BOTH, expand=True, pady=(8, 10))
        self.highlight_list.bind("<<ListboxSelect>>", self._on_highlight_selected)

        controls = tk.Frame(side, bg=theme.bg_secondary)
        controls.pack(fill=tk.X)
        self.color_var = tk.StringVar(value="yellow")
        self.color_combo = ttk.Combobox(
            controls,
            textvariable=self.color_var,
            values=list(HIGHLIGHT_COLORS.keys()),
            width=10,
            state="readonly",
        )
        self.color_combo.pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(
            controls,
            text=_("Add"),
            command=self._add_highlight_from_selection,
            bg=theme.accent_success,
            fg=readable_text_on(theme.accent_success),
            relief=tk.FLAT,
            padx=10,
            pady=4,
            cursor="hand2",
        ).pack(side=tk.LEFT)

        tk.Label(
            side,
            text=_("Note"),
            bg=theme.bg_secondary,
            fg=theme.text_secondary,
            font=FONTS.small(),
            anchor="w",
        ).pack(fill=tk.X, pady=(12, 4))
        self.note_text = tk.Text(
            side,
            height=5,
            wrap=tk.WORD,
            bg=theme.bg_primary,
            fg=theme.text_primary,
            relief=tk.FLAT,
            font=FONTS.small(),
            padx=8,
            pady=8,
        )
        self.note_text.pack(fill=tk.X)

        note_actions = tk.Frame(side, bg=theme.bg_secondary)
        note_actions.pack(fill=tk.X, pady=(8, 0))
        tk.Button(
            note_actions,
            text=_("Save"),
            command=self._save_selected_note,
            bg=theme.accent_primary,
            fg=readable_text_on(theme.accent_primary),
            relief=tk.FLAT,
            padx=10,
            pady=4,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(
            note_actions,
            text=_("Delete"),
            command=self._delete_selected_highlight,
            bg=theme.accent_error,
            fg=readable_text_on(theme.accent_error),
            relief=tk.FLAT,
            padx=10,
            pady=4,
            cursor="hand2",
        ).pack(side=tk.LEFT)

        self.status = tk.Label(
            side,
            text="",
            bg=theme.bg_secondary,
            fg=theme.text_muted,
            font=FONTS.small(),
            anchor="w",
        )
        self.status.pack(fill=tk.X, pady=(12, 0))

    def _load_highlights(self) -> None:
        self._clear_highlight_tags()
        self.highlight_list.delete(0, tk.END)
        self.highlight_ids = []
        for highlight in self.store.list_for_bookmark(int(self.bookmark.id)):
            self._apply_text_tag(highlight)
            preview = " ".join(highlight.text.split())[:64]
            self.highlight_list.insert(tk.END, f"{highlight.color} {highlight.char_start}-{highlight.char_end}: {preview}")
            self.highlight_ids.append(highlight.id)
        self.status.configure(text=_("{count} saved").format(count=len(self.highlight_ids)))

    def _clear_highlight_tags(self) -> None:
        self.text.configure(state=tk.NORMAL)
        for tag in self.text.tag_names():
            if tag.startswith("reader-highlight-"):
                self.text.tag_delete(tag)
        self.text.configure(state=tk.DISABLED)

    def _apply_text_tag(self, highlight: ReaderHighlight) -> None:
        theme = get_theme()
        tag = f"reader-highlight-{highlight.id}"
        start = f"1.0 + {highlight.char_start} chars"
        end = f"1.0 + {highlight.char_end} chars"
        bg = HIGHLIGHT_COLORS.get(highlight.color, HIGHLIGHT_COLORS["yellow"])
        self.text.configure(state=tk.NORMAL)
        self.text.tag_add(tag, start, end)
        self.text.tag_configure(
            tag,
            background=bg,
            foreground=readable_text_on(bg),
            selectbackground=theme.selection,
        )
        self.text.configure(state=tk.DISABLED)

    def _selected_highlight_id(self) -> str | None:
        selection = self.highlight_list.curselection()
        if not selection:
            return None
        index = int(selection[0])
        return self.highlight_ids[index] if index < len(self.highlight_ids) else None

    def _on_highlight_selected(self, _event=None) -> None:
        highlight_id = self._selected_highlight_id()
        if not highlight_id:
            return
        highlight = self.store.get(highlight_id)
        if not highlight:
            return
        self.note_text.delete("1.0", tk.END)
        self.note_text.insert("1.0", highlight.note)
        self.text.see(f"1.0 + {highlight.char_start} chars")

    def _add_highlight_from_selection(self) -> None:
        try:
            start_index, end_index = self.text.tag_ranges(tk.SEL)
        except ValueError:
            messagebox.showinfo(_("Reader"), _("Select text first."), parent=self)
            return
        if not start_index or not end_index:
            messagebox.showinfo(_("Reader"), _("Select text first."), parent=self)
            return
        start = text_index_offset(self.text, str(start_index))
        end = text_index_offset(self.text, str(end_index))
        note = self.note_text.get("1.0", tk.END).strip()
        try:
            self.store.add_from_text(
                int(self.bookmark.id),
                self.text_content,
                start,
                end,
                color=self.color_var.get(),
                note=note,
            )
        except ValueError as exc:
            messagebox.showerror("Reader", str(exc), parent=self)
            return
        self.note_text.delete("1.0", tk.END)
        self._load_highlights()

    def _save_selected_note(self) -> None:
        highlight_id = self._selected_highlight_id()
        if not highlight_id:
            messagebox.showinfo(_("Reader"), _("Select a highlight first."), parent=self)
            return
        self.store.set_note(highlight_id, self.note_text.get("1.0", tk.END).strip())
        self._load_highlights()

    def _delete_selected_highlight(self) -> None:
        highlight_id = self._selected_highlight_id()
        if not highlight_id:
            messagebox.showinfo(_("Reader"), _("Select a highlight first."), parent=self)
            return
        self.store.delete(highlight_id)
        self.note_text.delete("1.0", tk.END)
        self._load_highlights()

    def _export_highlights(self) -> None:
        output_dir = filedialog.askdirectory(parent=self, title=_("Export Reader Highlights"))
        if not output_dir:
            return
        path = export_bookmark_highlights(
            self.bookmark,
            self.store.list_for_bookmark(int(self.bookmark.id)),
            output_dir=output_dir,
        )
        self.status.configure(text=_("Exported {name}").format(name=path.name))
