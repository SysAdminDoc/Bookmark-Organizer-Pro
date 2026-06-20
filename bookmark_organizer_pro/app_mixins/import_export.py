"""Import and export workflows for the app coordinator."""

from __future__ import annotations

import json
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from typing import List

from bookmark_organizer_pro.constants import BACKUP_DIR
from bookmark_organizer_pro.importers import (
    BrowserProfileImporter,
    NetscapeBookmarkImporter,
    OPMLImporter,
    RaindropImporter,
    TextURLImporter,
)
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.ui.bookmark_workflows import SelectiveExportDialog
from bookmark_organizer_pro.ui.foundation import FONTS, pluralize
from bookmark_organizer_pro.ui.widgets import ModernButton, get_theme


class ImportProgressModal(tk.Toplevel):
    """Large centered modal that shows import progress."""

    def __init__(self, parent, source_label: str = "file"):
        super().__init__(parent)
        theme = get_theme()

        self.title("Importing Bookmarks")
        self.configure(bg=theme.bg_primary)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        width, height = 480, 260
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
            self, text=f"Importing from {source_label}…",
            bg=theme.bg_primary, fg=theme.text_primary,
            font=FONTS.subtitle(bold=True),
        )
        self._title_label.pack()

        # --- Status ---
        self._status_label = tk.Label(
            self, text="Preparing…",
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
        self._status_label.configure(text=f"Processing bookmark {current:,} of {total:,}")
        parts = []
        if added:
            parts.append(f"{added:,} added")
        if dupes:
            parts.append(f"{dupes:,} skipped")
        self._count_label.configure(text=" · ".join(parts) if parts else "")

    def set_categorizing(self):
        self._status_label.configure(text="Auto-categorizing bookmarks…")

    def set_saving(self):
        self._status_label.configure(text="Saving to library…")

    def finish(self, added: int, dupes: int):
        theme = get_theme()
        self._animating = False
        self._bar_fill.place(relx=0, relwidth=1.0)
        self._bar_fill.configure(bg=theme.accent_success)
        self._title_label.configure(text="Import Complete")
        self._status_label.configure(
            text=f"{added:,} bookmarks imported, {dupes:,} duplicates skipped",
            fg=theme.text_primary,
        )
        self._count_label.configure(text="")

        btn_frame = tk.Frame(self, bg=theme.bg_primary)
        btn_frame.pack(pady=(12, 0))
        ModernButton(
            btn_frame, text="Done", style="primary",
            command=self._close, padx=24, pady=8,
        ).pack()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def finish_error(self, message: str):
        theme = get_theme()
        self._animating = False
        self._bar_fill.place(relx=0, relwidth=1.0)
        self._bar_fill.configure(bg=theme.accent_error)
        self._title_label.configure(text="Import Failed")
        self._status_label.configure(text=message[:120], fg=theme.accent_error)

        btn_frame = tk.Frame(self, bg=theme.bg_primary)
        btn_frame.pack(pady=(12, 0))
        ModernButton(
            btn_frame, text="Close", command=self._close, padx=24, pady=8,
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
        modal = ImportProgressModal(self.root, source_label=file_names)

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
                            with open(filepath, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                            items = data if isinstance(data, list) else data.get('bookmarks', [])
                            for item in items:
                                if isinstance(item, dict) and item.get('url'):
                                    bm = Bookmark(id=None, url=item.get('url', ''),
                                                  title=item.get('title', ''),
                                                  category=item.get('category', 'Imported'))
                                    bookmarks.append(bm)
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
        dlg.title("Restore from Backup")
        dlg.configure(bg=theme.bg_primary)
        dlg.geometry("640x470")
        dlg.minsize(540, 380)
        dlg.transient(self.root)
        dlg.grab_set()
        apply_window_chrome(dlg)

        tk.Label(dlg, text="Restore bookmarks from a backup or safepoint",
                 bg=theme.bg_primary, fg=theme.text_primary,
                 font=FONTS.subtitle(bold=True)).pack(anchor="w", padx=18, pady=(16, 4))
        tk.Label(dlg, text=("A safepoint is captured automatically at startup and before each "
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
            lb.insert(tk.END, "  (no backups yet — they appear after the first save/import)")

        def do_restore():
            sel = lb.curselection()
            if not names or not sel:
                return
            if self.bookmark_manager.restore_backup(names[sel[0]]):
                self._refresh_all()
                if hasattr(self, "_show_toast"):
                    self._show_toast("Bookmarks restored from backup", "success")
                dlg.destroy()
            elif hasattr(self, "_show_toast"):
                self._show_toast("Restore failed — see logs", "error")

        ModernButton(btns, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT, padx=(10, 0))
        ModernButton(btns, text="Restore selected", command=do_restore,
                     style="primary").pack(side=tk.RIGHT)
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
        except Exception as e:
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
        """Show import options menu"""
        theme = get_theme()
        menu = tk.Menu(self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                       activebackground=theme.bg_hover, activeforeground=theme.text_primary,
                       font=FONTS.body())
        menu.add_command(label="  Import from File…", command=self.import_area._browse_files)
        menu.add_separator()

        # Detect installed browsers
        importer = BrowserProfileImporter()
        browsers = importer.get_available_browsers()
        if browsers:
            for browser in browsers:
                menu.add_command(
                    label=f"  Import from {browser.title()}…",
                    command=lambda b=browser: self._import_from_browser(b)
                )
        else:
            menu.add_command(label="  No browsers detected", state="disabled")

        menu.add_separator()
        service_importers = [
            ("Pocket (HTML/JSON)", "*.html *.json", self._import_service_pocket),
            ("Readwise Reader (CSV)", "*.csv", self._import_service_readwise),
            ("Pinboard (JSON)", "*.json", self._import_service_pinboard),
            ("Instapaper (CSV)", "*.csv", self._import_service_instapaper),
            ("Reddit Saved (JSON)", "*.json", self._import_service_reddit),
            ("Matter (CSV)", "*.csv", self._import_service_matter),
            ("Wallabag (JSON)", "*.json", self._import_service_wallabag),
            ("Arc Browser (JSON)", "*.json", self._import_service_arc),
            ("Zotero (RDF)", "*.rdf", self._import_service_zotero),
        ]
        for label, _, callback in service_importers:
            menu.add_command(label=f"  Import from {label}", command=callback)

        menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def _import_from_browser(self, browser: str):
        """Import bookmarks directly from a browser profile with progress modal."""
        importer = BrowserProfileImporter()
        profiles = importer.get_profiles(browser)

        if not profiles:
            self._show_toast(f"No {browser.title()} profiles found", "warning")
            return

        profile_name, profile_path = profiles[0]
        modal = ImportProgressModal(self.root, source_label=f"{browser.title()} ({profile_name})")

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
            title=f"Import from {label}",
            filetypes=filetypes,
            parent=self.root,
        )
        if not path:
            return
        added, dupes = import_into(self.bookmark_manager, importer_cls(), path)
        self._on_import_done(added, dupes)

    def _import_service_pocket(self):
        from bookmark_organizer_pro.importers_extra import PocketExportImporter
        self._import_service_file(PocketExportImporter, "Pocket",
                                  [("Pocket Export", "*.html *.json"), ("All", "*.*")])

    def _import_service_readwise(self):
        from bookmark_organizer_pro.importers_extra import ReadwiseReaderCSVImporter
        self._import_service_file(ReadwiseReaderCSVImporter, "Readwise",
                                  [("CSV", "*.csv"), ("All", "*.*")])

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
            title="Import from Zotero",
            filetypes=[("RDF", "*.rdf"), ("All", "*.*")],
            parent=self.root,
        )
        if not path:
            return
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

    def _show_export_dialog(self):
        """Show export dialog"""
        dialog = SelectiveExportDialog(self.root, self.bookmark_manager)

