"""Grid/card bookmark views."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Set

from bookmark_organizer_pro.models import Bookmark

from .shell_widgets import BookmarkCard
from .widget_controls import ThemedWidget
from .widget_runtime import get_theme

# =============================================================================
# Grid/Card View Components
# =============================================================================
class GridView(tk.Frame, ThemedWidget):
    """
        Grid/card view for displaying bookmarks.
        
        Displays bookmarks as cards in a responsive grid layout.
        
        Attributes:
            bookmarks: List of bookmarks to display
            columns: Number of columns
            card_width: Width of each card
            on_select: Selection callback
            on_open: Double-click callback
        
        Methods:
            set_bookmarks(bookmarks): Update displayed bookmarks
            get_selected(): Get selected bookmark IDs
            select_all(): Select all bookmarks
            clear_selection(): Clear selection
        
        Features:
            - Responsive column count
            - Smooth scrolling
            - Multi-select with Ctrl/Shift
            - Keyboard navigation
        """
    
    def __init__(self, parent, columns: int = 3,
                 on_select: Callable = None,
                 on_open: Callable = None,
                 on_context_menu: Callable = None,
                 favicon_manager=None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_primary)
        
        self.columns = columns
        self.on_select = on_select
        self.on_open = on_open
        self.on_context_menu = on_context_menu
        self.favicon_manager = favicon_manager
        self.theme = theme
        
        self.cards: Dict[int, BookmarkCard] = {}
        self.selected_ids: Set[int] = set()
        
        # Scrollable canvas
        self.canvas = tk.Canvas(self, bg=theme.bg_primary, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Inner frame for cards
        self.inner_frame = tk.Frame(self.canvas, bg=theme.bg_primary)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.inner_frame, anchor="nw")
        
        # Bindings
        self.inner_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
    
    def _on_frame_configure(self, e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    
    def _on_canvas_configure(self, e):
        # Adjust columns based on width
        card_width = 280
        new_cols = max(1, e.width // card_width)
        if new_cols != self.columns:
            self.columns = new_cols
            self._reflow_cards()
    
    def _on_mousewheel(self, e):
        self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
    
    def load_bookmarks(self, bookmarks: List[Bookmark]):
        """Load bookmarks into grid"""
        # Clear existing
        for card in self.cards.values():
            card.destroy()
        self.cards.clear()
        self.selected_ids.clear()
        
        # Create cards
        for i, bm in enumerate(bookmarks):
            card = BookmarkCard(
                self.inner_frame, bm,
                on_click=self._on_card_click,
                on_double_click=self._on_card_double_click,
                on_right_click=self._on_card_right_click,
                favicon_manager=self.favicon_manager
            )
            self.cards[bm.id] = card
            
            row = i // self.columns
            col = i % self.columns
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
        
        # Configure grid weights
        for i in range(self.columns):
            self.inner_frame.columnconfigure(i, weight=1)
    
    def _reflow_cards(self):
        """Reflow cards when column count changes"""
        cards_list = list(self.cards.values())
        for i, card in enumerate(cards_list):
            row = i // self.columns
            col = i % self.columns
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
    
    def _on_card_click(self, bookmark: Bookmark):
        # Single select for now
        for card in self.cards.values():
            card.set_selected(False)
        
        self.selected_ids = {bookmark.id}
        if bookmark.id in self.cards:
            self.cards[bookmark.id].set_selected(True)
        
        if self.on_select:
            self.on_select([bookmark])
    
    def _on_card_double_click(self, bookmark: Bookmark):
        if self.on_open:
            self.on_open(bookmark)
    
    def _on_card_right_click(self, event, bookmark: Bookmark):
        if self.on_context_menu:
            self.on_context_menu(event, bookmark)
    
    def get_selected(self) -> List[int]:
        """Get selected bookmark IDs"""
        return list(self.selected_ids)
    
    def select_all(self):
        """Select all cards"""
        self.selected_ids = set(self.cards.keys())
        for card in self.cards.values():
            card.set_selected(True)
    
    def clear_selection(self):
        """Clear selection"""
        self.selected_ids.clear()
        for card in self.cards.values():
            card.set_selected(False)
