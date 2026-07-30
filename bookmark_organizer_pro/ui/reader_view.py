"""Desktop reader dialog with highlight and note editing."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk
from pathlib import Path
from typing import List

from bookmark_organizer_pro.i18n import _
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.reader_annotations import (
    HIGHLIGHT_COLORS,
    ReaderAnnotationStore,
    ReaderHighlight,
    export_annotations,
    read_extracted_text,
)

from .foundation import FONTS, readable_text_on
from .widget_controls import ModernButton
from .window_geometry import apply_screen_aware_geometry
from .widgets import apply_window_chrome, get_theme


def text_index_offset(text_widget: tk.Text, index: str) -> int:
    """Return the zero-based character offset for a Tk text index."""
    count = text_widget.count("1.0", index, "chars")
    return int(count[0]) if count else 0


def reader_empty_message(bookmark: Bookmark) -> str:
    mime_type = str(bookmark.snapshot_mime_type or "").lower()
    if mime_type == "application/pdf":
        return _(
            "This bookmark has a verified PDF offline copy. Open the offline copy "
            "to read it; highlights require separately extracted text."
        )
    if mime_type.startswith("image/"):
        return _(
            "This bookmark has a verified image offline copy. Open the offline copy "
            "to view it; highlights require separately extracted text."
        )
    return _(
        "No extracted text is available yet.\n\n"
        "Run text extraction, then return here to highlight key passages."
    )


class ReaderViewDialog(tk.Toplevel):
    """Read extracted bookmark text and manage persisted highlights."""

    def __init__(self, parent, bookmark: Bookmark, store: ReaderAnnotationStore | None = None):
        theme = get_theme()
        super().__init__(parent)
        self.bookmark = bookmark
        self.store = store or ReaderAnnotationStore()
        self.text_content = read_extracted_text(bookmark)
        self.highlight_ids: List[str] = []
        self._deleted_highlight: ReaderHighlight | None = None

        self.title(_("Reader — {title}").format(title=bookmark.title))
        apply_screen_aware_geometry(self, 980, 720)
        self.minsize(720, 520)
        self.configure(bg=theme.bg_primary)
        self.transient(parent)
        apply_window_chrome(self)

        self._build()
        self._load_highlights()
        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Control-z>", self._undo_deleted_highlight)
        self.bind("<Command-z>", self._undo_deleted_highlight)
        self.after(50, self.text.focus_set)

    def _build(self) -> None:
        theme = get_theme()

        header = tk.Frame(self, bg=theme.bg_secondary, padx=16, pady=12)
        header.pack(fill=tk.X)
        title_stack = tk.Frame(header, bg=theme.bg_secondary)
        title_stack.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(
            title_stack,
            text=self.bookmark.title or self.bookmark.url,
            bg=theme.bg_secondary,
            fg=theme.text_primary,
            font=FONTS.header(bold=True),
            anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            title_stack,
            text=_("Highlight important passages and save notes for later review."),
            bg=theme.bg_secondary,
            fg=theme.text_secondary,
            font=FONTS.small(),
            anchor="w",
        ).pack(fill=tk.X, pady=(3, 0))
        self.export_button = ModernButton(
            header,
            text=_("Export highlights"),
            command=self._export_highlights,
            style="primary",
        )
        self.export_button.pack(side=tk.RIGHT, padx=(12, 0))

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
        self.text.insert(
            "1.0",
            self.text_content or reader_empty_message(self.bookmark),
        )
        self.text.configure(state=tk.DISABLED)
        body.add(text_frame, minsize=500)

        side = tk.Frame(body, bg=theme.bg_secondary, padx=12, pady=12)
        body.add(side, minsize=330)
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(3, weight=3, minsize=80)
        side.grid_rowconfigure(6, weight=1, minsize=50)

        tk.Label(
            side,
            text=_("Highlights"),
            bg=theme.bg_secondary,
            fg=theme.text_primary,
            font=FONTS.body(bold=True),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        tk.Label(
            side,
            text=_("Select text in the reader, choose a color, then add a highlight."),
            bg=theme.bg_secondary,
            fg=theme.text_muted,
            font=FONTS.small(),
            anchor="w",
            wraplength=250,
            justify=tk.LEFT,
        ).grid(row=1, column=0, sticky="ew", pady=(2, 6))

        self.status = tk.Label(
            side,
            text="",
            bg=theme.bg_secondary,
            fg=theme.text_muted,
            font=FONTS.small(),
            anchor="w",
            justify=tk.LEFT,
            wraplength=300,
        )
        self.status.grid(row=2, column=0, sticky="ew", pady=(0, 6))

        self.highlight_list = tk.Listbox(
            side,
            bg=theme.bg_primary,
            fg=theme.text_primary,
            selectbackground=theme.selection,
            selectforeground=theme.text_primary,
            relief=tk.FLAT,
            height=4,
            font=FONTS.small(),
        )
        self.highlight_list.grid(row=3, column=0, sticky="nsew", pady=(0, 8))
        self.highlight_list.bind("<<ListboxSelect>>", self._on_highlight_selected)

        controls = tk.Frame(side, bg=theme.bg_secondary)
        controls.grid(row=4, column=0, sticky="ew")
        self.color_var = tk.StringVar(value="yellow")
        self.color_combo = ttk.Combobox(
            controls,
            textvariable=self.color_var,
            values=list(HIGHLIGHT_COLORS.keys()),
            width=10,
            state="readonly",
        )
        self.color_combo.pack(fill=tk.X)
        self.add_button = ModernButton(
            controls,
            text=_("Add highlight"),
            command=self._add_highlight_from_selection,
            style="success",
            padx=10,
            pady=4,
            font=FONTS.small(),
        )
        self.add_button.pack(fill=tk.X, pady=(7, 0))

        tk.Label(
            side,
            text=_("Note"),
            bg=theme.bg_secondary,
            fg=theme.text_secondary,
            font=FONTS.small(),
            anchor="w",
        ).grid(row=5, column=0, sticky="ew", pady=(9, 4))
        self.note_text = tk.Text(
            side,
            height=2,
            wrap=tk.WORD,
            bg=theme.bg_primary,
            fg=theme.text_primary,
            relief=tk.FLAT,
            font=FONTS.small(),
            padx=8,
            pady=8,
        )
        self.note_text.grid(row=6, column=0, sticky="nsew")

        note_actions = tk.Frame(side, bg=theme.bg_secondary)
        note_actions.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        primary_note_actions = tk.Frame(note_actions, bg=theme.bg_secondary)
        primary_note_actions.pack(fill=tk.X)
        self.save_note_button = ModernButton(
            primary_note_actions,
            text=_("Save note"),
            command=self._save_selected_note,
            style="primary",
            padx=10,
            pady=4,
            font=FONTS.small(),
        )
        self.save_note_button.pack(side=tk.LEFT, padx=(0, 8))
        self.delete_button = ModernButton(
            primary_note_actions,
            text=_("Delete highlight"),
            command=self._delete_selected_highlight,
            style="danger",
            padx=10,
            pady=4,
            font=FONTS.small(),
        )
        self.delete_button.pack(side=tk.LEFT)
        secondary_note_actions = tk.Frame(note_actions, bg=theme.bg_secondary)
        secondary_note_actions.pack(fill=tk.X, pady=(8, 0))
        self.relink_button = ModernButton(
            secondary_note_actions,
            text=_("Relink orphan to selection"),
            command=self._relink_selected_highlight,
            state="disabled",
            padx=10,
            pady=4,
            font=FONTS.small(),
            tooltip=_("Attach the selected orphan to a new passage"),
        )
        self.relink_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.undo_delete_button = ModernButton(
            secondary_note_actions,
            text=_("Undo"),
            command=self._undo_deleted_highlight,
            state="disabled",
            padx=10,
            pady=4,
            font=FONTS.small(),
            tooltip=_("Restore the last deleted highlight (Ctrl+Z)"),
        )
        self.undo_delete_button.pack(side=tk.LEFT)

    def _load_highlights(self, select_id: str | None = None) -> None:
        self._clear_highlight_tags()
        self.highlight_list.delete(0, tk.END)
        self.highlight_ids = []
        highlights = self.store.reconcile_for_bookmark(
            int(self.bookmark.id),
            self.text_content,
        )
        orphan_count = 0
        for highlight in highlights:
            if highlight.anchor_status == "orphaned":
                orphan_count += 1
            else:
                self._apply_text_tag(highlight)
            preview = " ".join(highlight.text.split())[:64]
            state = (
                _("ORPHAN")
                if highlight.anchor_status == "orphaned"
                else highlight.color
            )
            self.highlight_list.insert(
                tk.END,
                f"{state} {highlight.char_start}-{highlight.char_end}: {preview}",
            )
            self.highlight_ids.append(highlight.id)
        if self.highlight_ids:
            if orphan_count:
                self.status.configure(
                    text=_(
                        "{count} saved · {orphans} orphaned; select one to relink or delete"
                    ).format(
                        count=len(self.highlight_ids),
                        orphans=orphan_count,
                    )
                )
            else:
                self.status.configure(
                    text=_("{count} highlight(s) saved locally").format(
                        count=len(self.highlight_ids)
                    )
                )
        else:
            self.status.configure(text=_("No highlights yet. Select a passage to create the first one."))
        self.export_button.set_state("normal" if self.highlight_ids else "disabled")
        if select_id in self.highlight_ids:
            index = self.highlight_ids.index(select_id)
            self.highlight_list.selection_set(index)
            self.highlight_list.activate(index)
            self.highlight_list.see(index)
        self._sync_selection_actions()

    def _sync_selection_actions(self) -> None:
        highlight_id = self._selected_highlight_id()
        selected = bool(highlight_id)
        highlight = self.store.get(highlight_id) if highlight_id else None
        self.save_note_button.set_state("normal" if selected else "disabled")
        self.delete_button.set_state("normal" if selected else "disabled")
        can_relink = bool(
            highlight
            and highlight.anchor_status == "orphaned"
            and self.text_content
        )
        self.relink_button.set_state("normal" if can_relink else "disabled")

    def _clear_highlight_tags(self) -> None:
        self.text.configure(state=tk.NORMAL)
        for tag in self.text.tag_names():
            if tag.startswith("reader-highlight-"):
                self.text.tag_delete(tag)
        self.text.configure(state=tk.DISABLED)

    def _apply_text_tag(self, highlight: ReaderHighlight) -> None:
        if highlight.anchor_status == "orphaned":
            return
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
            self._sync_selection_actions()
            return
        highlight = self.store.get(highlight_id)
        if not highlight:
            return
        self.note_text.delete("1.0", tk.END)
        self.note_text.insert("1.0", highlight.note)
        if highlight.anchor_status == "orphaned":
            self.status.configure(
                text=_("Orphaned highlight: {reason}").format(
                    reason=highlight.orphan_reason or _("source passage changed")
                )
            )
        else:
            self.text.see(f"1.0 + {highlight.char_start} chars")
        self._sync_selection_actions()

    def _add_highlight_from_selection(self) -> None:
        try:
            start_index, end_index = self.text.tag_ranges(tk.SEL)
        except ValueError:
            self.status.configure(text=_("Select a passage in the reader before adding a highlight."))
            return
        if not start_index or not end_index:
            self.status.configure(text=_("Select a passage in the reader before adding a highlight."))
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
            self.status.configure(text=_("Could not save this highlight: {error}").format(error=str(exc)))
            return
        self.note_text.delete("1.0", tk.END)
        self._load_highlights()

    def _save_selected_note(self) -> None:
        highlight_id = self._selected_highlight_id()
        if not highlight_id:
            self.status.configure(text=_("Choose a saved highlight before editing its note."))
            return
        self.store.set_note(highlight_id, self.note_text.get("1.0", tk.END).strip())
        self._load_highlights()

    def _relink_selected_highlight(self) -> None:
        highlight_id = self._selected_highlight_id()
        highlight = self.store.get(highlight_id) if highlight_id else None
        if not highlight or highlight.anchor_status != "orphaned":
            self.status.configure(
                text=_("Choose an orphaned highlight before relinking it.")
            )
            return
        ranges = self.text.tag_ranges(tk.SEL)
        if len(ranges) != 2:
            self.status.configure(
                text=_("Select the replacement passage in the reader first.")
            )
            return
        start = text_index_offset(self.text, str(ranges[0]))
        end = text_index_offset(self.text, str(ranges[1]))
        try:
            repaired = self.store.relink(
                highlight_id,
                self.text_content,
                start,
                end,
            )
        except ValueError as exc:
            self.status.configure(
                text=_("Could not relink this highlight: {error}").format(
                    error=str(exc)
                )
            )
            return
        if repaired is None:
            self._load_highlights()
            self.status.configure(text=_("That highlight no longer exists."))
            return
        self._load_highlights(select_id=repaired.id)
        self._on_highlight_selected()
        self.status.configure(
            text=_("Highlight relinked; its note, tags, and review history were preserved.")
        )

    def _delete_selected_highlight(self) -> None:
        highlight_id = self._selected_highlight_id()
        if not highlight_id:
            self.status.configure(text=_("Choose a saved highlight before deleting it."))
            return
        deleted = self.store.delete_and_return(highlight_id)
        if deleted is None:
            self._load_highlights()
            self.status.configure(text=_("That highlight no longer exists."))
            return
        self._deleted_highlight = deleted
        self.note_text.delete("1.0", tk.END)
        self._load_highlights()
        self.undo_delete_button.set_state("normal")
        self.undo_delete_button.focus_set()
        self.status.configure(text=_("Highlight deleted. Undo is available (Ctrl+Z)."))

    def _undo_deleted_highlight(self, _event=None):
        deleted = self._deleted_highlight
        if deleted is None:
            self.status.configure(text=_("No deleted highlight is available to restore."))
            return "break"
        if not self.store.restore(deleted):
            self._deleted_highlight = None
            self.undo_delete_button.set_state("disabled")
            self.highlight_list.focus_set()
            self.status.configure(text=_("The highlight already exists and was not replaced."))
            return "break"

        self._deleted_highlight = None
        self.undo_delete_button.set_state("disabled")
        self._load_highlights()
        if deleted.id in self.highlight_ids:
            index = self.highlight_ids.index(deleted.id)
            self.highlight_list.selection_clear(0, tk.END)
            self.highlight_list.selection_set(index)
            self.highlight_list.activate(index)
            self.highlight_list.see(index)
            self.highlight_list.focus_set()
            self._on_highlight_selected()
        self.status.configure(text=_("Highlight restored."))
        return "break"

    def _export_highlights(self) -> None:
        stem = f"{self.bookmark.id}-reader-highlights"
        output_path = filedialog.asksaveasfilename(
            parent=self,
            title=_("Export Reader Highlights"),
            initialfile=f"{stem}.md",
            defaultextension=".md",
            filetypes=[
                (_("Markdown"), "*.md"),
                (_("CSV"), "*.csv"),
                (_("JSON"), "*.json"),
            ],
        )
        if not output_path:
            return
        suffix = Path(output_path).suffix.lower()
        export_format = {".csv": "csv", ".json": "json"}.get(suffix, "markdown")
        path = export_annotations(
            [self.bookmark],
            self.store.list_for_bookmark(int(self.bookmark.id)),
            output_path,
            output_format=export_format,
        )
        self.status.configure(text=_("Exported {name}").format(name=path.name))
