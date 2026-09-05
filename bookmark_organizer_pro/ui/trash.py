"""Persistent Trash workspace for the desktop app."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable

from bookmark_organizer_pro.i18n import _, format_message, format_plural
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark

from .foundation import FONTS, truncate_middle
from .window_geometry import apply_screen_aware_geometry
from .widgets import ModernButton, apply_window_chrome, get_theme


@dataclass(frozen=True)
class TrashRow:
    """Display data for one independently deleted bookmark."""

    bookmark_id: int
    title: str
    url: str
    deleted_at: str
    archive_state: str


def build_trash_rows(bookmarks: Iterable[Bookmark]) -> list[TrashRow]:
    """Build deterministic rows without changing bookmark state."""

    rows: list[TrashRow] = []
    for bookmark in bookmarks:
        if bookmark.id is None or not bookmark.is_deleted:
            continue
        try:
            deleted_at = datetime.fromisoformat(
                bookmark.deleted_at.replace("Z", "+00:00")
            ).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            deleted_at = bookmark.deleted_at.replace("T", " ", 1)[:16]
        rows.append(
            TrashRow(
                bookmark_id=int(bookmark.id),
                title=bookmark.title or bookmark.url or f"Bookmark {bookmark.id}",
                url=bookmark.url or "",
                deleted_at=deleted_at,
                archive_state=_("Archived") if bookmark.is_archived else _("Active"),
            )
        )
    return rows


class TrashDialog(tk.Toplevel):
    """Restore or recovery-purge independently deleted bookmarks."""

    def __init__(
        self,
        parent: tk.Widget,
        bookmark_manager,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.bookmark_manager = bookmark_manager
        self._owner = parent
        self._on_change = on_change
        self._theme = get_theme()
        self._rows: list[TrashRow] = []
        self._busy = False
        self._status_var = tk.StringVar(value="")

        self.title(_("Trash"))
        self.configure(bg=self._theme.bg_primary)
        apply_screen_aware_geometry(self, 860, 570)
        self.minsize(720, 480)
        self.transient(parent)
        self.grab_set()
        apply_window_chrome(self)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self._build()
        self._refresh_rows()
        self.focus_set()

    def _build(self) -> None:
        theme = self._theme
        header = tk.Frame(self, bg=theme.bg_dark)
        header.pack(fill=tk.X, pady=(0, 12))
        title_stack = tk.Frame(header, bg=theme.bg_dark)
        title_stack.pack(fill=tk.X, padx=22, pady=(16, 14))
        tk.Label(
            title_stack,
            text=_("Trash"),
            bg=theme.bg_dark,
            fg=theme.text_primary,
            font=FONTS.title(bold=True),
        ).pack(anchor="w")
        tk.Label(
            title_stack,
            text=_(
                "Deleted bookmarks stay recoverable here. Purge first creates and verifies "
                "a full recovery bundle, including saved page artifacts."
            ),
            bg=theme.bg_dark,
            fg=theme.text_secondary,
            font=FONTS.body(),
            wraplength=790,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(5, 0))

        self.body = tk.Frame(self, bg=theme.bg_primary)

        style = ttk.Style(self)
        style.configure(
            "Trash.Treeview",
            background=theme.bg_secondary,
            fieldbackground=theme.bg_secondary,
            foreground=theme.text_primary,
            rowheight=30,
            borderwidth=0,
            font=FONTS.body(),
        )
        style.configure(
            "Trash.Treeview.Heading",
            background=theme.bg_tertiary,
            foreground=theme.text_primary,
            font=FONTS.small(bold=True),
            relief=tk.FLAT,
        )
        style.map(
            "Trash.Treeview",
            background=[("selected", theme.selection)],
            foreground=[("selected", theme.text_primary)],
        )

        table_frame = tk.Frame(
            self.body,
            bg=theme.bg_secondary,
            highlightthickness=1,
            highlightbackground=theme.border_muted,
        )
        table_frame.pack(fill=tk.BOTH, expand=True)
        columns = ("title", "url", "deleted", "archive")
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
            style="Trash.Treeview",
        )
        self.tree.heading("title", text=_("Title"))
        self.tree.heading("url", text=_("URL"))
        self.tree.heading("deleted", text=_("Deleted"))
        self.tree.heading("archive", text=_("Archive"))
        self.tree.column("title", width=230, minwidth=150, stretch=True)
        self.tree.column("url", width=245, minwidth=160, stretch=True)
        self.tree.column("deleted", width=175, minwidth=150, stretch=False)
        self.tree.column("archive", width=115, minwidth=100, stretch=False, anchor=tk.CENTER)
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._sync_action_states())

        self.footer = tk.Frame(self, bg=theme.bg_primary)
        self.footer.pack(fill=tk.X, side=tk.BOTTOM, padx=22, pady=(0, 18))
        tk.Label(
            self.footer,
            textvariable=self._status_var,
            bg=theme.bg_primary,
            fg=theme.text_secondary,
            font=FONTS.small(),
            wraplength=410,
            justify=tk.LEFT,
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 12))

        actions = tk.Frame(self.footer, bg=theme.bg_primary)
        actions.pack(side=tk.RIGHT)
        self.restore_button = ModernButton(
            actions,
            text=_("Restore Selected"),
            command=self._restore_selected,
            style="success",
            padx=12,
            pady=8,
        )
        self.restore_button.pack(side=tk.LEFT, padx=(0, 7))
        self.purge_selected_button = ModernButton(
            actions,
            text=_("Purge Selected"),
            command=self._purge_selected,
            style="danger",
            padx=12,
            pady=8,
        )
        self.purge_selected_button.pack(side=tk.LEFT, padx=(0, 7))
        self.purge_all_button = ModernButton(
            actions,
            text=_("Purge All"),
            command=self._purge_all,
            style="warning",
            padx=12,
            pady=8,
        )
        self.purge_all_button.pack(side=tk.LEFT, padx=(0, 7))
        self.close_button = ModernButton(
            actions,
            text=_("Close"),
            command=self.destroy,
            padx=12,
            pady=8,
        )
        self.close_button.pack(side=tk.LEFT)
        self.body.pack(fill=tk.BOTH, expand=True, padx=22, pady=(0, 12))

    def _selected_ids(self) -> list[int]:
        selected: list[int] = []
        for item_id in self.tree.selection():
            try:
                selected.append(int(item_id))
            except (TypeError, ValueError):
                continue
        return selected

    def _sync_action_states(self) -> None:
        has_rows = bool(self._rows)
        has_selection = bool(self._selected_ids())
        self.restore_button.set_state(
            "normal" if has_selection and not self._busy else "disabled"
        )
        self.purge_selected_button.set_state(
            "normal" if has_selection and not self._busy else "disabled"
        )
        self.purge_all_button.set_state(
            "normal" if has_rows and not self._busy else "disabled"
        )

    def _refresh_rows(self, select_id: int | None = None) -> None:
        self._rows = build_trash_rows(self.bookmark_manager.get_trash())
        for item_id in self.tree.get_children(""):
            self.tree.delete(item_id)
        for row in self._rows:
            self.tree.insert(
                "",
                tk.END,
                iid=str(row.bookmark_id),
                values=(
                    truncate_middle(row.title, 50),
                    truncate_middle(row.url, 62),
                    row.deleted_at,
                    row.archive_state,
                ),
            )
        if self._rows:
            available = {row.bookmark_id for row in self._rows}
            target = select_id if select_id in available else self._rows[0].bookmark_id
            self.tree.selection_set(str(target))
            self.tree.focus(str(target))
            self.tree.see(str(target))
            self._status_var.set(
                format_plural(
                    "{count} recoverable bookmark in Trash.",
                    "{count} recoverable bookmarks in Trash.",
                    len(self._rows),
                    count=len(self._rows),
                )
            )
        else:
            self._status_var.set(_("Trash is empty. Deleted bookmarks will appear here."))
        self._sync_action_states()

    def _restore_selected(self) -> None:
        if self._busy:
            return
        selected = self._selected_ids()
        if not selected:
            self._status_var.set(_("Select at least one bookmark to restore."))
            return
        restored = 0
        conflicts = 0
        for bookmark_id in selected:
            if self.bookmark_manager.restore_from_trash(bookmark_id):
                restored += 1
            else:
                conflicts += 1
        if restored and self._on_change:
            self._on_change()
        self._refresh_rows()
        if conflicts:
            self._status_var.set(
                format_message(
                    "Restored {restored}. {conflicts} could not be restored because its URL is already live.",
                    restored=restored,
                    conflicts=conflicts,
                )
            )
        else:
            self._status_var.set(
                format_plural(
                    "Restored {count} bookmark.",
                    "Restored {count} bookmarks.",
                    restored,
                    count=restored,
                )
            )

    def _purge_selected(self) -> None:
        selected = self._selected_ids()
        if not selected:
            self._status_var.set(_("Select at least one bookmark to purge."))
            return
        self._begin_purge(selected)

    def _purge_all(self) -> None:
        self._begin_purge(None)

    def _begin_purge(self, bookmark_ids: list[int] | None) -> None:
        if self._busy or not self._rows:
            return
        self._busy = True
        self._sync_action_states()
        self._status_var.set(
            _("Creating and verifying a full recovery bundle before anything is unlinked...")
        )

        def worker() -> None:
            result = None
            error = None
            try:
                result = self.bookmark_manager.purge_trash(bookmark_ids)
            except Exception as exc:  # pragma: no cover - last-resort GUI boundary
                log.exception("Trash purge failed unexpectedly")
                error = str(exc)

            def deliver() -> None:
                if result is not None and result.purged_count and self._on_change:
                    self._on_change()
                try:
                    if self.winfo_exists():
                        self._finish_purge(result, error)
                except tk.TclError:
                    return

            try:
                self._owner.after(0, deliver)
            except (RuntimeError, tk.TclError):
                return

        threading.Thread(target=worker, name="trash-recovery-purge", daemon=True).start()

    def _finish_purge(self, result, error: str | None) -> None:
        self._busy = False
        self._refresh_rows()
        if error:
            self._status_var.set(format_message("Purge failed: {error}", error=error))
            return
        if result is None:
            self._status_var.set(_("Purge failed before a result was produced."))
            return
        if result.success:
            self._status_var.set(
                format_message(
                    "Purged {count}. Verified recovery bundle: {path}",
                    count=result.purged_count,
                    path=result.recovery_bundle,
                )
            )
            return
        details = "; ".join(result.errors) or _("No matching Trash records were found.")
        if result.recovery_bundle:
            details = format_message(
                "{details} Recovery bundle: {path}",
                details=details,
                path=result.recovery_bundle,
            )
        self._status_var.set(format_message("Purge could not finish. {details}", details=details))
