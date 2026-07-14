"""Import and export workflows for the app coordinator."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from typing import List

from bookmark_organizer_pro.i18n import _
from bookmark_organizer_pro.importers import (
    BrowserProfileImporter,
    BrowserProfileSessionImporter,
    FirefoxBookmarkBackupImporter,
    GenericFileSessionImporter,
)
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.services.recovery_workflow import RecoveryWorkflow
from bookmark_organizer_pro.ui.bookmark_workflows import SelectiveExportDialog
from bookmark_organizer_pro.ui.foundation import FONTS, pluralize
from bookmark_organizer_pro.ui.import_center import ImportCenterDialog, ImportSource, build_import_sources
from bookmark_organizer_pro.ui.live_workflow import LiveWorkflowDialog
from bookmark_organizer_pro.ui.widgets import ModernButton, get_theme


class ImportProgressModal(tk.Toplevel):
    """Compatibility progress surface retained for visual and downstream probes."""

    def __init__(self, parent, source_label: str = "file", next_action: str = ""):
        super().__init__(parent)
        theme = get_theme()
        self._next_action = next_action
        self.title(_("Importing Bookmarks"))
        self.configure(bg=theme.bg_primary)
        self.geometry("500x300")
        self.resizable(False, False)
        self.transient(parent)
        self._title_label = tk.Label(
            self,
            text=_("Importing from {source}…").format(source=source_label),
            bg=theme.bg_primary,
            fg=theme.text_primary,
            font=FONTS.subtitle(bold=True),
        )
        self._title_label.pack(pady=(42, 8))
        self._status_label = tk.Label(
            self,
            text=_("Preparing…"),
            bg=theme.bg_primary,
            fg=theme.text_secondary,
            font=FONTS.body(),
        )
        self._status_label.pack(pady=(0, 12))
        bar = tk.Frame(self, bg=theme.bg_tertiary, height=6)
        bar.pack(fill=tk.X, padx=48)
        self._bar_fill = tk.Frame(bar, bg=theme.accent_primary, height=6)
        self._bar_fill.place(x=0, y=0, relheight=1.0, relwidth=0)
        self._count_label = tk.Label(
            self, text="", bg=theme.bg_primary, fg=theme.text_muted, font=FONTS.small(),
        )
        self._count_label.pack(pady=(10, 0))

    def set_progress(self, current: int, total: int, added: int, dupes: int):
        self._bar_fill.place(relwidth=min(1.0, current / max(total, 1)))
        self._status_label.configure(
            text=_("Processing bookmark {current} of {total}").format(
                current=f"{current:,}", total=f"{total:,}",
            )
        )
        self._count_label.configure(
            text=_("{added} added · {duplicates} skipped").format(
                added=f"{added:,}", duplicates=f"{dupes:,}",
            )
        )

    def finish(self, added: int, dupes: int):
        theme = get_theme()
        self._bar_fill.place(relwidth=1.0)
        self._bar_fill.configure(bg=theme.accent_success)
        self._title_label.configure(text=_("Import Complete"))
        self.set_progress(1, 1, added, dupes)

    def finish_error(self, message: str):
        theme = get_theme()
        self._bar_fill.place(relwidth=1.0)
        self._bar_fill.configure(bg=theme.accent_error)
        self._title_label.configure(text=_("Import Failed"))
        self._status_label.configure(text=message[:120], fg=theme.accent_error)


class ImportExportMixin:
    """File, browser, and export actions used by the app coordinator."""

    def _on_files_dropped(self, filepaths: List[str]):
        """Import one or more selected files through one durable session."""
        file_names = ", ".join(Path(f).name for f in filepaths[:3])
        if len(filepaths) > 3:
            file_names += f" (+{len(filepaths) - 3} more)"
        self._begin_import_session(
            file_names,
            GenericFileSessionImporter(),
            filepaths,
            source="generic-files",
            next_action=_("Review imported categories, then run duplicate and tag cleanup."),
        )
    
    def _show_restore_dialog(self):
        """List backups + safepoints and restore the selected one."""
        import re as _re
        from tkinter import ttk
        from bookmark_organizer_pro.ui.foundation import FONTS
        from bookmark_organizer_pro.ui.widgets import (
            ModernButton, apply_window_chrome, get_theme,
        )

        backups = self.bookmark_manager.list_backups()
        theme = get_theme()

        dlg = tk.Toplevel(self.root)
        dlg.title(_("Restore from Backup"))
        dlg.configure(bg=theme.bg_primary)
        dlg.geometry("640x470")
        dlg.minsize(540, 380)
        dlg.transient(self.root)
        dlg.grab_set()
        apply_window_chrome(dlg)

        tk.Label(dlg, text=_("Restore bookmarks from a backup or safepoint"),
                 bg=theme.bg_primary, fg=theme.text_primary,
                 font=FONTS.subtitle(bold=True)).pack(anchor="w", padx=18, pady=(16, 4))
        tk.Label(dlg, text=_("A safepoint is captured automatically at startup and before each "
                            "import. Restoring replaces your current bookmarks — a pre-restore "
                            "backup is saved first, so this is also reversible."),
                 bg=theme.bg_primary, fg=theme.text_muted, font=FONTS.small(),
                 wraplength=590, justify=tk.LEFT).pack(anchor="w", padx=18, pady=(0, 10))

        # Buttons pinned to the bottom so they're always visible.
        btns = tk.Frame(dlg, bg=theme.bg_primary)
        btns.pack(side=tk.BOTTOM, fill=tk.X, padx=18, pady=14)

        frame = tk.Frame(dlg, bg=theme.bg_primary)
        frame.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 4))
        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL)
        lb = tk.Listbox(frame, yscrollcommand=sb.set, bg=theme.bg_secondary,
                        fg=theme.text_primary, font=FONTS.body(), activestyle="none",
                        highlightthickness=0, selectmode=tk.SINGLE, borderwidth=0)
        sb.config(command=lb.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        names: List[str] = []
        for name, mtime, size in backups:
            if name.startswith("safepoints/"):
                m = _re.search(r"safepoint_([a-z0-9-]+)_\d", name)
                kind = f"safepoint · {m.group(1)}" if m else "safepoint"
            else:
                kind = "auto-backup"
            lb.insert(tk.END, f"  {mtime.strftime('%Y-%m-%d  %H:%M:%S')}    [{kind}]    {size // 1024} KB")
            names.append(name)
        if names:
            lb.selection_set(0)
        else:
            lb.insert(tk.END, "  " + _("(no backups yet — they appear after the first save/import)"))

        def start_recovery(operation: str, source: str = ""):
            title = _("Restoring Library") if operation == "restore" else _("Salvaging Library")
            activity = LiveWorkflowDialog(self.root, title=title, total=3, width=680, height=500)
            workflow = RecoveryWorkflow(
                self.bookmark_manager,
                on_progress=lambda status, step, detail: activity.add_result(
                    status=status, title=step, detail=detail,
                ),
            )

            def work():
                return workflow.restore(source) if operation == "restore" else workflow.salvage()

            def complete(result):
                if result.success:
                    self._refresh_all()
                activity.signal_finish(
                    result.summary, outcome="success" if result.success else "error"
                )
                if hasattr(self, "_show_toast"):
                    self._show_toast(result.summary, "success" if result.success else "error")

            def failed(error):
                log.error("Recovery task runner failed: %s", error)
                message = _("Recovery stopped unexpectedly; the source was left in place.")
                activity.add_result(status="error", title=_("Recovery stopped"), detail=str(error))
                activity.signal_finish(message, outcome="error")
                if hasattr(self, "_show_toast"):
                    self._show_toast(message, "error")

            dlg.destroy()
            activity.start()
            self.task_runner.run_task(
                f"library-{operation}-{id(activity)}",
                work,
                on_complete=complete,
                on_error=failed,
            )

        def do_restore():
            sel = lb.curselection()
            if not names or not sel:
                return
            start_recovery("restore", names[sel[0]])

        def do_salvage():
            start_recovery("salvage")

        ModernButton(btns, text=_("Cancel"), command=dlg.destroy).pack(side=tk.RIGHT, padx=(10, 0))
        ModernButton(btns, text=_("Restore selected"), command=do_restore,
                     style="primary").pack(side=tk.RIGHT)
        if self.bookmark_manager.recovery_required:
            ModernButton(
                btns,
                text=_("Salvage recoverable entries"),
                command=do_salvage,
            ).pack(side=tk.LEFT)
        lb.bind("<Double-Button-1>", lambda e: do_restore())
        dlg.bind("<Escape>", lambda e: dlg.destroy())

    def _on_import_done(self, added: int, dupes: int):
        """Handle import completion"""
        self.import_area.set_importing(False)
        if added > 0:
            self.import_area.set_compact(True)
        self._refresh_all()
        
        # Queue favicons for new bookmarks
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        self.favicon_manager.queue_bookmarks(bookmarks)
        
        self._set_status(f"Imported {pluralize(added, 'bookmark')}; skipped {pluralize(dupes, 'duplicate')}")
        
        if added > 0 or dupes > 0:
            self._show_toast(
                f"Imported {pluralize(added, 'bookmark')}. Skipped {pluralize(dupes, 'duplicate')}.",
                "success" if added > 0 else "info"
            )

    def _confirm_import_preflight(self, label, preflight) -> bool:
        """Require an explicit apply decision after showing source fidelity."""
        from tkinter import messagebox

        fields = "\n".join(
            _("{field}: {count} of {total} source rows").format(
                field=field.title(), count=count, total=preflight.total,
            )
            for field, count in preflight.field_coverage.items()
        )
        causes = "; ".join(
            f"{cause} ({count})" for cause, count in preflight.causes.items()
        ) or _("None detected")
        message = _(
            "Source: {source}\nValid bookmarks: {total}\nParse losses: {losses}\n\n"
            "Field coverage\n{fields}\n\nLoss details: {causes}\n\n"
            "Missing fields remain blank or use the library default. Apply this import?"
        ).format(
            source=label,
            total=preflight.total,
            losses=preflight.losses,
            fields=fields,
            causes=causes,
        )
        return bool(messagebox.askokcancel(_("Import Preflight"), message, parent=self.root))

    def _begin_import_session(
        self, label, importer, source_paths, *, source: str, next_action: str
    ):
        """Preflight and execute every GUI importer through the shared ledger."""
        from bookmark_organizer_pro.services.import_sessions import ImportSessionManager

        paths = list(source_paths) if isinstance(source_paths, (list, tuple)) else [source_paths]
        sessions = ImportSessionManager()
        self.import_area.set_importing(True)
        self._set_status(_("Inspecting {source} before import…").format(source=label))

        def prepared(preflight):
            if not self._confirm_import_preflight(label, preflight):
                self.import_area.set_importing(False)
                self._set_status(_("Import cancelled before changes were made"))
                return

            cancelled = threading.Event()
            activity = LiveWorkflowDialog(
                self.root,
                title=_("Importing from {source}").format(source=label),
                total=preflight.total,
                width=680,
                height=500,
                on_cancel=cancelled.set,
            )

            def progress(report):
                processed = report.added + report.duplicates + report.failed
                activity.add_result(
                    status="error" if report.failed else "ok",
                    title=_("Processed {processed} of {total}").format(
                        processed=processed, total=report.total,
                    ),
                    detail=_("{added} added · {duplicates} duplicates · {failed} failed").format(
                        added=report.added,
                        duplicates=report.duplicates,
                        failed=report.failed,
                    ),
                )

            def work():
                return sessions.run(
                    self.bookmark_manager,
                    importer,
                    paths,
                    source=source,
                    cancel_requested=cancelled.is_set,
                    on_progress=progress,
                    prepared=preflight,
                )

            def complete(report):
                self._on_import_done(report.added, report.duplicates)
                causes = "; ".join(
                    f"{cause} ({count})" for cause, count in report.causes.items()
                ) or _("none")
                diagnostics = _(
                    "Session {session} · {status} · {duration} ms · "
                    "{failed} failed · {losses} source losses · causes: {causes}."
                ).format(
                    session=report.session_id,
                    status=report.status,
                    duration=report.duration_ms,
                    failed=report.failed,
                    losses=report.losses,
                    causes=causes,
                )
                activity.signal_finish(
                    diagnostics,
                    outcome="error" if report.failed else (
                        "warning" if report.status == "cancelled" else "success"
                    ),
                )
                self._show_import_result_summary(
                    label,
                    report.added,
                    report.duplicates,
                    f"{next_action} {diagnostics}",
                    report=report,
                )

            def failed(error):
                self.import_area.set_importing(False)
                activity.add_result(status="error", title=_("Import interrupted"), detail=str(error))
                activity.signal_finish(str(error), outcome="error")
                self._show_toast(str(error), "error")

            activity.start()
            self.task_runner.run_task(
                f"import-session-{id(activity)}",
                work,
                on_complete=complete,
                on_error=failed,
            )

        def preflight_failed(error):
            self.import_area.set_importing(False)
            self._set_status(_("Import preflight failed"))
            self._show_toast(str(error), "error")

        self.task_runner.run_task(
            f"import-preflight-{id(importer)}",
            lambda: sessions.preflight(importer, paths, source=source),
            on_complete=prepared,
            on_error=preflight_failed,
        )
    
    def _show_import_dialog(self):
        """Show the guided import center."""
        importer = BrowserProfileImporter()
        sources = build_import_sources(importer.get_available_browsers())
        ImportCenterDialog(self.root, sources, self._handle_import_center_source)

    def _handle_import_center_source(self, source: ImportSource):
        """Dispatch a selected import-center card."""
        if source.action_kind == "file":
            self.import_area._browse_files_direct()
            return
        if source.action_kind == "browser_profile":
            self._import_from_browser(source.action_arg)
            return
        if source.action_kind == "service":
            handler = {
                "pocket": self._import_service_pocket,
                "readwise": self._import_service_readwise,
                "raindrop": self._import_service_raindrop,
                "arc": self._import_service_arc,
                "firefox-backup": self._import_service_firefox_backup,
            }.get(source.action_arg)
            if handler:
                handler()
                return
        if source.action_kind == "migration":
            self._preflight_competitor_migration(source.action_arg, source.title)
            return
        if source.action_kind == "reading_list_help":
            self._show_reading_list_import_help()
            return
        self._show_toast(_("This import path is not available yet."), "warning")

    def _import_from_browser(self, browser: str):
        """Require the user to choose a browser profile before preflight."""
        importer = BrowserProfileImporter()
        profiles = importer.get_profiles(browser)

        if not profiles:
            self._show_toast(_("No {browser} profiles found").format(browser=browser.title()), "warning")
            return

        self._show_browser_profile_picker(browser, profiles)

    def _show_browser_profile_picker(self, browser: str, profiles):
        theme = get_theme()
        dlg = tk.Toplevel(self.root)
        dlg.title(_("Select {browser} Profile").format(browser=browser.title()))
        dlg.configure(bg=theme.bg_primary)
        dlg.geometry("520x360")
        dlg.transient(self.root)
        dlg.grab_set()
        tk.Label(
            dlg,
            text=_("Choose the exact profile to import"),
            bg=theme.bg_primary,
            fg=theme.text_primary,
            font=FONTS.subtitle(bold=True),
        ).pack(anchor="w", padx=22, pady=(22, 6))
        tk.Label(
            dlg,
            text=_("No profile is selected automatically. The source is preflighted before changes."),
            bg=theme.bg_primary,
            fg=theme.text_secondary,
            font=FONTS.body(),
            wraplength=470,
            justify=tk.LEFT,
        ).pack(anchor="w", padx=22, pady=(0, 12))
        listing = tk.Listbox(
            dlg,
            bg=theme.bg_secondary,
            fg=theme.text_primary,
            selectbackground=theme.selection,
            font=FONTS.body(),
            exportselection=False,
            activestyle="none",
        )
        listing.pack(fill=tk.BOTH, expand=True, padx=22)
        for name, path in profiles:
            listing.insert(tk.END, f"{name}  —  {path}")
        listing.selection_set(0)
        listing.focus_set()

        def choose():
            selection = listing.curselection()
            if not selection:
                return
            profile_name, profile_path = profiles[selection[0]]
            source_path = profile_path / ("places.sqlite" if browser == "firefox" else "Bookmarks")
            dlg.destroy()
            self._begin_import_session(
                f"{browser.title()} ({profile_name})",
                BrowserProfileSessionImporter(browser),
                source_path,
                source=f"browserprofile:{browser}",
                next_action=_("Review browser folders, then run duplicate and tag cleanup."),
            )

        buttons = tk.Frame(dlg, bg=theme.bg_primary)
        buttons.pack(side=tk.BOTTOM, fill=tk.X, padx=22, pady=18, before=listing)
        ModernButton(buttons, text=_("Import Selected Profile"), command=choose,
                     style="primary", padx=14, pady=7).pack(side=tk.RIGHT)
        ModernButton(buttons, text=_("Cancel"), command=dlg.destroy,
                     padx=14, pady=7).pack(side=tk.RIGHT, padx=(0, 8))
        listing.bind("<Double-Button-1>", lambda _event: choose())
        listing.bind("<Return>", lambda _event: choose())
        dlg.bind("<Escape>", lambda _event: dlg.destroy())
    
    def _import_service_file(self, importer_cls, label, filetypes):
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            title=_("Import from {source}").format(source=label),
            filetypes=filetypes,
            parent=self.root,
        )
        if not path:
            return
        importer = importer_cls()
        source = importer_cls.__name__.removesuffix("Importer").lower()
        self._begin_import_session(
            label,
            importer,
            path,
            source=source,
            next_action=_("Review the imported rows and resolve any reported losses."),
        )

    def _preflight_competitor_migration(self, source: str, label: str):
        """Show field fidelity before a separately initiated, reversible apply."""
        from tkinter import filedialog
        from bookmark_organizer_pro.services.migration import apply_migration, preflight_migration

        extension = "*.json" if source in {"linkwarden", "karakeep"} else "*.csv"
        path = filedialog.askopenfilename(
            title=_("Preflight {source} Migration").format(source=label),
            filetypes=[(_("Export file"), extension), (_("All"), "*.*")],
            parent=self.root,
        )
        if not path:
            return
        try:
            plan = preflight_migration(
                source,
                path,
                existing_urls=[bookmark.url for bookmark in self.bookmark_manager.get_all_bookmarks()],
            )
        except (OSError, ValueError) as exc:
            self._show_toast(_("Migration preflight failed: {error}").format(error=str(exc)[:120]), "error")
            return

        report = plan.report
        unsupported = ", ".join(
            f"{name}: {count}" for name, count in sorted(report.unsupported.items())
        ) or _("None detected")
        transformed = ", ".join(
            f"{name}: {count}" for name, count in sorted(report.transformed.items())
        ) or _("None")
        theme = get_theme()
        dlg = tk.Toplevel(self.root)
        dlg.title(_("Migration Preflight"))
        dlg.configure(bg=theme.bg_primary)
        dlg.geometry("560x390")
        dlg.transient(self.root)
        tk.Label(
            dlg,
            text=_("{source} migration preflight").format(source=label),
            bg=theme.bg_primary,
            fg=theme.text_primary,
            font=FONTS.subtitle(bold=True),
        ).pack(anchor="w", padx=22, pady=(22, 8))
        summary = _(
            "{total} source records\n{ready} ready to import\n{duplicates} duplicates\n"
            "{invalid} invalid records\n\nTransformed: {transformed}\n\nUnsupported: {unsupported}"
        ).format(
            total=report.total_records,
            ready=report.importable,
            duplicates=report.duplicates,
            invalid=report.invalid,
            transformed=transformed,
            unsupported=unsupported,
        )
        tk.Label(
            dlg,
            text=summary,
            bg=theme.bg_primary,
            fg=theme.text_secondary,
            font=FONTS.body(),
            justify=tk.LEFT,
            anchor="nw",
            wraplength=510,
        ).pack(fill=tk.BOTH, expand=True, padx=22, pady=(0, 12))

        def apply_plan():
            try:
                result = apply_migration(self.bookmark_manager, plan)
            except RuntimeError as exc:
                self._show_toast(str(exc), "error")
                return
            dlg.destroy()
            self._on_import_done(result.added, result.duplicates)
            self._show_import_result_summary(
                label,
                result.added,
                result.duplicates,
                _("Restore point: {name}").format(name=result.safepoint),
            )

        buttons = tk.Frame(dlg, bg=theme.bg_primary)
        buttons.pack(fill=tk.X, padx=22, pady=(0, 18))
        ModernButton(buttons, text=_("Apply Migration"), command=apply_plan,
                     style="primary", padx=14, pady=7).pack(side=tk.RIGHT)
        ModernButton(buttons, text=_("Close"), command=dlg.destroy,
                     padx=14, pady=7).pack(side=tk.RIGHT, padx=(0, 8))

    def _reopen_incomplete_import_sessions(self):
        """Reopen durable work that did not reach a terminal state last run."""
        from bookmark_organizer_pro.services.import_sessions import ImportSessionManager

        reports = [
            report for report in ImportSessionManager().list(50)
            if report.pending or report.failed or report.status in {
                "pending", "running", "cancelled", "interrupted", "attention"
            }
        ]
        if reports:
            self._show_incomplete_import_sessions(reports)

    def _show_incomplete_import_sessions(self, reports):
        theme = get_theme()
        dlg = tk.Toplevel(self.root)
        dlg.title(_("Incomplete Imports"))
        dlg.configure(bg=theme.bg_primary)
        dlg.geometry("700x410")
        dlg.transient(self.root)
        tk.Label(
            dlg,
            text=_("Resume or recover incomplete imports"),
            bg=theme.bg_primary,
            fg=theme.text_primary,
            font=FONTS.subtitle(bold=True),
        ).pack(anchor="w", padx=22, pady=(22, 6))
        tk.Label(
            dlg,
            text=_("Each session keeps its row checkpoints and original rollback safepoint."),
            bg=theme.bg_primary,
            fg=theme.text_secondary,
            font=FONTS.body(),
        ).pack(anchor="w", padx=22, pady=(0, 12))
        listing = tk.Listbox(
            dlg,
            bg=theme.bg_secondary,
            fg=theme.text_primary,
            selectbackground=theme.selection,
            font=FONTS.body(),
            exportselection=False,
            activestyle="none",
        )
        listing.pack(fill=tk.BOTH, expand=True, padx=22)
        for report in reports:
            listing.insert(
                tk.END,
                _("{source} · {status} · {added}/{total} added · {failed} failed · {pending} pending").format(
                    source=report.source,
                    status=report.status,
                    added=report.added,
                    total=report.total,
                    failed=report.failed,
                    pending=report.pending,
                ),
            )
        listing.selection_set(0)
        listing.focus_set()

        def selected():
            indices = listing.curselection()
            return reports[indices[0]] if indices else None

        def run_action(action: str):
            report = selected()
            if not report:
                return
            from bookmark_organizer_pro.services.import_sessions import ImportSessionManager

            sessions = ImportSessionManager()

            def work():
                if action == "rollback":
                    return sessions.rollback(self.bookmark_manager, report.session_id)
                if report.failed:
                    return sessions.retry(self.bookmark_manager, report.session_id)
                return sessions.resume(self.bookmark_manager, report.session_id)

            def complete(updated):
                dlg.destroy()
                self._on_import_done(updated.added, updated.duplicates)
                self._show_import_result_summary(
                    updated.source,
                    updated.added,
                    updated.duplicates,
                    _("Review the resumed session diagnostics."),
                    report=updated,
                )

            self.task_runner.run_task(
                f"startup-import-{action}-{report.session_id}",
                work,
                on_complete=complete,
                on_error=lambda error: self._show_toast(str(error), "error"),
            )

        buttons = tk.Frame(dlg, bg=theme.bg_primary)
        buttons.pack(side=tk.BOTTOM, fill=tk.X, padx=22, pady=18, before=listing)
        ModernButton(buttons, text=_("Resume / Retry"), style="primary",
                     command=lambda: run_action("resume"), padx=14, pady=7).pack(side=tk.RIGHT)
        ModernButton(buttons, text=_("Close"), command=dlg.destroy,
                     padx=14, pady=7).pack(side=tk.RIGHT, padx=(0, 8))
        ModernButton(buttons, text=_("Roll Back Selected"),
                     command=lambda: run_action("rollback"), padx=14, pady=7).pack(side=tk.LEFT)
        listing.bind("<Double-Button-1>", lambda _event: run_action("resume"))
        listing.bind("<Return>", lambda _event: run_action("resume"))
        dlg.bind("<Escape>", lambda _event: dlg.destroy())

    def _show_import_result_summary(
        self, label: str, added: int, dupes: int, next_action: str, *, report=None
    ):
        """Show a compact non-blocking import result with the next action."""
        theme = get_theme()
        dlg = tk.Toplevel(self.root)
        dlg.title(_("Import Summary"))
        dlg.configure(bg=theme.bg_primary)
        dlg.geometry("430x230")
        dlg.resizable(False, False)
        dlg.transient(self.root)

        summary_title = _("{source} Import Complete").format(source=label)
        if report and report.status not in {"completed", "rolled_back"}:
            summary_title = _("{source} Import Needs Attention").format(source=label)
        tk.Label(
            dlg,
            text=summary_title,
            bg=theme.bg_primary,
            fg=theme.text_primary,
            font=FONTS.subtitle(bold=True),
        ).pack(anchor="w", padx=22, pady=(22, 8))

        tk.Label(
            dlg,
            text=_("{added} imported. {dupes} duplicates skipped.").format(
                added=pluralize(added, "bookmark"),
                dupes=pluralize(dupes, "duplicate"),
            ),
            bg=theme.bg_primary,
            fg=theme.text_secondary,
            font=FONTS.body(),
            wraplength=380,
            justify=tk.LEFT,
        ).pack(anchor="w", padx=22, pady=(0, 12))

        tk.Label(
            dlg,
            text=_("Next: {action}").format(action=next_action),
            bg=theme.bg_primary,
            fg=theme.text_muted,
            font=FONTS.small(),
            wraplength=380,
            justify=tk.LEFT,
        ).pack(anchor="w", padx=22)

        buttons = tk.Frame(dlg, bg=theme.bg_primary)
        buttons.pack(side=tk.BOTTOM, fill=tk.X, padx=22, pady=18)

        def session_action(action: str):
            from bookmark_organizer_pro.services.import_sessions import ImportSessionManager

            sessions = ImportSessionManager()

            def work():
                if action == "retry":
                    return sessions.retry(self.bookmark_manager, report.session_id)
                if action == "resume":
                    return sessions.resume(self.bookmark_manager, report.session_id)
                return sessions.rollback(self.bookmark_manager, report.session_id)

            def complete(updated):
                self._refresh_all()
                dlg.destroy()
                self._show_toast(
                    _("Import session {status}: {added} added, {failed} failed, {losses} losses.").format(
                        status=updated.status,
                        added=updated.added,
                        failed=updated.failed,
                        losses=updated.losses,
                    ),
                    "success" if updated.status in {"completed", "rolled_back"} else "warning",
                )

            def failed(error):
                self._show_toast(str(error), "error")

            self.task_runner.run_task(
                f"import-{action}-{report.session_id}",
                work,
                on_complete=complete,
                on_error=failed,
            )

        ModernButton(
            buttons,
            text=_("Review Library"),
            style="primary",
            command=lambda: (dlg.destroy(), self._clear_search()),
            padx=14,
            pady=7,
        ).pack(side=tk.RIGHT)
        ModernButton(buttons, text=_("Close"), command=dlg.destroy, padx=14, pady=7).pack(side=tk.RIGHT, padx=(0, 8))
        if report and report.failed:
            ModernButton(
                buttons, text=_("Retry Failed"), command=lambda: session_action("retry"),
                padx=12, pady=7,
            ).pack(side=tk.LEFT)
        if report and report.pending:
            ModernButton(
                buttons, text=_("Resume"), command=lambda: session_action("resume"),
                padx=12, pady=7,
            ).pack(side=tk.LEFT)
        if report and report.safepoint:
            ModernButton(
                buttons, text=_("Roll Back"), command=lambda: session_action("rollback"),
                padx=12, pady=7,
            ).pack(side=tk.LEFT, padx=(0, 8))

    def _import_service_pocket(self):
        from bookmark_organizer_pro.importers_extra import PocketExportImporter
        self._import_service_file(PocketExportImporter, "Pocket",
                                  [("Pocket Export", "*.html *.json"), ("All", "*.*")])

    def _import_service_readwise(self):
        from bookmark_organizer_pro.importers_extra import ReadwiseReaderCSVImporter
        self._import_service_file(ReadwiseReaderCSVImporter, "Readwise",
                                  [("CSV", "*.csv"), ("All", "*.*")])

    def _import_service_raindrop(self):
        self._import_service_file(
            GenericFileSessionImporter,
            "Raindrop",
            [("CSV", "*.csv"), ("All", "*.*")],
        )

    def _import_service_firefox_backup(self):
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            title=_("Import Firefox Bookmark Backup"),
            filetypes=[
                ("Firefox backup", "*.json *.jsonlz4"),
                ("JSON", "*.json"),
                ("All", "*.*"),
            ],
            parent=self.root,
        )
        if not path:
            return

        self._begin_import_session(
            "Firefox Backup",
            FirefoxBookmarkBackupImporter(),
            path,
            source="firefoxbookmarkbackup",
            next_action=_("Review imported folders, then run tag cleanup."),
        )

    def _import_service_pinboard(self):
        from bookmark_organizer_pro.importers_extra import PinboardJSONImporter
        self._import_service_file(PinboardJSONImporter, "Pinboard",
                                  [("JSON", "*.json"), ("All", "*.*")])

    def _import_service_instapaper(self):
        from bookmark_organizer_pro.importers_extra import InstapaperImporter
        self._import_service_file(InstapaperImporter, "Instapaper",
                                  [("CSV", "*.csv"), ("All", "*.*")])

    def _import_service_reddit(self):
        from bookmark_organizer_pro.importers_extra import RedditSavedImporter
        self._import_service_file(RedditSavedImporter, "Reddit",
                                  [("JSON", "*.json"), ("All", "*.*")])

    def _import_service_matter(self):
        from bookmark_organizer_pro.importers_extra import MatterImporter
        self._import_service_file(MatterImporter, "Matter",
                                  [("CSV", "*.csv"), ("All", "*.*")])

    def _import_service_wallabag(self):
        from bookmark_organizer_pro.importers_extra import WallabagJSONImporter
        self._import_service_file(WallabagJSONImporter, "Wallabag",
                                  [("JSON", "*.json"), ("All", "*.*")])

    def _import_service_arc(self):
        from bookmark_organizer_pro.importers_extra import ArcBrowserImporter
        self._import_service_file(ArcBrowserImporter, "Arc Browser",
                                  [("JSON", "*.json"), ("All", "*.*")])

    def _import_service_zotero(self):
        from tkinter import filedialog
        from bookmark_organizer_pro.importers import ZoteroRDFSessionImporter
        path = filedialog.askopenfilename(
            title=_("Import from Zotero"),
            filetypes=[("RDF", "*.rdf"), ("All", "*.*")],
            parent=self.root,
        )
        if not path:
            return
        self._begin_import_session(
            "Zotero",
            ZoteroRDFSessionImporter(),
            path,
            source="zoterordfsession",
            next_action=_("Review imported references and export notes if needed."),
        )

    def _show_reading_list_import_help(self):
        """Surface the browser-extension Reading List migration path."""
        message = _(
            "Chrome Reading List import runs from the browser extension side panel. "
            "Start the local API, open the extension side panel, choose Add, then select Reading List."
        )
        self._set_status(message)
        self._show_toast(message, "info")

    def _show_export_dialog(self):
        """Show export dialog"""
        SelectiveExportDialog(self.root, self.bookmark_manager)
