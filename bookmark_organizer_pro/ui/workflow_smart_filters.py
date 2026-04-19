"""Smart filter sidebar for bookmark collections."""

from __future__ import annotations

from datetime import datetime
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, List
from urllib.parse import urlparse

from bookmark_organizer_pro.models import Bookmark

from .foundation import FONTS
from .tk_interactions import make_keyboard_activatable
from .widget_controls import ThemedWidget, Tooltip
from .widget_runtime import get_theme

# =============================================================================
# Smart Filters Panel
# =============================================================================
class SmartFiltersPanel(tk.Frame, ThemedWidget):
    """Collapsible smart filters sidebar panel"""
    
    def __init__(self, parent, on_filter_change: Callable = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_secondary, width=250)
        
        self.on_filter_change = on_filter_change
        self.is_collapsed = False
        self.filters: Dict[str, Any] = {}
        
        # Header
        header = tk.Frame(self, bg=theme.bg_tertiary)
        header.pack(fill=tk.X)
        
        self.toggle_btn = tk.Label(
            header, text="◀", bg=theme.bg_tertiary,
            fg=theme.text_primary, font=FONTS.body(),
            cursor="hand2", padx=10, pady=8
        )
        self.toggle_btn.pack(side=tk.LEFT)
        make_keyboard_activatable(self.toggle_btn, self._toggle)
        Tooltip(self.toggle_btn, "Collapse Smart Filters")
        
        tk.Label(
            header, text="Smart Filters", bg=theme.bg_tertiary,
            fg=theme.text_primary, font=("Segoe UI", 10, "bold"),
            pady=8
        ).pack(side=tk.LEFT)
        
        self.clear_btn = tk.Label(
            header, text="Clear", bg=theme.bg_tertiary,
            fg=theme.accent_primary, font=FONTS.small(),
            cursor="hand2", padx=10
        )
        self.clear_btn.pack(side=tk.RIGHT)
        make_keyboard_activatable(self.clear_btn, self._clear_filters)
        Tooltip(self.clear_btn, "Clear Smart Filters")
        
        # Content
        self.content = tk.Frame(self, bg=theme.bg_secondary)
        self.content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self._create_filters()
    
    def _create_filters(self):
        """Create all filter controls"""
        theme = get_theme()
        
        # Date Range
        self._create_section("📅 Date Range")
        
        date_frame = tk.Frame(self.content, bg=theme.bg_secondary)
        date_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(
            date_frame, text="From:", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.small()
        ).pack(side=tk.LEFT)
        
        self.date_from_var = tk.StringVar()
        date_from = tk.Entry(
            date_frame, textvariable=self.date_from_var, width=12,
            bg=theme.bg_tertiary, fg=theme.text_primary, bd=0
        )
        date_from.pack(side=tk.LEFT, padx=5)
        date_from.insert(0, "YYYY-MM-DD")
        date_from.bind("<FocusIn>", lambda e: date_from.delete(0, tk.END) if date_from.get() == "YYYY-MM-DD" else None)
        
        tk.Label(
            date_frame, text="To:", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.small()
        ).pack(side=tk.LEFT, padx=(10, 0))
        
        self.date_to_var = tk.StringVar()
        date_to = tk.Entry(
            date_frame, textvariable=self.date_to_var, width=12,
            bg=theme.bg_tertiary, fg=theme.text_primary, bd=0
        )
        date_to.pack(side=tk.LEFT, padx=5)
        
        # Quick date buttons
        quick_dates = tk.Frame(self.content, bg=theme.bg_secondary)
        quick_dates.pack(fill=tk.X, pady=(0, 10))
        
        for label, days in [("Today", 1), ("Week", 7), ("Month", 30), ("Year", 365)]:
            btn = tk.Label(
                quick_dates, text=label, bg=theme.bg_tertiary,
                fg=theme.text_primary, font=FONTS.tiny(),
                padx=8, pady=3, cursor="hand2"
            )
            btn.pack(side=tk.LEFT, padx=2)
            make_keyboard_activatable(btn, lambda d=days: self._set_date_range(d))
            Tooltip(btn, f"Show bookmarks from the last {days} day{'s' if days != 1 else ''}")
        
        # Status Filters
        self._create_section("📊 Status")
        
        self.status_vars = {}
        for status, label in [("valid", "✓ Valid"), ("broken", "⚠ Broken"), 
                              ("unchecked", "? Unchecked")]:
            var = tk.BooleanVar(value=True)
            self.status_vars[status] = var
            cb = ttk.Checkbutton(
                self.content, text=label, variable=var,
                command=self._on_change
            )
            cb.pack(anchor="w", pady=2)
        
        # Bookmark Attributes
        self._create_section("📌 Attributes")
        
        self.attr_vars = {}
        for attr, label in [("pinned", "📌 Pinned Only"), 
                            ("archived", "📦 Archived Only"),
                            ("has_notes", "📝 Has Notes"),
                            ("has_tags", "🏷️ Has Tags")]:
            var = tk.BooleanVar(value=False)
            self.attr_vars[attr] = var
            cb = ttk.Checkbutton(
                self.content, text=label, variable=var,
                command=self._on_change
            )
            cb.pack(anchor="w", pady=2)
        
        # Domain Filter
        self._create_section("🌐 Domain")
        
        self.domain_var = tk.StringVar()
        domain_entry = tk.Entry(
            self.content, textvariable=self.domain_var,
            bg=theme.bg_tertiary, fg=theme.text_primary, bd=0
        )
        domain_entry.pack(fill=tk.X, pady=5, ipady=5)
        domain_entry.bind("<KeyRelease>", lambda e: self._on_change())
        
        # AI Confidence Slider
        self._create_section("🤖 AI Confidence")
        
        self.confidence_var = tk.DoubleVar(value=0.0)
        confidence_frame = tk.Frame(self.content, bg=theme.bg_secondary)
        confidence_frame.pack(fill=tk.X, pady=5)
        
        self.confidence_label = tk.Label(
            confidence_frame, text="Min: 0%", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.small()
        )
        self.confidence_label.pack(side=tk.LEFT)
        
        confidence_scale = ttk.Scale(
            confidence_frame, from_=0, to=100, variable=self.confidence_var,
            command=self._on_confidence_change
        )
        confidence_scale.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=10)
    
    def _create_section(self, title: str):
        """Create a section header"""
        theme = get_theme()
        tk.Label(
            self.content, text=title, bg=theme.bg_secondary,
            fg=theme.text_primary, font=("Segoe UI", 10, "bold"),
            anchor="w"
        ).pack(fill=tk.X, pady=(15, 5))
    
    def _toggle(self, e=None):
        """Toggle panel collapsed state"""
        theme = get_theme()
        self.is_collapsed = not self.is_collapsed
        
        if self.is_collapsed:
            self.content.pack_forget()
            self.toggle_btn.configure(text="▶")
            self.configure(width=40)
        else:
            self.content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            self.toggle_btn.configure(text="◀")
            self.configure(width=250)
    
    def _clear_filters(self, e=None):
        """Clear all filters"""
        self.date_from_var.set("")
        self.date_to_var.set("")
        self.domain_var.set("")
        self.confidence_var.set(0.0)
        
        for var in self.status_vars.values():
            var.set(True)
        for var in self.attr_vars.values():
            var.set(False)
        
        self._on_change()
    
    def _set_date_range(self, days: int):
        """Set date range to last N days"""
        end = datetime.now()
        start = end - timedelta(days=days)
        self.date_from_var.set(start.strftime("%Y-%m-%d"))
        self.date_to_var.set(end.strftime("%Y-%m-%d"))
        self._on_change()
    
    def _on_confidence_change(self, value):
        """Handle confidence slider change"""
        self.confidence_label.configure(text=f"Min: {int(float(value))}%")
        self._on_change()
    
    def _on_change(self):
        """Notify of filter change"""
        self.filters = self.get_filters()
        if self.on_filter_change:
            self.on_filter_change(self.filters)
    
    def get_filters(self) -> Dict[str, Any]:
        """Get current filter settings"""
        filters = {
            "date_from": self.date_from_var.get() if self.date_from_var.get() != "YYYY-MM-DD" else "",
            "date_to": self.date_to_var.get(),
            "domain": self.domain_var.get(),
            "min_confidence": self.confidence_var.get() / 100,
            "status": {k: v.get() for k, v in self.status_vars.items()},
            "attributes": {k: v.get() for k, v in self.attr_vars.items()},
        }
        return filters
    
    def apply_filters(self, bookmarks: List[Bookmark]) -> List[Bookmark]:
        """Apply current filters to bookmark list"""
        filters = self.get_filters()
        result = []
        
        for bm in bookmarks:
            # Date filter
            if filters["date_from"]:
                try:
                    from_date = datetime.fromisoformat(filters["date_from"])
                    created = datetime.fromisoformat(bm.created_at.replace('Z', '+00:00'))
                    if created.replace(tzinfo=None) < from_date:
                        continue
                except Exception:
                    pass
            
            if filters["date_to"]:
                try:
                    to_date = datetime.fromisoformat(filters["date_to"])
                    created = datetime.fromisoformat(bm.created_at.replace('Z', '+00:00'))
                    if created.replace(tzinfo=None) > to_date:
                        continue
                except Exception:
                    pass
            
            # Domain filter
            if filters["domain"] and filters["domain"].lower() not in bm.domain.lower():
                continue
            
            # Status filter
            if bm.is_valid and not filters["status"].get("valid", True):
                continue
            if not bm.is_valid and bm.http_status > 0 and not filters["status"].get("broken", True):
                continue
            if bm.http_status == 0 and not filters["status"].get("unchecked", True):
                continue
            
            # Attribute filters
            if filters["attributes"].get("pinned") and not bm.is_pinned:
                continue
            if filters["attributes"].get("archived") and not bm.is_archived:
                continue
            if filters["attributes"].get("has_notes") and not bm.notes:
                continue
            if filters["attributes"].get("has_tags") and not bm.tags:
                continue
            
            # AI Confidence
            if filters["min_confidence"] > 0 and bm.ai_confidence < filters["min_confidence"]:
                continue
            
            result.append(bm)
        
        return result
