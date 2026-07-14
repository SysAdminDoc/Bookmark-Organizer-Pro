"""Actionable cleanup review dialogs for duplicate and tag-lint results."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Callable, Iterable, List, Mapping, Sequence

from bookmark_organizer_pro.i18n import _, format_message
from bookmark_organizer_pro.models import Bookmark

from .foundation import FONTS, truncate_middle
from .tk_interactions import bind_scoped_mousewheel
from .widgets import ModernButton, apply_window_chrome, get_theme


@dataclass(frozen=True)
class CleanupReviewGroup:
    """One selectable cleanup group shown in a review dialog."""

    key: str
    title: str
    subtitle: str
    items: tuple[str, ...]
    action_label: str


@dataclass(frozen=True)
class CleanupApplyResult:
    """Explicit callback outcome used to allow only known-safe retries."""

    message: str
    retryable: bool = False


def _bookmark_label(bookmark: Bookmark, action: str) -> str:
    title = truncate_middle(bookmark.title or bookmark.url or f"Bookmark {bookmark.id}", 64)
    url = truncate_middle(bookmark.url or "", 86)
    return f"{action} #{bookmark.id}: {title} - {url}"


def build_url_duplicate_review_groups(dupes: Mapping[str, Sequence[Bookmark]]) -> List[CleanupReviewGroup]:
    """Build review groups from BookmarkManager.find_duplicates output."""
    groups: List[CleanupReviewGroup] = []
    for index, (canonical_url, bookmarks) in enumerate(sorted(dupes.items()), 1):
        clean = [bm for bm in bookmarks if bm and bm.id is not None]
        if len(clean) <= 1:
            continue
        keep = clean[0]
        extras = clean[1:]
        items = [_bookmark_label(keep, "Keep")]
        items.extend(_bookmark_label(bm, "Remove") for bm in extras)
        groups.append(CleanupReviewGroup(
            key=f"url:{index}:{keep.id}",
            title=truncate_middle(canonical_url or keep.url, 90),
            subtitle=f"{len(extras)} duplicate bookmark(s) will be removed; earliest item is kept.",
            items=tuple(items),
            action_label=f"Remove {len(extras)} duplicate(s)",
        ))
    return groups


def build_hybrid_duplicate_review_groups(report, bookmarks_by_id: Mapping[int, Bookmark]) -> List[CleanupReviewGroup]:
    """Build review groups from HybridDuplicateDetector reports."""
    raw_groups = getattr(report, "groups", report or [])
    groups: List[CleanupReviewGroup] = []
    for index, group in enumerate(raw_groups, 1):
        ids = [int(bookmark_id) for bookmark_id in getattr(group, "bookmark_ids", [])]
        if len(ids) <= 1:
            continue
        canonical_id = int(getattr(group, "canonical_id", ids[0]))
        ordered_ids = [canonical_id] + [bookmark_id for bookmark_id in ids if bookmark_id != canonical_id]
        bookmarks = [bookmarks_by_id[bookmark_id] for bookmark_id in ordered_ids if bookmark_id in bookmarks_by_id]
        if len(bookmarks) <= 1:
            continue
        method = str(getattr(group, "method", "duplicate"))
        confidence = float(getattr(group, "confidence", 0.0))
        keep = bookmarks[0]
        extras = bookmarks[1:]
        items = [_bookmark_label(keep, "Keep")]
        items.extend(_bookmark_label(bm, "Remove") for bm in extras)
        groups.append(CleanupReviewGroup(
            key=f"hybrid:{index}:{canonical_id}",
            title=format_message('{value_0} match for #{value_1}', value_0=method.title(), value_1=canonical_id),
            subtitle=f"Confidence {confidence:.2f}; {len(extras)} duplicate bookmark(s) will be removed.",
            items=tuple(items),
            action_label=f"Remove {len(extras)} duplicate(s)",
        ))
    return groups


def build_tag_lint_review_groups(report) -> List[CleanupReviewGroup]:
    """Build review groups from TagLinter reports."""
    suggestions = getattr(report, "suggestions", report or [])
    groups: List[CleanupReviewGroup] = []
    for index, suggestion in enumerate(suggestions, 1):
        if isinstance(suggestion, dict):
            canonical = str(suggestion.get("canonical", "") or "")
            variants = list(suggestion.get("variants") or suggestion.get("tags") or [])
            bookmark_count = int(suggestion.get("bookmark_count") or suggestion.get("count") or 0)
        else:
            canonical = str(getattr(suggestion, "canonical", "") or "")
            variants = list(getattr(suggestion, "variants", []) or [])
            bookmark_count = int(getattr(suggestion, "bookmark_count", 0) or 0)
        variants = [str(tag) for tag in variants if str(tag).strip()]
        if not canonical or not variants:
            continue
        items = tuple(f"Merge '{variant}' -> '{canonical}'" for variant in variants)
        groups.append(CleanupReviewGroup(
            key=f"tag:{index}:{canonical}",
            title=format_message("Normalize to '{value_0}'", value_0=canonical),
            subtitle=f"{bookmark_count} bookmark(s) affected; {len(variants)} variant tag(s).",
            items=items,
            action_label=f"Merge {len(variants)} variant(s)",
        ))
    return groups


class CleanupReviewDialog(tk.Toplevel):
    """Selectable cleanup queue with apply, skip, safepoint, and restore controls."""

    def __init__(
        self,
        parent: tk.Widget,
        title: str,
        intro: str,
        groups: Iterable[CleanupReviewGroup],
        on_apply: Callable[[List[str]], str | CleanupApplyResult],
        on_restore: Callable[[], bool],
    ):
        super().__init__(parent)
        self._theme = get_theme()
        self._groups = list(groups)
        self._on_apply = on_apply
        self._on_restore = on_restore
        self._vars: dict[str, tk.BooleanVar] = {}
        self._apply_in_progress = False
        self._applied = False
        self._status_var = tk.StringVar(value="Select groups to apply. A safepoint is created before changes.")

        self.title(title)
        self.configure(bg=self._theme.bg_primary)
        self.geometry("880x650")
        self.minsize(760, 520)
        self.transient(parent)
        self.grab_set()
        apply_window_chrome(self)

        self._build(title, intro)
        self.bind("<Escape>", lambda _event: self.destroy())

    def _build(self, title: str, intro: str) -> None:
        theme = self._theme
        header = tk.Frame(self, bg=theme.bg_primary)
        header.pack(fill=tk.X, padx=24, pady=(20, 12))
        tk.Label(header, text=title, bg=theme.bg_primary, fg=theme.text_primary, font=FONTS.title(bold=True)).pack(anchor="w")
        tk.Label(
            header,
            text=intro,
            bg=theme.bg_primary,
            fg=theme.text_secondary,
            font=FONTS.body(),
            wraplength=790,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(6, 0))

        body = tk.Frame(self, bg=theme.bg_primary)
        body.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 12))
        canvas = tk.Canvas(body, bg=theme.bg_primary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(body, orient=tk.VERTICAL, command=canvas.yview)
        cards = tk.Frame(canvas, bg=theme.bg_primary)
        cards.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=cards, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._wheel_binding = bind_scoped_mousewheel(
            canvas, lambda units, _event: canvas.yview_scroll(units, "units")
        )

        for group in self._groups:
            self._add_group(cards, group)

        footer = tk.Frame(self, bg=theme.bg_primary)
        footer.pack(fill=tk.X, padx=24, pady=(0, 18))
        tk.Label(
            footer,
            textvariable=self._status_var,
            bg=theme.bg_primary,
            fg=theme.text_secondary,
            font=FONTS.small(),
            wraplength=500,
            justify=tk.LEFT,
        ).pack(fill=tk.X, pady=(0, 9))
        actions = tk.Frame(footer, bg=theme.bg_primary)
        actions.pack(fill=tk.X)
        ModernButton(actions, text=_("Close"), command=self.destroy, padx=14, pady=7).pack(side=tk.RIGHT, padx=(8, 0))
        ModernButton(actions, text=_("Restore Safepoint"), command=self._restore, padx=14, pady=7).pack(side=tk.LEFT)
        self.skip_button = ModernButton(actions, text=_("Skip Selected"), command=self._skip_selected, padx=14, pady=7)
        self.skip_button.pack(side=tk.RIGHT, padx=(8, 0))
        self.apply_button = ModernButton(actions, text=_("Apply Selected"), command=self._apply_selected, style="primary", padx=14, pady=7)
        self.apply_button.pack(side=tk.RIGHT)

    def _add_group(self, parent: tk.Widget, group: CleanupReviewGroup) -> None:
        theme = self._theme
        var = tk.BooleanVar(value=True)
        self._vars[group.key] = var
        card = tk.Frame(
            parent,
            bg=theme.bg_secondary,
            highlightthickness=1,
            highlightbackground=theme.border_muted,
            padx=14,
            pady=12,
        )
        card.pack(fill=tk.X, pady=(0, 10))
        check = tk.Checkbutton(
            card,
            variable=var,
            command=self._selection_changed,
            text=group.title,
            bg=theme.bg_secondary,
            fg=theme.text_primary,
            selectcolor=theme.bg_tertiary,
            activebackground=theme.bg_secondary,
            activeforeground=theme.text_primary,
            font=FONTS.subtitle(bold=True),
            anchor="w",
        )
        check.pack(anchor="w")
        tk.Label(
            card,
            text=format_message('{value_0} Action: {value_1}.', value_0=group.subtitle, value_1=group.action_label),
            bg=theme.bg_secondary,
            fg=theme.text_secondary,
            font=FONTS.small(),
            wraplength=780,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(4, 8))
        for item in group.items:
            tk.Label(
                card,
                text=format_message('- {value_0}', value_0=item),
                bg=theme.bg_secondary,
                fg=theme.text_muted,
                font=FONTS.tiny(),
                wraplength=780,
                justify=tk.LEFT,
            ).pack(anchor="w", pady=1)

    def _selection_changed(self) -> None:
        count = len(self.selected_keys())
        self._status_var.set(
            f"{count} group(s) selected. A safepoint will be created before changes."
            if count else "Nothing selected. Choose at least one group to continue."
        )
        enabled = bool(count and not self._apply_in_progress and not self._applied)
        self.apply_button.set_state("normal" if enabled else "disabled")
        self.skip_button.set_state("normal" if enabled else "disabled")

    def selected_keys(self) -> List[str]:
        return [key for key, var in self._vars.items() if var.get()]

    def _skip_selected(self) -> None:
        if self._apply_in_progress or self._applied:
            return
        selected = self.selected_keys()
        for key in selected:
            self._vars[key].set(False)
        self._selection_changed()

    def _apply_selected(self) -> None:
        if self._apply_in_progress or self._applied:
            return
        selected = self.selected_keys()
        if not selected:
            self._status_var.set("No groups selected.")
            return
        self._apply_in_progress = True
        self.apply_button.set_state("disabled")
        self.skip_button.set_state("disabled")
        try:
            outcome = self._on_apply(list(selected))
        except Exception as exc:
            self._apply_in_progress = False
            self._applied = True
            self._status_var.set(f"Cleanup failed: {exc}. Reopen this workflow before retrying.")
            return
        result = outcome if isinstance(outcome, CleanupApplyResult) else CleanupApplyResult(str(outcome))
        self._apply_in_progress = False
        if result.retryable:
            self._status_var.set(result.message)
            self._selection_changed()
            return
        self._applied = True
        for key in selected:
            self._vars[key].set(False)
        self._status_var.set(result.message)

    def _restore(self) -> None:
        restored = False
        try:
            restored = bool(self._on_restore())
        except Exception:
            restored = False
        self._status_var.set("Restored the last safepoint." if restored else "No safepoint could be restored.")
