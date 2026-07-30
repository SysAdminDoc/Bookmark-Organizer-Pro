"""Category and favicon management dialogs for the desktop UI."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from bookmark_organizer_pro.i18n import _, format_message
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services import FaviconWrapperGenerator
from bookmark_organizer_pro.services.atomic_document_store import AtomicDocumentError
from bookmark_organizer_pro.services.category_delete_recovery import CategoryDeleteRecovery
from bookmark_organizer_pro.services.mcp_auth import (
    MCP_READ_SCOPE,
    MCP_WRITE_SCOPE,
    REST_EXTENSION_SCOPE,
    REST_READ_SCOPE,
    REST_WRITE_SCOPE,
)

from .foundation import FONTS, DesignTokens, pluralize
from .tk_interactions import bind_scoped_mousewheel, make_keyboard_activatable
from .widgets import ModernButton, Tooltip, apply_window_chrome, get_theme
from .window_geometry import apply_screen_aware_geometry


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
        self._category_delete_recovery = CategoryDeleteRecovery(
            category_manager, bookmark_manager
        )
        self._last_deleted_category = self._category_delete_recovery.pending()
        
        self.title(_("Manage Categories"))
        self.configure(bg=theme.bg_primary)
        apply_screen_aware_geometry(self, 620, 680)
        self.minsize(520, 520)
        self.transient(parent)
        self.grab_set()
        apply_window_chrome(self)
        
        # Header
        header = tk.Frame(self, bg=theme.bg_dark, height=DesignTokens.HEADER_HEIGHT)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(
            header, text=_("Manage Categories"), bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.title(bold=True)
        ).pack(anchor="w", padx=DesignTokens.PANEL_PAD, pady=(11, 1))
        
        tk.Label(
            header, text=_("Keep your collection structure clean and predictable."),
            bg=theme.bg_dark, fg=theme.text_secondary, font=FONTS.small()
        ).pack(anchor="w", padx=DesignTokens.PANEL_PAD, pady=(0, 9))
        
        # Add category section
        add_frame = tk.LabelFrame(
            self, text=_(" Add New Category "), bg=theme.bg_primary,
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
            add_inner, text=_("Add"), style="success",
            command=self._add_category
        )
        add_btn.pack(side=tk.RIGHT)
        
        # Category list
        list_frame = tk.LabelFrame(
            self, text=_(" Existing Categories "), bg=theme.bg_primary,
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

        _win = canvas.create_window((0, 0), window=self.cat_list_frame, anchor="nw")
        self.cat_list_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        # Keep the inner frame as wide as the canvas so rows fill the width.
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(_win, width=e.width))

        self._wheel_binding = bind_scoped_mousewheel(
            canvas, lambda units, _event: canvas.yview_scroll(units, "units")
        )
        
        self._populate_categories()
        
        footer = tk.Frame(self, bg=theme.bg_primary)
        footer.pack(fill=tk.X, padx=20, pady=(0, 18))

        self.status_var = tk.StringVar(value="")
        tk.Label(
            footer, textvariable=self.status_var, bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.small(), anchor="w",
            justify=tk.LEFT, wraplength=260
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        ModernButton(
            footer, text=_("Close"), command=self.destroy,
            padx=22, pady=9
        ).pack(side=tk.RIGHT)

        self.restore_button = ModernButton(
            footer, text=_("Restore last delete"), command=self._restore_last_deleted_category,
            padx=16, pady=9
        )
        self.restore_button.pack(side=tk.RIGHT, padx=(10, 0))
        self.restore_button.set_state("normal" if self._last_deleted_category else "disabled")

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

    def _set_status(self, message: str):
        if hasattr(self, "status_var"):
            self.status_var.set(message)

    def _set_restore_button_state(self, state: str):
        """Keep recovery logic usable in headless/service-driven call paths."""
        button = getattr(self, "restore_button", None)
        if button is not None:
            button.set_state(state)
    
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
                text=_("No categories yet. Create one above or import bookmarks to seed the list."),
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
                row, text=format_message('{value_0} {value_1}', value_0=cat.icon, value_1=cat_name), bg=theme.bg_secondary,
                fg=theme.text_primary, font=FONTS.body(bold=True), anchor="w"
            ).pack(side=tk.LEFT, padx=(12, 8), pady=9)
            
            # Count badge
            tk.Label(
                row, text=pluralize(count, "bookmark"),
                bg=theme.bg_secondary,
                fg=theme.text_secondary, font=FONTS.small()
            ).pack(side=tk.LEFT)
            
            # Buttons
            btn_frame = tk.Frame(row, bg=theme.bg_secondary)
            btn_frame.pack(side=tk.RIGHT, padx=5)
            
            # Edit button
            edit_btn = tk.Label(
                btn_frame, text=_("Rename"), bg=theme.bg_secondary,
                fg=theme.text_secondary, font=FONTS.small(), cursor="hand2",
                padx=4
            )
            edit_btn.pack(side=tk.LEFT, padx=5, pady=5)
            make_keyboard_activatable(edit_btn, lambda n=cat_name: self._edit_category(n))
            Tooltip(edit_btn, f"Rename {cat_name}")

            # Delete button
            del_btn = tk.Label(
                btn_frame, text=_("Delete"), bg=theme.bg_secondary,
                fg=theme.accent_error, font=FONTS.small(), cursor="hand2",
                padx=4
            )
            del_btn.pack(side=tk.LEFT, padx=5, pady=5)
            make_keyboard_activatable(del_btn, lambda n=cat_name: self._delete_category(n))
            Tooltip(del_btn, f"Delete {cat_name}")
    
    def _add_category(self):
        """Add new category"""
        name = self.new_cat_entry.get().strip()
        if self._category_placeholder_active or not name:
            self._set_status("Enter a category name before adding it.")
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
                    _("Category not added"),
                    _("That category already exists or the name is not valid."),
                    parent=self
                )
    
    def _edit_category(self, old_name: str):
        """Edit category name"""
        theme = get_theme()
        
        dialog = tk.Toplevel(self)
        dialog.title(_("Edit Category"))
        dialog.configure(bg=theme.bg_primary)
        dialog.geometry("350x150")
        dialog.transient(self)
        dialog.grab_set()
        apply_window_chrome(dialog)
        
        tk.Label(
            dialog, text=_("New name:"), bg=theme.bg_primary,
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
            dialog, text=_("Save"), command=save,
            padx=24, pady=8, style="primary"
        ).pack(pady=15)
        entry.bind("<Return>", lambda e: save())
        dialog.bind("<Escape>", lambda e: dialog.destroy())
    
    def _delete_category(self, name: str):
        """Delete category and move bookmarks to Uncategorized"""
        if name == "Uncategorized / Needs Review":
            self._set_status("The default review category cannot be deleted.")
            return

        recovery = getattr(self, "_category_delete_recovery", None)
        if recovery is not None:
            try:
                record = recovery.delete(name)
            except Exception as exc:
                self._set_status(str(exc))
                return
            self._last_deleted_category = record
            self._set_restore_button_state("normal")
            count = len(record["bookmark_ids"])
            self._populate_categories()
            if self.on_change:
                self.on_change()
            moved = f"; moved {pluralize(count, 'bookmark')}" if count else ""
            self._set_status(
                f"Deleted '{name}'{moved}. Restore Last Delete remains available after restart."
            )
            return

        bookmarks = list(self.bookmark_manager.get_bookmarks_by_category(name))
        count = len(bookmarks)
        self._last_deleted_category = {
            "name": name,
            "category": self.category_manager.categories.get(name),
            "bookmark_ids": [bm.id for bm in bookmarks],
        }
        self._set_restore_button_state("normal")

        for bm in bookmarks:
            bm.category = "Uncategorized / Needs Review"
            self.bookmark_manager.update_bookmark(bm)

        if name in self.category_manager.categories:
            del self.category_manager.categories[name]
            self.category_manager.save_categories()

        self._populate_categories()
        if self.on_change:
            self.on_change()
        moved = f"; moved {pluralize(count, 'bookmark')}" if count else ""
        self._set_status(f"Deleted '{name}'{moved}. Restore Last Delete is available.")

    def _restore_last_deleted_category(self):
        recovery = getattr(self, "_category_delete_recovery", None)
        if recovery is not None:
            try:
                name, restored = recovery.restore()
            except Exception as exc:
                self._set_status(str(exc))
                return False
            self._last_deleted_category = None
            self._set_restore_button_state("disabled")
            self._populate_categories()
            if self.on_change:
                self.on_change()
            self._set_status(f"Restored '{name}' and {pluralize(restored, 'bookmark')}.")
            return True

        record = self._last_deleted_category
        if not record:
            self._set_status("No deleted category is available to restore.")
            return False

        name = record["name"]
        category = record["category"]
        if category is not None:
            self.category_manager.categories[name] = category
            self.category_manager.save_categories()

        restored = 0
        for bookmark_id in record["bookmark_ids"]:
            bm = self.bookmark_manager.get_bookmark(bookmark_id)
            if not bm:
                continue
            bm.category = name
            self.bookmark_manager.update_bookmark(bm)
            restored += 1

        self._last_deleted_category = None
        self._set_restore_button_state("disabled")
        self._populate_categories()
        if self.on_change:
            self.on_change()
        self._set_status(f"Restored '{name}' and {pluralize(restored, 'bookmark')}.")
        return True

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
        
        self.title(_("Custom Favicon"))
        self.configure(bg=theme.bg_primary)
        self.geometry("450x350")
        self.transient(parent)
        self.grab_set()
        apply_window_chrome(self)
        
        # Header
        tk.Label(
            self, text=_("Set Custom Favicon"), bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.title(bold=False)
        ).pack(pady=(20, 5))
        
        tk.Label(
            self, text=format_message('For: {value_0}', value_0=bookmark.title[:50]), bg=theme.bg_primary,
            fg=theme.text_muted, font=FONTS.body()
        ).pack(pady=(0, 15))
        
        # Current favicon preview
        preview_frame = tk.Frame(self, bg=theme.bg_secondary)
        preview_frame.pack(pady=15, padx=20)
        
        tk.Label(
            preview_frame, text=_("Current:"), bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.body()
        ).pack(side=tk.LEFT, padx=10, pady=10)
        
        self.preview_label = tk.Label(
            preview_frame, text=_("Site"), bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.body(bold=True)
        )
        self.preview_label.pack(side=tk.LEFT, padx=10, pady=10)

        tk.Label(
            preview_frame, text=_("→"), bg=theme.bg_secondary,
            fg=theme.text_muted, font=FONTS.subtitle(bold=False)
        ).pack(side=tk.LEFT, padx=10)

        tk.Label(
            preview_frame, text=_("New:"), bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.body()
        ).pack(side=tk.LEFT, padx=10, pady=10)

        self.new_preview = tk.Label(
            preview_frame, text=_("?"), bg=theme.bg_secondary,
            font=FONTS.hero(bold=False), fg=theme.text_muted
        )
        self.new_preview.pack(side=tk.LEFT, padx=10, pady=10)
        
        # Select button
        ModernButton(
            self, text=_("Select Favicon Image"),
            command=self._select_favicon, padx=20, pady=8
        ).pack(pady=15)
        
        # Info
        tk.Label(
            self, text=_("Note: This creates a wrapper page with your custom icon.\n"
                      "The wrapper redirects instantly to the original site."),
            bg=theme.bg_primary, fg=theme.text_muted, font=FONTS.small(),
            justify=tk.CENTER
        ).pack(pady=10)

        self.status_var = tk.StringVar(value="")
        tk.Label(
            self, textvariable=self.status_var, bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.small(), justify=tk.CENTER,
            wraplength=360
        ).pack(pady=(0, 6))
        
        # Buttons
        btn_frame = tk.Frame(self, bg=theme.bg_primary)
        btn_frame.pack(pady=20)
        
        ModernButton(
            btn_frame, text=_("Apply"), command=self._apply,
            padx=25, pady=8, style="primary"
        ).pack(side=tk.LEFT, padx=5)
        
        ModernButton(
            btn_frame, text=_("Cancel"), command=self.destroy,
            padx=25, pady=8
        ).pack(side=tk.LEFT, padx=5)

        self.bind("<Escape>", lambda e: self.destroy())
        self.center_window()
    
    def _select_favicon(self):
        """Select favicon image"""
        filepath = filedialog.askopenfilename(
            title=_("Select Favicon Image"),
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
                self.new_preview.configure(text=_("✓"), fg=get_theme().accent_success)
            self._set_status("Favicon image selected.")

    def _set_status(self, message: str):
        if hasattr(self, "status_var"):
            self.status_var.set(message)
    
    def _apply(self):
        """Apply custom favicon"""
        if not self.selected_favicon:
            self._set_status("Select an image before applying a custom favicon.")
            return
        
        if FaviconWrapperGenerator.update_bookmark_with_wrapper(
            self.bookmark, self.selected_favicon
        ):
            self.bookmark_manager.update_bookmark(self.bookmark)
            self._set_status("Custom favicon applied.")
            if self.on_update:
                self.on_update()
            self.after(750, self.destroy)
        else:
            messagebox.showerror(
                _("Favicon not applied"),
                _("Could not create the favicon wrapper page."),
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


class CredentialSecurityDialog(tk.Toplevel):
    """Inspectable named-credential inventory and bounded usage audit."""

    PURPOSES = {
        _("MCP — read only"): (
            "mcp",
            [MCP_READ_SCOPE],
        ),
        _("MCP — read and write"): (
            "mcp",
            [MCP_READ_SCOPE, MCP_WRITE_SCOPE],
        ),
        _("REST API — read only"): (
            "rest",
            [REST_READ_SCOPE],
        ),
        _("REST API — read and write"): (
            "rest",
            [REST_READ_SCOPE, REST_WRITE_SCOPE],
        ),
        _("Browser extension"): (
            "rest",
            [REST_READ_SCOPE, REST_WRITE_SCOPE, REST_EXTENSION_SCOPE],
        ),
    }
    LIFETIMES = {
        _("Never expires"): None,
        _("1 day"): 86_400,
        _("30 days"): 2_592_000,
        _("90 days"): 7_776_000,
        _("1 year"): 31_536_000,
    }

    def __init__(self, parent, credential_manager):
        super().__init__(parent)
        self.credential_manager = credential_manager
        self._rows: dict[str, dict] = {}
        self._theme = get_theme()
        table_style = ttk.Style(self)
        native_heading = table_style.theme_use() in {
            "vista", "xpnative", "winnative", "aqua",
        }
        table_style.configure(
            "Credential.Treeview",
            background=self._theme.bg_secondary,
            fieldbackground=self._theme.bg_secondary,
            foreground=self._theme.text_primary,
            bordercolor=self._theme.border_muted,
            rowheight=30,
            font=FONTS.small(),
        )
        table_style.map(
            "Credential.Treeview",
            background=[("selected", self._theme.selection)],
            foreground=[("selected", self._theme.text_primary)],
        )
        table_style.configure(
            "Credential.Treeview.Heading",
            background=self._theme.bg_tertiary,
            foreground=(
                "#111827" if native_heading else self._theme.text_primary
            ),
            bordercolor=self._theme.border_muted,
            font=FONTS.small(bold=True),
        )

        self.title(_("Access Credentials"))
        self.configure(bg=self._theme.bg_primary)
        apply_screen_aware_geometry(self, 1140, 720)
        self.minsize(860, 600)
        self.transient(parent)
        self.grab_set()
        apply_window_chrome(self)

        header = tk.Frame(
            self,
            bg=self._theme.bg_dark,
            padx=DesignTokens.PANEL_PAD,
            pady=14,
        )
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text=_("Access Credentials"),
            bg=self._theme.bg_dark,
            fg=self._theme.text_primary,
            font=FONTS.title(bold=True),
        ).pack(anchor="w")
        tk.Label(
            header,
            text=_(
                "Create one-purpose bearer credentials, inspect use, and revoke "
                "access without exposing saved secrets."
            ),
            bg=self._theme.bg_dark,
            fg=self._theme.text_secondary,
            font=FONTS.small(),
        ).pack(anchor="w", pady=(3, 0))

        body = tk.Frame(
            self,
            bg=self._theme.bg_primary,
            padx=DesignTokens.PANEL_PAD,
            pady=14,
        )
        body.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            body,
            text=_("Credential inventory"),
            bg=self._theme.bg_primary,
            fg=self._theme.text_primary,
            font=FONTS.body(bold=True),
        ).pack(anchor="w", pady=(0, 6))

        inventory_frame = tk.Frame(body, bg=self._theme.bg_primary)
        inventory_frame.pack(fill=tk.BOTH, expand=True)
        columns = (
            "name", "audience", "scope", "status", "created",
            "last_used", "expires", "fingerprint",
        )
        self.inventory = ttk.Treeview(
            inventory_frame,
            columns=columns,
            show="headings",
            height=4,
            selectmode="browse",
            style="Credential.Treeview",
        )
        headings = {
            "name": _("Name"),
            "audience": _("Audience"),
            "scope": _("Scope"),
            "status": _("Status"),
            "created": _("Created"),
            "last_used": _("Last used"),
            "expires": _("Expires"),
            "fingerprint": _("Fingerprint"),
        }
        widths = {
            "name": 180,
            "audience": 85,
            "scope": 110,
            "status": 70,
            "created": 155,
            "last_used": 155,
            "expires": 155,
            "fingerprint": 180,
        }
        for column in columns:
            self.inventory.heading(column, text=headings[column])
            self.inventory.column(
                column,
                width=widths[column],
                minwidth=60,
                anchor=tk.W,
            )
        inventory_scroll = ttk.Scrollbar(
            inventory_frame,
            orient=tk.VERTICAL,
            command=self.inventory.yview,
        )
        self.inventory.configure(yscrollcommand=inventory_scroll.set)
        self.inventory.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        inventory_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.inventory.bind("<<TreeviewSelect>>", self._selection_changed)

        actions = tk.Frame(body, bg=self._theme.bg_primary)
        actions.pack(fill=tk.X, pady=(9, 14))
        self.new_button = ModernButton(
            actions,
            text=_("New credential"),
            command=self._create_credential,
            style="primary",
            padx=14,
            pady=7,
        )
        self.new_button.pack(side=tk.LEFT)
        self.rotate_button = ModernButton(
            actions,
            text=_("Rotate selected"),
            command=self._rotate_selected,
            padx=14,
            pady=7,
        )
        self.rotate_button.pack(side=tk.LEFT, padx=(8, 0))
        self.revoke_button = ModernButton(
            actions,
            text=_("Revoke selected"),
            command=self._revoke_selected,
            style="danger",
            padx=14,
            pady=7,
        )
        self.revoke_button.pack(side=tk.LEFT, padx=(8, 0))

        tk.Label(
            body,
            text=_("Recent credential activity"),
            bg=self._theme.bg_primary,
            fg=self._theme.text_primary,
            font=FONTS.body(bold=True),
        ).pack(anchor="w", pady=(0, 6))

        audit_frame = tk.Frame(body, bg=self._theme.bg_primary)
        audit_frame.pack(fill=tk.BOTH, expand=True)
        audit_columns = (
            "timestamp", "name", "audience", "operation", "result", "reason",
        )
        self.audit = ttk.Treeview(
            audit_frame,
            columns=audit_columns,
            show="headings",
            height=3,
            style="Credential.Treeview",
        )
        audit_headings = {
            "timestamp": _("Time"),
            "name": _("Credential"),
            "audience": _("Audience"),
            "operation": _("Operation"),
            "result": _("Result"),
            "reason": _("Reason"),
        }
        audit_widths = {
            "timestamp": 145,
            "name": 150,
            "audience": 70,
            "operation": 190,
            "result": 75,
            "reason": 150,
        }
        for column in audit_columns:
            self.audit.heading(column, text=audit_headings[column])
            self.audit.column(
                column,
                width=audit_widths[column],
                minwidth=60,
                anchor=tk.W,
            )
        audit_scroll = ttk.Scrollbar(
            audit_frame,
            orient=tk.VERTICAL,
            command=self.audit.yview,
        )
        self.audit.configure(yscrollcommand=audit_scroll.set)
        self.audit.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        audit_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        footer = tk.Frame(
            self,
            bg=self._theme.bg_primary,
            padx=DesignTokens.PANEL_PAD,
            pady=0,
        )
        # Reserve the footer before the expanding body. App-level ttk row
        # metrics can be much taller than platform defaults at high DPI.
        body.pack_forget()
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 14))
        body.pack(fill=tk.BOTH, expand=True)
        self.status_var = tk.StringVar(value="")
        tk.Label(
            footer,
            textvariable=self.status_var,
            bg=self._theme.bg_primary,
            fg=self._theme.text_secondary,
            font=FONTS.small(),
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ModernButton(
            footer,
            text=_("Close"),
            command=self.destroy,
            padx=18,
            pady=7,
        ).pack(side=tk.RIGHT)

        self.bind("<Escape>", lambda _event: self.destroy())
        self._refresh()

    @staticmethod
    def _display_time(value: str, fallback: str = "—") -> str:
        text = str(value or "")
        if not text:
            return fallback
        return text.replace("T", " ")[:16]

    def _refresh(self):
        selected = self.inventory.selection()
        selected_id = selected[0] if selected else ""
        for item in self.inventory.get_children():
            self.inventory.delete(item)
        listed_rows = self.credential_manager.list_credentials()
        self._rows = {
            row["id"]: row for row in listed_rows if row.get("id")
        }
        for index, row in enumerate(listed_rows):
            identifier = row.get("id") or f"status-{index}"
            fingerprint = row.get("fingerprint", "")
            self.inventory.insert(
                "",
                tk.END,
                iid=identifier,
                values=(
                    (
                        row["name"]
                        if row.get("id")
                        else _("Credential store recovery required")
                    ),
                    row["audience"].upper(),
                    row["scope"],
                    row["status"],
                    self._display_time(row["created_at"]),
                    self._display_time(row["last_used_at"], _("Never")),
                    self._display_time(row["expires_at"], _("Never")),
                    (
                        f"sha256:{fingerprint}"
                        if fingerprint and fingerprint != "unavailable"
                        else _("Unavailable")
                    ),
                ),
            )
        if selected_id in self._rows:
            self.inventory.selection_set(selected_id)

        for item in self.audit.get_children():
            self.audit.delete(item)
        for index, event in enumerate(self.credential_manager.list_audit(limit=100)):
            self.audit.insert(
                "",
                tk.END,
                iid=f"audit-{index}",
                values=(
                    self._display_time(event["timestamp"]),
                    event["name"] or _("Unknown credential"),
                    event["audience"].upper(),
                    event["operation"],
                    event["result"],
                    event["reason"].replace("_", " "),
                ),
            )
        health = self.credential_manager.diagnostics()
        available = bool(health.get("available"))
        self.new_button.set_state("normal" if available else "disabled")
        self._selection_changed()
        if available:
            self.status_var.set(
                format_message(
                    "{value_0} credentials · {value_1} recent events",
                    value_0=len(self._rows),
                    value_1=len(self.audit.get_children()),
                )
            )
        else:
            self.status_var.set(
                _(
                    "Credential changes are locked until the local credential "
                    "store is recovered."
                )
            )

    def _selected(self) -> tuple[str, dict | None]:
        selection = self.inventory.selection()
        if not selection:
            return "", None
        identifier = selection[0]
        return identifier, self._rows.get(identifier)

    def _selection_changed(self, _event=None):
        _identifier, row = self._selected()
        can_rotate = bool(row and row.get("status") != "revoked")
        can_revoke = bool(row and row.get("status") != "revoked")
        self.rotate_button.set_state("normal" if can_rotate else "disabled")
        self.revoke_button.set_state("normal" if can_revoke else "disabled")

    def _create_credential(self):
        form = tk.Toplevel(self)
        form.title(_("New Access Credential"))
        form.configure(bg=self._theme.bg_primary)
        form.geometry("500x330")
        form.resizable(False, False)
        form.transient(self)
        form.grab_set()
        apply_window_chrome(form)

        content = tk.Frame(
            form,
            bg=self._theme.bg_primary,
            padx=24,
            pady=20,
        )
        content.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            content,
            text=_("Name and purpose"),
            bg=self._theme.bg_primary,
            fg=self._theme.text_primary,
            font=FONTS.subtitle(bold=True),
        ).pack(anchor="w")
        tk.Label(
            content,
            text=_(
                "Choose the narrowest purpose that can perform the required work."
            ),
            bg=self._theme.bg_primary,
            fg=self._theme.text_secondary,
            font=FONTS.small(),
        ).pack(anchor="w", pady=(3, 12))

        name_var = tk.StringVar()
        name_entry = tk.Entry(
            content,
            textvariable=name_var,
            bg=self._theme.bg_secondary,
            fg=self._theme.text_primary,
            insertbackground=self._theme.text_primary,
            relief=tk.FLAT,
            font=FONTS.body(),
        )
        name_entry.pack(fill=tk.X, ipady=6)

        purpose_var = tk.StringVar(value=next(iter(self.PURPOSES)))
        ttk.Combobox(
            content,
            textvariable=purpose_var,
            values=list(self.PURPOSES),
            state="readonly",
        ).pack(fill=tk.X, pady=(12, 0), ipady=3)

        lifetime_var = tk.StringVar(value=next(iter(self.LIFETIMES)))
        ttk.Combobox(
            content,
            textvariable=lifetime_var,
            values=list(self.LIFETIMES),
            state="readonly",
        ).pack(fill=tk.X, pady=(12, 0), ipady=3)

        status_var = tk.StringVar(value="")
        tk.Label(
            content,
            textvariable=status_var,
            bg=self._theme.bg_primary,
            fg=self._theme.accent_error,
            font=FONTS.small(),
        ).pack(anchor="w", pady=(8, 0))

        actions = tk.Frame(content, bg=self._theme.bg_primary)
        actions.pack(fill=tk.X, side=tk.BOTTOM)

        def create():
            try:
                audience, scopes = self.PURPOSES[purpose_var.get()]
                created = self.credential_manager.create_credential(
                    name_var.get(),
                    audience=audience,
                    scopes=scopes,
                    expires_in_seconds=self.LIFETIMES[lifetime_var.get()],
                )
            except (
                AtomicDocumentError,
                KeyError,
                TypeError,
                ValueError,
                OSError,
            ) as exc:
                status_var.set(str(exc))
                return
            form.destroy()
            self._show_one_time_secret(created)
            self._refresh()

        ModernButton(
            actions,
            text=_("Cancel"),
            command=form.destroy,
            padx=15,
            pady=7,
        ).pack(side=tk.RIGHT)
        ModernButton(
            actions,
            text=_("Create credential"),
            command=create,
            style="success",
            padx=15,
            pady=7,
        ).pack(side=tk.RIGHT, padx=(0, 8))
        name_entry.bind("<Return>", lambda _event: create())
        form.bind("<Escape>", lambda _event: form.destroy())
        name_entry.focus_set()

    def _show_one_time_secret(self, created):
        dialog = tk.Toplevel(self)
        dialog.title(_("Copy Credential"))
        dialog.configure(bg=self._theme.bg_primary)
        dialog.geometry("620x280")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        apply_window_chrome(dialog)

        content = tk.Frame(
            dialog,
            bg=self._theme.bg_primary,
            padx=24,
            pady=20,
        )
        content.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            content,
            text=_("Copy this credential now"),
            bg=self._theme.bg_primary,
            fg=self._theme.text_primary,
            font=FONTS.subtitle(bold=True),
        ).pack(anchor="w")
        tk.Label(
            content,
            text=_(
                "The secret is shown once. Bookmark Organizer Pro stores only "
                "a salted verifier and cannot reveal it later."
            ),
            bg=self._theme.bg_primary,
            fg=self._theme.text_secondary,
            font=FONTS.small(),
            wraplength=560,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(4, 12))

        token_var = tk.StringVar(value=created.token)
        token_entry = tk.Entry(
            content,
            textvariable=token_var,
            state="readonly",
            readonlybackground=self._theme.bg_secondary,
            fg=self._theme.text_primary,
            font=FONTS.mono(),
            relief=tk.FLAT,
        )
        token_entry.pack(fill=tk.X, ipady=7)
        token_entry.selection_range(0, tk.END)

        status_var = tk.StringVar(
            value=format_message(
                "Fingerprint: sha256:{value_0}",
                value_0=created.fingerprint,
            )
        )
        tk.Label(
            content,
            textvariable=status_var,
            bg=self._theme.bg_primary,
            fg=self._theme.text_secondary,
            font=FONTS.small(),
        ).pack(anchor="w", pady=(7, 0))

        actions = tk.Frame(content, bg=self._theme.bg_primary)
        actions.pack(fill=tk.X, side=tk.BOTTOM)

        def copy_secret():
            dialog.clipboard_clear()
            dialog.clipboard_append(created.token)
            status_var.set(_("Copied. Store it in your client or password manager now."))

        ModernButton(
            actions,
            text=_("Copy"),
            command=copy_secret,
            style="primary",
            padx=18,
            pady=7,
        ).pack(side=tk.LEFT)
        ModernButton(
            actions,
            text=_("Done"),
            command=dialog.destroy,
            padx=18,
            pady=7,
        ).pack(side=tk.RIGHT)
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        token_entry.focus_set()

    def _rotate_selected(self):
        identifier, row = self._selected()
        if not identifier or row is None:
            return
        if not messagebox.askyesno(
            _("Rotate credential?"),
            _(
                "The current secret will stop working immediately. "
                "Continue and show a replacement secret?"
            ),
            parent=self,
        ):
            return
        try:
            created = self.credential_manager.rotate_credential(identifier)
        except (AtomicDocumentError, KeyError, ValueError, OSError) as exc:
            messagebox.showerror(_("Credential not rotated"), str(exc), parent=self)
            return
        self._show_one_time_secret(created)
        self._refresh()

    def _revoke_selected(self):
        identifier, row = self._selected()
        if not identifier or row is None:
            return
        if not messagebox.askyesno(
            _("Revoke credential?"),
            format_message(
                "Revoke '{value_0}' immediately? This cannot be undone.",
                value_0=row["name"],
            ),
            parent=self,
        ):
            return
        try:
            changed = self.credential_manager.revoke_credential(identifier)
        except (AtomicDocumentError, OSError) as exc:
            messagebox.showerror(_("Credential not revoked"), str(exc), parent=self)
            return
        if not changed:
            messagebox.showinfo(
                _("Credential unchanged"),
                _("The selected credential was already revoked or no longer exists."),
                parent=self,
            )
        self._refresh()
