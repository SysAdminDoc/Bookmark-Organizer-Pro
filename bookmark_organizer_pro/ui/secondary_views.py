"""Standalone secondary bookmark views for the desktop UI."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import ttk
from typing import Callable, Dict, List

from bookmark_organizer_pro.core import get_category_icon
from bookmark_organizer_pro.models import Bookmark

from .foundation import FONTS, display_or_fallback, pluralize
from .tk_interactions import make_keyboard_activatable
from .widgets import ThemedWidget, Tooltip, create_tooltip, get_theme


# =============================================================================
# Tag Cloud View
# =============================================================================
class TagCloudView(tk.Frame, ThemedWidget):
    """
        Represents a bookmark tag with metadata.
        
        Attributes:
            name: Tag name (unique identifier)
            color: Hex color code for display
            description: Optional tag description
            created_at: ISO timestamp of creation
            usage_count: Number of bookmarks using this tag
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
        """
    
    def __init__(self, parent, tag_counts: Dict[str, int], 
                 on_tag_click: Callable = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_primary)
        
        self.on_tag_click = on_tag_click
        self.tag_counts = tag_counts
        
        self._render_cloud()
    
    def _render_cloud(self):
        """Render the tag cloud"""
        theme = get_theme()
        
        if not self.tag_counts:
            tk.Label(
                self, text="No tags yet", bg=theme.bg_primary,
                fg=theme.text_muted, font=FONTS.body()
            ).pack(pady=20)
            return
        
        # Calculate font sizes
        max_count = max(self.tag_counts.values())
        min_count = min(self.tag_counts.values())
        count_range = max_count - min_count or 1
        
        # Sort by count descending
        sorted_tags = sorted(self.tag_counts.items(), key=lambda x: -x[1])
        
        # Create tag labels
        current_row = tk.Frame(self, bg=theme.bg_primary)
        current_row.pack(fill=tk.X, pady=5)
        row_width = 0
        max_width = 600
        
        for tag, count in sorted_tags:
            # Calculate size (8-18pt based on frequency)
            size_ratio = (count - min_count) / count_range
            font_size = int(8 + (size_ratio * 10))
            
            # Generate color
            colors = [
                theme.accent_primary, theme.accent_success, theme.accent_warning,
                theme.accent_purple, theme.accent_cyan, theme.accent_pink
            ]
            color = colors[hash(tag) % len(colors)]
            
            # Create label
            label = tk.Label(
                current_row, text=f"#{tag}", bg=theme.bg_primary,
                fg=color, font=("Segoe UI", font_size),
                cursor="hand2", padx=5, pady=3
            )
            
            # Estimate width
            est_width = len(tag) * font_size
            
            if row_width + est_width > max_width:
                current_row = tk.Frame(self, bg=theme.bg_primary)
                current_row.pack(fill=tk.X, pady=5)
                row_width = 0
            
            label.pack(side=tk.LEFT, padx=3, pady=2)
            row_width += est_width + 20
            
            # Bindings
            def on_enter(e, l=label, c=color):
                l.configure(bg=theme.bg_secondary)
            
            def on_leave(e, l=label):
                l.configure(bg=theme.bg_primary)
            
            def on_click(e, t=tag):
                if self.on_tag_click:
                    self.on_tag_click(t)

            def activate(t=tag):
                if self.on_tag_click:
                    self.on_tag_click(t)
            
            label.bind("<Enter>", on_enter)
            label.bind("<Leave>", on_leave)
            label.bind("<Button-1>", on_click)
            make_keyboard_activatable(label, activate)
            Tooltip(label, f"Filter by #{tag} ({pluralize(count, 'bookmark')})")
    
    def update_counts(self, tag_counts: Dict[str, int]):
        """Update tag counts and re-render"""
        self.tag_counts = tag_counts
        for widget in self.winfo_children():
            widget.destroy()
        self._render_cloud()


# =============================================================================
# Kanban View
# =============================================================================
class KanbanColumn(tk.Frame, ThemedWidget):
    """A single column in the Kanban view"""
    
    def __init__(self, parent, category: str, bookmarks: List[Bookmark],
                 on_bookmark_click: Callable = None,
                 on_bookmark_drop: Callable = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_secondary, width=280)
        
        self.category = category
        self.bookmarks = bookmarks
        self.on_bookmark_click = on_bookmark_click
        self.on_bookmark_drop = on_bookmark_drop
        
        self.pack_propagate(False)
        self.configure(highlightbackground=theme.border, highlightthickness=1)
        
        # Header
        header = tk.Frame(self, bg=theme.bg_tertiary)
        header.pack(fill=tk.X)
        
        # Get icon
        icon = get_category_icon(category)
        
        tk.Label(
            header, text=f"{icon} {category}", bg=theme.bg_tertiary,
            fg=theme.text_primary, font=("Segoe UI", 10, "bold"),
            anchor="w", padx=10, pady=10
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        tk.Label(
            header, text=str(len(bookmarks)), bg=theme.bg_tertiary,
            fg=theme.text_muted, font=FONTS.body(),
            padx=10
        ).pack(side=tk.RIGHT)
        
        # Cards container with scrolling
        container = tk.Frame(self, bg=theme.bg_secondary)
        container.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(container, bg=theme.bg_secondary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.cards_frame = tk.Frame(canvas, bg=theme.bg_secondary)
        
        self.cards_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.cards_frame, anchor="nw", width=270)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Mouse wheel
        canvas.bind("<MouseWheel>", 
            lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        
        # Enable drop
        self.bind("<ButtonRelease-1>", self._on_drop)
        canvas.bind("<ButtonRelease-1>", self._on_drop)
        self.cards_frame.bind("<ButtonRelease-1>", self._on_drop)
        
        self._render_cards()
    
    def _render_cards(self):
        """Render bookmark cards"""
        theme = get_theme()
        
        for bm in self.bookmarks[:50]:  # Limit for performance
            card = tk.Frame(
                self.cards_frame, bg=theme.card_bg,
                cursor="hand2"
            )
            card.pack(fill=tk.X, padx=8, pady=4)
            card.configure(highlightbackground=theme.card_border, highlightthickness=1)
            
            # Title
            title = bm.title[:35] + "..." if len(bm.title) > 38 else bm.title
            if bm.is_pinned:
                title = "📌 " + title
            
            tk.Label(
                card, text=title, bg=theme.card_bg,
                fg=theme.text_primary, font=FONTS.small(),
                anchor="w", padx=8, pady=(8, 4)
            ).pack(fill=tk.X)
            
            # Domain
            tk.Label(
                card, text=bm.domain, bg=theme.card_bg,
                fg=theme.text_muted, font=FONTS.tiny(),
                anchor="w", padx=8, pady=(0, 4)
            ).pack(fill=tk.X)
            
            # Tags
            if bm.tags:
                tags_text = " ".join(f"#{t}" for t in bm.tags[:3])
                tk.Label(
                    card, text=tags_text, bg=theme.card_bg,
                    fg=theme.accent_primary, font=FONTS.tiny(),
                    anchor="w", padx=8, pady=(0, 8)
                ).pack(fill=tk.X)
            
            # Click handler
            def on_click(e, bookmark=bm):
                if self.on_bookmark_click:
                    self.on_bookmark_click(bookmark)

            make_keyboard_activatable(
                card,
                lambda bookmark=bm: self.on_bookmark_click and self.on_bookmark_click(bookmark)
            )
            for child in card.winfo_children():
                child.bind("<Button-1>", on_click)
            Tooltip(card, f"Open details for {display_or_fallback(bm.title, bm.domain)}")
            
            # Hover effect
            def on_enter(e, c=card):
                c.configure(bg=theme.card_hover)
                for child in c.winfo_children():
                    child.configure(bg=theme.card_hover)
            
            def on_leave(e, c=card):
                c.configure(bg=theme.card_bg)
                for child in c.winfo_children():
                    child.configure(bg=theme.card_bg)
            
            card.bind("<Enter>", on_enter)
            card.bind("<Leave>", on_leave)
    
    def _on_drop(self, e):
        """Handle drop on this column"""
        if self.on_bookmark_drop:
            self.on_bookmark_drop(self.category)


class KanbanView(tk.Frame, ThemedWidget):
    """Kanban board view for bookmarks"""
    
    def __init__(self, parent, bookmark_manager: BookmarkManager,
                 on_bookmark_click: Callable = None,
                 on_move: Callable = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_primary)
        
        self.bookmark_manager = bookmark_manager
        self.on_bookmark_click = on_bookmark_click
        self.on_move = on_move
        self.columns: Dict[str, KanbanColumn] = {}
        
        # Scrollable container
        self.canvas = tk.Canvas(self, bg=theme.bg_primary, highlightthickness=0)
        self.h_scrollbar = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.inner = tk.Frame(self.canvas, bg=theme.bg_primary)
        
        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(xscrollcommand=self.h_scrollbar.set)
        
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Mouse wheel horizontal scroll
        self.canvas.bind("<Shift-MouseWheel>", 
            lambda e: self.canvas.xview_scroll(-1 * (e.delta // 120), "units"))
    
    def refresh(self, categories: List[str] = None):
        """Refresh the Kanban board"""
        theme = get_theme()
        
        # Clear existing columns
        for widget in self.inner.winfo_children():
            widget.destroy()
        self.columns.clear()
        
        # Get categories
        if categories is None:
            categories = self.bookmark_manager.category_manager.get_sorted_categories()
        
        # Create columns
        for cat in categories:
            bookmarks = self.bookmark_manager.get_bookmarks_by_category(cat)
            
            column = KanbanColumn(
                self.inner, cat, bookmarks,
                on_bookmark_click=self.on_bookmark_click,
                on_bookmark_drop=lambda c: self._on_column_drop(c)
            )
            column.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=10)
            self.columns[cat] = column
    
    def _on_column_drop(self, category: str):
        """Handle drop on a category column"""
        if self.on_move:
            self.on_move(category)


# =============================================================================
# Reading List Queue View
# =============================================================================
class ReadingListView(tk.Frame, ThemedWidget):
    """View for managing a reading list queue"""
    
    def __init__(self, parent, bookmarks: List[Bookmark],
                 on_open: Callable = None,
                 on_mark_read: Callable = None,
                 on_remove: Callable = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_primary)
        
        self.bookmarks = bookmarks
        self.on_open = on_open
        self.on_mark_read = on_mark_read
        self.on_remove = on_remove
        
        # Header
        header = tk.Frame(self, bg=theme.bg_dark)
        header.pack(fill=tk.X)
        
        tk.Label(
            header, text="📖 Reading List", bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.header(),
            padx=15, pady=12
        ).pack(side=tk.LEFT)
        
        self.count_label = tk.Label(
            header, text=f"{len(bookmarks)} items", bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.body(),
            padx=15
        )
        self.count_label.pack(side=tk.RIGHT)
        
        # List container
        container = tk.Frame(self, bg=theme.bg_primary)
        container.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(container, bg=theme.bg_primary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.list_frame = tk.Frame(canvas, bg=theme.bg_primary)
        
        self.list_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        canvas.bind("<MouseWheel>", 
            lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        
        self._render_list()
    
    def _render_list(self):
        """Render the reading list"""
        theme = get_theme()
        
        for i, bm in enumerate(self.bookmarks):
            item = tk.Frame(self.list_frame, bg=theme.bg_secondary)
            item.pack(fill=tk.X, padx=10, pady=5)
            
            # Number
            tk.Label(
                item, text=f"{i+1}.", bg=theme.bg_secondary,
                fg=theme.text_muted, font=FONTS.body(),
                width=4
            ).pack(side=tk.LEFT, padx=(10, 5), pady=10)
            
            # Content
            content = tk.Frame(item, bg=theme.bg_secondary)
            content.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=10)
            
            # Title
            title = bm.title[:60] + "..." if len(bm.title) > 63 else bm.title
            tk.Label(
                content, text=title, bg=theme.bg_secondary,
                fg=theme.text_primary, font=FONTS.body(),
                anchor="w"
            ).pack(fill=tk.X)
            
            # Meta info
            meta = f"{bm.domain}"
            if bm.reading_time > 0:
                meta += f" • {bm.reading_time} min read"
            
            tk.Label(
                content, text=meta, bg=theme.bg_secondary,
                fg=theme.text_muted, font=FONTS.small(),
                anchor="w"
            ).pack(fill=tk.X)
            
            # Actions
            actions = tk.Frame(item, bg=theme.bg_secondary)
            actions.pack(side=tk.RIGHT, padx=10)
            
            # Open button
            open_btn = tk.Label(
                actions, text="📖", bg=theme.bg_secondary,
                fg=theme.accent_primary, font=("Segoe UI", 12),
                cursor="hand2"
            )
            open_btn.pack(side=tk.LEFT, padx=5)
            make_keyboard_activatable(open_btn, lambda b=bm: self._on_open(b))
            create_tooltip(open_btn, "Open Bookmark")
            
            # Mark read button
            done_btn = tk.Label(
                actions, text="✓", bg=theme.bg_secondary,
                fg=theme.accent_success, font=("Segoe UI", 12),
                cursor="hand2"
            )
            done_btn.pack(side=tk.LEFT, padx=5)
            make_keyboard_activatable(done_btn, lambda b=bm: self._on_mark_read(b))
            create_tooltip(done_btn, "Mark as Read")
            
            # Remove button
            remove_btn = tk.Label(
                actions, text="✕", bg=theme.bg_secondary,
                fg=theme.accent_error, font=("Segoe UI", 12),
                cursor="hand2"
            )
            remove_btn.pack(side=tk.LEFT, padx=5)
            make_keyboard_activatable(remove_btn, lambda b=bm: self._on_remove(b))
            create_tooltip(remove_btn, "Remove from Reading List")

    def _on_open(self, bookmark: Bookmark):
        if self.on_open:
            self.on_open(bookmark)

    def _on_mark_read(self, bookmark: Bookmark):
        if self.on_mark_read:
            self.on_mark_read(bookmark)

    def _on_remove(self, bookmark: Bookmark):
        if self.on_remove:
            self.on_remove(bookmark)

    def refresh(self, bookmarks: List[Bookmark]):
        """Refresh the reading list"""
        self.bookmarks = bookmarks
        self.count_label.configure(text=f"{len(bookmarks)} items")
        
        for widget in self.list_frame.winfo_children():
            widget.destroy()
        
        self._render_list()


# =============================================================================
# Timeline View
# =============================================================================
class TimelineView(tk.Frame, ThemedWidget):
    """Chronological timeline view of bookmarks"""
    
    def __init__(self, parent, bookmarks: List[Bookmark],
                 on_bookmark_click: Callable = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_primary)
        
        self.bookmarks = bookmarks
        self.on_bookmark_click = on_bookmark_click
        
        # Group bookmarks by date
        self.grouped = self._group_by_date()
        
        # Create scrollable container
        canvas = tk.Canvas(self, bg=theme.bg_primary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = tk.Frame(canvas, bg=theme.bg_primary)
        
        self.inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        canvas.bind("<MouseWheel>", 
            lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        
        self._render_timeline()
    
    def _group_by_date(self) -> Dict[str, List[Bookmark]]:
        """Group bookmarks by date"""
        grouped: Dict[str, List[Bookmark]] = {}
        
        for bm in self.bookmarks:
            try:
                created = datetime.fromisoformat(bm.created_at.replace('Z', '+00:00'))
                date_key = created.strftime("%Y-%m-%d")
            except Exception:
                date_key = "Unknown"
            
            if date_key not in grouped:
                grouped[date_key] = []
            grouped[date_key].append(bm)
        
        # Sort by date descending
        return dict(sorted(grouped.items(), key=lambda x: x[0], reverse=True))
    
    def _render_timeline(self):
        """Render the timeline"""
        theme = get_theme()
        
        for date_str, bms in self.grouped.items():
            # Date header
            date_frame = tk.Frame(self.inner, bg=theme.bg_primary)
            date_frame.pack(fill=tk.X, pady=(20, 10))
            
            # Timeline line
            tk.Frame(
                date_frame, bg=theme.accent_primary, width=3
            ).pack(side=tk.LEFT, fill=tk.Y, padx=(20, 0))
            
            # Date circle
            circle = tk.Frame(
                date_frame, bg=theme.accent_primary,
                width=12, height=12
            )
            circle.pack(side=tk.LEFT, padx=(0, 15))
            
            # Format date nicely
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                display_date = date_obj.strftime("%B %d, %Y")
                
                # Add relative time
                days_ago = (datetime.now() - date_obj).days
                if days_ago == 0:
                    relative = "Today"
                elif days_ago == 1:
                    relative = "Yesterday"
                elif days_ago < 7:
                    relative = f"{days_ago} days ago"
                elif days_ago < 30:
                    relative = f"{days_ago // 7} weeks ago"
                else:
                    relative = f"{days_ago // 30} months ago"
                
                display_date = f"{display_date} ({relative})"
            except Exception:
                display_date = date_str
            
            tk.Label(
                date_frame, text=display_date, bg=theme.bg_primary,
                fg=theme.text_primary, font=("Segoe UI", 11, "bold")
            ).pack(side=tk.LEFT)
            
            tk.Label(
                date_frame, text=f"{len(bms)} bookmarks", bg=theme.bg_primary,
                fg=theme.text_muted, font=FONTS.body()
            ).pack(side=tk.RIGHT, padx=20)
            
            # Bookmarks for this date
            for bm in bms:
                self._render_bookmark_item(bm)
    
    def _render_bookmark_item(self, bookmark: Bookmark):
        """Render a single bookmark in the timeline"""
        theme = get_theme()
        
        item_frame = tk.Frame(self.inner, bg=theme.bg_primary)
        item_frame.pack(fill=tk.X, padx=(35, 20), pady=3)
        
        # Timeline connector line
        connector = tk.Frame(item_frame, bg=theme.border, width=1, height=40)
        connector.pack(side=tk.LEFT, padx=(7, 15))
        
        # Content card
        card = tk.Frame(item_frame, bg=theme.bg_secondary, cursor="hand2")
        card.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=2)
        card.configure(highlightbackground=theme.border, highlightthickness=1)
        
        # Inner content
        inner = tk.Frame(card, bg=theme.bg_secondary)
        inner.pack(fill=tk.X, padx=12, pady=8)
        
        # Title with status indicators
        title = bookmark.title[:50] + "..." if len(bookmark.title) > 53 else bookmark.title
        if bookmark.is_pinned:
            title = "📌 " + title
        
        tk.Label(
            inner, text=title, bg=theme.bg_secondary,
            fg=theme.text_primary, font=FONTS.body(),
            anchor="w"
        ).pack(fill=tk.X)
        
        # Domain and category
        meta = f"{bookmark.domain} • {bookmark.category}"
        tk.Label(
            inner, text=meta, bg=theme.bg_secondary,
            fg=theme.text_muted, font=FONTS.small(),
            anchor="w"
        ).pack(fill=tk.X)
        
        # Click handler
        def on_click(e, bm=bookmark):
            if self.on_bookmark_click:
                self.on_bookmark_click(bm)
        
        card.bind("<Button-1>", on_click)
        inner.bind("<Button-1>", on_click)
        for child in inner.winfo_children():
            child.bind("<Button-1>", on_click)
        
        # Hover effects
        def on_enter(e):
            card.configure(bg=theme.bg_hover)
            inner.configure(bg=theme.bg_hover)
            for child in inner.winfo_children():
                child.configure(bg=theme.bg_hover)
        
        def on_leave(e):
            card.configure(bg=theme.bg_secondary)
            inner.configure(bg=theme.bg_secondary)
            for child in inner.winfo_children():
                child.configure(bg=theme.bg_secondary)
        
        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)
