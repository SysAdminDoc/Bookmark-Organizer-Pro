"""AI categorization workflow for bookmark selections."""

from __future__ import annotations

from datetime import datetime
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Dict, List

from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.ui.foundation import FONTS
from bookmark_organizer_pro.ui.widgets import ModernButton, apply_window_chrome, get_theme

class AiCategorizationMixin:
    """AI categorization workflow for selected bookmarks."""

    def _ai_categorize(self):
        """AI categorize selected bookmarks"""
        if not self._ensure_ai_ready("AI categorization"):
            return
        
        bookmarks = self._get_selected_bookmarks_for_action(
            "Select Bookmarks",
            "Select one or more bookmarks, then run AI categorization."
        )
        if not bookmarks:
            return
        
        # Confirm action
        if not messagebox.askyesno(
            "Categorize with AI",
            f"Categorize {len(bookmarks)} bookmark(s) with AI?\n\n"
            f"Provider: {self._ai_provider_name()}\n"
            f"Model: {self.ai_config.get_model()}\n"
            f"Minimum confidence: {int(self.ai_config.get_min_confidence() * 100)}%\n\n"
            "Changes are applied only when the result meets your confidence threshold.",
            parent=self.root
        ):
            return
        
        # Run AI categorization
        self._run_ai_categorization(bookmarks)
    
    def _run_ai_categorization(self, bookmarks: List[Bookmark]):
        """Run AI categorization in background with progress"""
        theme = get_theme()
        
        # Create progress dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("AI Categorization")
        dialog.configure(bg=theme.bg_primary)
        dialog.geometry("480x280")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        apply_window_chrome(dialog)
        
        # Center dialog
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 480) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 280) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # Content
        content = tk.Frame(dialog, bg=theme.bg_primary, padx=28, pady=24)
        content.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            content, text="AI categorization", bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.title(bold=True)
        ).pack(anchor="w")

        tk.Label(
            content,
            text=f"Reviewing {len(bookmarks)} bookmark(s) with {self._ai_provider_name()}.",
            bg=theme.bg_primary, fg=theme.text_secondary,
            font=FONTS.small(), wraplength=420, justify=tk.LEFT
        ).pack(anchor="w", pady=(4, 18))
        
        status_label = tk.Label(
            content, text="Preparing request…", bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.body()
        )
        status_label.pack(anchor="w")
        
        # Progress bar frame
        progress_frame = tk.Frame(content, bg=theme.bg_tertiary, height=10)
        progress_frame.pack(fill=tk.X, pady=(12, 10))
        progress_frame.pack_propagate(False)
        
        progress_fill = tk.Frame(progress_frame, bg=theme.accent_primary, height=10)
        progress_fill.place(x=0, y=0, relheight=1.0, relwidth=0)
        
        results_label = tk.Label(
            content, text="No changes have been applied yet.", bg=theme.bg_primary,
            fg=theme.text_muted, font=FONTS.small()
        )
        results_label.pack(anchor="w")
        
        # Cancel flag
        self._ai_cancelled = False
        
        def cancel():
            self._ai_cancelled = True
            cancel_btn.set_state("disabled")
            cancel_btn.set_text("Cancelling…")
            status_label.configure(text="Cancelling after the current request finishes…")
            self._set_status("Cancelling AI categorization…")
        
        footer = tk.Frame(dialog, bg=theme.bg_secondary, padx=20, pady=14)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        cancel_btn = ModernButton(footer, text="Cancel", command=cancel, style="default", padx=18, pady=7)
        cancel_btn.pack(side=tk.RIGHT)
        dialog.bind("<Escape>", lambda e: cancel())
        
        # Process in batches
        batch_size = self.ai_config.get_batch_size()
        categories = self.category_manager.get_sorted_categories()
        allow_new = self.ai_config.get_auto_create_categories()
        suggest_tags = self.ai_config.get_suggest_tags()
        
        total_processed = 0
        total_changed = 0
        all_results = []
        
        def process_batch(start_idx):
            nonlocal total_processed, total_changed, all_results
            
            if self._ai_cancelled:
                if dialog.winfo_exists():
                    dialog.destroy()
                self._set_status(f"AI categorization cancelled after {total_processed} bookmark(s)")
                return

            if start_idx >= len(bookmarks):
                # Done - apply results
                progress_fill.place(relwidth=1)
                if dialog.winfo_exists():
                    dialog.destroy()
                self._apply_ai_results(bookmarks, all_results, total_changed)
                return
            
            end_idx = min(start_idx + batch_size, len(bookmarks))
            batch = bookmarks[start_idx:end_idx]
            
            status_label.configure(text=f"Processing batch {start_idx//batch_size + 1}…")
            progress_fill.place(relwidth=start_idx / len(bookmarks))
            dialog.update()
            
            try:
                client = self._get_ai_client()
                if not client:
                    self._show_ai_client_error("AI categorization")
                    dialog.destroy()
                    return
                
                # Prepare bookmark data for AI
                bm_data = [{"url": bm.url, "title": bm.title} for bm in batch]
                
                # Call AI
                results = client.categorize_bookmarks(bm_data, categories, allow_new, suggest_tags)
                all_results.extend(results)
                
                # Count changes
                for i, result in enumerate(results):
                    if start_idx + i < len(bookmarks):
                        bm = bookmarks[start_idx + i]
                        if result.get("category") != bm.category:
                            total_changed += 1
                
                total_processed = end_idx
                results_label.configure(
                    text=f"{total_processed}/{len(bookmarks)} processed • {total_changed} category changes found"
                )
                
                # Rate limiting delay
                delay = int(60000 / self.ai_config.get_rate_limit())
                dialog.after(delay, lambda: process_batch(end_idx))
                
            except Exception as e:
                log.warning("AI categorization failed", exc_info=True)
                messagebox.showerror(
                    "AI Categorization Failed",
                    f"Categorization stopped before changes were applied.\n\n{str(e)[:240]}",
                    parent=self.root
                )
                self._set_status("AI categorization failed")
                dialog.destroy()
        
        # Start processing
        dialog.after(100, lambda: process_batch(0))
    
    def _apply_ai_results(self, bookmarks: List[Bookmark], results: List[Dict], changed_count: int):
        """Apply AI categorization results to bookmarks"""
        min_confidence = self.ai_config.get_min_confidence()
        
        # Create result mapping
        result_map = {r["url"]: r for r in results}
        
        applied = 0
        titles_changed = 0
        new_categories = set()
        
        for bm in bookmarks:
            result = result_map.get(bm.url)
            if not result:
                continue
            
            confidence = result.get("confidence", 0)
            if confidence < min_confidence:
                continue
            
            # Update category
            new_cat = result.get("category", bm.category)
            if new_cat and new_cat != bm.category:
                # Add new category if needed
                if result.get("new_category") and new_cat not in self.category_manager.categories:
                    self.category_manager.add_category(new_cat)
                    new_categories.add(new_cat)
                
                bm.category = new_cat
                bm.ai_confidence = confidence
                applied += 1
            
            # Update AI tags
            ai_tags = result.get("tags", [])
            if ai_tags:
                bm.ai_tags = [t.lower().strip() for t in ai_tags if t]
            
            # Update title if suggested
            suggested_title = result.get("suggested_title")
            if suggested_title and suggested_title != bm.title and suggested_title.lower() not in ["null", "none", ""]:
                bm.title = suggested_title
                titles_changed += 1
            
            # Store reasoning if available
            reasoning = result.get("reasoning", "")
            if reasoning and not bm.description:
                bm.description = reasoning
            
            bm.modified_at = datetime.now().isoformat()
        
        # Save changes
        self.bookmark_manager.save_bookmarks()
        self.category_manager.save_categories()
        self._refresh_all()
        
        # Show summary
        msg = "AI categorization is complete.\n\n"
        msg += f"Bookmarks processed: {len(bookmarks)}\n"
        msg += f"Categories changed: {applied}\n"
        if titles_changed > 0:
            msg += f"Titles improved: {titles_changed}\n"
        if new_categories:
            msg += f"New categories created: {', '.join(new_categories)}\n"
        
        messagebox.showinfo("AI Categorization Complete", msg, parent=self.root)
        self._set_status(f"AI categorized {applied} bookmarks, {titles_changed} titles improved")
