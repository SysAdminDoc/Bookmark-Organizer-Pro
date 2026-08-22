"""Tools menu actions for the app coordinator."""

from __future__ import annotations

import json
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from bookmark_organizer_pro.i18n import format_message

try:
                from bookmark_organizer_pro.services.egress import public_egress as requests
except ImportError:  # pragma: no cover - optional runtime dependency
    requests = None

from bookmark_organizer_pro.constants import DATA_DIR
from bookmark_organizer_pro.core.category_manager import get_category_icon
from bookmark_organizer_pro.i18n import _
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Category
from bookmark_organizer_pro.services.favicons import (
    FAVICON_PROXY_NONE,
    FAVICON_PROXY_PROVIDERS,
    FaviconPrivacyPolicy,
    save_favicon_policy,
)
from bookmark_organizer_pro.services.mcp_auth import MCPTokenManager
from bookmark_organizer_pro.services.settings_store import load_settings
from bookmark_organizer_pro.services.snapshot import SnapshotArchiver, SnapshotFailureStore
from bookmark_organizer_pro.ui.cleanup_review import (
                CleanupApplyResult,
                CleanupReviewDialog,
                build_hybrid_duplicate_review_groups,
                build_tag_lint_review_groups,
                build_url_duplicate_review_groups,
)
from bookmark_organizer_pro.ui.foundation import FONTS, readable_text_on
from bookmark_organizer_pro.ui.graph_view import GraphViewDialog
from bookmark_organizer_pro.ui.highlights_workspace import HighlightsWorkspaceDialog
from bookmark_organizer_pro.ui.organization_rules import OrganizationRulesDialog
from bookmark_organizer_pro.ui.management_dialogs import (
    CategoryManagementDialog,
    CredentialSecurityDialog,
    CustomFaviconDialog,
)
from bookmark_organizer_pro.ui.read_later_queue import ReadLaterQueueDialog
from bookmark_organizer_pro.ui.reader_view import ReaderViewDialog
from bookmark_organizer_pro.ui.tk_interactions import make_keyboard_activatable
from bookmark_organizer_pro.ui.treeview import (
                accessible_list_mode_enabled,
                save_accessible_list_mode,
)
from bookmark_organizer_pro.ui.widget_runtime import _open_external_url
from bookmark_organizer_pro.ui.widgets import (
                AnalyticsDashboard,
                ModernButton,
                ThemeSelectorDialog,
                Tooltip,
                apply_window_chrome,
                get_theme,
)


