"""Tools menu actions for the app coordinator."""

from __future__ import annotations

import json
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox

try:
    import requests
except ImportError:  # pragma: no cover - optional runtime dependency
    requests = None

from bookmark_organizer_pro.constants import DATA_DIR
from bookmark_organizer_pro.core.category_manager import get_category_icon
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Category
from bookmark_organizer_pro.ui.foundation import FONTS, pluralize
from bookmark_organizer_pro.ui.management_dialogs import CategoryManagementDialog, CustomFaviconDialog
from bookmark_organizer_pro.ui.tk_interactions import make_keyboard_activatable
from bookmark_organizer_pro.ui.widgets import AnalyticsDashboard, Tooltip, get_theme
from bookmark_organizer_pro.url_utils import URLUtilities


class ToolsActionsMixin:
    """Tools menu, maintenance, and utility actions used by the app coordinator."""

    def _show_tools_menu(self):
        """Show tools menu"""
        theme = get_theme()
        
        menu = tk.Menu(self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                      font=FONTS.body(), activebackground=theme.bg_hover,
                      activeforeground=theme.text_primary, bd=0)
        
        menu.add_command(label="  Manage Categories", command=self._show_category_manager)
        menu.add_command(label="  Categorize All Bookmarks", command=self._categorize_all_bookmarks)
        menu.add_command(label="  Import Categories File", command=self._import_categories_file)
        menu.add_command(label="  Set Custom Favicon", command=self._show_custom_favicon_dialog)
        menu.add_separator()
        menu.add_command(label="  Check All Links", command=self._check_all_links)
        menu.add_command(label="  Find Duplicates", command=self._find_duplicates)
        menu.add_command(label="  Clean Tracking Parameters", command=self._clean_urls)
        menu.add_separator()
        menu.add_command(label="  Full Analytics", command=self._show_analytics)
        menu.add_command(label="  Backup Now", command=self._backup_now)
        menu.add_separator()
        menu.add_command(label="  Redownload All Favicons", command=self._redownload_all_favicons)
        menu.add_command(label="  Redownload Missing Favicons", command=self._redownload_missing_favicons)
        menu.add_command(label="  Clear Favicon Cache", command=self._clear_favicon_cache)
        
        # Position below button
        x = self.tools_btn.winfo_rootx()
        y = self.tools_btn.winfo_rooty() + self.tools_btn.winfo_height()
        menu.tk_popup(x, y)

    def _categorize_all_bookmarks(self):
        """Reprocess all bookmarks and categorize them based on category patterns - non-blocking"""
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        if not bookmarks:
            messagebox.showinfo(
                "Nothing to Categorize",
                "Import or add bookmarks before running automatic categorization.",
                parent=self.root
            )
            self._set_status("Add bookmarks before categorizing")
            return
        
        result = messagebox.askyesno(
            "Categorize All Bookmarks",
            f"Re-categorize {len(bookmarks)} bookmark(s) using your saved category patterns?\n\n"
            "This updates categories based on URL and title matches.",
            parent=self.root
        )
        
        if not result:
            return
        
        # Create progress display
        theme = get_theme()
        self._cat_cancelled = False
        
        progress_frame = tk.Frame(self.status_bar, bg=theme.bg_dark)
        progress_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        
        progress_label = tk.Label(
            progress_frame, text="Categorizing…", bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.small()
        )
        progress_label.pack(side=tk.LEFT, padx=5)
        
        progress_bar = tk.Frame(progress_frame, bg=theme.bg_tertiary, height=8, width=200)
        progress_bar.pack(side=tk.LEFT, padx=5)
        progress_bar.pack_propagate(False)
        
        progress_fill = tk.Frame(progress_bar, bg=theme.accent_primary, height=8)
        progress_fill.place(x=0, y=0, relheight=1.0, relwidth=0)
        
        cancel_btn = tk.Label(
            progress_frame, text="✕ Cancel", bg=theme.accent_error, fg="white",
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
                    self._set_status(f"Cancelled. Changed {self._cat_changed} bookmarks.")
                else:
                    self._set_status(f"Categorized {self._cat_changed} bookmarks")
                    messagebox.showinfo(
                        "Categorization Complete",
                        f"Categorized: {self._cat_changed} bookmarks\n"
                        f"Unchanged: {self._cat_unchanged} bookmarks"
                    )
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
            progress_label.configure(text=f"Categorizing: {self._cat_index}/{len(self._cat_bookmarks)} ({self._cat_changed} changed)")
            
            # Schedule next batch
            self.root.after(10, process_batch)
        
        # Start processing
        self.root.after(100, process_batch)

    def _import_categories_file(self):
        """Import categories from a JSON file"""
        filepath = filedialog.askopenfilename(
            title="Select Categories JSON File",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        
        if not filepath:
            return
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                categories_data = json.load(f)
            
            if not isinstance(categories_data, dict):
                messagebox.showerror(
                    "Categories Import Failed",
                    "The selected file is not a categories JSON object. Choose a file whose top level contains category names.",
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
            
            messagebox.showinfo(
                "Import Complete",
                f"Imported {imported} new categories.\n"
                f"Updated {updated} existing categories.\n"
                f"Total categories: {len(self.category_manager.categories)}",
                parent=self.root
            )
            self._set_status(f"Imported {imported} categories, updated {updated}")
            
        except json.JSONDecodeError as e:
            messagebox.showerror(
                "Categories Import Failed",
                f"The selected file is not valid JSON.\n\n{e}",
                parent=self.root
            )
        except Exception as e:
            log.warning("Categories import failed", exc_info=True)
            messagebox.showerror(
                "Categories Import Failed",
                f"Categories could not be imported.\n\n{e}",
                parent=self.root
            )

    def _check_all_links(self):
        """Check all links - non-blocking with cancel support"""
        if requests is None:
            messagebox.showerror(
                "Link Check Unavailable",
                "The requests package is required before link checks can run.",
                parent=self.root
            )
            self._set_status("Link checking is unavailable")
            return
        
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        if not bookmarks:
            messagebox.showinfo(
                "Nothing to Check",
                "Import or add bookmarks before running a link check.",
                parent=self.root
            )
            self._set_status("Add bookmarks before checking links")
            return
        
        # Create progress frame with cancel button
        theme = get_theme()
        self._link_check_cancelled = False
        
        progress_frame = tk.Frame(self.status_bar, bg=theme.bg_dark)
        progress_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        
        progress_label = tk.Label(
            progress_frame, text="Checking links…", bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.small()
        )
        progress_label.pack(side=tk.LEFT, padx=5)
        
        progress_bar = tk.Frame(progress_frame, bg=theme.bg_tertiary, height=8, width=200)
        progress_bar.pack(side=tk.LEFT, padx=5)
        progress_bar.pack_propagate(False)
        
        progress_fill = tk.Frame(progress_bar, bg=theme.accent_primary, height=8)
        progress_fill.place(x=0, y=0, relheight=1.0, relwidth=0)
        
        cancel_btn = tk.Label(
            progress_frame, text="✕ Cancel", bg=theme.accent_error, fg="white",
            font=FONTS.small(), padx=8, pady=2, cursor="hand2"
        )
        cancel_btn.pack(side=tk.LEFT, padx=10)
        
        def cancel_check():
            self._link_check_cancelled = True
            cancel_btn.configure(text="Cancelling…", bg=theme.text_muted)

        make_keyboard_activatable(cancel_btn, cancel_check)
        Tooltip(cancel_btn, "Cancel Link Check")
        
        self._set_status("Checking links…")
        
        broken_count = [0]  # Use list to allow modification in closure
        checked_count = [0]
        
        def check_links_batch():
            batch_size = 5
            start_idx = checked_count[0]
            end_idx = min(start_idx + batch_size, len(bookmarks))
            
            for i in range(start_idx, end_idx):
                if self._link_check_cancelled:
                    break
                
                bm = bookmarks[i]
                try:
                    if not URLUtilities._is_safe_url(bm.url):
                        bm.http_status = 0
                        bm.is_valid = False
                    else:
                        response = requests.head(
                            bm.url,
                            timeout=5,
                            allow_redirects=False,
                            headers={'User-Agent': 'Mozilla/5.0'}
                        )
                        bm.http_status = response.status_code
                        bm.is_valid = response.status_code < 400
                except Exception:
                    bm.http_status = 0
                    bm.is_valid = False
                
                if not bm.is_valid:
                    broken_count[0] += 1
                
                bm.last_checked = datetime.now().isoformat()
                checked_count[0] += 1
            
            # Update progress
            progress = checked_count[0] / len(bookmarks)
            progress_fill.place(relwidth=progress)
            progress_label.configure(text=f"Checked {checked_count[0]}/{len(bookmarks)} - {broken_count[0]} broken")
            
            # Save periodically and refresh filter counts
            if checked_count[0] % 20 == 0:
                self.bookmark_manager.save_bookmarks()
                self._refresh_analytics()
            
            # Continue or finish
            if checked_count[0] < len(bookmarks) and not self._link_check_cancelled:
                self.root.after(10, check_links_batch)
            else:
                # Complete
                self.bookmark_manager.save_bookmarks()
                progress_frame.destroy()
                status = "Cancelled" if self._link_check_cancelled else "Complete"
                self._set_status(f"{status}: Found {broken_count[0]} broken links")
                self._refresh_all()
                if not self._link_check_cancelled:
                    self._show_toast(f"Checked {checked_count[0]} links, found {broken_count[0]} broken", "success" if broken_count[0] == 0 else "warning")
        
        # Start checking
        self.root.after(100, check_links_batch)

    def _find_duplicates(self):
        """Find duplicates"""
        dupes = self.bookmark_manager.find_duplicates()
        
        if not dupes:
            self._show_toast("No duplicate bookmarks found", "success")
            return
        
        # dupes is Dict[str, List[Bookmark]] - use values()
        total = sum(len(g) - 1 for g in dupes.values())
        
        if messagebox.askyesno("Duplicates", f"Found {total} duplicates. Remove?"):
            for group in dupes.values():
                for bm in group[1:]:
                    self.bookmark_manager.delete_bookmark(bm.id)
            self._refresh_all()
            self._set_status(f"Removed {total} duplicates")

    def _clean_urls(self):
        """Clean tracking params"""
        count = self.bookmark_manager.clean_tracking_params()
        self._refresh_all()
        self._set_status(f"Cleaned {count} URLs")

    def _show_analytics(self):
        """Show full analytics"""
        dialog = AnalyticsDashboard(self.root, self.bookmark_manager)

    def _backup_now(self):
        """Create backup"""
        backup_dir = DATA_DIR / "backups"
        backup_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = backup_dir / f"backup_{timestamp}.json"
        
        self.bookmark_manager.export_json(str(filepath))
        self._set_status(f"Backup saved to {filepath.name}")

    def _clear_favicon_cache(self):
        """Clear favicon cache"""
        if messagebox.askyesno(
            "Clear Favicon Cache",
            "Clear all cached favicons?\n\n"
            "Bookmarks are kept. Icons will be downloaded again when needed.",
            parent=self.root
        ):
            self.favicon_manager.clear_cache()
            self._refresh_all()
            self._set_status("Favicon cache cleared")

    def _redownload_all_favicons(self):
        """Redownload all favicons"""
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        if not bookmarks:
            messagebox.showinfo(
                "No Favicons to Fetch",
                "Import or add bookmarks before downloading favicons.",
                parent=self.root
            )
            self._set_status("Add bookmarks before fetching favicons")
            return
        
        result = messagebox.askyesno(
            "Redownload Favicons",
            f"Redownload favicons for all {len(bookmarks)} bookmark(s)?\n\n"
            "This clears cached icons first and may take a little while.",
            parent=self.root
        )
        if not result:
            return
        
        self._set_status("Redownloading all favicons…")
        self.favicon_manager.redownload_all_favicons(bookmarks)

    def _redownload_missing_favicons(self):
        """Redownload only missing favicons"""
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        if not bookmarks:
            messagebox.showinfo(
                "No Favicons to Fetch",
                "Import or add bookmarks before downloading favicons.",
                parent=self.root
            )
            self._set_status("Add bookmarks before fetching favicons")
            return
        
        # Count missing
        missing_count = sum(1 for bm in bookmarks if not self.favicon_manager.get_cached(bm.domain))
        failed_count = len(self.favicon_manager.get_failed_domains())
        if missing_count == 0 and failed_count == 0:
            messagebox.showinfo(
                "Favicons Up to Date",
                "Every bookmark already has a cached favicon.",
                parent=self.root
            )
            self._set_status("Favicons are up to date")
            return
        
        result = messagebox.askyesno(
            "Redownload Missing Favicons",
            f"Found approximately {missing_count} bookmark(s) without cached favicons.\n"
            f"Previously failed domains: {failed_count}\n\n"
            "Retry missing and previously failed favicon downloads?",
            parent=self.root
        )
        if not result:
            return
        
        self._set_status("Redownloading missing favicons…")
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
            messagebox.showinfo(
                "Select a Bookmark",
                "Select one bookmark before choosing a custom favicon.",
                parent=self.root
            )
            self._set_status("Select one bookmark to customize its favicon")
            return
        
        bm_id = list(self.selected_bookmarks)[0]
        bookmark = self.bookmark_manager.get_bookmark(bm_id)
        if bookmark:
            CustomFaviconDialog(
                self.root, bookmark, self.bookmark_manager,
                on_update=self._refresh_all
            )

