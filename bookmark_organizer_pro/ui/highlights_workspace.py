"""Keyboard-accessible collection workspace for reader highlights."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from bookmark_organizer_pro.i18n import _, format_message, format_plural
from bookmark_organizer_pro.services.highlight_workspace import (
    HighlightWorkspacePage,
    HighlightWorkspaceQuery,
    HighlightWorkspaceRecord,
    HighlightWorkspaceService,
)
from bookmark_organizer_pro.services.reader_annotations import HIGHLIGHT_COLORS, ReaderAnnotationStore

from .foundation import FONTS
from .reader_view import ReaderViewDialog
from .widget_controls import ModernButton
from .window_geometry import apply_screen_aware_geometry
from .widgets import apply_window_chrome, get_theme


def _truncate(value: object, length: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= length:
        return text
    return text[: max(1, length - 1)].rstrip() + "…"


class HighlightsWorkspaceDialog(tk.Toplevel):
    """Search, review, open, export, and undo-delete collection highlights."""

    PAGE_SIZE = 40

    def __init__(
        self,
        parent,
        bookmark_manager,
        *,
        store: ReaderAnnotationStore | None = None,
    ):
        theme = get_theme()
        super().__init__(parent)
        self.bookmark_manager = bookmark_manager
        self.workspace = HighlightWorkspaceService(
            store=store,
            bookmark_manager=bookmark_manager,
        )
        self.page: HighlightWorkspacePage | None = None
        self._rows: dict[str, HighlightWorkspaceRecord] = {}
        # A stack of deleted batches. One slot meant a second delete
        # silently replaced the first while the status line still said
        # undo was available.
        self._deleted_batches: list[tuple] = []
        self._bookmark_choices: dict[str, int | None] = {}
        self._bookmark_label_by_id: dict[int, str] = {}
        self.title(_("Highlights workspace"))
        apply_screen_aware_geometry(self, 1120, 720)
        self.minsize(860, 560)
        self.configure(bg=theme.bg_primary)
        self.transient(parent)
        apply_window_chrome(self)
        self._build()
        self._load_bookmark_choices()
        self._refresh()
        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Return>", self._on_return)
        self.bind("<Delete>", lambda _event: self._delete_selected() or "break")

    def _build(self) -> None:
        theme = get_theme()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        header = tk.Frame(self, bg=theme.bg_secondary, padx=18, pady=12)
        header.grid(row=0, column=0, sticky="ew")
        copy = tk.Frame(header, bg=theme.bg_secondary)
        copy.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(
            copy, text=_("Highlights workspace"),
            bg=theme.bg_secondary, fg=theme.text_primary,
            font=FONTS.header(bold=True), anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            copy,
            text=_("Search saved passages, notes, anchors, and review state without loading every source."),
            bg=theme.bg_secondary, fg=theme.text_secondary,
            font=FONTS.small(), anchor="w",
        ).pack(fill=tk.X, pady=(3, 0))
        self.status = tk.Label(
            header, text="", bg=theme.bg_secondary,
            fg=theme.text_muted, font=FONTS.small(), anchor="e",
        )
        self.status.pack(side=tk.RIGHT, padx=(12, 0))

        filters = tk.Frame(self, bg=theme.bg_primary, padx=18, pady=10)
        filters.grid(row=1, column=0, sticky="ew")
        for column in range(8):
            filters.grid_columnconfigure(column, weight=1 if column in {1, 3, 5, 7} else 0)

        self.text_var = tk.StringVar()
        self.note_var = tk.StringVar()
        self.tag_var = tk.StringVar()
        self.bookmark_var = tk.StringVar()
        self.color_var = tk.StringVar(value=_("All colors"))
        self.review_var = tk.StringVar(value=_("All review states"))
        self.anchor_var = tk.StringVar(value=_("All anchor states"))
        self._filter_entry(filters, 0, _("Text"), self.text_var)
        self._filter_entry(filters, 2, _("Note"), self.note_var)
        self._filter_entry(filters, 4, _("Tag"), self.tag_var)
        self._filter_entry(filters, 6, _("Bookmark"), self.bookmark_var, readonly=True)

        self.bookmark_combo = self._bookmark_entry
        self.color_combo = self._combo(
            filters, 0, 2, _("All colors"), self.color_var,
            [_("All colors"), *HIGHLIGHT_COLORS.keys()],
        )
        self.review_combo = self._combo(
            filters, 2, 2, _("All review states"), self.review_var,
            [_("All review states"), _("New"), _("Due"), _("Scheduled"), _("Reviewed")],
        )
        self.anchor_combo = self._combo(
            filters, 4, 2, _("All anchor states"), self.anchor_var,
            [_("All anchor states"), _("Anchored"), _("Reanchored"), _("Orphaned"), _("Unverified")],
        )
        ModernButton(
            filters, text=_("Apply filters"), icon="⌕",
            command=self._apply_filters, style="primary", padx=10, pady=6,
        ).grid(row=2, column=7, sticky="e", padx=(8, 0), pady=(4, 0))
        ModernButton(
            filters, text=_("Clear"), command=self._clear_filters,
            padx=10, pady=6,
        ).grid(row=2, column=6, sticky="e", padx=(8, 0), pady=(4, 0))

        body = tk.Frame(self, bg=theme.bg_primary, padx=18)
        body.grid(row=2, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            body,
            columns=("bookmark", "highlight", "note", "tags", "color", "review", "anchor"),
            show="headings",
            selectmode="extended",
            height=6,
        )
        headings = {
            "bookmark": _("Bookmark"),
            "highlight": _("Highlight"),
            "note": _("Note"),
            "tags": _("Tags"),
            "color": _("Color"),
            "review": _("Review"),
            "anchor": _("Anchor"),
        }
        widths = {"bookmark": 190, "highlight": 300, "note": 190, "tags": 130, "color": 85, "review": 95, "anchor": 105}
        for column, label in headings.items():
            self.tree.heading(column, text=label)
            self.tree.column(column, width=widths[column], minwidth=60, stretch=column in {"bookmark", "highlight", "note"})
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._sync_actions())
        self.tree.bind("<Double-1>", lambda _event: self._open_selected())

        footer = tk.Frame(self, bg=theme.bg_secondary, padx=18, pady=10)
        footer.grid(row=3, column=0, sticky="ew")
        self.prev_button = ModernButton(
            footer, text=_("Previous"), command=self._previous_page,
            padx=10, pady=6,
        )
        self.prev_button.pack(side=tk.LEFT)
        self.page_label = tk.Label(
            footer, text="", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.small(),
        )
        self.page_label.pack(side=tk.LEFT, padx=12)
        self.next_button = ModernButton(
            footer, text=_("Next"), command=self._next_page,
            padx=10, pady=6,
        )
        self.next_button.pack(side=tk.LEFT)
        actions = tk.Frame(footer, bg=theme.bg_secondary)
        actions.pack(side=tk.RIGHT)
        self.open_button = ModernButton(
            actions, text=_("Open source"), icon="↗",
            command=self._open_selected, style="primary", padx=10, pady=6,
        )
        self.open_button.pack(side=tk.LEFT, padx=(0, 6))
        self.export_selected_button = ModernButton(
            actions, text=_("Export selected"), command=self._export_selected,
            padx=10, pady=6,
        )
        self.export_selected_button.pack(side=tk.LEFT, padx=(0, 6))
        ModernButton(
            actions, text=_("Export filtered"), command=self._export_filtered,
            padx=10, pady=6,
        ).pack(side=tk.LEFT, padx=(0, 6))
        self.delete_button = ModernButton(
            actions, text=_("Delete selected"), icon="×",
            command=self._delete_selected, style="danger", padx=10, pady=6,
        )
        self.delete_button.pack(side=tk.LEFT, padx=(0, 6))
        self.undo_button = ModernButton(
            actions, text=_("Undo delete"), command=self._undo_delete,
            state="disabled", padx=10, pady=6,
        )
        self.undo_button.pack(side=tk.LEFT)

    def _filter_entry(self, parent, column: int, label: str, variable: tk.StringVar, readonly: bool = False):
        theme = get_theme()
        tk.Label(
            parent, text=label, bg=theme.bg_primary,
            fg=theme.text_muted, font=FONTS.tiny(), anchor="w",
        ).grid(row=0, column=column, sticky="w", padx=(0, 6))
        if readonly:
            self._bookmark_entry = ttk.Combobox(
                parent, textvariable=variable, state="readonly", width=26,
            )
            self._bookmark_entry.grid(row=1, column=column, columnspan=2, sticky="ew", padx=(0, 8), pady=(4, 0))
            self._bookmark_entry.bind("<<ComboboxSelected>>", lambda _event: self._apply_filters())
        else:
            entry = ttk.Entry(parent, textvariable=variable)
            entry.grid(row=1, column=column, columnspan=2, sticky="ew", padx=(0, 8), pady=(4, 0))
            entry.bind("<Return>", lambda _event: self._apply_filters())

    @staticmethod
    def _combo(parent, column: int, row: int, label: str, variable: tk.StringVar, values: list[str]):
        combo = ttk.Combobox(parent, textvariable=variable, state="readonly", values=values, width=16)
        combo.grid(row=row, column=column, columnspan=2, sticky="ew", padx=(0, 8), pady=(4, 0))
        combo.bind("<<ComboboxSelected>>", lambda _event: None)
        return combo

    def _load_bookmark_choices(self) -> None:
        choices = [_("All bookmarks")]
        self._bookmark_choices = {choices[0]: None}
        bookmarks = sorted(
            self.bookmark_manager.get_all_bookmarks(),
            key=lambda item: (str(item.title or item.url).casefold(), int(item.id or 0)),
        )
        for bookmark in bookmarks:
            try:
                label = format_message(
                    "{id} · {title}",
                    id=bookmark.id,
                    title=_truncate(bookmark.title or bookmark.url, 48),
                )
                self._bookmark_choices[label] = int(bookmark.id)
                self._bookmark_label_by_id[int(bookmark.id)] = label
                choices.append(label)
            except (AttributeError, TypeError, ValueError):
                continue
        self.bookmark_combo.configure(values=choices)
        self.bookmark_var.set(choices[0])

    def _selected_bookmark_id(self) -> int | None:
        return self._bookmark_choices.get(self.bookmark_var.get())

    @staticmethod
    def _selected_filter(value: str, all_label: str) -> str:
        return "" if value == all_label else value

    def _build_query(self, *, offset: int = 0, page_size: int | None = None) -> HighlightWorkspaceQuery:
        review_labels = {
            _("All review states"): "all", _("New"): "new", _("Due"): "due",
            _("Scheduled"): "scheduled", _("Reviewed"): "reviewed",
        }
        anchor_labels = {
            _("All anchor states"): "all", _("Anchored"): "anchored",
            _("Reanchored"): "reanchored", _("Orphaned"): "orphaned",
            _("Unverified"): "unverified",
        }
        color = self._selected_filter(self.color_var.get(), _("All colors"))
        return HighlightWorkspaceQuery.create(
            text=self.text_var.get(),
            note=self.note_var.get(),
            tag=self.tag_var.get(),
            color=color,
            bookmark_id=self._selected_bookmark_id(),
            review_status=review_labels.get(self.review_var.get(), "all"),
            anchor_status=anchor_labels.get(self.anchor_var.get(), "all"),
            limit=page_size or self.PAGE_SIZE,
            offset=offset,
        )

    def _apply_filters(self) -> None:
        self._refresh(offset=0)

    def _clear_filters(self) -> None:
        self.text_var.set("")
        self.note_var.set("")
        self.tag_var.set("")
        self.bookmark_var.set(_("All bookmarks"))
        self.color_var.set(_("All colors"))
        self.review_var.set(_("All review states"))
        self.anchor_var.set(_("All anchor states"))
        self._refresh(offset=0)

    def _refresh(self, *, offset: int | None = None) -> None:
        try:
            query = self._build_query(offset=offset if offset is not None else 0)
            if offset is None and self.page is not None:
                query = self._build_query(offset=self.page.offset)
            self.page = self.workspace.query(query)
        except ValueError as exc:
            self.status.configure(text=str(exc))
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._rows = {item.id: item for item in self.page.items}
        for item in self.page.items:
            bookmark = item.bookmark_title or _("Missing bookmark")
            self.tree.insert(
                "", tk.END, iid=item.id,
                values=(
                    _truncate(bookmark, 32),
                    item.preview or _("(empty highlight)"),
                    _truncate(item.highlight.note, 28) or "—",
                    ", ".join(item.highlight.tags) or "—",
                    item.highlight.color,
                    item.review_status,
                    item.highlight.anchor_status,
                ),
            )
        self.status.configure(
            text=format_plural(
                "{count} highlight matching", "{count} highlights matching",
                self.page.total, count=self.page.total,
            ),
        )
        start = self.page.offset + 1 if self.page.total else 0
        end = self.page.offset + len(self.page.items)
        self.page_label.configure(
            text=format_message("{start}–{end} of {total}", start=start, end=end, total=self.page.total)
            if self.page.total else _("No highlights"),
        )
        self.prev_button.set_state("normal" if self.page.offset else "disabled")
        self.next_button.set_state("normal" if self.page.has_more else "disabled")
        self._sync_actions()

    def _sync_actions(self) -> None:
        selected = bool(self.tree.selection())
        self.open_button.set_state("normal" if len(self.tree.selection()) == 1 else "disabled")
        self.export_selected_button.set_state("normal" if selected else "disabled")
        self.delete_button.set_state("normal" if selected else "disabled")
        self.undo_button.set_state("normal" if self._deleted_batches else "disabled")

    def _previous_page(self) -> None:
        if self.page is None or self.page.offset <= 0:
            return
        self._refresh(offset=max(0, self.page.offset - self.page.limit))

    def _next_page(self) -> None:
        if self.page is None or not self.page.has_more:
            return
        self._refresh(offset=self.page.next_offset or self.page.offset)

    def _on_return(self, _event=None):
        if len(self.tree.selection()) == 1:
            self._open_selected()
        return "break"

    def _selected_records(self) -> list[HighlightWorkspaceRecord]:
        return [self._rows[item_id] for item_id in self.tree.selection() if item_id in self._rows]

    def _open_selected(self) -> None:
        selected = self._selected_records()
        if len(selected) != 1:
            self.status.configure(text=_("Select one highlight to open its source."))
            return
        item = selected[0]
        bookmark = self.bookmark_manager.get_bookmark(item.bookmark_id)
        if bookmark is None:
            self.status.configure(text=_("The bookmark for this highlight is no longer available."))
            return
        ReaderViewDialog(
            self,
            bookmark,
            store=self.workspace.store,
            highlight_id=item.id,
        )

    def _delete_selected(self):
        selected = self._selected_records()
        if not selected:
            return "break"
        # Deleting is immediate: `_undo_delete` restores the exact ids below and
        # the Undo button takes focus, so a modal asking first added nothing.
        deleted = self.workspace.delete_many([item.id for item in selected])
        if deleted:
            self._deleted_batches.append(tuple(deleted))
        self._refresh(offset=self.page.offset if self.page else 0)
        self.status.configure(
            text=format_plural(
                "Deleted {count} highlight. Undo is available.",
                "Deleted {count} highlights. Undo is available.",
                len(deleted), count=len(deleted),
            ),
        )
        self.undo_button.focus_set()
        return "break"

    def _undo_delete(self) -> None:
        """Restore the most recent batch, keeping the ones before it."""
        if not self._deleted_batches:
            return
        count = self.workspace.restore_many(self._deleted_batches[-1])
        # Only drop the batch once the store has taken it back.
        self._deleted_batches.pop()
        self._refresh(offset=self.page.offset if self.page else 0)
        message = format_plural(
            "Restored {count} highlight.", "Restored {count} highlights.",
            count, count=count,
        )
        if self._deleted_batches:
            message += " " + format_plural(
                "{count} earlier batch can still be restored.",
                "{count} earlier batches can still be restored.",
                len(self._deleted_batches), count=len(self._deleted_batches),
            )
        self.status.configure(text=message)

    def _export_selected(self) -> None:
        selected = self._selected_records()
        if not selected:
            return
        self._export(highlight_ids=[item.id for item in selected])

    def _export_filtered(self) -> None:
        self._export(query=self._build_query(offset=0, page_size=self.PAGE_SIZE))

    def _export(self, *, query=None, highlight_ids=None) -> None:
        output = filedialog.asksaveasfilename(
            parent=self,
            title=_("Export highlights"),
            initialfile="highlights.md",
            defaultextension=".md",
            filetypes=[(_("Markdown"), "*.md"), (_("CSV"), "*.csv"), (_("JSON"), "*.json")],
        )
        if not output:
            return
        suffix = str(output).lower().rsplit(".", 1)[-1] if "." in str(output) else "md"
        output_format = {"csv": "csv", "json": "json"}.get(suffix, "markdown")
        try:
            path = self.workspace.export(
                output,
                query=query,
                highlight_ids=highlight_ids,
                output_format=output_format,
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror(_("Export failed"), str(exc), parent=self)
            return
        self.status.configure(text=format_message("Exported {name}", name=path.name))


__all__ = ["HighlightsWorkspaceDialog"]
