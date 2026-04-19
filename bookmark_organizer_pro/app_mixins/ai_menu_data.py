"""AI menu and learned-data actions for the app coordinator."""

from __future__ import annotations

import json
import re
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover - optional runtime dependency
    requests = None

from bookmark_organizer_pro.ai import AI_PROVIDERS, create_ai_client
from bookmark_organizer_pro.core.category_manager import get_category_icon
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark, Category
from bookmark_organizer_pro.ui.components import ScrollableFrame
from bookmark_organizer_pro.ui.foundation import FONTS, pluralize
from bookmark_organizer_pro.ui.widgets import ModernButton, apply_window_chrome, get_theme


class AiMenuDataMixin:
    """AI menu, tag merge, data export, stats, and learned pattern workflows."""

    def _show_ai_menu(self):
        """Show AI tools menu"""
        theme = get_theme()
        
        menu = tk.Menu(self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                      font=FONTS.body(), activebackground=theme.bg_hover,
                      activeforeground=theme.text_primary, bd=0)
        
        menu.add_command(label="  Categorize Selected", command=self._ai_categorize)
        menu.add_command(label="  Suggest Tags", command=self._ai_suggest_tags)
        menu.add_command(label="  Summarize", command=self._ai_summarize)
        menu.add_command(label="  Improve Titles", command=self._ai_improve_titles)
        menu.add_separator()
        menu.add_command(label="  Merge AI Tags to User Tags", command=self._merge_ai_tags)
        menu.add_separator()
        menu.add_command(label="  Export AI Data (JSON)", command=self._export_ai_data)
        menu.add_command(label="  Export Learned Patterns", command=self._generate_category_patterns)
        menu.add_command(label="  Import Learned Patterns", command=self._import_ai_learned_data)
        menu.add_separator()
        menu.add_command(label="  View AI Statistics", command=self._show_ai_stats)
        menu.add_command(label="  AI Settings", command=self._show_ai_settings)
        
        # Position below button
        x = self.ai_btn.winfo_rootx()
        y = self.ai_btn.winfo_rooty() + self.ai_btn.winfo_height()
        menu.tk_popup(x, y)
    
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
            messagebox.showinfo("Tags Merged", 
                f"Merged AI tags into user tags.\n\n"
                f"Bookmarks updated: {merged}\n"
                f"Tags added: {tags_added}")
        else:
            messagebox.showinfo("No AI Tags", 
                "No AI tags found to merge.\n\n"
                "Use 'AI Suggest Tags' first to generate AI tags.")
        
        self._set_status(f"Merged {tags_added} AI tags")
    
    def _export_ai_data(self):
        """Export AI-enriched bookmark data to JSON"""
        filepath = filedialog.asksaveasfilename(
            title="Export AI Data",
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
            
            messagebox.showinfo("Export Complete", 
                f"AI data exported successfully.\n\n"
                f"File: {filepath}\n"
                f"Bookmarks: {len(bookmarks)}\n"
                f"Categories: {len(export_data['categories'])}")
            self._set_status(f"Exported AI data to {Path(filepath).name}")
            
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export: {str(e)}")
    
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
        dialog.title("AI Statistics")
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
        tk.Label(dialog, text="📊 AI Processing Statistics", bg=theme.bg_primary,
                fg=theme.text_primary, font=FONTS.title(bold=False)).pack(pady=20)
        
        # Stats
        stats_frame = tk.Frame(dialog, bg=theme.bg_primary)
        stats_frame.pack(fill=tk.X, padx=30)
        
        stats = [
            ("Total Bookmarks", str(total)),
            ("AI Categorized", f"{with_ai_cat} ({100*with_ai_cat//max(1,total)}%)"),
            ("With AI Tags", f"{with_ai_tags} ({100*with_ai_tags//max(1,total)}%)"),
            ("With Descriptions", f"{with_desc} ({100*with_desc//max(1,total)}%)"),
            ("Avg. Confidence", f"{avg_confidence:.1%}"),
            ("Unique AI Tags", str(len(all_ai_tags)))
        ]
        
        for label, value in stats:
            row = tk.Frame(stats_frame, bg=theme.bg_primary)
            row.pack(fill=tk.X, pady=5)
            
            tk.Label(row, text=label + ":", bg=theme.bg_primary,
                    fg=theme.text_secondary, font=FONTS.body(),
                    width=20, anchor="w").pack(side=tk.LEFT)
            tk.Label(row, text=value, bg=theme.bg_primary,
                    fg=theme.text_primary, font=("Segoe UI", 10, "bold"),
                    anchor="e").pack(side=tk.RIGHT)
        
        # Top AI tags
        if all_ai_tags:
            tk.Label(dialog, text="Top AI Tags:", bg=theme.bg_primary,
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
        tk.Button(dialog, text="Close", command=dialog.destroy,
                 bg=theme.bg_secondary, fg=theme.text_primary,
                 font=FONTS.body(), padx=20, pady=5).pack(pady=20)
    
    def _generate_category_patterns(self):
        """Generate category patterns from AI-categorized bookmarks to enhance built-in rules"""
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        # Only use high-confidence AI categorizations
        ai_categorized = [bm for bm in bookmarks if bm.ai_confidence >= 0.7]
        
        if not ai_categorized:
            messagebox.showinfo("No AI Data", 
                "No high-confidence AI categorizations found.\n\n"
                "Run AI Categorize on your bookmarks first.")
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
            title="Export Category Patterns",
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
                "source": "Bookmark Organizer Pro - AI Learning",
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
            messagebox.showinfo("Patterns Exported", 
                f"Category patterns exported successfully!\n\n"
                f"File: {Path(filepath).name}\n"
                f"Categories: {len(export_data['categories'])}\n"
                f"Total patterns: {total_patterns}\n\n"
                "Share this file to help improve categorization for others!")
            self._set_status(f"Exported {total_patterns} learned patterns")
            
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export: {str(e)}")
    
    def _import_ai_learned_data(self):
        """Import AI-learned data from another user's export"""
        filepath = filedialog.askopenfilename(
            title="Import AI Learned Data",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        
        if not filepath:
            return
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check if it's our format
            if "categories" not in data:
                messagebox.showerror("Invalid File", "This doesn't appear to be an AI learned data file.")
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
            
            messagebox.showinfo("Import Complete", 
                f"AI learned data imported!\n\n"
                f"New categories: {imported}\n"
                f"Patterns added: {updated}")
            self._set_status(f"Imported {imported} categories, {updated} patterns")
            
        except Exception as e:
            messagebox.showerror("Import Error", f"Failed to import: {str(e)}")