class ToolsActionsMixin:
    """Tools menu, maintenance, and utility actions used by the app coordinator."""

    def _show_settings_menu(self):
        """Show settings dropdown from the gear button."""
        theme = get_theme()
        menu = tk.Menu(self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                       font=FONTS.body(), activebackground=theme.bg_hover,
                       activeforeground=theme.text_primary, bd=0)
        menu.add_command(label=_("Assistant Provider Settings"), command=self._show_ai_settings)
        menu.add_command(label=_("Theme Settings"), command=lambda: ThemeSelectorDialog(self.root, self.theme_manager))
        menu.add_command(label=_("Scheduled Snapshots"), command=self._show_snapshot_settings)
        menu.add_command(
            label=_("Access Credentials"),
            command=self._show_credential_security,
        )
        self._accessible_list_var = tk.BooleanVar(value=accessible_list_mode_enabled())
        menu.add_checkbutton(
            label=_("Accessible bookmark table"),
            variable=self._accessible_list_var,
            command=self._save_accessible_list_preference,
        )
        self._favicon_enabled_var = tk.BooleanVar(
            value=self.favicon_manager.enabled
        )
        menu.add_checkbutton(
            label=_("Show and fetch site icons"),
            variable=self._favicon_enabled_var,
            command=self._save_favicon_enabled_preference,
        )
        self._favicon_proxy_var = tk.StringVar(
            value=self.favicon_manager.proxy_provider
        )
        proxy_menu = tk.Menu(
            menu,
            tearoff=0,
            bg=theme.bg_secondary,
            fg=theme.text_primary,
            font=FONTS.body(),
            activebackground=theme.bg_hover,
            activeforeground=theme.text_primary,
            bd=0,
        )
        proxy_menu.add_radiobutton(
            label=_("None — same-origin only"),
            variable=self._favicon_proxy_var,
            value=FAVICON_PROXY_NONE,
            command=self._save_favicon_proxy_preference,
        )
        proxy_menu.add_radiobutton(
            label=_("Google — shares missing domains"),
            variable=self._favicon_proxy_var,
            value="google",
            command=self._save_favicon_proxy_preference,
        )
        proxy_menu.add_radiobutton(
            label=_("DuckDuckGo — shares missing domains"),
            variable=self._favicon_proxy_var,
            value="duckduckgo",
            command=self._save_favicon_proxy_preference,
        )
        menu.add_cascade(label=_("Fallback icon proxy"), menu=proxy_menu)
        menu.add_command(label=_("Manage Categories"), command=self._show_category_manager)
        menu.add_separator()
        menu.add_command(label=_("Flatten All Folders"), command=self._flatten_all_folders)
        menu.add_command(label=_("Clear All Tags"), command=self._clear_all_tags)
        menu.add_separator()
        menu.add_command(label=_("Backup Now"), command=self._backup_now)
        menu.add_command(label=_("Restore Last Maintenance Safepoint"), command=self._restore_last_maintenance_safepoint)

        x = self.settings_btn.winfo_rootx()
        y = self.settings_btn.winfo_rooty() + self.settings_btn.winfo_height()
        menu.tk_popup(x, y)

    def _show_credential_security(self):
        """Open the named MCP/REST credential inventory."""
        manager = getattr(self, "_credential_manager", None)
        if manager is None:
            manager = MCPTokenManager()
            self._credential_manager = manager
        CredentialSecurityDialog(self.root, manager)

    def _save_accessible_list_preference(self):
        """Persist the semantic table preference for the next app launch."""
        enabled = bool(self._accessible_list_var.get())
        save_accessible_list_mode(enabled)
        mode = _("enabled") if enabled else _("disabled")
        self._show_toast(
            _("Accessible bookmark table {mode}; applies on next launch").format(mode=mode),
            "success",
        )

    def _save_favicon_enabled_preference(self):
        """Persist display/fetch consent and immediately cancel when disabled."""
        policy = FaviconPrivacyPolicy(
            enabled=bool(self._favicon_enabled_var.get()),
            proxy_provider=self.favicon_manager.proxy_provider,
        )
        policy = save_favicon_policy(policy)
        self.favicon_manager.set_policy(policy)
        self._refresh_bookmark_list()
        if policy.enabled:
            self.favicon_manager.queue_bookmarks(
                self.bookmark_manager.get_all_bookmarks()
            )
            self._show_toast(
                _("Site icons enabled; same-origin sources are tried first"),
                "success",
            )
        else:
            self._show_toast(
                _("Site icons disabled; queued downloads were cancelled"),
                "success",
            )

    def _save_favicon_proxy_preference(self):
        """Require named consent before a saved domain can reach a proxy."""
        selected = str(self._favicon_proxy_var.get() or FAVICON_PROXY_NONE)
        previous = self.favicon_manager.proxy_provider
        if selected not in FAVICON_PROXY_PROVIDERS:
            selected = FAVICON_PROXY_NONE
        if selected != FAVICON_PROXY_NONE:
            disclosure = str(FAVICON_PROXY_PROVIDERS[selected]["disclosure"])
            if not messagebox.askyesno(
                _("Share missing favicon domains?"),
                _(
                    "{provider} is a third-party favicon proxy. {disclosure}\n\n"
                    "Bookmark titles, paths, queries, and fragments are not sent. "
                    "Enable this fallback?"
                ).format(
                    provider=selected.title(),
                    disclosure=disclosure,
                ),
                parent=self.root,
            ):
                self._favicon_proxy_var.set(previous)
                return

        policy = save_favicon_policy(
            FaviconPrivacyPolicy(
                enabled=self.favicon_manager.enabled,
                proxy_provider=selected,
            )
        )
        self.favicon_manager.set_policy(policy)
        if policy.enabled:
            self.favicon_manager.queue_bookmarks(
                self.bookmark_manager.get_all_bookmarks()
            )
        provider_label = (
            _("same-origin only")
            if selected == FAVICON_PROXY_NONE
            else _("{provider} fallback").format(provider=selected.title())
        )
        self._show_toast(
            _("Site icon privacy set to {provider}").format(
                provider=provider_label
            ),
            "success",
        )

    def _show_snapshot_settings(self):
        """Edit the persisted scheduled-snapshot preference."""
        theme = get_theme()
        settings = load_settings()
        scheduler = self._ensure_snapshot_scheduler()
        try:
            initial_interval = max(
                1, min(24 * 30, int(settings.get("auto_snapshot_interval_hours", 24) or 24))
            )
        except (TypeError, ValueError):
            initial_interval = 24
        enabled_var = tk.BooleanVar(
            value=bool(settings.get("auto_snapshot_enabled", False)),
        )
        interval_var = tk.IntVar(value=initial_interval)

        dialog = tk.Toplevel(self.root)
        dialog.title(_("Scheduled Snapshots"))
        dialog.configure(bg=theme.bg_primary)
        dialog.geometry("620x430")
        dialog.minsize(520, 360)
        dialog.transient(self.root)
        dialog.grab_set()
        apply_window_chrome(dialog)

        header = tk.Frame(dialog, bg=theme.bg_dark, padx=20, pady=16)
        header.pack(fill=tk.X)
        tk.Label(
            header, text=_("Scheduled Snapshots"), bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.title(bold=True),
        ).pack(anchor="w")
        tk.Label(
            header,
            text=_("Re-capture selected bookmarks on a bounded local schedule."),
            bg=theme.bg_dark, fg=theme.text_secondary, font=FONTS.small(),
            wraplength=560, justify=tk.LEFT,
        ).pack(anchor="w", pady=(5, 0))

        body = tk.Frame(dialog, bg=theme.bg_primary, padx=20, pady=18)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Checkbutton(
            body, text=_("Enable scheduled snapshots"), variable=enabled_var,
        ).pack(anchor="w", pady=(0, 14))

        interval_row = tk.Frame(body, bg=theme.bg_primary)
        interval_row.pack(fill=tk.X, anchor="w")
        tk.Label(
            interval_row, text=_("Capture interval (hours)"),
            bg=theme.bg_primary, fg=theme.text_primary, font=FONTS.body(),
        ).pack(side=tk.LEFT)
        ttk.Spinbox(
            interval_row, from_=1, to=24 * 30, textvariable=interval_var,
            width=8, wrap=False,
        ).pack(side=tk.LEFT, padx=(12, 0))

        scheduled_count = len(scheduler.list_scheduled()) if scheduler else 0
        tk.Label(
            body,
            text=format_message(
                "{count} bookmark(s) currently scheduled. Use Tools to add or remove the selected bookmarks.",
                count=scheduled_count,
            ),
            bg=theme.bg_primary, fg=theme.text_secondary, font=FONTS.small(),
            wraplength=560, justify=tk.LEFT, anchor="w",
        ).pack(fill=tk.X, pady=(18, 0))
        tk.Label(
            body,
            text=_("Failures remain visible in Snapshot Failure Report and retry with bounded backoff."),
            bg=theme.bg_primary, fg=theme.text_muted, font=FONTS.tiny(),
            wraplength=560, justify=tk.LEFT, anchor="w",
        ).pack(fill=tk.X, pady=(8, 0))

        footer = tk.Frame(dialog, bg=theme.bg_secondary, padx=16, pady=12)
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        def save():
            try:
                interval = int(interval_var.get())
            except (TypeError, ValueError, tk.TclError):
                self._show_toast(_("Enter a valid snapshot interval."), "error")
                return
            if self._set_snapshot_schedule_preferences(bool(enabled_var.get()), interval):
                dialog.destroy()
                state = _("enabled") if enabled_var.get() else _("paused")
                self._set_status(format_message(
                    "Scheduled snapshots {state} ({hours}h interval)",
                    state=state, hours=max(1, min(24 * 30, interval)),
                ))
                self._show_toast(
                    format_message("Scheduled snapshots {state}", state=state),
                    "success",
                )

        ModernButton(
            footer, text=_("Cancel"), command=dialog.destroy,
            padx=16, pady=7,
        ).pack(side=tk.RIGHT, padx=(8, 0))
        ModernButton(
            footer, text=_("Save Settings"), command=save, style="success",
            padx=18, pady=7,
        ).pack(side=tk.RIGHT)
        dialog.bind("<Escape>", lambda _event: dialog.destroy())

    def _schedule_selected_snapshots(self):
        """Add the current selection to the persisted snapshot schedule."""
        bookmark_ids = [
            int(bookmark_id)
            for bookmark_id in (getattr(self, "selected_bookmarks", []) or [])
            if bookmark_id is not None
        ]
        if not bookmark_ids:
            self._show_toast(_("Select one or more bookmarks first."), "info")
            return
        scheduler = self._ensure_snapshot_scheduler()
        if scheduler is None:
            self._show_toast(_("Scheduled snapshots could not be initialized."), "error")
            return
        for bookmark_id in bookmark_ids:
            scheduler.add(bookmark_id)
        settings = load_settings()
        try:
            interval = int(
                settings.get("auto_snapshot_interval_hours", scheduler.interval_hours)
                or scheduler.interval_hours
            )
        except (TypeError, ValueError):
            interval = scheduler.interval_hours
        if not self._set_snapshot_schedule_preferences(True, interval):
            return
        self._set_status(format_message(
            "Scheduled {count} bookmark(s) for automatic snapshots",
            count=len(bookmark_ids),
        ))
        self._show_toast(
            format_message("Scheduled {count} bookmark(s)", count=len(bookmark_ids)),
            "success",
        )

    def _unschedule_selected_snapshots(self):
        """Remove the current selection from the persisted snapshot schedule."""
        bookmark_ids = [
            int(bookmark_id)
            for bookmark_id in (getattr(self, "selected_bookmarks", []) or [])
            if bookmark_id is not None
        ]
        if not bookmark_ids:
            self._show_toast(_("Select one or more bookmarks first."), "info")
            return
        scheduler = self._ensure_snapshot_scheduler()
        if scheduler is None:
            self._show_toast(_("Scheduled snapshots could not be initialized."), "error")
            return
        removed = 0
        for bookmark_id in bookmark_ids:
            if scheduler.is_scheduled(bookmark_id):
                removed += 1
            scheduler.remove(bookmark_id)
        if not scheduler.list_scheduled():
            scheduler.stop()
        self._set_status(format_message(
            "Removed {count} scheduled snapshot(s)", count=removed,
        ))
        self._show_toast(
            format_message("Removed {count} scheduled snapshot(s)", count=removed),
            "success",
        )

    def _show_tools_menu(self):
        """Show tools menu"""
        theme = get_theme()
        
        menu = tk.Menu(self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                      font=FONTS.body(), activebackground=theme.bg_hover,
                      activeforeground=theme.text_primary, bd=0)
        
        menu.add_command(label=_("Manage Categories"), command=self._show_category_manager)
        menu.add_command(label=_("Categorize All Bookmarks"), command=self._categorize_all_bookmarks)
        menu.add_command(label=_("Import Categories File"), command=self._import_categories_file)
        menu.add_command(label=_("Set Custom Favicon"), command=self._show_custom_favicon_dialog)
        menu.add_separator()

        menu.add_command(label=_("Flatten All Folders"), command=self._flatten_all_folders)
        menu.add_command(label=_("Clear All Categories"), command=self._clear_all_categories)
        menu.add_command(label=_("Clear All Tags"), command=self._clear_all_tags)
        menu.add_separator()

        menu.add_command(label=_("Check All Links"), command=self._check_all_links)
        menu.add_command(label=_("View Dead Links"), command=self._view_dead_links)
        menu.add_command(label=_("Schedule Selected Snapshots"), command=self._schedule_selected_snapshots)
        menu.add_command(label=_("Remove Selected Snapshot Schedules"), command=self._unschedule_selected_snapshots)
        menu.add_command(label=_("Scheduled Snapshot Settings"), command=self._show_snapshot_settings)
        menu.add_command(label=_("Snapshot Failure Report"), command=self._view_snapshot_failures)
        menu.add_command(label=_("Find Duplicates"), command=self._find_duplicates)
        menu.add_command(label=_("Smart Duplicate Scan"), command=self._smart_duplicate_scan)
        menu.add_command(label=_("Lint Tags"), command=self._lint_tags_gui)
        menu.add_command(label=_("Clean Tracking Parameters"), command=self._clean_urls)
        menu.add_separator()
        menu.add_command(label=_("Smart Collections"), command=self._show_smart_collections)
        menu.add_command(label=_("Read Later Queue"), command=self._show_read_later_queue)
        menu.add_command(label=_("Reader View"), command=self._open_reader_view)
        menu.add_command(label=_("Highlights workspace"), command=self._open_highlights_workspace)
        menu.add_command(label=_("Organization rules"), command=self._open_organization_rules)
        menu.add_command(label=_("Fetch YouTube Transcript…"), command=self._fetch_youtube_transcripts)
        menu.add_command(label=_("Graph View"), command=self._open_graph_view)
        menu.add_command(label=_("Full Analytics"), command=self._show_analytics)
        menu.add_command(label=_("Migrate to SQLite"), command=self._migrate_to_sqlite)
        menu.add_command(label=_("Backup Now"), command=self._backup_now)
        menu.add_command(label=_("Restore Last Maintenance Safepoint"), command=self._restore_last_maintenance_safepoint)
        menu.add_separator()
        menu.add_command(label=_("Redownload All Favicons"), command=self._redownload_all_favicons)
        menu.add_command(label=_("Redownload Missing Favicons"), command=self._redownload_missing_favicons)
        menu.add_command(label=_("Clear Favicon Cache"), command=self._clear_favicon_cache)
        
        # Position below button
        x = self.tools_btn.winfo_rootx()
        y = self.tools_btn.winfo_rooty() + self.tools_btn.winfo_height()
        menu.tk_popup(x, y)

    def _toast(self, message: str, style: str = "info") -> None:
        if hasattr(self, "_show_toast"):
            self._show_toast(message, style)

    def _begin_maintenance_workflow(self) -> None:
        self._last_maintenance_safepoint = ""
        self._maintenance_safepoint_locked = False

    def _create_maintenance_safepoint(self, label: str) -> str | None:
        existing = getattr(self, "_last_maintenance_safepoint", "")
        if existing and getattr(self, "_maintenance_safepoint_locked", False):
            return existing
        try:
            create_safepoint = getattr(self.bookmark_manager, "create_safepoint", None)
            if not create_safepoint:
                raise RuntimeError("bookmark storage does not support safepoints")
            safepoint = create_safepoint(label)
            if not safepoint:
                raise RuntimeError("safepoint was not created")
            self._last_maintenance_safepoint = safepoint
            self._maintenance_safepoint_locked = True
            return safepoint
        except Exception as exc:
            log.warning("Maintenance safepoint failed before %s: %s", label, exc)
            self._set_status(format_message(
                "{label} skipped: recovery safepoint unavailable",
                label=label.replace("-", " ").title(),
            ))
            self._toast("Could not create a recovery safepoint; no changes were made", "error")
            return None

    def _restore_last_maintenance_safepoint(self) -> bool:
        safepoint = getattr(self, "_last_maintenance_safepoint", "")
        if not safepoint:
            self._set_status("No maintenance safepoint is available yet")
            self._toast("No maintenance safepoint is available yet", "info")
            return False

        try:
            if self.bookmark_manager.restore_backup(safepoint):
                self._last_maintenance_safepoint = ""
                self._maintenance_safepoint_locked = False
                self._refresh_all()
                self._set_status("Restored the last maintenance safepoint")
                self._toast("Restored the last maintenance safepoint", "success")
                return True
        except Exception as exc:
            log.exception("Failed to restore maintenance safepoint %s", safepoint)
            self._set_status(format_message(
                "Maintenance safepoint restore failed: {error}", error=exc,
            ))
            self._toast("Maintenance safepoint restore failed; see logs", "error")
            return False

        self._set_status("Maintenance safepoint restore failed")
        self._toast("Maintenance safepoint restore failed; see logs", "error")
        return False

    def _show_cleanup_review_dialog(self, title: str, intro: str, groups, on_apply) -> None:
        self._begin_maintenance_workflow()
        CleanupReviewDialog(
            self.root,
            title=title,
            intro=intro,
            groups=groups,
            on_apply=on_apply,
            on_restore=self._restore_last_maintenance_safepoint,
        )

    def _show_nonblocking_report(
        self,
        title: str,
        lines,
        status: str,
        toast: str | None = None,
        actions: list[tuple[str, object, str]] | None = None,
    ) -> None:
        text = "\n".join(lines) if isinstance(lines, list) else str(lines)
        self._set_status(status)
        if toast:
            self._toast(toast, "info")

        root = getattr(self, "root", None)
        if root is None or not hasattr(root, "winfo_exists"):
            return

        try:
            theme = get_theme()
            win = tk.Toplevel(root)
            win.title(title)
            win.configure(bg=theme.bg_primary)
            win.geometry("680x430")
            win.minsize(520, 320)
            win.transient(root)
            apply_window_chrome(win)

            tk.Label(
                win, text=title, bg=theme.bg_primary, fg=theme.text_primary,
                font=FONTS.subtitle(bold=True)
            ).pack(anchor="w", padx=18, pady=(16, 6))

            body_frame = tk.Frame(win, bg=theme.bg_primary)
            body_frame.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 12))
            scroll = tk.Scrollbar(body_frame)
            body = tk.Text(
                body_frame, bg=theme.bg_secondary, fg=theme.text_primary,
                insertbackground=theme.text_primary, font=FONTS.mono(),
                relief=tk.FLAT, wrap=tk.WORD, yscrollcommand=scroll.set,
                padx=12, pady=10, borderwidth=0, highlightthickness=1,
                highlightbackground=theme.border_muted,
            )
            scroll.configure(command=body.yview)
            scroll.pack(side=tk.RIGHT, fill=tk.Y)
            body.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            body.insert("1.0", text)
            body.configure(state=tk.DISABLED)

            footer = tk.Frame(win, bg=theme.bg_primary)
            footer.pack(fill=tk.X, padx=18, pady=(0, 16))
            for label, command, style in actions or []:
                ModernButton(
                    footer,
                    text=label,
                    command=command,
                    style=style,
                    padx=18,
                    pady=8,
                ).pack(side=tk.LEFT, padx=(0, 8))
            ModernButton(footer, text=_("Close"), command=win.destroy, padx=22, pady=8).pack(side=tk.RIGHT)
            win.bind("<Escape>", lambda _event: win.destroy())
        except Exception as exc:
            log.warning("Could not show non-blocking report '%s': %s", title, exc)

    # ── Bulk cleanup ─────────────────────────────────────────────────

    def _flatten_all_folders(self):
        """Move every bookmark to a flat 'Uncategorized / Needs Review' category."""
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        if not bookmarks:
            self._show_toast("No bookmarks to flatten", "info")
            return

        categorized = [bm for bm in bookmarks if bm.category and bm.category != "Uncategorized / Needs Review"]
        if not categorized:
            self._show_toast("All bookmarks are already uncategorized", "info")
            return

        self._begin_maintenance_workflow()
        if not self._create_maintenance_safepoint("flatten-folders"):
            return

        for bm in categorized:
            bm.category = "Uncategorized / Needs Review"
            bm.parent_category = ""
        self.bookmark_manager.save_bookmarks()
        self._refresh_all()
        self._set_status(format_message(
            "Flattened {count} bookmarks out of folders; restore available from Tools",
            count=len(categorized),
        ))
        self._toast(format_message(
            "Moved {count} bookmarks out of folders; safepoint ready",
            count=len(categorized),
        ), "success")

    def _clear_all_categories(self):
        """Reset every bookmark's category to 'Uncategorized / Needs Review'."""
        self._flatten_all_folders()

    def _clear_all_tags(self):
        """Strip tags from all bookmarks (or selected, if any are selected)."""
        if self.selected_bookmarks:
            targets = [self.bookmark_manager.get_bookmark(bid) for bid in self.selected_bookmarks]
            targets = [bm for bm in targets if bm]
        else:
            targets = self.bookmark_manager.get_all_bookmarks()

        if not targets:
            self._show_toast("No bookmarks to clear tags from", "info")
            return

        tagged = [bm for bm in targets if bm.tags or bm.ai_tags]
        if not tagged:
            self._show_toast("No tags to clear", "info")
            return

        self._begin_maintenance_workflow()
        if not self._create_maintenance_safepoint("clear-tags"):
            return

        for bm in tagged:
            bm.tags = []
            bm.ai_tags = []
        self.bookmark_manager.save_bookmarks()
        self._refresh_all()
        self._set_status(format_message(
            "Cleared tags from {count} bookmarks; restore available from Tools",
            count=len(tagged),
        ))
        self._toast(format_message(
            "Cleared tags from {count} bookmarks; safepoint ready", count=len(tagged),
        ), "success")

    def _organize_selected(self):
        """Auto-categorize + tag selected bookmarks using the pattern engine."""
        if not self.selected_bookmarks:
            self._show_toast("Select bookmarks first", "info")
            return

        changed = 0
        for bm_id in self.selected_bookmarks:
            bm = self.bookmark_manager.get_bookmark(bm_id)
            if not bm:
                continue
            new_cat = self.category_manager.categorize_url(bm.url, bm.title)
            if new_cat != bm.category:
                bm.category = new_cat
                changed += 1
        self.bookmark_manager.save_bookmarks()
        self._refresh_all()
        self._set_status(format_message(
            "Organized {total} bookmarks ({changed} re-categorized)",
            total=len(self.selected_bookmarks), changed=changed,
        ))
        self._show_toast(format_message(
            "Re-categorized {changed} of {total} bookmarks",
            changed=changed, total=len(self.selected_bookmarks),
        ), "success")

    def _categorize_all_bookmarks(self):
        """Reprocess all bookmarks and categorize them based on category patterns - non-blocking"""
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        if not bookmarks:
            self._set_status("Add bookmarks before categorizing")
            self._toast("Import or add bookmarks before running categorization", "info")
            return

        self._begin_maintenance_workflow()
        if not self._create_maintenance_safepoint("categorize-all"):
            return
        
        # Create progress display
        theme = get_theme()
        self._cat_cancelled = False
        
        progress_frame = tk.Frame(self.status_bar, bg=theme.bg_dark)
        progress_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        
        progress_label = tk.Label(
            progress_frame, text=_("Categorizing…"), bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.small()
        )
        progress_label.pack(side=tk.LEFT, padx=5)
        
        progress_bar = tk.Frame(progress_frame, bg=theme.bg_tertiary, height=8, width=200)
        progress_bar.pack(side=tk.LEFT, padx=5)
        progress_bar.pack_propagate(False)
        
        progress_fill = tk.Frame(progress_bar, bg=theme.accent_primary, height=8)
        progress_fill.place(x=0, y=0, relheight=1.0, relwidth=0)
        
        cancel_btn = tk.Label(
            progress_frame, text=_("✕ Cancel"), bg=theme.accent_error, fg=readable_text_on(theme.accent_error),
            font=FONTS.small(), padx=8, pady=2, cursor="hand2"
        )
        cancel_btn.pack(side=tk.LEFT, padx=10)
        make_keyboard_activatable(cancel_btn, lambda: setattr(self, '_cat_cancelled', True))
        Tooltip(cancel_btn, "Cancel Categorization")
        
        # Categorize in batches using after() for UI responsiveness
        self._cat_index = 0
        self._cat_changed = 0
        self._cat_unchanged = 0
        self._cat_bookmarks = bookmarks
        
        def process_batch():
            if self._cat_cancelled or self._cat_index >= len(self._cat_bookmarks):
                # Done or cancelled
                progress_frame.destroy()
                self.bookmark_manager.save_bookmarks()
                self._refresh_all()
                
                if self._cat_cancelled:
                    self._set_status(format_message(
                        "Cancelled. Changed {count} bookmarks.", count=self._cat_changed,
                    ))
                    self._toast(format_message(
                        "Categorization cancelled after {count} changes", count=self._cat_changed,
                    ), "warning")
                else:
                    self._set_status(format_message(
                        "Categorized {count} bookmarks", count=self._cat_changed,
                    ))
                    self._toast(format_message(
                        "Categorized {count} bookmarks; {unchanged} unchanged",
                        count=self._cat_changed, unchanged=self._cat_unchanged,
                    ), "success")
                return
            
            # Process batch of 20
            batch_end = min(self._cat_index + 20, len(self._cat_bookmarks))
            for i in range(self._cat_index, batch_end):
                bm = self._cat_bookmarks[i]
                old_cat = bm.category
                new_cat = self.category_manager.categorize_url(bm.url, bm.title)
                
                if new_cat != old_cat:
                    bm.category = new_cat
                    self._cat_changed += 1
                else:
                    self._cat_unchanged += 1
            
            self._cat_index = batch_end
            
            # Update progress
            progress = self._cat_index / len(self._cat_bookmarks)
            progress_fill.place(relwidth=progress)
            progress_label.configure(text=format_message('Categorizing: {value_0}/{value_1} ({value_2} changed)', value_0=self._cat_index, value_1=len(self._cat_bookmarks), value_2=self._cat_changed))
            
            # Schedule next batch
            self.root.after(10, process_batch)
        
        # Start processing
        self.root.after(100, process_batch)

    def _import_categories_file(self):
        """Import categories from a JSON file"""
        filepath = filedialog.askopenfilename(
            title=_("Select Categories JSON File"),
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        
        if not filepath:
            return
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                categories_data = json.load(f)
            
            if not isinstance(categories_data, dict):
                messagebox.showerror(
                    _("Categories Import Failed"),
                    _("The selected file is not a categories JSON object. Choose a file whose top level contains category names."),
                    parent=self.root
                )
                return
            
            # Merge with existing categories
            imported = 0
            updated = 0
            for cat_name, patterns in categories_data.items():
                patterns_list = patterns if isinstance(patterns, list) else []
                
                if cat_name not in self.category_manager.categories:
                    # Create new Category object
                    new_cat = Category(
                        name=cat_name,
                        patterns=patterns_list,
                        icon=get_category_icon(cat_name)
                    )
                    self.category_manager.categories[cat_name] = new_cat
                    imported += 1
                else:
                    # Merge patterns into existing category
                    existing_cat = self.category_manager.categories[cat_name]
                    if hasattr(existing_cat, 'patterns'):
                        for p in patterns_list:
                            if p not in existing_cat.patterns:
                                existing_cat.patterns.append(p)
                        updated += 1
            
            # Rebuild pattern engine and save
            self.category_manager._rebuild_patterns()
            self.category_manager.save_categories()
            self._refresh_category_list()
            self._refresh_analytics()
            
            self._set_status(format_message(
                "Imported {imported} categories, updated {updated}",
                imported=imported, updated=updated,
            ))
            self._toast(format_message(
                "Imported {imported} categories; updated {updated}; total {total}",
                imported=imported, updated=updated,
                total=len(self.category_manager.categories),
            ), "success")
            
        except json.JSONDecodeError as e:
            messagebox.showerror(
                _("Categories Import Failed"),
                format_message('The selected file is not valid JSON.\n\n{value_0}', value_0=e),
                parent=self.root
            )
        except Exception as e:
            log.warning("Categories import failed", exc_info=True)
            messagebox.showerror(
                _("Categories Import Failed"),
                format_message('Categories could not be imported.\n\n{value_0}', value_0=e),
                parent=self.root
            )

    def _check_all_links(self):
        """Check all links - non-blocking with cancel support"""
        if requests is None:
            messagebox.showerror(
                _("Link Check Unavailable"),
                _("The requests package is required before link checks can run."),
                parent=self.root
            )
            self._set_status("Link checking is unavailable")
            return
        
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        if not bookmarks:
            self._set_status("Add bookmarks before checking links")
            self._toast("Import or add bookmarks before running a link check", "info")
            return
        
        # Create progress frame with cancel button
        theme = get_theme()
        self._link_check_cancelled = False
        
        progress_frame = tk.Frame(self.status_bar, bg=theme.bg_dark)
        progress_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        
        progress_label = tk.Label(
            progress_frame, text=_("Checking links…"), bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.small()
        )
        progress_label.pack(side=tk.LEFT, padx=5)
        
        progress_bar = tk.Frame(progress_frame, bg=theme.bg_tertiary, height=8, width=200)
        progress_bar.pack(side=tk.LEFT, padx=5)
        progress_bar.pack_propagate(False)
        
        progress_fill = tk.Frame(progress_bar, bg=theme.accent_primary, height=8)
        progress_fill.place(x=0, y=0, relheight=1.0, relwidth=0)
        
        cancel_btn = tk.Label(
            progress_frame, text=_("✕ Cancel"), bg=theme.accent_error, fg=readable_text_on(theme.accent_error),
            font=FONTS.small(), padx=8, pady=2, cursor="hand2"
        )
        cancel_btn.pack(side=tk.LEFT, padx=10)
        
        def cancel_check():
            self._link_check_cancelled = True
            cancel_btn.configure(text=_("Cancelling…"), bg=theme.text_muted)

        make_keyboard_activatable(cancel_btn, cancel_check)
        Tooltip(cancel_btn, "Cancel Link Check")
        
        self._set_status("Checking links…")
        
        import threading

        from bookmark_organizer_pro.services.dead_link_scanner import DeadLinkScanner

        total = len(bookmarks)
        # The scanner reports counts; the UI only mirrors its latest snapshot.
        latest = {"done": 0, "broken": 0, "rate_limited": 0}

        def _apply_progress(done, broken, rate_limited):
            latest.update(done=done, broken=broken, rate_limited=rate_limited)
            progress_fill.place(relwidth=(done / total) if total else 1.0)
            progress_label.configure(text=format_message(
                'Checked {value_0}/{value_1} - {value_2} broken',
                value_0=done, value_1=total, value_2=broken,
            ))

        def _on_progress(progress):
            self._post_to_ui(
                lambda d=progress.done, b=progress.broken, r=progress.rate_limited:
                _apply_progress(d, b, r)
            )

        def _worker():
            # A host that answers 429/503 is rate limiting us, not dead, so the
            # scanner owns this check: it caps per-host concurrency, honours
            # Retry-After, and leaves is_valid alone when a host never answers.
            scanner = DeadLinkScanner(get_bookmarks=lambda: bookmarks)
            try:
                scanner.scan_now(
                    progress_callback=_on_progress,
                    should_cancel=lambda: self._link_check_cancelled,
                )
            except Exception:
                log.warning("Link check failed", exc_info=True)
            self._post_to_ui(_finish)

        def _finish():
            self.bookmark_manager.save_bookmarks()
            progress_frame.destroy()
            broken = latest["broken"]
            rate_limited = latest["rate_limited"]
            status = "Cancelled" if self._link_check_cancelled else "Complete"
            self._set_status(format_message(
                "{status}: Found {broken} broken links",
                status=status, broken=broken,
            ))
            self._refresh_all()
            if self._link_check_cancelled:
                return
            if rate_limited:
                self._show_toast(format_message(
                    "Checked {checked} links, found {broken} broken; "
                    "{limited} hosts rate limited and left unchanged",
                    checked=latest["done"], broken=broken, limited=rate_limited,
                ), "warning")
            else:
                self._show_toast(format_message(
                    "Checked {checked} links, found {broken} broken",
                    checked=latest["done"], broken=broken,
                ), "success" if broken == 0 else "warning")

        threading.Thread(target=_worker, daemon=True).start()

    def _find_duplicates(self):
        """Find URL duplicates and open an actionable review queue."""
        dupes = self.bookmark_manager.find_duplicates()
        
        if not dupes:
            self._show_toast("No duplicate bookmarks found", "success")
            return

        review_groups = build_url_duplicate_review_groups(dupes)
        group_map = {}
        for index, (_canonical_url, bookmarks) in enumerate(sorted(dupes.items()), 1):
            clean = [bm for bm in bookmarks if bm and bm.id is not None]
            if len(clean) > 1:
                group_map[f"url:{index}:{clean[0].id}"] = clean

        def _apply(selected_keys):
            selected = [group_map[key] for key in selected_keys if key in group_map]
            total = sum(max(len(group) - 1, 0) for group in selected)
            if total <= 0:
                return "No duplicate groups selected."
            if not self._create_maintenance_safepoint("remove-duplicates"):
                return CleanupApplyResult(
                    "No changes made because a recovery safepoint could not be created.",
                    retryable=True,
                )
            removed = 0
            for group in selected:
                for bm in list(group)[1:]:
                    if self.bookmark_manager.delete_bookmark(bm.id):
                        removed += 1
            if removed:
                self.bookmark_manager.save_bookmarks()
                self._refresh_all()
            self._set_status(format_message(
                "Removed {count} duplicates; restore available from Tools", count=removed,
            ))
            self._toast(format_message(
                "Removed {count} duplicate bookmarks; safepoint ready", count=removed,
            ), "success")
            return f"Removed {removed} duplicate bookmark(s). Restore is available from this dialog or Tools."

        self._show_cleanup_review_dialog(
            "Duplicate Review",
            "Select URL duplicate groups to remove. The first bookmark in each group is kept.",
            review_groups,
            _apply,
        )

    def _smart_duplicate_scan(self):
        """Run the 3-pass hybrid duplicate detector and show grouped results."""
        import threading
        self._set_status("Scanning for duplicates (URL + SimHash + semantic)...")

        def _run():
            try:
                from bookmark_organizer_pro.services.dup_hybrid import HybridDuplicateDetector
                bms = self.bookmark_manager.get_all_bookmarks()
                detector = HybridDuplicateDetector()
                report = detector.detect(bms)
                self._post_to_ui(lambda: self._show_dup_results(report))
            except Exception as exc:
                msg = str(exc)
                self._post_to_ui(lambda: self._set_status(format_message(
                    "Duplicate scan failed: {error}", error=msg,
                )))

        threading.Thread(target=_run, daemon=True).start()

    def _show_dup_results(self, report):
        raw_groups = list(getattr(report, "groups", report or []))
        if not raw_groups:
            self._show_toast("No duplicates found", "success")
            self._set_status("Smart duplicate scan complete: 0 groups")
            return

        bookmarks_by_id = {bm.id: bm for bm in self.bookmark_manager.get_all_bookmarks() if bm.id is not None}
        review_groups = build_hybrid_duplicate_review_groups(report, bookmarks_by_id)
        if not review_groups:
            self._show_toast("No actionable duplicates found", "success")
            self._set_status("Smart duplicate scan complete: 0 actionable groups")
            return

        review_keys = {group.key for group in review_groups}
        detector_groups_by_key = {}
        for index, group in enumerate(raw_groups, 1):
            ids = [int(bookmark_id) for bookmark_id in getattr(group, "bookmark_ids", [])]
            if len(ids) <= 1:
                continue
            canonical_id = int(getattr(group, "canonical_id", ids[0]))
            key = f"hybrid:{index}:{canonical_id}"
            if key in review_keys:
                detector_groups_by_key[key] = group

        def _apply(selected_keys):
            selected = [detector_groups_by_key[key] for key in selected_keys if key in detector_groups_by_key]
            total = sum(max(len(getattr(group, "bookmark_ids", [])) - 1, 0) for group in selected)
            if total <= 0:
                return "No smart duplicate groups selected."
            if not self._create_maintenance_safepoint("smart-duplicates"):
                return CleanupApplyResult(
                    "No changes made because a recovery safepoint could not be created.",
                    retryable=True,
                )
            removed = 0
            for group in selected:
                ids = [int(bookmark_id) for bookmark_id in getattr(group, "bookmark_ids", [])]
                canonical_id = int(getattr(group, "canonical_id", ids[0]))
                for bookmark_id in ids:
                    if bookmark_id == canonical_id:
                        continue
                    if self.bookmark_manager.delete_bookmark(bookmark_id):
                        removed += 1
            if removed:
                self.bookmark_manager.save_bookmarks()
                self._refresh_all()
            self._set_status(format_message(
                "Smart duplicates: removed {count}; restore available from Tools", count=removed,
            ))
            self._toast(format_message(
                "Removed {count} smart duplicate bookmark(s); safepoint ready", count=removed,
            ), "success")
            return f"Removed {removed} duplicate bookmark(s). Restore is available from this dialog or Tools."

        total = sum(len(getattr(group, "bookmark_ids", [])) - 1 for group in raw_groups)
        self._show_cleanup_review_dialog(
            "Smart Duplicate Review",
            f"Found {len(review_groups)} group(s) and {total} extra bookmark(s). Select only the groups you want to apply.",
            review_groups,
            _apply,
        )

    def _lint_tags_gui(self):
        """Run the tag linter and show suggested merges."""
        import threading
        self._set_status("Linting tags...")

        def _run():
            try:
                from bookmark_organizer_pro.services.tag_linter import TagLinter
                bms = self.bookmark_manager.get_all_bookmarks()
                linter = TagLinter()
                suggestions = linter.lint(bms)
                self._post_to_ui(lambda: self._show_lint_results(suggestions))
            except Exception as exc:
                msg = str(exc)
                self._post_to_ui(lambda: self._set_status(format_message(
                    "Tag lint failed: {error}", error=msg,
                )))

        threading.Thread(target=_run, daemon=True).start()

    def _show_lint_results(self, report):
        suggestions = list(getattr(report, "suggestions", report or []))
        if not suggestions:
            self._show_toast("Tags are clean - no issues found", "success")
            self._set_status("Tag lint complete: 0 issues")
            return

        review_groups = build_tag_lint_review_groups(report)
        if not review_groups:
            self._show_toast("No actionable tag issues found", "success")
            self._set_status("Tag lint complete: 0 actionable issues")
            return

        review_keys = {group.key for group in review_groups}
        suggestion_by_key = {}
        for index, suggestion in enumerate(suggestions, 1):
            if isinstance(suggestion, dict):
                canonical = str(suggestion.get("canonical", "") or "")
            else:
                canonical = str(getattr(suggestion, "canonical", "") or "")
            key = f"tag:{index}:{canonical}"
            if key in review_keys:
                suggestion_by_key[key] = suggestion

        def _apply(selected_keys):
            selected = [suggestion_by_key[key] for key in selected_keys if key in suggestion_by_key]
            if not selected:
                return "No tag lint groups selected."
            if not self._create_maintenance_safepoint("lint-tags"):
                return CleanupApplyResult(
                    "No changes made because a recovery safepoint could not be created.",
                    retryable=True,
                )
            try:
                from bookmark_organizer_pro.services.tag_linter import TagLinter
                bms = self.bookmark_manager.get_all_bookmarks()
                linter = TagLinter()
                applied = linter.apply(bms, selected)
                if applied:
                    self.bookmark_manager.save_bookmarks()
                    self._refresh_all()
                self._set_status(format_message(
                    "Tag lint: applied {count} merge(s); restore available from Tools",
                    count=applied,
                ))
                self._toast(format_message(
                    "Applied {count} tag merge(s); safepoint ready", count=applied,
                ), "success")
                return f"Applied {applied} tag merge(s). Restore is available from this dialog or Tools."
            except Exception as exc:
                detail = format_message("Tag lint apply failed: {error}", error=exc)
                self._set_status(detail)
                return detail

        self._show_cleanup_review_dialog(
            "Tag Cleanup Review",
            f"Found {len(review_groups)} tag issue group(s). Select the merges to apply.",
            review_groups,
            _apply,
        )

    def _show_smart_collections(self):
        """Show smart collections in a dialog."""
        try:
            from bookmark_organizer_pro.services.smart_collections import SmartCollectionManager
            mgr = SmartCollectionManager()
            collections = mgr.list_collections()
        except Exception:
            collections = []

        if not collections:
            self._show_nonblocking_report(
                "Smart Collections",
                [
                    "No smart collections defined.",
                    "",
                    "Create one with: bop smart-collections create <name>",
                    "  --tags python,tutorial",
                    "  --domains github.com",
                    "  --keywords async",
                ],
                "No smart collections defined",
                "No smart collections defined",
            )
            return

        bms = self.bookmark_manager.get_all_bookmarks()
        lines = [f"{len(collections)} smart collection(s):\n"]
        for sc in collections:
            matching = [b for b in bms if sc.matches(b)]
            lines.append(f"  {sc.icon or '#'} {sc.name}: {len(matching)} bookmark(s)")
            filters = []
            if sc.filters.tags:
                filters.append(f"tags={','.join(sc.filters.tags)}")
            if sc.filters.domains:
                filters.append(f"domains={','.join(sc.filters.domains)}")
            if sc.filters.keywords:
                filters.append(f"keywords={','.join(sc.filters.keywords)}")
            if sc.filters.categories:
                filters.append(f"categories={','.join(sc.filters.categories)}")
            if sc.filters.reader_state:
                filters.append(f"reader_state={sc.filters.reader_state}")
            if filters:
                lines.append(f"    Filters: {'; '.join(filters)}")
        self._show_nonblocking_report(
            "Smart Collections",
            lines,
            f"Smart collections: {len(collections)} defined",
            f"Listed {len(collections)} smart collection(s)",
        )

    def _show_read_later_queue(self):
        """Open the dedicated Read Later queue workflow."""
        ReadLaterQueueDialog(
            self.root,
            bookmark_manager=self.bookmark_manager,
            on_changed=self._refresh_all,
            on_open_url=_open_external_url,
        )

    def _view_dead_links(self):
        """Show dead-link scan results from the persistent queue."""
        try:
            from bookmark_organizer_pro.services.dead_link_scanner import DeadLinkScanner
            scanner = DeadLinkScanner(
                get_bookmarks=lambda: self.bookmark_manager.get_all_bookmarks(),
            )
            records = scanner.list_dead_links()
        except Exception:
            records = []

        if not records:
            self._show_toast("No dead links on file. Run Check All Links first.", "info")
            return

        broken = [r for r in records if r.status >= 400 or r.status == 0]
        redirected = [r for r in records if 300 <= r.status < 400]

        lines = [f"{len(records)} dead/redirected link(s) on file:\n"]
        if broken:
            lines.append(f"  Broken ({len(broken)}):")
            for r in broken[:15]:
                lines.append(f"    [{r.status}] {r.url[:60]}")
            if len(broken) > 15:
                lines.append(f"    ... and {len(broken) - 15} more")
        if redirected:
            lines.append(f"\n  Redirected ({len(redirected)}):")
            for r in redirected[:10]:
                lines.append(f"    [{r.status}] {r.url[:50]} -> {r.redirect_to[:50]}")
            if len(redirected) > 10:
                lines.append(f"    ... and {len(redirected) - 10} more")
        lines.append("\nUse 'bop scan' from the CLI to refresh.")
        self._show_nonblocking_report(
            "Dead Link Scan Results",
            lines,
            f"Dead link results: {len(records)} saved records",
            f"Loaded {len(records)} saved dead-link result(s)",
        )

    def _view_snapshot_failures(self):
        """Show recoverable snapshot backend failures."""
        records = SnapshotFailureStore().list_failures()
        if not records:
            self._set_status("No snapshot failures on file")
            self._toast("No snapshot failures on file", "success")
            return

        retryable = sum(1 for record in records if record.retry_eligible)
        lines = [f"{len(records)} failed snapshot(s) on file; {retryable} retryable.\n"]
        for record in records[:20]:
            title = record.title or record.url or "Untitled bookmark"
            lines.append(f"- {title[:70]}")
            lines.append(f"  URL: {record.url[:90]}")
            lines.append(f"  Failed: {record.failed_at or 'unknown'}")
            lines.append(f"  Retry: {'yes' if record.retry_eligible else 'no'}")
            if record.attempts:
                lines.append("  Backend attempts:")
                for attempt in record.attempts:
                    lines.append(f"    - {attempt.backend}: {attempt.message[:120]}")
            else:
                lines.append(f"  Reason: {record.error[:160]}")
            if record.retry_count:
                lines.append(f"  Retry attempt: {record.retry_count}")
            if record.next_retry_at:
                lines.append(f"  Next retry after: {record.next_retry_at}")
            lines.append("")
        if len(records) > 20:
            lines.append(f"... and {len(records) - 20} more failure(s)")

        self._show_nonblocking_report(
            "Snapshot Failure Report",
            lines,
            f"Snapshot failures: {len(records)} saved records",
            f"Loaded {len(records)} snapshot failure record(s)",
            actions=[
                ("Retry Failed", self._retry_snapshot_failures, "primary"),
                ("Clear Reports", self._clear_snapshot_failures, "danger"),
            ],
        )

    def _retry_snapshot_failures(self):
        """Retry retryable snapshot failure reports."""
        store = SnapshotFailureStore()
        records = [record for record in store.list_failures() if record.retry_eligible]
        if not records:
            self._set_status("No retryable snapshot failures")
            self._toast("No retryable snapshot failures", "info")
            return

        bookmarks = self.bookmark_manager.get_all_bookmarks()
        by_id = {bm.id: bm for bm in bookmarks if bm.id is not None}
        by_url = {bm.url: bm for bm in bookmarks if bm.url}
        archiver = SnapshotArchiver(failure_store=store)
        success = 0
        failed = 0
        skipped = 0

        self._set_status(format_message(
            "Retrying {count} failed snapshot(s)...", count=len(records),
        ))
        for record in records:
            bookmark = by_id.get(record.bookmark_id) if record.bookmark_id is not None else None
            if bookmark is None:
                bookmark = by_url.get(record.url)
            if bookmark is None:
                skipped += 1
                continue
            ok, _msg = archiver.snapshot(bookmark)
            if ok:
                success += 1
            else:
                failed += 1

        if success:
            self.bookmark_manager.save_bookmarks()
            self._refresh_all()
        self._set_status(format_message(
            "Snapshot retry complete: {success} fixed, {failed} still failing, {skipped} missing",
            success=success, failed=failed, skipped=skipped,
        ))
        style = "success" if success and failed == 0 else "info"
        self._toast(format_message(
            "Snapshot retry complete: {success} fixed, {failed} failed, {skipped} skipped",
            success=success, failed=failed, skipped=skipped,
        ), style)

    def _clear_snapshot_failures(self):
        """Clear saved snapshot failure reports."""
        cleared = SnapshotFailureStore().clear_all()
        self._refresh_all()
        self._set_status(format_message(
            "Cleared {count} snapshot failure report(s)", count=cleared,
        ))
        self._toast(format_message(
            "Cleared {count} snapshot failure report(s)", count=cleared,
        ), "success")

    def _clean_urls(self):
        """Clean tracking params"""
        self._begin_maintenance_workflow()
        if not self._create_maintenance_safepoint("clean-tracking-params"):
            return
        count = self.bookmark_manager.clean_tracking_params()
        self._refresh_all()
        self._set_status(format_message(
            "Cleaned {count} URLs; restore available from Tools", count=count,
        ))
        self._toast(format_message(
            "Cleaned {count} URLs; safepoint ready", count=count,
        ), "success")

    def _show_analytics(self):
        """Show full analytics"""
        AnalyticsDashboard(self.root, self.bookmark_manager)

    def _backup_now(self):
        """Create backup"""
        backup_dir = DATA_DIR / "backups"
        backup_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = backup_dir / f"backup_{timestamp}.json"
        
        self.bookmark_manager.export_json(str(filepath))
        self._set_status(format_message("Backup saved to {path}", path=filepath.name))

    def _clear_favicon_cache(self):
        """Clear favicon cache"""
        self.favicon_manager.clear_cache()
        self._refresh_all()
        self._set_status("Favicon cache cleared")
        self._toast("Favicon cache cleared; icons will refresh as needed", "success")

    def _redownload_all_favicons(self):
        """Redownload all favicons"""
        if not self.favicon_manager.enabled:
            self._set_status(_("Site icon fetching is disabled"))
            self._toast(
                _("Enable Show and fetch site icons in Settings before downloading icons"),
                "info",
            )
            return
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        if not bookmarks:
            self._set_status("Add bookmarks before fetching favicons")
            self._toast("Import or add bookmarks before downloading favicons", "info")
            return

        self._set_status("Redownloading all favicons...")
        self._toast(format_message(
            "Redownloading favicons for {count} bookmarks", count=len(bookmarks),
        ), "info")
        self.favicon_manager.redownload_all_favicons(bookmarks)

    def _redownload_missing_favicons(self):
        """Redownload only missing favicons"""
        if not self.favicon_manager.enabled:
            self._set_status(_("Site icon fetching is disabled"))
            self._toast(
                _("Enable Show and fetch site icons in Settings before downloading icons"),
                "info",
            )
            return
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        if not bookmarks:
            self._set_status("Add bookmarks before fetching favicons")
            self._toast("Import or add bookmarks before downloading favicons", "info")
            return
        
        # Count missing
        missing_count = sum(1 for bm in bookmarks if not self.favicon_manager.get_cached(bm.domain))
        failed_count = len(self.favicon_manager.get_failed_domains())
        if missing_count == 0 and failed_count == 0:
            self._set_status("Favicons are up to date")
            self._toast("Every bookmark already has a cached favicon", "success")
            return

        self._set_status("Redownloading missing favicons...")
        self._toast(format_message(
            "Retrying {missing} missing favicon(s) and {failed} failed domain(s)",
            missing=missing_count, failed=failed_count,
        ), "info")
        self.favicon_manager.redownload_missing_favicons(bookmarks)

    def _show_category_manager(self):
        """Show category management dialog"""
        CategoryManagementDialog(
            self.root, self.category_manager, self.bookmark_manager,
            on_change=self._refresh_all
        )

    def _show_custom_favicon_dialog(self):
        """Show custom favicon dialog for selected bookmark"""
        if not self.selected_bookmarks:
            self._set_status("Select one bookmark to customize its favicon")
            self._toast("Select one bookmark before choosing a custom favicon", "info")
            return
        
        bm_id = list(self.selected_bookmarks)[0]
        bookmark = self.bookmark_manager.get_bookmark(bm_id)
        if bookmark:
            CustomFaviconDialog(
                self.root, bookmark, self.bookmark_manager,
                on_update=self._refresh_all
            )

    def _migrate_to_sqlite(self):
        """Run JSON-to-SQLite migration from the GUI with a progress indicator."""
        import threading

        from bookmark_organizer_pro.constants import MASTER_BOOKMARKS_FILE

        sqlite_path = MASTER_BOOKMARKS_FILE.with_suffix(".sqlite")
        if sqlite_path.exists():
            self._set_status(format_message("SQLite already exists at {path}", path=sqlite_path))
            self._toast("SQLite database already exists; rename it before migrating again", "info")
            return

        bookmarks = self.bookmark_manager.get_all_bookmarks()
        if not bookmarks:
            self._set_status("Add bookmarks before migrating to SQLite")
            self._toast("Add bookmarks before migrating to SQLite", "info")
            return

        self._set_status("Migrating to SQLite...")
        self._toast(format_message(
            "Migrating {count} bookmark(s) to SQLite", count=len(bookmarks),
        ), "info")

        def _worker():
            try:
                from bookmark_organizer_pro.core import migrate_json_to_sqlite
                count = migrate_json_to_sqlite(MASTER_BOOKMARKS_FILE, sqlite_path)
                self._post_to_ui(lambda: self._on_sqlite_migrate_done(count, sqlite_path))
            except Exception as exc:
                err = exc
                self._post_to_ui(lambda: self._on_sqlite_migrate_error(err))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_sqlite_migrate_done(self, count, path):
        self._set_status(format_message("Migrated {count} bookmarks to SQLite", count=count))
        self._show_toast(format_message(
            "SQLite migration complete: {count} bookmarks", count=count,
        ), "success")
        self._show_nonblocking_report(
            "Migration Complete",
            [
                f"Migrated {count} bookmark(s) to:",
                str(path),
                "",
                "To use SQLite as the runtime backend, set the environment variable:",
                "  BOOKMARK_STORAGE_BACKEND=sqlite",
                "or pass --backend sqlite to the CLI.",
            ],
            format_message("Migrated {count} bookmarks to SQLite", count=count),
        )

    def _on_sqlite_migrate_error(self, exc):
        self._set_status("SQLite migration failed")
        messagebox.showerror(
            _("Migration Failed"),
            format_message('Could not migrate to SQLite:\n\n{value_0}', value_0=exc),
            parent=self.root,
        )

    def _open_reader_view(self):
        """Open the extracted-text reader for the first selected bookmark."""
        if not self.selected_bookmarks:
            self._set_status("Select one bookmark to open reader view")
            self._toast("Select one bookmark before opening reader view", "info")
            return
        bm_id = list(self.selected_bookmarks)[0]
        bookmark = self.bookmark_manager.get_bookmark(bm_id)
        if not bookmark:
            self._set_status("Selected bookmark was not found")
            return
        ReaderViewDialog(
            self.root,
            bookmark,
            on_progress_changed=lambda _bookmark: self._refresh_bookmark_list(),
        )
        self._set_status(format_message("Reader opened for {title}", title=bookmark.title[:60]))

    def _open_highlights_workspace(self):
        """Open collection-wide highlight search without loading source pages."""
        HighlightsWorkspaceDialog(self.root, self.bookmark_manager)

    def _open_organization_rules(self):
        """Open the previewable organization-rules workspace."""
        OrganizationRulesDialog(self.root, self.bookmark_manager)

    def _open_graph_view(self):
        """Open the bookmark relationship graph."""
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        if not bookmarks:
            self._show_toast("No bookmarks to graph", "info")
            return
        GraphViewDialog(self.root, bookmarks, on_open_bookmark=self._open_bookmark)
        self._set_status(format_message(
            "Graph opened with {count} bookmark(s)", count=len(bookmarks),
        ))
