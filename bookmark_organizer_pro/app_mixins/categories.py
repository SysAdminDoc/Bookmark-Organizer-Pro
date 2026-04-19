"""Category sidebar actions for the desktop app coordinator."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from bookmark_organizer_pro.ui.foundation import FONTS, format_compact_count, pluralize, truncate_middle
from bookmark_organizer_pro.ui.tk_interactions import make_keyboard_activatable
from bookmark_organizer_pro.ui.widgets import ModernButton, Tooltip, apply_window_chrome, get_theme


class CategoryActionsMixin:
    """Category sidebar rendering and category-management actions."""

    def _refresh_category_list(self):
        """Refresh category list in sidebar with right-click support"""
        if not hasattr(self, 'categories_frame') or not self.categories_frame:
            return
        
        theme = get_theme()
        
        for widget in self.categories_frame.winfo_children():
            widget.destroy()
        
        counts = self.bookmark_manager.get_category_counts()
        categories = sorted(
            set(self.category_manager.get_sorted_categories()) |
            {cat for cat, count in counts.items() if count > 0},
            key=lambda name: name.lower()
        )
        self.categories_frame.bind("<Button-3>", self._show_add_category_menu)

        total_bookmarks = len(self.bookmark_manager.get_all_bookmarks())
        if total_bookmarks == 0:
            tk.Label(
                self.categories_frame,
                text="Categories appear after you import or add bookmarks.",
                bg=theme.bg_dark, fg=theme.text_muted,
                font=FONTS.small(), wraplength=250, justify=tk.LEFT
            ).pack(anchor="w", padx=10, pady=8)
            return

        categories = [cat for cat in categories if counts.get(cat, 0) > 0 or cat == self.current_category]
        if not categories:
            tk.Label(
                self.categories_frame,
                text="No active categories yet.",
                bg=theme.bg_dark, fg=theme.text_muted,
                font=FONTS.small(), wraplength=260, justify=tk.LEFT
            ).pack(anchor="w", padx=10, pady=8)
            return
        
        for cat in categories:
            count = counts.get(cat, 0)
            is_selected = (cat == self.current_category)
            bg = theme.selection if is_selected else theme.bg_dark

            row = tk.Frame(
                self.categories_frame, bg=bg, cursor="hand2",
                highlightthickness=1,
                highlightbackground=theme.border_muted if is_selected else bg
            )
            row.pack(fill=tk.X, pady=2)

            name_lbl = tk.Label(
                row, text=truncate_middle(cat, 20),
                bg=bg, fg=theme.text_primary if is_selected else theme.text_secondary,
                font=FONTS.body(bold=is_selected), anchor="w", padx=10, pady=6,
                cursor="hand2"
            )
            name_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

            if count > 0:
                count_lbl = tk.Label(
                    row, text=format_compact_count(count),
                    bg=theme.bg_tertiary, fg=theme.text_secondary,
                    font=FONTS.tiny(bold=True), padx=7, pady=1,
                    cursor="hand2"
                )
                count_lbl.pack(side=tk.RIGHT, padx=(4, 8), pady=6)
            else:
                count_lbl = None

            for w in [row, name_lbl] + ([count_lbl] if count_lbl else []):
                w.bind("<Button-1>", lambda e, c=cat: self._select_category(c))
                w.bind("<Button-3>", lambda e, c=cat: self._show_category_context_menu(e, c))

            def on_enter(e, r=row, n=name_lbl, cl=count_lbl, c=cat):
                if c != self.current_category:
                    for w in [r, n] + ([cl] if cl else []):
                        w.configure(bg=theme.bg_hover)
                    n.configure(fg=theme.text_primary)
            def on_leave(e, r=row, n=name_lbl, cl=count_lbl, c=cat):
                if c != self.current_category:
                    bg_ = theme.bg_dark
                    for w in [r, n]:
                        w.configure(bg=bg_)
                    n.configure(fg=theme.text_secondary)
                    if cl:
                        cl.configure(bg=theme.bg_tertiary)

            for w in [row, name_lbl] + ([count_lbl] if count_lbl else []):
                w.bind("<Enter>", on_enter)
                w.bind("<Leave>", on_leave)

            make_keyboard_activatable(row, lambda c=cat: self._select_category(c))
            row.bind("<FocusIn>", lambda e, r=row, n=name_lbl, cl=count_lbl, c=cat: on_enter(e, r, n, cl, c), add="+")
            row.bind("<FocusOut>", lambda e, r=row, n=name_lbl, cl=count_lbl, c=cat: on_leave(e, r, n, cl, c), add="+")
            Tooltip(row, f"Show {cat} ({pluralize(count, 'bookmark')})")
        
        # Also bind right-click on empty space for "Add Category"
        self.categories_frame.bind("<Button-3>", self._show_add_category_menu)
    
    def _show_category_context_menu(self, event, category: str):
        """Show context menu for category"""
        theme = get_theme()
        
        menu = tk.Menu(self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                      activebackground=theme.bg_hover, activeforeground=theme.text_primary)
        menu.add_command(label="  ➕  Add New Category", command=self._add_new_category_dialog)
        menu.add_command(label="  ✏️  Rename Category", command=lambda: self._rename_category_dialog(category))
        menu.add_separator()
        menu.add_command(label="  🗑️  Delete Category", command=lambda: self._delete_category_confirm(category))
        
        menu.tk_popup(event.x_root, event.y_root)
    
    def _show_add_category_menu(self, event):
        """Show menu for adding new category"""
        theme = get_theme()
        
        menu = tk.Menu(self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                      activebackground=theme.bg_hover, activeforeground=theme.text_primary)
        menu.add_command(label="  ➕  Add New Category", command=self._add_new_category_dialog)
        
        menu.tk_popup(event.x_root, event.y_root)
    
    def _add_new_category_dialog(self):
        """Show dialog to add new category"""
        theme = get_theme()
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Category")
        dialog.configure(bg=theme.bg_primary)
        dialog.geometry("380x170")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        apply_window_chrome(dialog)
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 380) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 170) // 2
        dialog.geometry(f"+{x}+{y}")
        
        tk.Label(
            dialog, text="Add category", bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.header(bold=True)
        ).pack(anchor="w", padx=24, pady=(20, 2))

        tk.Label(
            dialog, text="Create a reusable destination for future bookmark organization.",
            bg=theme.bg_primary, fg=theme.text_secondary,
            font=FONTS.small(), wraplength=320, justify=tk.LEFT
        ).pack(anchor="w", padx=24, pady=(0, 10))
        
        entry = tk.Entry(
            dialog, bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary,
            font=FONTS.body(), relief=tk.FLAT, width=34,
            highlightthickness=1, highlightbackground=theme.border_muted,
            highlightcolor=theme.accent_primary
        )
        entry.pack(anchor="w", padx=24, ipady=6)
        entry.focus_set()
        
        def add():
            name = entry.get().strip()
            if name:
                if self.category_manager.add_category(name):
                    dialog.destroy()
                    self._refresh_category_list()
                    self._set_status(f"Added category: {name}")
                else:
                    messagebox.showerror(
                        "Category Not Added",
                        "Use a unique category name with at least one visible character.",
                        parent=dialog
                    )
            else:
                dialog.destroy()
        
        entry.bind("<Return>", lambda e: add())

        actions = tk.Frame(dialog, bg=theme.bg_primary)
        actions.pack(fill=tk.X, padx=24, pady=(14, 0))
        ModernButton(actions, text="Add", command=add, style="success", padx=20, pady=7).pack(side=tk.RIGHT)
        ModernButton(actions, text="Cancel", command=dialog.destroy, padx=16, pady=7).pack(side=tk.RIGHT, padx=(0, 8))
        dialog.bind("<Escape>", lambda e: dialog.destroy())
    
    def _rename_category_dialog(self, old_name: str):
        """Show dialog to rename category"""
        theme = get_theme()
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Rename Category")
        dialog.configure(bg=theme.bg_primary)
        dialog.geometry("350x120")
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(
            dialog, text="New Name:", bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.body()
        ).pack(pady=(20, 5))
        
        entry = tk.Entry(
            dialog, bg=theme.bg_secondary, fg=theme.text_primary,
            font=FONTS.body(), relief=tk.FLAT, width=30
        )
        entry.pack(pady=5, ipady=5)
        entry.insert(0, old_name)
        entry.select_range(0, tk.END)
        entry.focus_set()
        
        def rename():
            new_name = entry.get().strip()
            if new_name and new_name != old_name:
                # Update bookmarks
                for bm in self.bookmark_manager.get_bookmarks_by_category(old_name):
                    bm.category = new_name
                    self.bookmark_manager.update_bookmark(bm)
                
                self.category_manager.rename_category(old_name, new_name)
                dialog.destroy()
                self._refresh_category_list()
                self._refresh_bookmark_list()
                self._set_status(f"Renamed category to: {new_name}")
            else:
                dialog.destroy()
        
        entry.bind("<Return>", lambda e: rename())
        
        tk.Button(
            dialog, text="Rename", bg=theme.accent_primary, fg="white",
            font=FONTS.body(), relief=tk.FLAT, command=rename, padx=20
        ).pack(pady=10)
    
    def _delete_category_confirm(self, category: str):
        """Confirm and delete category"""
        count = len(self.bookmark_manager.get_bookmarks_by_category(category))
        
        msg = f"Delete the category '{category}'?"
        if count > 0:
            msg += f"\n\n{pluralize(count, 'bookmark')} will be moved to 'Uncategorized / Needs Review'."
        
        if messagebox.askyesno("Delete Category", msg, parent=self.root):
            # Move bookmarks to Uncategorized
            for bm in self.bookmark_manager.get_bookmarks_by_category(category):
                bm.category = "Uncategorized / Needs Review"
                self.bookmark_manager.update_bookmark(bm)
            
            # Delete the category
            if category in self.category_manager.categories:
                del self.category_manager.categories[category]
                self.category_manager.save_categories()
            
            self._refresh_category_list()
            self._refresh_bookmark_list()
            self._refresh_analytics()
            self._set_status(f"Deleted category: {category}")

