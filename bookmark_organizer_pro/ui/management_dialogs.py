"""Category and favicon management dialogs for the desktop UI."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services import FaviconWrapperGenerator

from .foundation import FONTS, pluralize
from .tk_interactions import make_keyboard_activatable
from .widgets import ModernButton, Tooltip, apply_window_chrome, get_theme


# =============================================================================
# CATEGORY MANAGEMENT DIALOG
# =============================================================================
class CategoryManagementDialog(tk.Toplevel):
    """Dialog for creating, renaming, and deleting bookmark categories."""
    
    def __init__(self, parent, category_manager, bookmark_manager, on_change: Callable = None):
        super().__init__(parent)
        
        theme = get_theme()
        self.category_manager = category_manager
        self.bookmark_manager = bookmark_manager
        self.on_change = on_change
        self._category_placeholder = "New category name…"
        self._category_placeholder_active = True
        
        self.title("Manage Categories")
        self.configure(bg=theme.bg_primary)
        self.geometry("560x660")
        self.transient(parent)
        self.grab_set()
        apply_window_chrome(self)
        
        # Header
        header = tk.Frame(self, bg=theme.bg_dark)
        header.pack(fill=tk.X)
        
        tk.Label(
            header, text="📁 Manage Categories", bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.title(bold=True)
        ).pack(anchor="w", padx=22, pady=(18, 4))
        
        tk.Label(
            header, text="Keep your collection structure clean and predictable.",
            bg=theme.bg_dark, fg=theme.text_secondary, font=FONTS.body()
        ).pack(anchor="w", padx=22, pady=(0, 18))
        
        # Add category section
        add_frame = tk.LabelFrame(
            self, text=" Add New Category ", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        )
        add_frame.pack(fill=tk.X, padx=20, pady=(0, 15))
        
        add_inner = tk.Frame(add_frame, bg=theme.bg_primary)
        add_inner.pack(fill=tk.X, padx=10, pady=10)
        
        self.new_cat_entry = tk.Entry(
            add_inner, bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, font=FONTS.body(),
            relief=tk.FLAT,
            highlightthickness=1, highlightbackground=theme.border_muted,
            highlightcolor=theme.accent_primary
        )
        self.new_cat_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10), ipady=5)
        self._show_category_placeholder()
        self.new_cat_entry.bind("<FocusIn>", lambda e: self._clear_placeholder())
        self.new_cat_entry.bind("<FocusOut>", lambda e: self._restore_placeholder())
        self.new_cat_entry.bind("<Return>", lambda e: self._add_category())
        
        add_btn = ModernButton(
            add_inner, text="Add", style="success", icon="➕",
            command=self._add_category
        )
        add_btn.pack(side=tk.RIGHT)
        
        # Category list
        list_frame = tk.LabelFrame(
            self, text=" Existing Categories ", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        )
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 15))
        
        # Scrollable list
        canvas = tk.Canvas(list_frame, bg=theme.bg_primary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)
        self.cat_list_frame = tk.Frame(canvas, bg=theme.bg_primary)
        
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        canvas.create_window((0, 0), window=self.cat_list_frame, anchor="nw")
        self.cat_list_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        self._populate_categories()
        
        footer = tk.Frame(self, bg=theme.bg_primary)
        footer.pack(fill=tk.X, padx=20, pady=(0, 18))

        ModernButton(
            footer, text="Close", command=self.destroy,
            padx=22, pady=9
        ).pack(side=tk.RIGHT)

        self.bind("<Escape>", lambda e: self.destroy())
        self.center_window()
    
    def _clear_placeholder(self):
        if self._category_placeholder_active:
            self.new_cat_entry.delete(0, tk.END)
            self.new_cat_entry.configure(fg=get_theme().text_primary)
            self._category_placeholder_active = False

    def _show_category_placeholder(self):
        self.new_cat_entry.delete(0, tk.END)
        self.new_cat_entry.insert(0, self._category_placeholder)
        self.new_cat_entry.configure(fg=get_theme().text_muted)
        self._category_placeholder_active = True

    def _restore_placeholder(self):
        if not self.new_cat_entry.get().strip():
            self._show_category_placeholder()
    
    def _populate_categories(self):
        """Populate the category list"""
        theme = get_theme()
        
        # Clear existing
        for widget in self.cat_list_frame.winfo_children():
            widget.destroy()
        
        categories = self.category_manager.get_sorted_categories()

        if not categories:
            tk.Label(
                self.cat_list_frame,
                text="No categories yet. Create one above or import bookmarks to seed the list.",
                bg=theme.bg_primary, fg=theme.text_secondary,
                font=FONTS.body(), wraplength=460,
                justify=tk.LEFT, padx=12, pady=18
            ).pack(anchor="w", fill=tk.X)
            return
        
        for cat_name in categories:
            cat = self.category_manager.categories.get(cat_name)
            if not cat:
                continue
            
            # Count bookmarks in this category
            count = len(self.bookmark_manager.get_bookmarks_by_category(cat_name))
            
            row = tk.Frame(
                self.cat_list_frame, bg=theme.bg_secondary,
                highlightbackground=theme.border_muted,
                highlightthickness=1
            )
            row.pack(fill=tk.X, pady=2, padx=5)
            
            # Icon and name
            tk.Label(
                row, text=f"{cat.icon} {cat_name}", bg=theme.bg_secondary,
                fg=theme.text_primary, font=FONTS.body(bold=True), anchor="w"
            ).pack(side=tk.LEFT, padx=(12, 8), pady=9)
            
            # Count badge
            tk.Label(
                row, text=f"{count} bookmark{'s' if count != 1 else ''}",
                bg=theme.bg_secondary,
                fg=theme.text_secondary, font=FONTS.small()
            ).pack(side=tk.LEFT)
            
            # Buttons
            btn_frame = tk.Frame(row, bg=theme.bg_secondary)
            btn_frame.pack(side=tk.RIGHT, padx=5)
            
            # Edit button
            edit_btn = tk.Label(
                btn_frame, text="✏️", bg=theme.bg_secondary,
                fg=theme.text_secondary, font=("Segoe UI", 12), cursor="hand2"
            )
            edit_btn.pack(side=tk.LEFT, padx=5, pady=5)
            make_keyboard_activatable(edit_btn, lambda n=cat_name: self._edit_category(n))
            Tooltip(edit_btn, f"Rename {cat_name}")
            
            # Delete button
            del_btn = tk.Label(
                btn_frame, text="🗑️", bg=theme.bg_secondary,
                fg=theme.accent_error, font=("Segoe UI", 12), cursor="hand2"
            )
            del_btn.pack(side=tk.LEFT, padx=5, pady=5)
            make_keyboard_activatable(del_btn, lambda n=cat_name: self._delete_category(n))
            Tooltip(del_btn, f"Delete {cat_name}")
    
    def _add_category(self):
        """Add new category"""
        name = self.new_cat_entry.get().strip()
        if self._category_placeholder_active or not name:
            messagebox.showinfo(
                "Category name required",
                "Enter a category name before adding it.",
                parent=self
            )
            self.new_cat_entry.focus_set()
            return

        if name:
            if self.category_manager.add_category(name):
                self._show_category_placeholder()
                self._populate_categories()
                if self.on_change:
                    self.on_change()
            else:
                messagebox.showerror(
                    "Category not added",
                    "That category already exists or the name is not valid.",
                    parent=self
                )
    
    def _edit_category(self, old_name: str):
        """Edit category name"""
        theme = get_theme()
        
        dialog = tk.Toplevel(self)
        dialog.title("Edit Category")
        dialog.configure(bg=theme.bg_primary)
        dialog.geometry("350x150")
        dialog.transient(self)
        dialog.grab_set()
        apply_window_chrome(dialog)
        
        tk.Label(
            dialog, text="New name:", bg=theme.bg_primary,
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
        
        def save():
            new_name = entry.get().strip()
            if new_name and new_name != old_name:
                # Update bookmarks with this category
                for bm in self.bookmark_manager.get_bookmarks_by_category(old_name):
                    bm.category = new_name
                    self.bookmark_manager.update_bookmark(bm)
                
                self.category_manager.rename_category(old_name, new_name)
                dialog.destroy()
                self._populate_categories()
                if self.on_change:
                    self.on_change()
            else:
                dialog.destroy()
        
        ModernButton(
            dialog, text="Save", bg=theme.accent_primary, fg="white",
            command=save, padx=24, pady=8, style="primary"
        ).pack(pady=15)
        entry.bind("<Return>", lambda e: save())
        dialog.bind("<Escape>", lambda e: dialog.destroy())
    
    def _delete_category(self, name: str):
        """Delete category and move bookmarks to Uncategorized"""
        if name == "Uncategorized / Needs Review":
            messagebox.showwarning(
                "Category required",
                "The default review category keeps uncategorized bookmarks recoverable and cannot be deleted.",
                parent=self
            )
            return

        count = len(self.bookmark_manager.get_bookmarks_by_category(name))
        
        msg = f"Delete category '{name}'?"
        if count > 0:
            msg += f"\n\n{pluralize(count, 'bookmark')} will be moved to 'Uncategorized / Needs Review'."
        
        if messagebox.askyesno("Delete Category", msg, parent=self):
            # Move bookmarks to Uncategorized
            for bm in self.bookmark_manager.get_bookmarks_by_category(name):
                bm.category = "Uncategorized / Needs Review"
                self.bookmark_manager.update_bookmark(bm)
            
            # Delete the category
            if name in self.category_manager.categories:
                del self.category_manager.categories[name]
                self.category_manager.save_categories()
            
            self._populate_categories()
            if self.on_change:
                self.on_change()

    def center_window(self):
        """Center the dialog on screen."""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')



# =============================================================================
# CUSTOM FAVICON DIALOG
# =============================================================================
class CustomFaviconDialog(tk.Toplevel):
    """Dialog to set a custom favicon for a bookmark"""
    
    def __init__(self, parent, bookmark: Bookmark, bookmark_manager, on_update: Callable = None):
        super().__init__(parent)
        
        theme = get_theme()
        self.bookmark = bookmark
        self.bookmark_manager = bookmark_manager
        self.on_update = on_update
        self.selected_favicon = None
        
        self.title("Custom Favicon")
        self.configure(bg=theme.bg_primary)
        self.geometry("450x350")
        self.transient(parent)
        self.grab_set()
        apply_window_chrome(self)
        
        # Header
        tk.Label(
            self, text="🎨 Set Custom Favicon", bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.title(bold=False)
        ).pack(pady=(20, 5))
        
        tk.Label(
            self, text=f"For: {bookmark.title[:50]}", bg=theme.bg_primary,
            fg=theme.text_muted, font=FONTS.body()
        ).pack(pady=(0, 15))
        
        # Current favicon preview
        preview_frame = tk.Frame(self, bg=theme.bg_secondary)
        preview_frame.pack(pady=15, padx=20)
        
        tk.Label(
            preview_frame, text="Current:", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.body()
        ).pack(side=tk.LEFT, padx=10, pady=10)
        
        self.preview_label = tk.Label(
            preview_frame, text="🌐", bg=theme.bg_secondary,
            font=("Segoe UI Emoji", 24)
        )
        self.preview_label.pack(side=tk.LEFT, padx=10, pady=10)
        
        tk.Label(
            preview_frame, text="→", bg=theme.bg_secondary,
            fg=theme.text_muted, font=("Segoe UI", 16)
        ).pack(side=tk.LEFT, padx=10)
        
        tk.Label(
            preview_frame, text="New:", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.body()
        ).pack(side=tk.LEFT, padx=10, pady=10)
        
        self.new_preview = tk.Label(
            preview_frame, text="?", bg=theme.bg_secondary,
            font=("Segoe UI", 24), fg=theme.text_muted
        )
        self.new_preview.pack(side=tk.LEFT, padx=10, pady=10)
        
        # Select button
        ModernButton(
            self, text="Select Favicon Image", icon="📂",
            command=self._select_favicon, padx=20, pady=8
        ).pack(pady=15)
        
        # Info
        tk.Label(
            self, text="Note: This creates a wrapper page with your custom icon.\n"
                      "The wrapper redirects instantly to the original site.",
            bg=theme.bg_primary, fg=theme.text_muted, font=FONTS.small(),
            justify=tk.CENTER
        ).pack(pady=10)
        
        # Buttons
        btn_frame = tk.Frame(self, bg=theme.bg_primary)
        btn_frame.pack(pady=20)
        
        ModernButton(
            btn_frame, text="Apply", bg=theme.accent_primary, fg="white",
            command=self._apply, padx=25, pady=8, style="primary"
        ).pack(side=tk.LEFT, padx=5)
        
        ModernButton(
            btn_frame, text="Cancel", command=self.destroy,
            padx=25, pady=8
        ).pack(side=tk.LEFT, padx=5)

        self.bind("<Escape>", lambda e: self.destroy())
        self.center_window()
    
    def _select_favicon(self):
        """Select favicon image"""
        filepath = filedialog.askopenfilename(
            title="Select Favicon Image",
            filetypes=[
                ("Image Files", "*.png *.ico *.jpg *.jpeg *.gif"),
                ("PNG", "*.png"),
                ("ICO", "*.ico"),
                ("All Files", "*.*")
            ]
        )
        
        if filepath:
            self.selected_favicon = filepath
            # Try to show preview
            try:
                from PIL import Image, ImageTk
                img = Image.open(filepath)
                img = img.resize((32, 32), Image.Resampling.LANCZOS)
                self._preview_img = ImageTk.PhotoImage(img)
                self.new_preview.configure(image=self._preview_img, text="")
            except Exception:
                self.new_preview.configure(text="✓", fg=get_theme().accent_success)
    
    def _apply(self):
        """Apply custom favicon"""
        if not self.selected_favicon:
            messagebox.showwarning(
                "Favicon required",
                "Select an image before applying a custom favicon.",
                parent=self
            )
            return
        
        if FaviconWrapperGenerator.update_bookmark_with_wrapper(
            self.bookmark, self.selected_favicon
        ):
            self.bookmark_manager.update_bookmark(self.bookmark)
            messagebox.showinfo(
                "Custom favicon applied",
                "The bookmark now uses a wrapper page with your selected icon.",
                parent=self
            )
            if self.on_update:
                self.on_update()
            self.destroy()
        else:
            messagebox.showerror(
                "Favicon not applied",
                "Could not create the favicon wrapper page.",
                parent=self
            )

    def center_window(self):
        """Center the dialog on screen."""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')

