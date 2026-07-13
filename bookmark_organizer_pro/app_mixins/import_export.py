"""Import and export workflows for the app coordinator."""

from __future__ import annotations

import json
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from typing import List

from bookmark_organizer_pro.constants import BACKUP_DIR
from bookmark_organizer_pro.i18n import _
from bookmark_organizer_pro.importers import (
    BrowserProfileImporter,
    FirefoxBookmarkBackupImporter,
    NetscapeBookmarkImporter,
    OPMLImporter,
    RaindropImporter,
    TextURLImporter,
)
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.recovery_workflow import RecoveryWorkflow
from bookmark_organizer_pro.ui.bookmark_workflows import SelectiveExportDialog
from bookmark_organizer_pro.ui.foundation import FONTS, pluralize
from bookmark_organizer_pro.ui.import_center import ImportCenterDialog, ImportSource, build_import_sources
from bookmark_organizer_pro.ui.live_workflow import LiveWorkflowDialog
from bookmark_organizer_pro.ui.widgets import ModernButton, get_theme


class ImportProgressModal(tk.Toplevel):
    """Large centered modal that shows import progress."""

    def __init__(
        self,
        parent,
        source_label: str = "file",
        next_action: str = "Review imported bookmarks, then run duplicate and tag cleanup.",
    ):
        super().__init__(parent)
        theme = get_theme()
        self._next_action = next_action

        self.title(_("Importing Bookmarks"))
        self.configure(bg=theme.bg_primary)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        width, height = 500, 300
        self.geometry(f"{width}x{height}")
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
        self.geometry(f"+{max(0, px)}+{max(0, py)}")

        try:
            self.attributes("-topmost", True)
        except Exception:
            pass

        # --- Icon ---
        tk.Label(
            self, text="↓", bg=theme.bg_primary,
            fg=theme.accent_primary, font=FONTS.display(bold=True),
        ).pack(pady=(28, 8))

        # --- Title ---
        self._title_label = tk.Label(
            self, text=_("Importing from {source}…").format(source=source_label),
            bg=theme.bg_primary, fg=theme.text_primary,
            font=FONTS.subtitle(bold=True),
        )
        self._title_label.pack()

        # --- Status ---
        self._status_label = tk.Label(
            self, text=_("Preparing…"),
            bg=theme.bg_primary, fg=theme.text_secondary,
            font=FONTS.body(),
        )
        self._status_label.pack(pady=(6, 12))

        # --- Progress bar ---
        bar_frame = tk.Frame(self, bg=theme.bg_primary)
        bar_frame.pack(fill=tk.X, padx=48)

        self._bar_bg = tk.Frame(bar_frame, bg=theme.bg_tertiary, height=6)
        self._bar_bg.pack(fill=tk.X)

        self._bar_fill = tk.Frame(self._bar_bg, bg=theme.accent_primary, height=6)
        self._bar_fill.place(x=0, y=0, relheight=1.0, relwidth=0)

        # --- Count ---
        self._count_label = tk.Label(
            self, text="",
            bg=theme.bg_primary, fg=theme.text_muted,
            font=FONTS.small(),
        )
        self._count_label.pack(pady=(10, 0))

        self._animating = True
        self._animate_pos = 0.0
        self._animate()

    def _animate(self):
        if not self._animating:
            return
        self._animate_pos += 0.03
        if self._animate_pos > 0.7:
            self._animate_pos = 0.0
        self._bar_fill.place(relx=self._animate_pos, relwidth=0.3)
        self.after(40, self._animate)

    def set_progress(self, current: int, total: int, added: int, dupes: int):
        self._animating = False
        pct = current / max(total, 1)
        self._bar_fill.place(relx=0, relwidth=pct)
        self._status_label.configure(text=_("Processing bookmark {current} of {total}").format(current=f"{current:,}", total=f"{total:,}"))
        parts = []
        if added:
            parts.append(_("{count} added").format(count=f"{added:,}"))
        if dupes:
            parts.append(_("{count} skipped").format(count=f"{dupes:,}"))
        self._count_label.configure(text=" · ".join(parts) if parts else "")

    def set_categorizing(self):
        self._status_label.configure(text=_("Auto-categorizing bookmarks…"))

    def set_saving(self):
        self._status_label.configure(text=_("Saving to library…"))

    def finish(self, added: int, dupes: int):
        theme = get_theme()
        self._animating = False
        self._bar_fill.place(relx=0, relwidth=1.0)
        self._bar_fill.configure(bg=theme.accent_success)
        self._title_label.configure(text=_("Import Complete"))
        self._status_label.configure(
            text=_("{added} bookmarks imported, {dupes} duplicates skipped").format(added=f"{added:,}", dupes=f"{dupes:,}"),
            fg=theme.text_primary,
        )
        self._count_label.configure(text="")

        tk.Label(
            self,
            text=_("Next: {action}").format(action=self._next_action),
            bg=theme.bg_primary,
            fg=theme.text_secondary,
            font=FONTS.small(),
            wraplength=400,
            justify=tk.CENTER,
        ).pack(pady=(8, 0))

        btn_frame = tk.Frame(self, bg=theme.bg_primary)
        btn_frame.pack(pady=(12, 0))
        ModernButton(
            btn_frame, text=_("Done"), style="primary",
            command=self._close, padx=24, pady=8,
        ).pack()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def finish_error(self, message: str):
        theme = get_theme()
        self._animating = False
        self._bar_fill.place(relx=0, relwidth=1.0)
        self._bar_fill.configure(bg=theme.accent_error)
        self._title_label.configure(text=_("Import Failed"))
        self._status_label.configure(text=message[:120], fg=theme.accent_error)

        btn_frame = tk.Frame(self, bg=theme.bg_primary)
        btn_frame.pack(pady=(12, 0))
        ModernButton(
            btn_frame, text=_("Close"), command=self._close, padx=24, pady=8,
        ).pack()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _close(self):
        self.grab_release()
        self.destroy()


