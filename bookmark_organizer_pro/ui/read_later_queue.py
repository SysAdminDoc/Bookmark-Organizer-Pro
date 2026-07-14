"""Desktop Read Later queue workflow."""

from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable, List

from bookmark_organizer_pro.i18n import _, format_plural
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.read_later import ReadLaterQueue

from .foundation import FONTS, truncate_middle
from .widgets import ModernButton, apply_window_chrome, get_theme


@dataclass(frozen=True)
class ReadLaterQueueRow:
    bookmark_id: int
    position: int
    title: str
    url: str
    domain: str


def build_read_later_rows(bookmarks: Iterable[Bookmark]) -> List[ReadLaterQueueRow]:
    """Build ordered queue rows for tests and the desktop dialog."""
    rows: List[ReadLaterQueueRow] = []
    for index, bookmark in enumerate(ReadLaterQueue.list_queue(bookmarks), 1):
        if bookmark.id is None:
            continue
        rows.append(ReadLaterQueueRow(
            bookmark_id=int(bookmark.id),
            position=index,
            title=bookmark.title or bookmark.url or f"Bookmark {bookmark.id}",
            url=bookmark.url or "",
            domain=bookmark.domain or "",
        ))
    return rows


class ReadLaterQueueDialog(tk.Toplevel):
    """Full desktop queue controls for Read Later bookmarks."""

    def __init__(
        self,
        parent: tk.Widget,
        bookmark_manager,
        on_changed: Callable[[], None],
        on_open_url: Callable[[str], bool],
    ):
        super().__init__(parent)
        self.bookmark_manager = bookmark_manager
        self._on_changed = on_changed
        self._on_open_url = on_open_url
        self._theme = get_theme()
        self._rows: List[ReadLaterQueueRow] = []
        self._status_var = tk.StringVar(value="")

        self.title(_("Read Later Queue"))
        self.configure(bg=self._theme.bg_primary)
        self.geometry("760x560")
        self.minsize(680, 480)
        self.transient(parent)
        self.grab_set()
        apply_window_chrome(self)

        self._build()
        self._refresh_rows()
        self.bind("<Escape>", lambda _event: self.destroy())

    def _build(self) -> None:
        theme = self._theme
        header = tk.Frame(self, bg=theme.bg_primary)
        header.pack(fill=tk.X, padx=22, pady=(20, 12))
        tk.Label(
            header,
            text=_("Read Later Queue"),
            bg=theme.bg_primary,
            fg=theme.text_primary,
            font=FONTS.title(bold=True),
        ).pack(anchor="w")
        tk.Label(
            header,
            text=_("Open, reorder, complete, or remove queued bookmarks without leaving the desktop workspace."),
            bg=theme.bg_primary,
            fg=theme.text_secondary,
            font=FONTS.body(),
            wraplength=690,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(6, 0))

        body = tk.Frame(self, bg=theme.bg_primary)
        body.pack(fill=tk.BOTH, expand=True, padx=22, pady=(0, 12))
        list_frame = tk.Frame(body, bg=theme.bg_secondary, highlightthickness=1, highlightbackground=theme.border_muted)
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.listbox = tk.Listbox(
            list_frame,
            bg=theme.bg_secondary,
            fg=theme.text_primary,
            selectbackground=theme.selection,
            selectforeground=theme.text_primary,
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            font=FONTS.body(),
        )
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.bind("<Double-Button-1>", lambda _event: self._open_selected())
        self.listbox.bind("<Return>", lambda _event: self._open_selected())
        self.listbox.bind("<space>", lambda _event: self._open_selected())

        controls = tk.Frame(body, bg=theme.bg_primary)
        controls.pack(side=tk.RIGHT, fill=tk.Y, padx=(14, 0))
        button_specs = [
            (_("Open Next"), self._open_next, "primary"),
            (_("Open Selected"), self._open_selected, "default"),
            (_("Move Up"), lambda: self._move_selected(-1), "default"),
            (_("Move Down"), lambda: self._move_selected(1), "default"),
            (_("Mark Done"), self._mark_done, "success"),
            (_("Remove"), self._remove_selected, "danger"),
        ]
        for text, command, style in button_specs:
            ModernButton(controls, text=text, command=command, style=style, padx=14, pady=8).pack(fill=tk.X, pady=(0, 8))

        footer = tk.Frame(self, bg=theme.bg_primary)
        footer.pack(fill=tk.X, padx=22, pady=(0, 18))
        tk.Label(
            footer,
            textvariable=self._status_var,
            bg=theme.bg_primary,
            fg=theme.text_secondary,
            font=FONTS.small(),
            wraplength=520,
            justify=tk.LEFT,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ModernButton(footer, text=_("Close"), command=self.destroy, padx=16, pady=8).pack(side=tk.RIGHT)

    def _all_bookmarks(self) -> List[Bookmark]:
        return list(self.bookmark_manager.get_all_bookmarks())

    def _bookmark_by_id(self, bookmark_id: int) -> Bookmark | None:
        get_bookmark = getattr(self.bookmark_manager, "get_bookmark", None)
        if get_bookmark:
            return get_bookmark(bookmark_id)
        return next((bm for bm in self._all_bookmarks() if bm.id == bookmark_id), None)

    def _refresh_rows(self, select_id: int | None = None) -> None:
        self._rows = build_read_later_rows(self._all_bookmarks())
        self.listbox.delete(0, tk.END)
        if not self._rows:
            self.listbox.insert(tk.END, _("Nothing queued"))
            self._status_var.set(_("Read Later is empty. Add bookmarks from the editor or browser extension."))
            return

        for row in self._rows:
            title = truncate_middle(row.title, 56)
            domain = truncate_middle(row.domain or row.url, 32)
            self.listbox.insert(tk.END, f"{row.position:02d}. {title}  [{domain}]")
        selected_index = 0
        if select_id is not None:
            for index, row in enumerate(self._rows):
                if row.bookmark_id == select_id:
                    selected_index = index
                    break
        self.listbox.selection_set(selected_index)
        self.listbox.activate(selected_index)
        count = len(self._rows)
        self._status_var.set(format_plural(
            "{count} queued bookmark.",
            "{count} queued bookmarks.",
            count,
            count=count,
        ))

    def _selected_row(self) -> ReadLaterQueueRow | None:
        if not self._rows:
            return None
        selection = self.listbox.curselection()
        if not selection:
            return self._rows[0]
        index = int(selection[0])
        if index >= len(self._rows):
            return None
        return self._rows[index]

    def _persist_queue_order(self, ordered_ids: List[int], select_id: int | None = None) -> None:
        moved = ReadLaterQueue.reorder(self._all_bookmarks(), ordered_ids)
        if moved:
            self.bookmark_manager.save_bookmarks()
            self._on_changed()
        self._refresh_rows(select_id=select_id)
        self._status_var.set(_("Queue order saved."))

    def _move_selected(self, delta: int) -> None:
        row = self._selected_row()
        if not row:
            return
        ids = [item.bookmark_id for item in self._rows]
        index = ids.index(row.bookmark_id)
        new_index = max(0, min(len(ids) - 1, index + delta))
        if new_index == index:
            self._status_var.set(_("Selected item is already at that edge."))
            return
        ids[index], ids[new_index] = ids[new_index], ids[index]
        self._persist_queue_order(ids, select_id=row.bookmark_id)

    def _open_next(self) -> None:
        bookmark = ReadLaterQueue.peek_next(self._all_bookmarks())
        if not bookmark:
            self._status_var.set(_("Read Later is empty."))
            return
        if self._on_open_url(bookmark.url):
            self._status_var.set(_("Opened next queued bookmark."))

    def _open_selected(self) -> None:
        row = self._selected_row()
        if not row:
            self._status_var.set(_("Read Later is empty."))
            return
        bookmark = self._bookmark_by_id(row.bookmark_id)
        if bookmark and self._on_open_url(bookmark.url):
            self._status_var.set(_("Opened selected bookmark."))

    def _mark_done(self) -> None:
        row = self._selected_row()
        if not row:
            self._status_var.set(_("Read Later is empty."))
            return
        bookmark = self._bookmark_by_id(row.bookmark_id)
        if not bookmark:
            return
        ReadLaterQueue.complete(bookmark)
        self.bookmark_manager.save_bookmarks()
        self._on_changed()
        self._refresh_rows()
        self._status_var.set(_("Marked bookmark done and removed it from Read Later."))

    def _remove_selected(self) -> None:
        row = self._selected_row()
        if not row:
            self._status_var.set(_("Read Later is empty."))
            return
        bookmark = self._bookmark_by_id(row.bookmark_id)
        if not bookmark:
            return
        ReadLaterQueue.dequeue(bookmark)
        self.bookmark_manager.save_bookmarks()
        self._on_changed()
        self._refresh_rows()
        self._status_var.set(_("Removed bookmark from Read Later."))
