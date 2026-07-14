"""AI menu and learned-data actions for the app coordinator."""

from __future__ import annotations

import json
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Dict, List

from bookmark_organizer_pro.i18n import _, format_message

try:
    import requests
except ImportError:  # pragma: no cover - optional runtime dependency
    requests = None

from bookmark_organizer_pro.core.category_manager import get_category_icon
from bookmark_organizer_pro.models import Category
from bookmark_organizer_pro.ui.foundation import FONTS
from bookmark_organizer_pro.ui.widgets import ModernButton, get_theme


class AiMenuDataMixin:
    """AI menu, tag merge, data export, stats, and learned pattern workflows."""

    def _show_ai_menu(self):
        """Show AI tools menu"""
        theme = get_theme()
        
        menu = tk.Menu(self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                      font=FONTS.body(), activebackground=theme.bg_hover,
                      activeforeground=theme.text_primary, bd=0)
        
        menu.add_command(label=_("Categorize Selected"), command=self._ai_categorize)
        menu.add_command(label=_("Suggest Tags"), command=self._ai_suggest_tags)
        menu.add_command(label=_("Summarize Selected"), command=self._ai_summarize)
        menu.add_command(label=_("Improve Titles"), command=self._ai_improve_titles)
        menu.add_separator()
        menu.add_command(label=_("Undo Last Assistant Action"), command=self._undo_last_ai_operation)
        menu.add_separator()
        menu.add_command(label=_("Accept Suggested Tags"), command=self._merge_ai_tags)
        menu.add_separator()
        menu.add_command(label=_("Export Assistant Data"), command=self._export_ai_data)
        menu.add_command(label=_("Export Learned Patterns"), command=self._generate_category_patterns)
        menu.add_command(label=_("Import Learned Patterns"), command=self._import_ai_learned_data)
        menu.add_separator()
        menu.add_command(label=_("Assistant Activity"), command=self._show_ai_stats)
        menu.add_command(label=_("Assistant Settings"), command=self._show_ai_settings)
        
        # Position below button
        x = self.ai_btn.winfo_rootx()
        y = self.ai_btn.winfo_rooty() + self.ai_btn.winfo_height()
        menu.tk_popup(x, y)
    
    def _undo_last_ai_operation(self):
        """Restore bookmarks to their state before the most recent AI batch."""
        from bookmark_organizer_pro.services.ai_snapshot import delete_snapshot, list_snapshots, restore_snapshot

        snapshots = list_snapshots()
        if not snapshots:
            messagebox.showinfo(
                _("No Assistant Snapshots"),
                _("No assistant action snapshots are available to undo."),
                parent=self.root,
            )
            return

        latest = snapshots[0]
        count = restore_snapshot(latest["snapshot_id"], self.bookmark_manager)
        if count:
            delete_snapshot(latest["snapshot_id"])
            self._refresh_all()
            self._show_toast(f"Restored {count} bookmarks to the previous assistant state", "success")
            self._set_status(f"Undid assistant {latest['operation']} — {count} bookmarks restored")
        else:
            self._show_toast("No bookmarks could be restored", "info")

    def _merge_ai_tags(self):
        """Merge AI-suggested tags into user tags"""
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        merged = 0
        tags_added = 0
        
        for bm in bookmarks:
            if bm.ai_tags:
                # Merge AI tags into user tags (avoid duplicates)
                existing = set(t.lower() for t in bm.tags)
                for tag in bm.ai_tags:
                    if tag.lower() not in existing:
                        bm.tags.append(tag)
                        tags_added += 1
                        existing.add(tag.lower())
                
                if bm.ai_tags:
                    merged += 1
                    bm.modified_at = datetime.now().isoformat()
        
        if merged > 0:
            self.bookmark_manager.save_bookmarks()
            self._refresh_bookmark_list()
            messagebox.showinfo(_("Suggested Tags Accepted"),
                format_message('Suggested tags were added to user tags.\n\nBookmarks updated: {value_0}\nTags added: {value_1}', value_0=merged, value_1=tags_added))
        else:
            messagebox.showinfo(_("No Suggested Tags"),
                _("No suggested tags are available to accept.\n\n"
                "Use Suggest Tags first to generate suggestions."))
        
        self._set_status(f"Accepted {tags_added} suggested tags")
    
    def _export_ai_data(self):
        """Export AI-enriched bookmark data to JSON"""
        filepath = filedialog.asksaveasfilename(
            title=_("Export Assistant Data"),
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            initialfilename="bookmarks_ai_data.json"
        )
        
        if not filepath:
            return
        
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        # Build export data
        export_data = {
            "export_date": datetime.now().isoformat(),
            "total_bookmarks": len(bookmarks),
            "categories": {},
            "bookmarks": []
        }
        
        # Export category data
        for cat_name, cat in self.category_manager.categories.items():
            export_data["categories"][cat_name] = {
                "icon": cat.icon,
                "patterns": cat.patterns,
                "description": cat.description
            }
        
        # Export bookmark data with AI fields
        for bm in bookmarks:
            bm_data = {
                "url": bm.url,
                "title": bm.title,
                "domain": bm.domain,
                "category": bm.category,
                "tags": bm.tags,
                "ai_tags": bm.ai_tags,
                "ai_confidence": bm.ai_confidence,
                "description": bm.description,
                "created_at": bm.created_at
            }
            export_data["bookmarks"].append(bm_data)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            messagebox.showinfo(_("Export Complete"),
                format_message('Assistant data exported successfully.\n\nFile: {value_0}\nBookmarks: {value_1}\nCategories: {value_2}', value_0=filepath, value_1=len(bookmarks), value_2=len(export_data['categories'])))
            self._set_status(f"Exported assistant data to {Path(filepath).name}")
            
        except Exception as e:
            messagebox.showerror(_("Export Error"), format_message('Failed to export: {value_0}', value_0=str(e)))
    
    def _show_ai_stats(self):
        """Show AI processing statistics"""
        theme = get_theme()
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        # Calculate stats
        total = len(bookmarks)
        with_ai_cat = sum(1 for bm in bookmarks if bm.ai_confidence > 0)
        with_ai_tags = sum(1 for bm in bookmarks if bm.ai_tags)
        with_desc = sum(1 for bm in bookmarks if bm.description)
        
        avg_confidence = 0
        if with_ai_cat > 0:
            avg_confidence = sum(bm.ai_confidence for bm in bookmarks if bm.ai_confidence > 0) / with_ai_cat
        
        # Count unique AI tags
        all_ai_tags = set()
        for bm in bookmarks:
            all_ai_tags.update(bm.ai_tags)
        
        # Show dialog
        dialog = tk.Toplevel(self.root)
        dialog.title(_("Assistant Activity"))
        dialog.configure(bg=theme.bg_primary)
        dialog.geometry("400x350")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 400) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 350) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # Header
        tk.Label(dialog, text=_("Assistant Activity"), bg=theme.bg_primary,
                fg=theme.text_primary, font=FONTS.title(bold=False)).pack(pady=20)
        
        # Stats
        stats_frame = tk.Frame(dialog, bg=theme.bg_primary)
        stats_frame.pack(fill=tk.X, padx=30)
        
        stats = [
            ("Total Bookmarks", str(total)),
            ("Suggested Categories", f"{with_ai_cat} ({100*with_ai_cat//max(1,total)}%)"),
            ("Suggested Tags", f"{with_ai_tags} ({100*with_ai_tags//max(1,total)}%)"),
            ("With Descriptions", f"{with_desc} ({100*with_desc//max(1,total)}%)"),
            ("Avg. Confidence", f"{avg_confidence:.1%}"),
            ("Unique Suggestions", str(len(all_ai_tags)))
        ]
        
        for label, value in stats:
            row = tk.Frame(stats_frame, bg=theme.bg_primary)
            row.pack(fill=tk.X, pady=5)
            
            tk.Label(row, text=label + _(":"), bg=theme.bg_primary,
                    fg=theme.text_secondary, font=FONTS.body(),
                    width=20, anchor="w").pack(side=tk.LEFT)
            tk.Label(row, text=value, bg=theme.bg_primary,
                    fg=theme.text_primary, font=FONTS.small(bold=True),
                    anchor="e").pack(side=tk.RIGHT)
        
        # Top AI tags
        if all_ai_tags:
            tk.Label(dialog, text=_("Top Suggested Tags"), bg=theme.bg_primary,
                    fg=theme.text_secondary, font=FONTS.body()).pack(pady=(20, 5))
            
            # Count tag frequency
            tag_counts = {}
            for bm in bookmarks:
                for tag in bm.ai_tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
            
            top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            tags_text = ", ".join(f"{t} ({c})" for t, c in top_tags)
            
            tk.Label(dialog, text=tags_text, bg=theme.bg_primary,
                    fg=theme.accent_primary, font=FONTS.small(),
                    wraplength=350).pack(padx=20)
        
        # Close button
        ModernButton(
            dialog, text=_("Close"), command=dialog.destroy,
            padx=20, pady=5,
        ).pack(pady=20)
    
    def _generate_category_patterns(self):
        """Generate category patterns from AI-categorized bookmarks to enhance built-in rules"""
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        # Only use high-confidence AI categorizations
        ai_categorized = [bm for bm in bookmarks if bm.ai_confidence >= 0.7]
        
        if not ai_categorized:
            messagebox.showinfo(_("No Learned Patterns"),
                _("No high-confidence assistant categorizations are available yet.\n\n"
                "Run Categorize Selected on your bookmarks first."))
            return
        
        # Group domains by category
        category_domains: Dict[str, List[str]] = {}
        for bm in ai_categorized:
            cat = bm.category
            domain = bm.domain
            if cat and domain:
                if cat not in category_domains:
                    category_domains[cat] = []
                if domain not in category_domains[cat]:
                    category_domains[cat].append(domain)
        
        # Generate patterns file
        filepath = filedialog.asksaveasfilename(
            title=_("Export Category Patterns"),
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            initialfilename="learned_category_patterns.json"
        )
        
        if not filepath:
            return
        
        # Build export with domains sorted by frequency
        export_data = {
            "_meta": {
                "generated": datetime.now().isoformat(),
                "source": "Bookmark Organizer Pro - Assistant Learning",
                "total_bookmarks_analyzed": len(ai_categorized),
                "min_confidence": 0.7,
                "instructions": "Import this file using Tools > Import Categories File to add these patterns"
            },
            "categories": {}
        }
        
        for cat, domains in sorted(category_domains.items()):
            # Count how many bookmarks per domain
            domain_counts = {}
            for bm in ai_categorized:
                if bm.category == cat:
                    d = bm.domain
                    domain_counts[d] = domain_counts.get(d, 0) + 1
            
            # Sort by frequency and take top patterns
            sorted_domains = sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)
            top_patterns = [d for d, c in sorted_domains[:20]]  # Top 20 domains per category
            
            export_data["categories"][cat] = top_patterns
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            total_patterns = sum(len(p) for p in export_data["categories"].values())
            messagebox.showinfo(_("Patterns Exported"),
                format_message('Category patterns exported successfully!\n\nFile: {value_0}\nCategories: {value_1}\nTotal patterns: {value_2}\n\nShare this file to help improve categorization for others!', value_0=Path(filepath).name, value_1=len(export_data['categories']), value_2=total_patterns))
            self._set_status(f"Exported {total_patterns} learned patterns")
            
        except Exception as e:
            messagebox.showerror(_("Export Error"), format_message('Failed to export: {value_0}', value_0=str(e)))
    
    def _import_ai_learned_data(self):
        """Import AI-learned data from another user's export"""
        filepath = filedialog.askopenfilename(
            title=_("Import Learned Patterns"),
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        
        if not filepath:
            return
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check if it's our format
            if "categories" not in data:
                messagebox.showerror(_("Invalid File"), _("This does not appear to be a learned-pattern export."))
                return
            
            imported = 0
            updated = 0
            
            for cat_name, patterns in data.get("categories", {}).items():
                if not isinstance(patterns, list):
                    continue
                
                if cat_name not in self.category_manager.categories:
                    # Create new category
                    new_cat = Category(
                        name=cat_name,
                        patterns=patterns,
                        icon=get_category_icon(cat_name)
                    )
                    self.category_manager.categories[cat_name] = new_cat
                    imported += 1
                else:
                    # Merge patterns into existing
                    existing = self.category_manager.categories[cat_name]
                    existing_patterns = set(existing.patterns)
                    for pattern in patterns:
                        if pattern not in existing_patterns:
                            existing.patterns.append(pattern)
                            updated += 1
            
            self.category_manager.save_categories()
            self._refresh_category_list()
            
            messagebox.showinfo(_("Import Complete"),
                format_message('Learned patterns imported.\n\nNew categories: {value_0}\nPatterns added: {value_1}', value_0=imported, value_1=updated))
            self._set_status(f"Imported {imported} categories, {updated} patterns")
            
        except Exception as e:
            messagebox.showerror(_("Import Error"), format_message('Failed to import: {value_0}', value_0=str(e)))
