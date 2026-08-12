"""Contextual bookmark inspector for the primary library rail."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from bookmark_organizer_pro.i18n import _, format_message
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.extraction_templates import (
    format_structured_value,
    structured_metadata_fields,
)
from bookmark_organizer_pro.services.processing_timeline import (
    ProcessingTimelineEvent,
    ProcessingTimelineService,
)

from .foundation import FONTS, DesignTokens, display_or_fallback
from .widget_controls import ModernButton, ThemedWidget
from .widget_runtime import get_theme


def _bookmark_type(url: str) -> str:
    """Return a calm human label for the inspector metadata."""
    suffix = Path(urlparse(str(url or "")).path).suffix.lower()
    if suffix == ".pdf":
        return _("PDF")
    if suffix in {".epub", ".mobi"}:
        return _("E-book")
    if suffix in {".mp3", ".m4a", ".wav", ".ogg"}:
        return _("Audio")
    if suffix in {".mp4", ".webm", ".mov"}:
        return _("Video")
    return _("Website")


def _format_date(value: str) -> str:
    """Format persisted ISO timestamps without raising on legacy values."""
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return display_or_fallback(value)
    return parsed.strftime("%b %d, %Y · %I:%M %p").replace(" 0", " ")


def _next_action(bookmark: Bookmark) -> tuple[str, str, str, str]:
    """Return focused next-step copy plus the action kind to invoke."""
    if not bookmark.is_valid:
        return (
            _("Verify this bookmark"),
            _("Review the URL and details before returning it to your library."),
            _("Review details"),
            "edit",
        )
    if bookmark.read_later:
        return (
            _("Continue where you left off"),
            _("Open the source and keep it in your reading queue."),
            _("Continue reading"),
            "open",
        )
    if getattr(bookmark, "reader_progress_state", "unread") == "in_progress":
        return (
            _("Continue where you left off"),
            _("Resume the saved reader position for this bookmark."),
            _("Continue reading"),
            "open",
        )
    if not str(bookmark.notes or "").strip():
        return (
            _("Add useful context"),
            _("A short note will make this save easier to rediscover."),
            _("Add a note"),
            "edit",
        )
    return (
        _("Revisit the source"),
        _("Open the original page when you are ready."),
        _("Open bookmark"),
        "open",
    )


_TIMELINE_OPERATION_LABELS = {
    "capture": _("Bookmark saved"),
    "metadata": _("Metadata"),
    "link_check": _("Link check"),
    "ingest": _("Content extraction"),
    "extraction": _("Extracted text"),
    "snapshot": _("Offline snapshot"),
    "youtube_transcript": _("YouTube transcript"),
    "youtube_transcript_remove": _("Transcript removal"),
    "embedding": _("Search index"),
}
_TIMELINE_STATE_LABELS = {
    "running": _("Running"),
    "success": _("Complete"),
    "failure": _("Failed"),
    "cancelled": _("Cancelled"),
    "missing": _("Missing artifact"),
}


def _timeline_operation_label(operation: str) -> str:
    return _TIMELINE_OPERATION_LABELS.get(str(operation or ""), _("Local processing"))


def _timeline_state_label(state: str) -> str:
    return _TIMELINE_STATE_LABELS.get(str(state or ""), _("Unknown state"))


def _timeline_time_label(timestamp: str) -> str:
    return _format_date(timestamp) if str(timestamp or "").strip() else _("Time unavailable")


def _timeline_artifact_label(event: ProcessingTimelineEvent) -> str:
    details = []
    if event.artifact_size:
        details.append(format_message("{size} bytes", size=f"{event.artifact_size:,}"))
    if event.artifact_digest:
        details.append(format_message("SHA-256 {digest}", digest=event.artifact_digest[:12]))
    return " · ".join(details) or _("No artifact details")


class BookmarkDetailPanel(tk.Frame, ThemedWidget):
    """Selected-bookmark inspector with actions, metadata, and one next step."""

    def __init__(
        self,
        parent,
        on_edit: Callable[[Bookmark], None] | None = None,
        on_open: Callable[[Bookmark], None] | None = None,
        on_open_offline: Callable[[Bookmark], None] | None = None,
        on_delete: Callable[[Bookmark], None] | None = None,
        on_close: Callable[[], None] | None = None,
        on_retry_processing: Callable[[Bookmark, ProcessingTimelineEvent], None] | None = None,
        on_remove_processing: Callable[[Bookmark, ProcessingTimelineEvent], None] | None = None,
        timeline_service: ProcessingTimelineService | None = None,
    ):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_dark, width=DesignTokens.RIGHT_SIDEBAR_WIDTH)
        self.on_edit = on_edit
        self.on_open = on_open
        self.on_open_offline = on_open_offline
        self.on_delete = on_delete
        self.on_close = on_close
        self.on_retry_processing = on_retry_processing
        self.on_remove_processing = on_remove_processing
        self.timeline_service = timeline_service or ProcessingTimelineService()
        self.current_bookmark: Optional[Bookmark] = None
        self.content = tk.Frame(self, bg=theme.bg_dark)
        self.content.pack(fill=tk.BOTH, expand=True, padx=DesignTokens.PANEL_PAD)
        self.clear()

    def clear(self, message: str | None = None):
        """Reset the rail to a useful, non-blank selection prompt."""
        self.current_bookmark = None
        for widget in self.content.winfo_children():
            widget.destroy()
        theme = get_theme()
        empty = tk.Frame(
            self.content, bg=theme.bg_card,
            highlightbackground=theme.card_border, highlightthickness=1,
        )
        empty.pack(fill=tk.X, pady=(8, 0))
        tk.Label(
            empty, text=_("Select a bookmark"), bg=theme.bg_card,
            fg=theme.text_primary, font=FONTS.body(bold=True),
        ).pack(anchor="w", padx=14, pady=(14, 4))
        tk.Label(
            empty,
            text=message or _("Choose one row to see notes, saved state, and quick actions."),
            bg=theme.bg_card, fg=theme.text_secondary, font=FONTS.small(),
            justify=tk.LEFT, wraplength=280,
        ).pack(anchor="w", padx=14, pady=(0, 14))

    def show_bookmark(self, bookmark: Bookmark, **_context):
        """Render a selected bookmark without opening another window."""
        theme = get_theme()
        self.current_bookmark = bookmark
        for widget in self.content.winfo_children():
            widget.destroy()

        hero = tk.Frame(self.content, bg=theme.bg_dark)
        hero.pack(fill=tk.X, pady=(10, 8))
        domain = display_or_fallback(bookmark.domain, "?")
        tk.Label(
            hero, text=domain[0].upper(), bg=theme.bg_tertiary,
            fg=theme.text_primary, font=FONTS.hero(bold=True), width=3, pady=9,
        ).pack(side=tk.LEFT, anchor="n", padx=(0, 12))
        identity = tk.Frame(hero, bg=theme.bg_dark)
        identity.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(
            identity, text=display_or_fallback(bookmark.title, _("Untitled bookmark")),
            bg=theme.bg_dark, fg=theme.text_primary, font=FONTS.subtitle(bold=True),
            wraplength=250, justify=tk.LEFT, anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            identity, text=domain, bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.small(), anchor="w",
        ).pack(fill=tk.X, pady=(3, 0))

        status_text, status_color = self._status_presentation(bookmark)
        status = tk.Frame(self.content, bg=theme.bg_dark)
        status.pack(fill=tk.X, pady=(2, 12))
        tk.Label(
            status, text=_("●"), bg=theme.bg_dark, fg=status_color,
            font=FONTS.tiny(),
        ).pack(side=tk.LEFT)
        tk.Label(
            status, text=status_text, bg=theme.bg_dark, fg=theme.text_secondary,
            font=FONTS.small(),
        ).pack(side=tk.LEFT, padx=(5, 0))
        tk.Label(
            status, text=_("Type: {kind}").format(kind=_bookmark_type(bookmark.url)),
            bg=theme.bg_dark, fg=theme.text_muted, font=FONTS.tiny(),
        ).pack(side=tk.RIGHT)

        ModernButton(
            self.content, text=_("Open"), icon="↗", style="primary",
            command=self._open_bookmark, tooltip=_("Open this bookmark"),
            padx=12, pady=9,
        ).pack(fill=tk.X, pady=(0, 8))
        actions = tk.Frame(self.content, bg=theme.bg_dark)
        actions.pack(fill=tk.X, pady=(0, 14))
        ModernButton(
            actions, text=_("Edit"), icon="✎", command=self._edit_bookmark,
            tooltip=_("Edit title, collection, tags, notes, and URL"), pady=8,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self.more_button = ModernButton(
            actions, text=_("More"), icon="⋮", command=self._show_more_menu,
            tooltip=_("More bookmark actions"), pady=8,
        )
        self.more_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        self._render_next_action(bookmark)

        self._separator()
        self._section_label(_("Notes"))
        notes = str(bookmark.notes or "").strip()
        tk.Label(
            self.content,
            text=notes or _("No notes yet. Edit this bookmark to add context for your future self."),
            bg=theme.bg_dark, fg=theme.text_secondary if notes else theme.text_muted,
            font=FONTS.small(), justify=tk.LEFT, anchor="w", wraplength=318,
        ).pack(fill=tk.X, pady=(0, 12))

        self._separator()
        self._detail(_("Collection"), display_or_fallback(bookmark.category, _("Uncategorized")))
        tags = [*bookmark.tags, *bookmark.ai_tags]
        self._detail(_("Tags"), "  ".join(f"#{tag}" for tag in tags) if tags else _("No tags"))
        self._detail(_("Saved"), _format_date(bookmark.created_at))
        progress_labels = {
            "unread": _("Unread"),
            "in_progress": _("In progress"),
            "finished": _("Finished"),
        }
        self._detail(
            _("Reading progress"),
            progress_labels.get(
                getattr(bookmark, "reader_progress_state", "unread"),
                _("Unread"),
            ),
        )
        self._detail(_("Offline copy"), self._offline_state(bookmark))

        structured_fields = structured_metadata_fields(bookmark)
        if structured_fields:
            self._separator()
            self._section_label(_("Extracted details"))
            for key, value in sorted(structured_fields.items())[:6]:
                label = key.replace("_", " ").title()
                self._detail(label, format_structured_value(value))

        self._render_processing_timeline(bookmark)

    def _render_processing_timeline(self, bookmark: Bookmark):
        """Show bounded local processing state without source content."""
        self._separator()
        self._section_label(_("Processing timeline"))
        try:
            events = self.timeline_service.list_events(bookmark)
        except Exception:
            events = []
        if not events:
            tk.Label(
                self.content,
                text=_("No local processing events yet."),
                bg=get_theme().bg_dark, fg=get_theme().text_muted,
                font=FONTS.small(), anchor="w", justify=tk.LEFT,
            ).pack(fill=tk.X, pady=(0, 12))
            return

        for event in events[-20:]:
            self._render_processing_event(bookmark, event)

    def _render_processing_event(self, bookmark: Bookmark, event: ProcessingTimelineEvent):
        theme = get_theme()
        row = tk.Frame(
            self.content, bg=theme.bg_card,
            highlightbackground=theme.card_border, highlightthickness=1,
        )
        row.pack(fill=tk.X, pady=(0, 7))
        heading = tk.Frame(row, bg=theme.bg_card)
        heading.pack(fill=tk.X, padx=11, pady=(9, 3))
        tk.Label(
            heading,
            text=_timeline_operation_label(event.operation),
            bg=theme.bg_card, fg=theme.text_primary,
            font=FONTS.small(bold=True), anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(
            heading, text=_timeline_state_label(event.state),
            bg=theme.bg_card, fg=theme.text_secondary,
            font=FONTS.tiny(), anchor="e",
        ).pack(side=tk.RIGHT)
        tk.Label(
            row,
            text=format_message(
                "{backend} · {time}",
                backend=event.backend or _("local"),
                time=_timeline_time_label(event.timestamp),
            ),
            bg=theme.bg_card, fg=theme.text_muted,
            font=FONTS.tiny(), anchor="w",
        ).pack(fill=tk.X, padx=11, pady=(0, 2))
        tk.Label(
            row, text=_timeline_artifact_label(event),
            bg=theme.bg_card, fg=theme.text_secondary,
            font=FONTS.tiny(), anchor="w",
        ).pack(fill=tk.X, padx=11, pady=(0, 2))
        if event.error:
            tk.Label(
                row,
                text=_("Error: {error}").format(error=event.error),
                bg=theme.bg_card, fg=theme.accent_warning,
                font=FONTS.tiny(), anchor="w", justify=tk.LEFT,
                wraplength=285,
            ).pack(fill=tk.X, padx=11, pady=(0, 3))
        if event.retryable or event.removable:
            actions = tk.Frame(row, bg=theme.bg_card)
            actions.pack(fill=tk.X, padx=11, pady=(3, 9))
            if event.retryable and self.on_retry_processing:
                ModernButton(
                    actions, text=_("Retry"), icon="↻",
                    command=lambda bm=bookmark, item=event: self.on_retry_processing(bm, item),
                    tooltip=_("Retry this local processing step"),
                    padx=8, pady=5,
                ).pack(side=tk.LEFT, padx=(0, 5))
            if event.removable and event.state in {"success", "missing"} and self.on_remove_processing:
                ModernButton(
                    actions, text=_("Remove"), icon="×",
                    command=lambda bm=bookmark, item=event: self.on_remove_processing(bm, item),
                    tooltip=_("Remove this derived artifact"),
                    padx=8, pady=5,
                ).pack(side=tk.LEFT)

    def _render_next_action(self, bookmark: Bookmark):
        """Render one calm, state-aware recommendation instead of analytics."""
        theme = get_theme()
        self._separator()
        self._section_label(_("Next action"))
        title, detail, action_label, action_kind = _next_action(bookmark)
        card = tk.Frame(
            self.content, bg=theme.bg_card,
            highlightbackground=theme.card_border, highlightthickness=1,
        )
        card.pack(fill=tk.X, pady=(0, 14))
        tk.Label(
            card, text=title, bg=theme.bg_card,
            fg=theme.text_primary, font=FONTS.body(bold=True),
            anchor="w",
        ).pack(fill=tk.X, padx=13, pady=(12, 4))
        tk.Label(
            card, text=detail, bg=theme.bg_card,
            fg=theme.text_secondary, font=FONTS.small(),
            justify=tk.LEFT, anchor="w", wraplength=270,
        ).pack(fill=tk.X, padx=13, pady=(0, 10))
        command = self._edit_bookmark if action_kind == "edit" else self._open_bookmark
        ModernButton(
            card, text=action_label, icon="→", style="primary",
            command=command, tooltip=detail, padx=11, pady=8,
        ).pack(fill=tk.X, padx=13, pady=(0, 12))

    def _detail(self, label: str, value: str):
        theme = get_theme()
        tk.Label(
            self.content, text=label, bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.tiny(), anchor="w",
        ).pack(fill=tk.X, pady=(0, 2))
        tk.Label(
            self.content, text=display_or_fallback(value), bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.small(), anchor="w",
            justify=tk.LEFT, wraplength=318,
        ).pack(fill=tk.X, pady=(0, 10))

    def _section_label(self, text: str):
        theme = get_theme()
        tk.Label(
            self.content, text=text, bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.body(bold=True), anchor="w",
        ).pack(fill=tk.X, pady=(0, 7))

    def _separator(self):
        theme = get_theme()
        tk.Frame(self.content, bg=theme.border_muted, height=1).pack(fill=tk.X, pady=(2, 12))

    def _status_presentation(self, bookmark: Bookmark) -> tuple[str, str]:
        theme = get_theme()
        if not bookmark.is_valid:
            return _("Needs review"), theme.accent_warning
        if bookmark.read_later:
            return _("Read later"), theme.accent_secondary
        reader_state = getattr(bookmark, "reader_progress_state", "unread")
        if reader_state == "finished":
            return _("Finished"), theme.accent_success
        if reader_state == "in_progress":
            return _("In progress"), theme.accent_primary
        if bookmark.visit_count:
            return _("Read"), theme.accent_success
        return _("Unread"), theme.accent_cyan

    @staticmethod
    def _offline_state(bookmark: Bookmark) -> str:
        path = str(bookmark.snapshot_path or "").strip()
        if not path:
            return _("Not captured")
        try:
            size = Path(path).stat().st_size
        except OSError:
            return _("Capture unavailable")
        if size >= 1024 * 1024:
            rendered = f"{size / (1024 * 1024):.1f} MB"
        else:
            rendered = f"{max(1, round(size / 1024))} KB"
        mime_label = {
            "application/pdf": _("PDF"),
            "image/png": _("PNG image"),
            "image/jpeg": _("JPEG image"),
            "image/gif": _("GIF image"),
            "image/webp": _("WebP image"),
            "text/html": _("HTML"),
        }.get(str(bookmark.snapshot_mime_type or "").lower())
        if mime_label:
            return _("Available ({kind}, {size})").format(
                kind=mime_label,
                size=rendered,
            )
        return _("Available ({size})").format(size=rendered)

    def _show_more_menu(self):
        theme = get_theme()
        menu = tk.Menu(
            self, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
            activebackground=theme.selection, activeforeground=theme.text_primary,
            borderwidth=0,
        )
        if (
            self.current_bookmark
            and self.current_bookmark.snapshot_path
            and self.on_open_offline
        ):
            menu.add_command(
                label=_("Open offline copy"),
                command=self._open_offline_copy,
            )
        menu.add_command(label=_("Edit bookmark"), command=self._edit_bookmark)
        menu.add_separator()
        menu.add_command(label=_("Delete bookmark…"), command=self._delete_bookmark)
        button = self.more_button
        menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height() + 3)

    def _open_bookmark(self):
        if self.current_bookmark and self.on_open:
            self.on_open(self.current_bookmark)

    def _open_offline_copy(self):
        if self.current_bookmark and self.on_open_offline:
            self.on_open_offline(self.current_bookmark)

    def _edit_bookmark(self):
        if self.current_bookmark and self.on_edit:
            self.on_edit(self.current_bookmark)

    def _delete_bookmark(self):
        if self.current_bookmark and self.on_delete:
            self.on_delete(self.current_bookmark)