class ImportExportMixin:
    """File, browser, and export actions used by the app coordinator."""

    def _on_files_dropped(self, filepaths: List[str]):
        """Handle dropped files for import with progress modal."""
        self.import_area.set_importing(True)

        file_names = ", ".join(Path(f).name for f in filepaths[:3])
        if len(filepaths) > 3:
            file_names += f" (+{len(filepaths) - 3} more)"
        modal = ImportProgressModal(
            self.root,
            source_label=file_names,
            next_action="Review imported categories, then run duplicate and tag cleanup.",
        )

        def do_import():
            # Capture a recoverable snapshot of the pre-import state first, so a
            # bad import can be rolled back from File → Restore from Backup.
            self.bookmark_manager.create_safepoint("pre-import")

            total_added = 0
            total_dupes = 0
            imported_bookmarks = []
            all_parsed: List[Bookmark] = []

            try:
                # Phase 1: Parse all files
                for filepath in filepaths:
                    ext = Path(filepath).suffix.lower()
                    bookmarks: List[Bookmark] = []
                    try:
                        if ext in ('.html', '.htm'):
                            bookmarks = NetscapeBookmarkImporter.import_from_netscape(filepath)
                        elif ext == '.json':
                            if FirefoxBookmarkBackupImporter.looks_like_backup(filepath):
                                bookmarks = FirefoxBookmarkBackupImporter.import_from_json(filepath)
                            else:
                                with open(filepath, 'r', encoding='utf-8') as f:
                                    data = json.load(f)
                                items = data if isinstance(data, list) else data.get('bookmarks', [])
                                for item in items:
                                    if isinstance(item, dict) and item.get('url'):
                                        bm = Bookmark(id=None, url=item.get('url', ''),
                                                      title=item.get('title', ''),
                                                      category=item.get('category', 'Imported'))
                                        bookmarks.append(bm)
                        elif ext == '.jsonlz4':
                            bookmarks = FirefoxBookmarkBackupImporter.import_from_json(filepath)
                        elif ext == '.csv':
                            bookmarks = RaindropImporter.import_from_csv(filepath)
                        elif ext == '.opml':
                            bookmarks = OPMLImporter.import_from_opml(filepath)
                        elif ext == '.txt':
                            bookmarks = TextURLImporter.import_from_text(filepath)
                    except Exception as e:
                        log.error(f"Import error for {filepath}: {e}")
                    all_parsed.extend(b for b in bookmarks if b and b.url)

                total = len(all_parsed)

                # Phase 2: Deduplicate, categorize, add
                for i, bm in enumerate(all_parsed):
                    existing = self.bookmark_manager.find_by_url(bm.url)
                    if existing:
                        total_dupes += 1
                    else:
                        if not bm.category or bm.category in (
                            "Imported", "Uncategorized", "Uncategorized / Needs Review"
                        ):
                            bm.category = self.category_manager.categorize_url(bm.url, bm.title)
                        self.bookmark_manager.add_bookmark(bm, save=False)
                        imported_bookmarks.append(bm)
                        total_added += 1

                    if (i + 1) % 25 == 0 or i == total - 1:
                        self.root.after(0, lambda c=i+1, t=total, a=total_added, d=total_dupes:
                                        modal.set_progress(c, t, a, d))

                # Phase 3: Save
                self.root.after(0, modal.set_saving)
                self.bookmark_manager.save_bookmarks()

                if imported_bookmarks:
                    self._save_import_backup(imported_bookmarks)

                self.root.after(0, lambda: modal.finish(total_added, total_dupes))

            except Exception as e:
                log.error(f"Import thread error: {e}")
                # `e` is unbound once this except block exits; capture the text
                # before scheduling the deferred UI callback.
                err_text = str(e)[:120]
                self.root.after(0, lambda: modal.finish_error(err_text))
            finally:
                self.root.after(0, lambda: self._on_import_done(total_added, total_dupes))

        threading.Thread(target=do_import, daemon=True).start()
    
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

    def _save_import_backup(self, bookmarks: List[Bookmark]):
        """Save imported bookmarks to permanent backup file (grows forever)"""
        backup_file = BACKUP_DIR / "import_history_backup.json"
        
        try:
            # Load existing backup
            existing = []
            if backup_file.exists():
                with open(backup_file, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            
            # Add new bookmarks with timestamp
            timestamp = datetime.now().isoformat()
            for bm in bookmarks:
                existing.append({
                    'url': bm.url,
                    'title': bm.title,
                    'category': bm.category,
                    'tags': bm.tags,
                    'notes': bm.notes,
                    'imported_at': timestamp
                })
            
            # Save back
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            
            log.info("Saved %s bookmarks to import backup. Total: %s", len(bookmarks), len(existing))
        except Exception:
            log.warning("Error saving import backup", exc_info=True)
    
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
        """Import bookmarks directly from a browser profile with progress modal."""
        importer = BrowserProfileImporter()
        profiles = importer.get_profiles(browser)

        if not profiles:
            self._show_toast(_("No {browser} profiles found").format(browser=browser.title()), "warning")
            return

        profile_name, profile_path = profiles[0]
        modal = ImportProgressModal(
            self.root,
            source_label=f"{browser.title()} ({profile_name})",
            next_action="Review browser folders, then run duplicate and tag cleanup.",
        )

        def do_import():
            try:
                if browser == "firefox":
                    bookmarks = importer.import_from_firefox(profile_path)
                else:
                    bookmarks = importer.import_from_chrome(profile_path)

                valid = [bm for bm in bookmarks if bm.url and bm.url.startswith(('http://', 'https://'))]
                total = len(valid)
                added = 0
                dupes = 0

                for i, bm in enumerate(valid):
                    existing = self.bookmark_manager.find_by_url(bm.url)
                    if existing:
                        dupes += 1
                    else:
                        if not bm.category or bm.category in (
                            "Imported", "Uncategorized", "Uncategorized / Needs Review"
                        ):
                            bm.category = self.category_manager.categorize_url(bm.url, bm.title)
                        bm.source_file = f"{browser}:{profile_name}"
                        self.bookmark_manager.add_bookmark(bm, save=False)
                        added += 1

                    if (i + 1) % 25 == 0 or i == total - 1:
                        self.root.after(0, lambda c=i+1, t=total, a=added, d=dupes:
                                        modal.set_progress(c, t, a, d))

                self.root.after(0, modal.set_saving)
                if added > 0:
                    self.bookmark_manager.save_bookmarks()

                self.root.after(0, lambda: modal.finish(added, dupes))
                self.root.after(0, lambda: self._on_import_done(added, dupes))

            except Exception as e:
                log.error(f"Browser import error: {e}")
                # `e` is unbound once this except block exits; capture the text
                # before scheduling the deferred UI callback.
                err_text = str(e)[:120]
                self.root.after(0, lambda: modal.finish_error(err_text))

        threading.Thread(target=do_import, daemon=True).start()
    
    def _import_service_file(self, importer_cls, label, filetypes):
        from tkinter import filedialog
        from bookmark_organizer_pro.importers_extra import import_into
        path = filedialog.askopenfilename(
            title=_("Import from {source}").format(source=label),
            filetypes=filetypes,
            parent=self.root,
        )
        if not path:
            return
        self.bookmark_manager.create_safepoint("pre-import")
        added, dupes = import_into(self.bookmark_manager, importer_cls(), path)
        self._on_import_done(added, dupes)
        self._show_import_result_summary(
            label,
            added,
            dupes,
            _("Review imported items, then run duplicate and tag cleanup."),
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

    def _show_import_result_summary(self, label: str, added: int, dupes: int, next_action: str):
        """Show a compact non-blocking import result with the next action."""
        theme = get_theme()
        dlg = tk.Toplevel(self.root)
        dlg.title(_("Import Summary"))
        dlg.configure(bg=theme.bg_primary)
        dlg.geometry("430x230")
        dlg.resizable(False, False)
        dlg.transient(self.root)

        tk.Label(
            dlg,
            text=_("{source} Import Complete").format(source=label),
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
        ModernButton(
            buttons,
            text=_("Review Library"),
            style="primary",
            command=lambda: (dlg.destroy(), self._clear_search()),
            padx=14,
            pady=7,
        ).pack(side=tk.RIGHT)
        ModernButton(buttons, text=_("Close"), command=dlg.destroy, padx=14, pady=7).pack(side=tk.RIGHT, padx=(0, 8))

    def _import_service_pocket(self):
        from bookmark_organizer_pro.importers_extra import PocketExportImporter
        self._import_service_file(PocketExportImporter, "Pocket",
                                  [("Pocket Export", "*.html *.json"), ("All", "*.*")])

    def _import_service_readwise(self):
        from bookmark_organizer_pro.importers_extra import ReadwiseReaderCSVImporter
        self._import_service_file(ReadwiseReaderCSVImporter, "Readwise",
                                  [("CSV", "*.csv"), ("All", "*.*")])

    def _import_service_raindrop(self):
        class RaindropCSVServiceImporter:
            def from_path(self, path: str):
                return iter(RaindropImporter.import_from_csv(path))

        self._import_service_file(
            RaindropCSVServiceImporter,
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

        from bookmark_organizer_pro.importers_extra import import_into

        self.bookmark_manager.create_safepoint("pre-import")
        importer = FirefoxBookmarkBackupImporter()
        added, dupes = import_into(self.bookmark_manager, importer, path)
        skipped = importer.stats.skipped
        self._on_import_done(added, dupes)
        self._show_import_result_summary(
            "Firefox Backup",
            added,
            dupes,
            _(
                "{skipped} invalid or missing-URL item(s) skipped. Review imported folders, then run tag cleanup."
            ).format(skipped=skipped),
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
        from bookmark_organizer_pro.services.zotero_interop import import_zotero_rdf
        path = filedialog.askopenfilename(
            title=_("Import from Zotero"),
            filetypes=[("RDF", "*.rdf"), ("All", "*.*")],
            parent=self.root,
        )
        if not path:
            return
        self.bookmark_manager.create_safepoint("pre-import")
        bookmarks = import_zotero_rdf(path)
        added = dupes = 0
        for bm in bookmarks:
            if self.bookmark_manager.url_exists(bm.url):
                dupes += 1
            else:
                self.bookmark_manager.add_bookmark(bm, save=False)
                added += 1
        if added:
            self.bookmark_manager.save_bookmarks()
        self._on_import_done(added, dupes)
        self._show_import_result_summary(
            "Zotero",
            added,
            dupes,
            _("Review imported references and export notes if needed."),
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
