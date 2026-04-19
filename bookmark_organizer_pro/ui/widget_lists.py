"""List and category navigation widgets."""

from __future__ import annotations

from datetime import datetime
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Any, Callable, Dict, List

from bookmark_organizer_pro.core import CategoryManager, get_category_icon
from bookmark_organizer_pro.models import Bookmark, Category

from .foundation import FONTS
from .widget_controls import ThemedWidget
from .widget_runtime import get_theme

# =============================================================================
# Theme Selector Dialog
# =============================================================================
class BookmarkListView(tk.Frame, ThemedWidget):
    """
        Represents a single bookmark with all metadata.
        
        Attributes:
            id: Unique integer identifier
            url: Bookmark URL
            title: Display title
            category: Category name
            tags: List of tag names
            ai_tags: List of AI-suggested tags
            description: Optional description
            favicon_url: URL to favicon image
            created_at: ISO timestamp of creation
            updated_at: ISO timestamp of last update
            visited_at: ISO timestamp of last visit
            visit_count: Number of times visited
            is_valid: Whether URL validation passed
            is_pinned: Whether bookmark is pinned
            ai_category: AI-suggested category
            ai_summary: AI-generated summary
            notes: User notes
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
            matches_search(query): Check if bookmark matches search
        """
    
    def __init__(self, parent, on_select: Callable = None,
                 on_open: Callable = None, on_context_menu: Callable = None,
                 favicon_manager=None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_primary)
        
        self.on_select = on_select
        self.on_open = on_open
        self.on_context_menu = on_context_menu
        self.favicon_manager = favicon_manager
        self.theme = theme
        
        self._bookmarks: Dict[str, Bookmark] = {}  # iid -> bookmark
        self._favicon_images: Dict[str, Any] = {}
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the list view UI"""
        # Configure style
        style = ttk.Style()
        style.configure("Bookmark.Treeview",
            background=self.theme.bg_primary,
            foreground=self.theme.text_primary,
            fieldbackground=self.theme.bg_primary,
            rowheight=32
        )
        style.configure("Bookmark.Treeview.Heading",
            background=self.theme.bg_secondary,
            foreground=self.theme.text_primary,
            font=FONTS.small(bold=True)
        )
        style.map("Bookmark.Treeview",
            background=[("selected", self.theme.selection)],
            foreground=[("selected", self.theme.text_primary)]
        )
        
        # Treeview with columns
        columns = ("title", "domain", "category", "tags", "added")
        self.tree = ttk.Treeview(
            self, columns=columns, show="headings",
            style="Bookmark.Treeview", selectmode="extended"
        )
        
        # Column configuration
        self.tree.heading("title", text="Title", anchor="w")
        self.tree.heading("domain", text="Domain", anchor="w")
        self.tree.heading("category", text="Category", anchor="w")
        self.tree.heading("tags", text="Tags", anchor="w")
        self.tree.heading("added", text="Added", anchor="w")
        
        self.tree.column("title", width=300, minwidth=150)
        self.tree.column("domain", width=150, minwidth=100)
        self.tree.column("category", width=150, minwidth=100)
        self.tree.column("tags", width=150, minwidth=80)
        self.tree.column("added", width=100, minwidth=80)
        
        # Scrollbars
        vsb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Layout
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # Bindings
        self.tree.bind("<<TreeviewSelect>>", self._on_selection)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Button-3>", self._on_right_click)
        self.tree.bind("<Return>", self._on_double_click)
        
        # Drag and drop
        self.tree.bind("<ButtonPress-1>", self._on_drag_start)
        self.tree.bind("<B1-Motion>", self._on_drag_motion)
        self.tree.bind("<ButtonRelease-1>", self._on_drag_end)
        
        self._drag_data = {"item": None, "start_y": 0}
    
    def load_bookmarks(self, bookmarks: List[Bookmark]):
        """Load bookmarks into the list"""
        # Clear existing
        self.tree.delete(*self.tree.get_children())
        self._bookmarks.clear()
        
        for bm in bookmarks:
            # Format data
            tags_str = ", ".join(bm.tags[:3])
            if len(bm.tags) > 3:
                tags_str += f" +{len(bm.tags)-3}"
            
            try:
                added = datetime.fromisoformat(bm.created_at.replace('Z', '+00:00'))
                added_str = added.strftime("%Y-%m-%d")
            except Exception:
                added_str = ""
            
            # Insert item
            iid = self.tree.insert("", "end", values=(
                bm.title[:60],
                bm.domain,
                bm.category[:30],
                tags_str,
                added_str
            ))
            
            self._bookmarks[iid] = bm
    
    def _on_selection(self, e):
        """Handle selection change"""
        if self.on_select:
            selected = self.get_selected_bookmarks()
            self.on_select(selected)
    
    def _on_double_click(self, e):
        """Handle double click"""
        if self.on_open:
            selected = self.get_selected_bookmarks()
            if selected:
                self.on_open(selected[0])
    
    def _on_right_click(self, e):
        """Handle right click"""
        # Select item under cursor
        item = self.tree.identify_row(e.y)
        if item:
            if item not in self.tree.selection():
                self.tree.selection_set(item)
        
        if self.on_context_menu:
            selected = self.get_selected_bookmarks()
            if selected:
                self.on_context_menu(e, selected)
    
    def _on_drag_start(self, e):
        """Start drag operation"""
        item = self.tree.identify_row(e.y)
        if item:
            self._drag_data["item"] = item
            self._drag_data["start_y"] = e.y
    
    def _on_drag_motion(self, e):
        """Handle drag motion"""
        pass  # Could show visual feedback
    
    def _on_drag_end(self, e):
        """End drag operation"""
        self._drag_data["item"] = None
    
    def get_selected_bookmarks(self) -> List[Bookmark]:
        """Get selected bookmarks"""
        selected = []
        for iid in self.tree.selection():
            if iid in self._bookmarks:
                selected.append(self._bookmarks[iid])
        return selected
    
    def get_selected_ids(self) -> List[int]:
        """Get selected bookmark IDs"""
        return [bm.id for bm in self.get_selected_bookmarks()]
    
    def select_all(self):
        """Select all items"""
        self.tree.selection_set(self.tree.get_children())
    
    def clear_selection(self):
        """Clear selection"""
        self.tree.selection_remove(self.tree.selection())
    
    def refresh_item(self, bookmark: Bookmark):
        """Refresh a single item"""
        for iid, bm in self._bookmarks.items():
            if bm.id == bookmark.id:
                tags_str = ", ".join(bookmark.tags[:3])
                if len(bookmark.tags) > 3:
                    tags_str += f" +{len(bookmark.tags)-3}"
                
                try:
                    added = datetime.fromisoformat(bookmark.created_at.replace('Z', '+00:00'))
                    added_str = added.strftime("%Y-%m-%d")
                except Exception:
                    added_str = ""
                
                self.tree.item(iid, values=(
                    bookmark.title[:60],
                    bookmark.domain,
                    bookmark.category[:30],
                    tags_str,
                    added_str
                ))
                self._bookmarks[iid] = bookmark
                break


# =============================================================================
# Category Sidebar
# =============================================================================
class CategorySidebar(tk.Frame, ThemedWidget):
    """
        Represents a bookmark category.
        
        Attributes:
            name: Category name (unique identifier)
            parent: Parent category name (for nesting)
            icon: Emoji icon for display
            color: Optional color override
            sort_order: Order within parent
            created_at: ISO timestamp of creation
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
        """
    
    def __init__(self, parent, category_manager: CategoryManager,
                 on_select: Callable = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_secondary, width=250)
        
        self.category_manager = category_manager
        self.on_select = on_select
        self.theme = theme
        self.selected_category = None
        
        self.pack_propagate(False)
        
        self._build_ui()
    
    def _build_ui(self):
        """Build sidebar UI"""
        # Header
        header = tk.Frame(self, bg=self.theme.bg_secondary)
        header.pack(fill=tk.X, padx=15, pady=(15, 10))
        
        tk.Label(
            header, text="Categories", bg=self.theme.bg_secondary,
            fg=self.theme.text_primary, font=FONTS.header()
        ).pack(side=tk.LEFT)
        
        # Add button
        add_btn = tk.Label(
            header, text="+", bg=self.theme.bg_secondary,
            fg=self.theme.accent_primary, font=("Segoe UI", 14),
            cursor="hand2"
        )
        add_btn.pack(side=tk.RIGHT)
        add_btn.bind("<Button-1>", lambda e: self._add_category())
        
        # Special items
        specials_frame = tk.Frame(self, bg=self.theme.bg_secondary)
        specials_frame.pack(fill=tk.X, pady=(0, 10))
        
        self._create_special_item(specials_frame, "📚", "All Bookmarks", "_all")
        self._create_special_item(specials_frame, "📌", "Pinned", "_pinned")
        self._create_special_item(specials_frame, "🕐", "Recent", "_recent")
        self._create_special_item(specials_frame, "🏷️", "Tags", "_tags")
        
        # Separator
        tk.Frame(self, bg=self.theme.border, height=1).pack(fill=tk.X, padx=15, pady=5)
        
        # Scrollable categories
        self.canvas = tk.Canvas(self, bg=self.theme.bg_secondary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.categories_frame = tk.Frame(self.canvas, bg=self.theme.bg_secondary)
        
        self.categories_frame.bind("<Configure>", 
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        
        self.canvas.create_window((0, 0), window=self.categories_frame, anchor="nw", width=235)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.refresh_categories()
    
    def _create_special_item(self, parent, icon: str, text: str, key: str):
        """Create a special category item"""
        frame = tk.Frame(parent, bg=self.theme.bg_secondary)
        frame.pack(fill=tk.X)
        
        inner = tk.Frame(frame, bg=self.theme.bg_secondary)
        inner.pack(fill=tk.X, padx=15, pady=4)
        
        tk.Label(
            inner, text=icon, bg=self.theme.bg_secondary,
            font=FONTS.body()
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        tk.Label(
            inner, text=text, bg=self.theme.bg_secondary,
            fg=self.theme.text_primary, font=FONTS.body(),
            cursor="hand2"
        ).pack(side=tk.LEFT)
        
        for widget in [frame, inner] + list(inner.winfo_children()):
            widget.bind("<Button-1>", lambda e, k=key: self._select_category(k))
            widget.bind("<Enter>", lambda e, f=frame: f.configure(bg=self.theme.bg_hover))
            widget.bind("<Leave>", lambda e, f=frame: f.configure(bg=self.theme.bg_secondary))
    
    def refresh_categories(self, counts: Dict[str, int] = None):
        """Refresh the category list"""
        for widget in self.categories_frame.winfo_children():
            widget.destroy()
        
        counts = counts or {}
        
        for cat, depth in self.category_manager.get_tree():
            self._create_category_item(cat, counts.get(cat.name, 0), depth)
    
    def _create_category_item(self, category: Category, count: int, depth: int):
        """Create a category list item"""
        is_selected = category.name == self.selected_category
        bg = self.theme.selection if is_selected else self.theme.bg_secondary
        
        frame = tk.Frame(self.categories_frame, bg=bg)
        frame.pack(fill=tk.X)
        
        inner = tk.Frame(frame, bg=bg)
        inner.pack(fill=tk.X, padx=(15 + depth * 15, 15), pady=3)
        
        # Icon
        icon = category.icon or get_category_icon(category.name)
        tk.Label(
            inner, text=icon, bg=bg,
            font=FONTS.body()
        ).pack(side=tk.LEFT, padx=(0, 8))
        
        # Name
        name = category.name
        if len(name) > 20:
            name = name[:18] + "..."
        tk.Label(
            inner, text=name, bg=bg,
            fg=self.theme.text_primary, font=FONTS.body(),
            cursor="hand2"
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Count
        if count > 0:
            tk.Label(
                inner, text=str(count), bg=bg,
                fg=self.theme.text_muted, font=FONTS.small()
            ).pack(side=tk.RIGHT)
        
        # Bindings
        for widget in [frame, inner] + list(inner.winfo_children()):
            widget.bind("<Button-1>", lambda e, c=category.name: self._select_category(c))
            if not is_selected:
                widget.bind("<Enter>", lambda e, f=frame, i=inner: self._hover_enter(f, i))
                widget.bind("<Leave>", lambda e, f=frame, i=inner: self._hover_leave(f, i))
    
    def _hover_enter(self, frame, inner):
        frame.configure(bg=self.theme.bg_hover)
        inner.configure(bg=self.theme.bg_hover)
        for child in inner.winfo_children():
            try:
                child.configure(bg=self.theme.bg_hover)
            except tk.TclError:
                pass
    
    def _hover_leave(self, frame, inner):
        frame.configure(bg=self.theme.bg_secondary)
        inner.configure(bg=self.theme.bg_secondary)
        for child in inner.winfo_children():
            try:
                child.configure(bg=self.theme.bg_secondary)
            except tk.TclError:
                pass
    
    def _select_category(self, category: str):
        """Select a category"""
        self.selected_category = category
        self.refresh_categories()
        if self.on_select:
            self.on_select(category)
    
    def _add_category(self):
        """Add a new category"""
        name = simpledialog.askstring("New Category", "Enter category name:")
        if name and name.strip():
            if self.category_manager.add_category(name.strip()):
                self.refresh_categories()
            else:
                messagebox.showerror(
                    "Category Not Added",
                    "That category already exists. Choose a unique category name.",
                    parent=self
                )
