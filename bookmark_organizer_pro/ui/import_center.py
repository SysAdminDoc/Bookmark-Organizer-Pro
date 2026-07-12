"""Guided migration center for desktop bookmark imports."""

from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable, List, Optional

from bookmark_organizer_pro.i18n import _

from .foundation import FONTS
from .widgets import ModernButton, apply_window_chrome, get_theme


@dataclass(frozen=True)
class ImportSource:
    """One source-specific import path shown in the migration center."""

    key: str
    title: str
    description: str
    accepted_formats: str
    privacy_note: str
    duplicate_policy: str
    import_summary: str
    next_action: str
    action_label: str
    action_kind: str
    action_arg: str = ""
    enabled: bool = True


def _browser_source(browser: str, detected: bool) -> ImportSource:
    browser_title = browser.title()
    if browser == "edge":
        browser_title = "Edge"
    if browser == "safari":
        browser_title = "Safari"

    if detected and browser in {"chrome", "firefox", "edge"}:
        accepted = "Detected local profile"
        action_label = f"Import {browser_title} Profile"
        action_kind = "browser_profile"
        next_action = "Review imported folders, then run duplicate and tag checks."
    else:
        accepted = "Bookmark HTML export (.html/.htm)"
        action_label = "Choose Export File"
        action_kind = "file"
        next_action = "Export bookmarks from the browser, then choose the HTML file here."

    return ImportSource(
        key=f"browser-{browser}",
        title=f"{browser_title} bookmarks",
        description="Bring over browser folders and saved pages.",
        accepted_formats=accepted,
        privacy_note="Processed locally; source browser data is read-only and never uploaded.",
        duplicate_policy="Existing normalized URLs are skipped before saving.",
        import_summary="Progress shows bookmarks added and duplicates skipped.",
        next_action=next_action,
        action_label=action_label,
        action_kind=action_kind,
        action_arg=browser,
    )


def build_import_sources(detected_browsers: Iterable[str] = ()) -> List[ImportSource]:
    """Return the source cards shown by the import center."""
    detected = {str(name).lower() for name in detected_browsers}
    sources = [
        _browser_source("chrome", "chrome" in detected),
        _browser_source("firefox", "firefox" in detected),
        _browser_source("edge", "edge" in detected),
        _browser_source("safari", False),
        ImportSource(
            key="firefox-backup",
            title="Firefox bookmark backup",
            description="Import Firefox bookmarkbackups JSON with folders and tags preserved.",
            accepted_formats="Firefox bookmarkbackups .json or .jsonlz4",
            privacy_note="The backup is parsed locally and the Firefox profile is not modified.",
            duplicate_policy="Existing normalized URLs are skipped; tag-only references are merged.",
            import_summary="Result shows added, duplicate, and invalid/missing URL counts.",
            next_action="Review imported folder categories, then run tag cleanup if needed.",
            action_label="Choose Firefox Backup",
            action_kind="service",
            action_arg="firefox-backup",
        ),
        ImportSource(
            key="pocket",
            title="Pocket export",
            description="Migrate saved Pocket links after exporting from Pocket.",
            accepted_formats="Pocket HTML or JSON export",
            privacy_note="The export file is parsed locally; no Pocket account connection is made.",
            duplicate_policy="Normalized duplicate URLs are skipped.",
            import_summary="Result shows added bookmarks and skipped duplicates.",
            next_action="Review imported tags and add items to Read Later when useful.",
            action_label="Choose Pocket File",
            action_kind="service",
            action_arg="pocket",
        ),
        ImportSource(
            key="arc",
            title="Arc Browser sidebar",
            description="Import Arc StorableSidebar exports into a local category.",
            accepted_formats="StorableSidebar.json",
            privacy_note="The local JSON file is parsed without modifying Arc data.",
            duplicate_policy="Existing normalized URLs are skipped.",
            import_summary="Result shows added bookmarks and skipped duplicates.",
            next_action="Review spaces/folders that were mapped into imported categories.",
            action_label="Choose Arc JSON",
            action_kind="service",
            action_arg="arc",
        ),
        ImportSource(
            key="linkwarden",
            title="Linkwarden export",
            description="Preflight Linkwarden links, collections, tags, notes, and state before import.",
            accepted_formats="Linkwarden JSON export",
            privacy_note="The export is analyzed locally and never uploaded.",
            duplicate_policy="The preflight identifies normalized URL duplicates before apply.",
            import_summary="A field-fidelity report lists preserved, transformed, and unsupported values.",
            next_action="Review the report, then apply from its restorable safepoint.",
            action_label="Preflight JSON",
            action_kind="migration",
            action_arg="linkwarden",
        ),
        ImportSource(
            key="karakeep",
            title="Karakeep export",
            description="Preflight Karakeep bookmarks, lists, tags, notes, and state before import.",
            accepted_formats="Karakeep JSON export",
            privacy_note="The export is analyzed locally and never uploaded.",
            duplicate_policy="The preflight identifies normalized URL duplicates before apply.",
            import_summary="A field-fidelity report lists preserved, transformed, and unsupported values.",
            next_action="Review the report, then apply from its restorable safepoint.",
            action_label="Preflight JSON",
            action_kind="migration",
            action_arg="karakeep",
        ),
        ImportSource(
            key="raindrop",
            title="Raindrop CSV",
            description="Bring over Raindrop collections, tags, notes, and saved dates.",
            accepted_formats="Raindrop CSV export",
            privacy_note="CSV content stays on this machine.",
            duplicate_policy="Existing URLs are skipped; imported tags and notes are preserved.",
            import_summary="Result shows added bookmarks and skipped duplicates.",
            next_action="Run tag cleanup to normalize imported tag names.",
            action_label="Preflight CSV",
            action_kind="migration",
            action_arg="raindrop",
        ),
        ImportSource(
            key="readwise",
            title="Readwise-compatible CSV",
            description="Import Readwise Reader document exports and compatible CSV files.",
            accepted_formats="CSV with URL, Title, Tags, and note/date columns",
            privacy_note="CSV content is parsed locally and not sent to Readwise.",
            duplicate_policy="Existing normalized URLs are skipped.",
            import_summary="Result shows added bookmarks and skipped duplicates.",
            next_action="Open the reader view for saved articles that need highlights or review.",
            action_label="Preflight CSV",
            action_kind="migration",
            action_arg="readwise",
        ),
        ImportSource(
            key="chrome-reading-list",
            title="Chrome Reading List",
            description="Use the browser extension side panel to save Reading List entries.",
            accepted_formats="Chrome Reading List API through the MV3 extension",
            privacy_note="The extension sends URLs only to the local API using your bearer token.",
            duplicate_policy="The local API rejects URLs already in the library.",
            import_summary="The side panel reports how many Reading List items were imported.",
            next_action="Start the local API, open the extension side panel, then use Add > Reading List.",
            action_label="Show Steps",
            action_kind="reading_list_help",
        ),
    ]
    return sources


