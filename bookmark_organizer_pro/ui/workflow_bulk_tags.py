"""Bulk tag editing dialog."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Set

from bookmark_organizer_pro.models import Bookmark

from .foundation import FONTS
from .widget_controls import ModernButton, TagEditor, TagWidget, ThemedWidget
from .widget_runtime import apply_window_chrome, get_theme

# =============================================================================
# Bulk Tag Editor Dialog
# =============================================================================
class BulkTagEditorDialog(tk.Toplevel, ThemedWidget):
    """Dialog for bulk editing tags on multiple bookmarks"""
    
    def __init__(self, parent, bookmarks: List[Bookmark], 
                 available_tags: List[str],
                 on_apply: Callable = None):
        super().__init__(parent)
        self.bookmarks = bookmarks
        self.available_tags = available_tags
        self.on_apply = on_apply
        self.result = None
        
        theme = get_theme()
        
        self.title("Bulk Tag Editor")
        self.geometry("500x500")
        self.configure(bg=theme.bg_primary)
        self.transient(parent)
        self.grab_set()
        
        apply_window_chrome(self)
        
        # Header
        header = tk.Frame(self, bg=theme.bg_dark, height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(
            header, text=f"🏷️ Edit Tags for {len(bookmarks)} Bookmarks",
            bg=theme.bg_dark, fg=theme.text_primary,
            font=FONTS.header()
        ).pack(side=tk.LEFT, padx=20, pady=15)
        
        # Content
        content = tk.Frame(self, bg=theme.bg_primary)
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        # Current common tags
        tk.Label(
            content, text="Common Tags (present in all selected):",
            bg=theme.bg_primary, fg=theme.text_secondary,
            font=FONTS.body()
        ).pack(anchor="w")
        
        self.common_tags = self._get_common_tags()
        common_frame = tk.Frame(content, bg=theme.bg_primary)
        common_frame.pack(fill=tk.X, pady=(5, 15))
        
        if self.common_tags:
            for tag in self.common_tags:
                TagWidget(common_frame, tag, show_remove=False).pack(side=tk.LEFT, padx=2)
        else:
            tk.Label(
                common_frame, text="No common tags",
                bg=theme.bg_primary, fg=theme.text_muted,
                font=("Segoe UI", 9, "italic")
            ).pack(side=tk.LEFT)
        
        # Add tags section
        tk.Label(
            content, text="Add Tags:", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        ).pack(anchor="w", pady=(10, 5))
        
        self.add_tag_editor = TagEditor(content, tags=[], available_tags=available_tags)
        self.add_tag_editor.pack(fill=tk.X)
        
        # Remove tags section
        tk.Label(
            content, text="Remove Tags:", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        ).pack(anchor="w", pady=(15, 5))
        
        # Checkboxes for tags that exist on any bookmark
        self.all_tags = self._get_all_tags()
        self.remove_vars: Dict[str, tk.BooleanVar] = {}
        
        remove_frame = tk.Frame(content, bg=theme.bg_secondary)
        remove_frame.pack(fill=tk.X, pady=5)
        
        row_frame = tk.Frame(remove_frame, bg=theme.bg_secondary)
        row_frame.pack(fill=tk.X, padx=10, pady=10)
        col = 0
        
        for tag in sorted(self.all_tags):
            var = tk.BooleanVar(value=False)
            self.remove_vars[tag] = var
            
            cb = ttk.Checkbutton(
                row_frame, text=f"#{tag}", variable=var
            )
            cb.grid(row=col // 3, column=col % 3, sticky="w", padx=5, pady=2)
            col += 1
        
        # Replace all option
        self.replace_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            content, text="Replace all existing tags (instead of add/remove)",
            variable=self.replace_var
        ).pack(anchor="w", pady=(15, 10))
        
        # Buttons
        btn_frame = tk.Frame(self, bg=theme.bg_primary)
        btn_frame.pack(fill=tk.X, padx=20, pady=15)
        
        ModernButton(
            btn_frame, text="Cancel", command=self.destroy
        ).pack(side=tk.RIGHT, padx=(10, 0))
        
        ModernButton(
            btn_frame, text="Apply", command=self._apply,
            style="primary", icon="✓"
        ).pack(side=tk.RIGHT)
        
        self.center_window()
    
    def _get_common_tags(self) -> List[str]:
        """Get tags that are present in all selected bookmarks"""
        if not self.bookmarks:
            return []
        
        common = set(self.bookmarks[0].tags)
        for bm in self.bookmarks[1:]:
            common &= set(bm.tags)
        
        return sorted(common)
    
    def _get_all_tags(self) -> Set[str]:
        """Get all unique tags across selected bookmarks"""
        all_tags = set()
        for bm in self.bookmarks:
            all_tags.update(bm.tags)
        return all_tags
    
    def _apply(self):
        """Apply tag changes"""
        add_tags = self.add_tag_editor.get_tags()
        remove_tags = [tag for tag, var in self.remove_vars.items() if var.get()]
        replace_all = self.replace_var.get()
        
        self.result = {
            "add": add_tags,
            "remove": remove_tags,
            "replace_all": replace_all
        }
        
        if self.on_apply:
            self.on_apply(self.result)
        
        self.destroy()
    
    def center_window(self):
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')
