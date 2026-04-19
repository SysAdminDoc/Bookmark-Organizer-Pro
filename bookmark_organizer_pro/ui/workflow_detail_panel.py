"""Bookmark detail side panel."""

from __future__ import annotations

from datetime import datetime
import tkinter as tk
from typing import Callable, Optional

from bookmark_organizer_pro.core import get_category_icon
from bookmark_organizer_pro.models import Bookmark

from .foundation import FONTS
from .tk_interactions import make_keyboard_activatable
from .widget_controls import ModernButton, ThemedWidget, create_tooltip
from .widget_runtime import get_theme
from .workflow_runtime import _open_external_url

# =============================================================================
# Split View with Details Panel
# =============================================================================
class BookmarkDetailPanel(tk.Frame, ThemedWidget):
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
    
    def __init__(self, parent, on_edit: Callable = None, 
                 on_open: Callable = None,
                 on_delete: Callable = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_secondary, width=350)
        
        self.on_edit = on_edit
        self.on_open = on_open
        self.on_delete = on_delete
        self.current_bookmark: Optional[Bookmark] = None
        
        self.pack_propagate(False)
        
        # Header
        self.header = tk.Frame(self, bg=theme.bg_tertiary)
        self.header.pack(fill=tk.X)
        
        tk.Label(
            self.header, text="Bookmark Details", bg=theme.bg_tertiary,
            fg=theme.text_primary, font=("Segoe UI", 11, "bold"),
            padx=15, pady=12
        ).pack(side=tk.LEFT)
        
        # Close button
        close_btn = tk.Label(
            self.header, text="✕", bg=theme.bg_tertiary,
            fg=theme.text_muted, font=FONTS.header(bold=False),
            cursor="hand2", padx=15
        )
        close_btn.pack(side=tk.RIGHT)
        make_keyboard_activatable(close_btn, lambda: self.pack_forget())
        create_tooltip(close_btn, "Close Details")
        
        # Content
        self.content = tk.Frame(self, bg=theme.bg_secondary)
        self.content.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # Placeholder
        self.placeholder = tk.Label(
            self.content, text="Select a bookmark to view details",
            bg=theme.bg_secondary, fg=theme.text_muted,
            font=FONTS.body()
        )
        self.placeholder.pack(expand=True)
    
    def show_bookmark(self, bookmark: Bookmark):
        """Display bookmark details"""
        theme = get_theme()
        self.current_bookmark = bookmark
        
        # Clear content
        for widget in self.content.winfo_children():
            widget.destroy()
        
        # Favicon / Icon
        icon_frame = tk.Frame(self.content, bg=theme.bg_secondary)
        icon_frame.pack(fill=tk.X, pady=(0, 15))
        
        icon_label = tk.Label(
            icon_frame, text=bookmark.domain[0].upper(),
            bg=theme.accent_primary, fg="#ffffff",
            font=("Segoe UI", 24, "bold"),
            width=3, height=1
        )
        icon_label.pack(side=tk.LEFT)
        
        # Title
        title_frame = tk.Frame(icon_frame, bg=theme.bg_secondary)
        title_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=15)
        
        tk.Label(
            title_frame, text=bookmark.title,
            bg=theme.bg_secondary, fg=theme.text_primary,
            font=FONTS.header(),
            wraplength=200, justify=tk.LEFT, anchor="w"
        ).pack(fill=tk.X)
        
        tk.Label(
            title_frame, text=bookmark.domain,
            bg=theme.bg_secondary, fg=theme.text_muted,
            font=FONTS.body()
        ).pack(fill=tk.X, anchor="w")
        
        # Actions
        actions = tk.Frame(self.content, bg=theme.bg_secondary)
        actions.pack(fill=tk.X, pady=15)
        
        ModernButton(
            actions, text="Open", icon="🔗",
            command=lambda: self._open_bookmark()
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ModernButton(
            actions, text="Edit", icon="✏️",
            command=lambda: self._edit_bookmark()
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ModernButton(
            actions, text="Delete", icon="🗑️", style="danger",
            command=lambda: self._delete_bookmark()
        ).pack(side=tk.LEFT)
        
        # Separator
        tk.Frame(self.content, bg=theme.border, height=1).pack(fill=tk.X, pady=15)
        
        # Details
        self._add_detail("URL", bookmark.url, is_link=True)
        self._add_detail("Category", f"{get_category_icon(bookmark.category)} {bookmark.category}")
        
        if bookmark.tags:
            tags_text = ", ".join(f"#{t}" for t in bookmark.tags)
            self._add_detail("Tags", tags_text)
        
        self._add_detail("Added", self._format_date(bookmark.created_at))
        
        if bookmark.last_visited:
            self._add_detail("Last Visited", self._format_date(bookmark.last_visited))
        
        self._add_detail("Visits", str(bookmark.visit_count))
        
        # Status indicators
        status_parts = []
        if bookmark.is_pinned:
            status_parts.append("📌 Pinned")
        if bookmark.is_archived:
            status_parts.append("📦 Archived")
        if not bookmark.is_valid:
            status_parts.append("⚠️ Broken")
        if bookmark.ai_categorized:
            status_parts.append(f"🤖 AI ({int(bookmark.ai_confidence*100)}%)")
        
        if status_parts:
            self._add_detail("Status", " • ".join(status_parts))
        
        # Notes
        if bookmark.notes:
            tk.Frame(self.content, bg=theme.border, height=1).pack(fill=tk.X, pady=15)
            
            tk.Label(
                self.content, text="Notes:", bg=theme.bg_secondary,
                fg=theme.text_secondary, font=FONTS.body(),
                anchor="w"
            ).pack(fill=tk.X)
            
            notes_text = tk.Text(
                self.content, bg=theme.bg_tertiary, fg=theme.text_primary,
                font=FONTS.body(), height=4, wrap=tk.WORD, bd=0
            )
            notes_text.pack(fill=tk.X, pady=5)
            notes_text.insert("1.0", bookmark.notes)
            notes_text.configure(state=tk.DISABLED)
    
    def _add_detail(self, label: str, value: str, is_link: bool = False):
        """Add a detail row"""
        theme = get_theme()
        
        row = tk.Frame(self.content, bg=theme.bg_secondary)
        row.pack(fill=tk.X, pady=3)
        
        tk.Label(
            row, text=f"{label}:", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.small(),
            width=12, anchor="w"
        ).pack(side=tk.LEFT)
        
        value_label = tk.Label(
            row, text=value[:40] + "..." if len(value) > 43 else value,
            bg=theme.bg_secondary,
            fg=theme.text_link if is_link else theme.text_primary,
            font=FONTS.small(),
            anchor="w", cursor="hand2" if is_link else ""
        )
        value_label.pack(side=tk.LEFT, fill=tk.X)
        
        if is_link:
            make_keyboard_activatable(value_label, lambda v=value: _open_external_url(v))
    
    def _format_date(self, date_str: str) -> str:
        """Format date string nicely"""
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return date_str
    
    def _open_bookmark(self):
        if self.current_bookmark and self.on_open:
            self.on_open(self.current_bookmark)
    
    def _edit_bookmark(self):
        if self.current_bookmark and self.on_edit:
            self.on_edit(self.current_bookmark)
    
    def _delete_bookmark(self):
        if self.current_bookmark and self.on_delete:
            self.on_delete(self.current_bookmark)
    
    def clear(self):
        """Clear the panel"""
        self.current_bookmark = None
        for widget in self.content.winfo_children():
            widget.destroy()
        
        theme = get_theme()
        self.placeholder = tk.Label(
            self.content, text="Select a bookmark to view details",
            bg=theme.bg_secondary, fg=theme.text_muted,
            font=FONTS.body()
        )
        self.placeholder.pack(expand=True)
# =============================================================================
# Archive, local web capture, and summarization services are implemented in bookmark_organizer_pro.services.
# =============================================================================



# =============================================================================
# AI Semantic Duplicate Detection
# =============================================================================
# AI duplicate/cost services are implemented in bookmark_organizer_pro.services.
# =============================================================================
