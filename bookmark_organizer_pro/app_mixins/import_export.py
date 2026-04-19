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
from bookmark_organizer_pro.ui.widgets import get_theme


class ImportExportMixin:
    """File, browser, and export actions used by the app coordinator."""

    def _on_files_dropped(self, filepaths: List[str]):
        """Handle dropped files for import with backup and auto-categorization"""
        self.import_area.set_importing(True)
        self._set_status(f"Importing {pluralize(len(filepaths), 'file')}…")
        
        def do_import():
            total_added = 0
            total_dupes = 0
            imported_bookmarks = []
            
            try:
                for filepath in filepaths:
                    ext = Path(filepath).suffix.lower()
                    bookmarks = []
                    
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
                                                title=item.get('title', ''), category=item.get('category', 'Imported'))
                                    bookmarks.append(bm)
                        elif ext == '.csv':
                            bookmarks = RaindropImporter.import_from_csv(filepath)
                        elif ext == '.opml':
                            bookmarks = OPMLImporter.import_from_opml(filepath)
                        elif ext == '.txt':
                            bookmarks = TextURLImporter.import_from_text(filepath)
                        else:
                            continue
                        
                        for bm in bookmarks:
                            if bm and bm.url:
                                existing = self.bookmark_manager.find_by_url(bm.url)
                                if not existing:
                                    # Auto-categorize before adding
                                    if not bm.category or bm.category in ("Imported", "Uncategorized", "Uncategorized / Needs Review"):
                                        bm.category = self.category_manager.categorize_url(bm.url, bm.title)
                                    
                                    self.bookmark_manager.add_bookmark(bm, save=False)
                                    imported_bookmarks.append(bm)
                                    total_added += 1
                                else:
                                    total_dupes += 1
                    except Exception as e:
                        log.error(f"Import error for {filepath}: {e}")
                        self.root.after(0, lambda err=e: self._show_toast(
                            f"Error importing file: {str(err)[:80]}", "error"))
                
                # Save all bookmarks after batch import
                self.bookmark_manager.save_bookmarks()
                
                # Save to permanent import backup (grows forever)
                if imported_bookmarks:
                    self._save_import_backup(imported_bookmarks)
                    
            except Exception as e:
                log.error(f"Import thread error: {e}")
                self.root.after(0, lambda err=e: self._show_toast(
                    f"Import failed: {str(err)[:80]}", "error"))
            finally:
                # Always call completion handler
                self.root.after(0, lambda: self._on_import_done(total_added, total_dupes))
        
        # Start import thread
        import_thread = threading.Thread(target=do_import, daemon=True)
        import_thread.start()
    
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

        # Position below the import button area
        menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def _import_from_browser(self, browser: str):
        """Import bookmarks directly from a browser profile"""
        importer = BrowserProfileImporter()
        profiles = importer.get_profiles(browser)

        if not profiles:
            self._show_toast(f"No {browser.title()} profiles found", "warning")
            return

        # Use first profile (Default) — could add profile picker later
        profile_name, profile_path = profiles[0]

        def do_import():
            if browser == "firefox":
                bookmarks = importer.import_from_firefox(profile_path)
            else:
                bookmarks = importer.import_from_chrome(profile_path)

            added = 0
            dupes = 0
            for bm in bookmarks:
                if not bm.url or not bm.url.startswith(('http://', 'https://')):
                    continue
                existing = self.bookmark_manager.find_by_url(bm.url) if hasattr(self.bookmark_manager, 'find_by_url') else None
                if existing:
                    dupes += 1
                    continue
                bm.source_file = f"{browser}:{profile_name}"
                self.bookmark_manager.add_bookmark(bm, save=False)
                added += 1

            if added > 0:
                self.bookmark_manager.save_bookmarks()
                self.root.after(0, self._refresh_all)

            self.root.after(0, lambda: self._show_toast(
                f"Imported {pluralize(added, 'bookmark')} from {browser.title()}. Skipped {pluralize(dupes, 'duplicate')}.",
                "success" if added > 0 else "info"
            ))

        import threading
        threading.Thread(target=do_import, daemon=True).start()
        self._show_toast(f"Importing from {browser.title()}…", "info")
    
    def _show_export_dialog(self):
        """Show export dialog"""
        dialog = SelectiveExportDialog(self.root, self.bookmark_manager)

