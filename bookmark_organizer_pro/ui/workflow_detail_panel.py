"""Bookmark detail side panel."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tkinter as tk
from typing import Callable, Optional

from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.extraction_templates import (
    format_structured_value,
    structured_metadata_fields,
    structured_metadata_payload,
)

from .foundation import DesignTokens, FONTS, readable_text_on
from .tk_interactions import make_keyboard_activatable
from .widget_controls import ModernButton, ThemedWidget, create_tooltip
from .widget_runtime import get_theme
from .workflow_runtime import _open_external_url

# =============================================================================
# Split View with Details Panel
# =============================================================================
class BookmarkDetailPanel(tk.Frame, ThemedWidget):
    """Split-view detail panel showing full bookmark metadata and notes.
        """
    
    def __init__(self, parent, on_edit: Callable = None, 
                 on_open: Callable = None,
                 on_delete: Callable = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_secondary, width=DesignTokens.RIGHT_SIDEBAR_WIDTH)
        
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
            fg=theme.text_primary, font=FONTS.body(bold=True),
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
            bg=theme.accent_primary, fg=readable_text_on(theme.accent_primary),
            font=FONTS.hero(bold=True),
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
            actions, text="Open",
            command=lambda: self._open_bookmark()
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ModernButton(
            actions, text="Edit",
            command=lambda: self._edit_bookmark()
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ModernButton(
            actions, text="Delete", style="danger",
            command=lambda: self._delete_bookmark()
        ).pack(side=tk.LEFT)
        
        # Separator
        tk.Frame(self.content, bg=theme.border, height=1).pack(fill=tk.X, pady=15)
        
        # Details
        self._add_detail("URL", bookmark.url, is_link=True)
        self._add_detail("Category", bookmark.category)
        
        if bookmark.tags:
            tags_text = ", ".join(f"#{t}" for t in bookmark.tags)
            self._add_detail("Tags", tags_text)
        
        self._add_detail("Added", self._format_date(bookmark.created_at))
        
        if bookmark.last_visited:
            self._add_detail("Last Visited", self._format_date(bookmark.last_visited))
        
        self._add_detail("Visits", str(bookmark.visit_count))

        if bookmark.snapshot_path:
            self._add_detail("Snapshot", self._format_date(bookmark.snapshot_at) or "Available")
            try:
                from bookmark_organizer_pro.services.snapshot_history import SnapshotHistoryStore
                versions = SnapshotHistoryStore(Path(bookmark.snapshot_path).parent).list_versions(bookmark.id)
                self._add_detail("Versions", str(len(versions)))
                if versions:
                    latest = versions[0]
                    provenance = f"{latest.status_code or 'n/a'} · {latest.resolved_url}"
                    self._add_detail("Capture", provenance)
                if len(versions) > 1:
                    report = SnapshotHistoryStore(Path(bookmark.snapshot_path).parent).change_report(
                        versions[1].version_id, versions[0].version_id, max_diff_lines=1,
                    )
                    changes = []
                    if report["content_changed"]:
                        changes.append("content")
                    if report["redirect_changed"]:
                        changes.append("redirect")
                    if report["status_changed"]:
                        changes.append("status")
                    self._add_detail("Changed", ", ".join(changes) if changes else "No change")
            except (OSError, RuntimeError, ValueError, KeyError):
                pass
        
        # Status indicators
        status_parts = []
        if bookmark.is_pinned:
            status_parts.append("Pinned")
        if bookmark.is_archived:
            status_parts.append("Archived")
        if not bookmark.is_valid:
            status_parts.append("Needs review")
        if bookmark.ai_categorized:
            status_parts.append(f"AI ({int(bookmark.ai_confidence*100)}%)")
        
        if status_parts:
            self._add_detail("Status", " • ".join(status_parts))
        
        structured_fields = structured_metadata_fields(bookmark)
        if structured_fields:
            template = structured_metadata_payload(bookmark).get("template", "")
            self._add_detail("Template", str(template or "Structured metadata"))
            for key, value in sorted(structured_fields.items()):
                self._add_detail(key.replace("_", " ").title(), format_structured_value(value))

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
