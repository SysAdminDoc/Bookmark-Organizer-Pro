"""Drag-and-drop helpers for category ordering."""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Dict, Optional

from .widgets import get_theme


# =============================================================================
# Category Drag & Drop Manager
# =============================================================================
class CategoryDragDropManager:
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
    
    def __init__(self, container: tk.Frame, category_manager: CategoryManager,
                 on_reorder: Callable = None):
        self.container = container
        self.category_manager = category_manager
        self.on_reorder = on_reorder
        
        self._dragging = False
        self._drag_item: Optional[tk.Widget] = None
        self._drag_category: Optional[str] = None
        self._drag_start_y = 0
        self._placeholder: Optional[tk.Frame] = None
        self._item_widgets: Dict[str, tk.Widget] = {}
    
    def make_draggable(self, widget: tk.Widget, category_name: str):
        """Make a category widget draggable"""
        self._item_widgets[category_name] = widget
        
        widget.bind('<ButtonPress-1>', lambda e: self._start_drag(e, category_name))
        widget.bind('<B1-Motion>', self._on_drag)
        widget.bind('<ButtonRelease-1>', self._end_drag)
    
    def _start_drag(self, event, category_name: str):
        """Start dragging a category"""
        self._dragging = True
        self._drag_category = category_name
        self._drag_item = event.widget
        self._drag_start_y = event.y_root
        
        # Create visual feedback
        theme = get_theme()
        self._drag_item.configure(bg=getattr(theme, "drag_active", theme.drag_target_bg))
    
    def _on_drag(self, event):
        """Handle drag motion"""
        if not self._dragging or not self._drag_item:
            return
        
        # Find position among siblings
        y = event.y_root
        target_category = None
        
        for cat_name, widget in self._item_widgets.items():
            if cat_name == self._drag_category:
                continue
            
            widget_y = widget.winfo_rooty()
            widget_height = widget.winfo_height()
            
            if widget_y <= y <= widget_y + widget_height:
                target_category = cat_name
                break
        
        # Update visual indicator
        if target_category:
            self._show_drop_indicator(target_category)
    
    def _show_drop_indicator(self, target_category: str):
        """Show drop position indicator"""
        theme = get_theme()
        
        # Remove old placeholder
        if self._placeholder:
            self._placeholder.destroy()
        
        # Create new placeholder
        target_widget = self._item_widgets.get(target_category)
        if target_widget:
            self._placeholder = tk.Frame(
                self.container, bg=theme.accent_primary, height=3
            )
            # Pack before target
            self._placeholder.pack(before=target_widget, fill=tk.X, pady=2)
    
    def _end_drag(self, event):
        """End drag operation"""
        if not self._dragging:
            return
        
        theme = get_theme()
        
        # Reset visual
        if self._drag_item:
            self._drag_item.configure(bg=theme.bg_secondary)
        
        # Remove placeholder
        if self._placeholder:
            self._placeholder.destroy()
            self._placeholder = None
        
        # Find drop target
        y = event.y_root
        target_category = None
        insert_before = True
        
        for cat_name, widget in self._item_widgets.items():
            if cat_name == self._drag_category:
                continue
            
            widget_y = widget.winfo_rooty()
            widget_height = widget.winfo_height()
            
            if widget_y <= y <= widget_y + widget_height:
                target_category = cat_name
                # Determine if inserting before or after
                insert_before = y < widget_y + widget_height / 2
                break
        
        # Perform reorder
        if target_category and self._drag_category:
            self._reorder_category(self._drag_category, target_category, insert_before)
        
        self._dragging = False
        self._drag_item = None
        self._drag_category = None
    
    def _reorder_category(self, source: str, target: str, before: bool):
        """Reorder category in the manager"""
        # Get current order
        categories = self.category_manager.get_sorted_categories()
        
        if source not in categories or target not in categories:
            return
        
        # Remove source
        categories.remove(source)
        
        # Find target index
        target_idx = categories.index(target)
        
        # Insert at new position
        if before:
            categories.insert(target_idx, source)
        else:
            categories.insert(target_idx + 1, source)
        
        # Update sort orders
        for i, cat_name in enumerate(categories):
            if cat_name in self.category_manager.categories:
                self.category_manager.categories[cat_name].sort_order = i
        
        self.category_manager.save_categories()
        
        if self.on_reorder:
            self.on_reorder()