class ImportCenterDialog(tk.Toplevel):
    """Source-specific import launcher with migration guidance."""

    def __init__(
        self,
        parent: tk.Widget,
        sources: Iterable[ImportSource],
        on_select: Callable[[ImportSource], None],
        intro: Optional[str] = None,
    ):
        super().__init__(parent)
        self._sources = list(sources)
        self._on_select = on_select
        self._theme = get_theme()

        self.title(_("Import Center"))
        self.configure(bg=self._theme.bg_primary)
        self.geometry("860x640")
        self.minsize(760, 520)
        self.transient(parent)
        self.grab_set()
        apply_window_chrome(self)

        self._build(intro)
        self.bind("<Escape>", lambda _event: self.destroy())

    def _build(self, intro: Optional[str]) -> None:
        theme = self._theme
        header = tk.Frame(self, bg=theme.bg_primary)
        header.pack(fill=tk.X, padx=24, pady=(22, 14))

        tk.Label(
            header,
            text=_("Import Center"),
            bg=theme.bg_primary,
            fg=theme.text_primary,
            font=FONTS.title(bold=True),
        ).pack(anchor="w")

        tk.Label(
            header,
            text=intro or _("Choose the source that matches your export. Each path stays local and skips duplicates."),
            bg=theme.bg_primary,
            fg=theme.text_secondary,
            font=FONTS.body(),
            wraplength=780,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(7, 0))

        body = tk.Frame(self, bg=theme.bg_primary)
        body.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 12))

        canvas = tk.Canvas(body, bg=theme.bg_primary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(body, orient=tk.VERTICAL, command=canvas.yview)
        self._cards = tk.Frame(canvas, bg=theme.bg_primary)
        self._cards.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self._cards, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for source in self._sources:
            self._add_card(source)

        footer = tk.Frame(self, bg=theme.bg_primary)
        footer.pack(fill=tk.X, padx=24, pady=(0, 18))
        ModernButton(footer, text=_("Close"), command=self.destroy, padx=18, pady=8).pack(side=tk.RIGHT)

    def _add_card(self, source: ImportSource) -> None:
        theme = self._theme
        card = tk.Frame(
            self._cards,
            bg=theme.bg_secondary,
            highlightthickness=1,
            highlightbackground=theme.border_muted,
            padx=16,
            pady=14,
        )
        card.pack(fill=tk.X, pady=(0, 10))

        top = tk.Frame(card, bg=theme.bg_secondary)
        top.pack(fill=tk.X)

        title_col = tk.Frame(top, bg=theme.bg_secondary)
        title_col.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(
            title_col,
            text=source.title,
            bg=theme.bg_secondary,
            fg=theme.text_primary,
            font=FONTS.subtitle(bold=True),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            title_col,
            text=source.description,
            bg=theme.bg_secondary,
            fg=theme.text_secondary,
            font=FONTS.small(),
            wraplength=560,
            justify=tk.LEFT,
            anchor="w",
        ).pack(anchor="w", pady=(3, 0))

        ModernButton(
            top,
            text=source.action_label,
            command=lambda s=source: self._select(s),
            style="primary" if source.enabled else "default",
            state="normal" if source.enabled else "disabled",
            padx=14,
            pady=7,
        ).pack(side=tk.RIGHT, padx=(14, 0))

        details = [
            ("Accepted", source.accepted_formats),
            ("Privacy", source.privacy_note),
            ("Duplicates", source.duplicate_policy),
            ("Summary", source.import_summary),
            ("Next", source.next_action),
        ]
        grid = tk.Frame(card, bg=theme.bg_secondary)
        grid.pack(fill=tk.X, pady=(12, 0))
        for row, (label, value) in enumerate(details):
            tk.Label(
                grid,
                text=f"{label}:",
                bg=theme.bg_secondary,
                fg=theme.text_muted,
                font=FONTS.tiny(bold=True),
                width=11,
                anchor="w",
            ).grid(row=row, column=0, sticky="nw", pady=2)
            tk.Label(
                grid,
                text=value,
                bg=theme.bg_secondary,
                fg=theme.text_secondary,
                font=FONTS.tiny(),
                wraplength=690,
                justify=tk.LEFT,
                anchor="w",
            ).grid(row=row, column=1, sticky="ew", pady=2)
        grid.columnconfigure(1, weight=1)

    def _select(self, source: ImportSource) -> None:
        self.grab_release()
        self.destroy()
        self._on_select(source)
