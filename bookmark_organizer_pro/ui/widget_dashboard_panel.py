"""Embedded dashboard panel widgets."""

from __future__ import annotations

import tkinter as tk

from bookmark_organizer_pro.managers import BookmarkManager

from .foundation import FONTS
from .view_models import DashboardStatisticsViewModel, build_dashboard_statistics
from .widget_controls import ThemedWidget
from .widget_runtime import get_theme

# =============================================================================
# Analytics Dashboard
# =============================================================================
class DashboardPanel(tk.Frame, ThemedWidget):
    """
        Analytics dashboard panel.
        
        Displays bookmark statistics, charts, and insights.
        
        Sections:
            - Overview: Total counts, recent additions
            - Categories: Distribution chart
            - Tags: Tag cloud
            - Domains: Top domains
            - Timeline: Activity over time
            - Health: Broken links, duplicates
        
        Methods:
            refresh(): Update all statistics
            set_bookmarks(bookmarks): Update data source
        """
    
    def __init__(self, parent, bookmark_manager: BookmarkManager):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_primary)
        
        self.manager = bookmark_manager
        self.theme = theme
        
        self._build_ui()
    
    def _build_ui(self):
        """Build dashboard UI"""
        # Title
        title = tk.Label(
            self, text="Dashboard", bg=self.theme.bg_primary,
            fg=self.theme.text_primary, font=FONTS.title(bold=True)
        )
        title.pack(pady=(20, 15), padx=20, anchor="w")
        
        # Stats grid
        stats_frame = tk.Frame(self, bg=self.theme.bg_primary)
        stats_frame.pack(fill=tk.X, padx=20, pady=10)
        
        stats = self._load_statistics()

        if stats.is_degraded:
            tk.Label(
                self,
                text=stats.degraded_message,
                bg=self.theme.bg_primary,
                fg=self.theme.status_warning,
                font=FONTS.small(),
                anchor="w",
            ).pack(fill=tk.X, padx=20, pady=(0, 4))
        
        # Stat cards
        stat_cards = [
            ("All", "Total Bookmarks", stats.total_bookmarks),
            ("Cat", "Categories", stats.total_categories),
            ("Tag", "Tags Used", stats.total_tags),
            ("Pin", "Pinned", stats.pinned),
            ("New", "Uncategorized", stats.uncategorized),
            ("Dup", "Duplicates", stats.duplicate_bookmarks),
            ("Fix", "Broken Links", stats.broken),
            ("Old", "Stale (90+ days)", stats.stale),
        ]
        
        for i, (icon, label, value) in enumerate(stat_cards):
            card = self._create_stat_card(stats_frame, icon, label, value)
            row = i // 4
            col = i % 4
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
        
        for i in range(4):
            stats_frame.columnconfigure(i, weight=1)
        
        # Category distribution
        cat_frame = tk.LabelFrame(
            self, text="Category Distribution", bg=self.theme.bg_primary,
            fg=self.theme.text_primary, font=FONTS.body(bold=True)
        )
        cat_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        cat_counts = stats.category_counts
        sorted_cats = sorted(cat_counts.items(), key=lambda x: -x[1])[:10]
        
        for cat, count in sorted_cats:
            self._create_bar(cat_frame, cat, count, stats.total_bookmarks)
        
        # Top domains
        domain_frame = tk.LabelFrame(
            self, text="Top Domains", bg=self.theme.bg_primary,
            fg=self.theme.text_primary, font=FONTS.body(bold=True)
        )
        domain_frame.pack(fill=tk.X, padx=20, pady=(0, 20))
        
        for domain, count in stats.top_domains[:5]:
            row = tk.Frame(domain_frame, bg=self.theme.bg_primary)
            row.pack(fill=tk.X, padx=10, pady=3)
            
            tk.Label(
                row, text=domain, bg=self.theme.bg_primary,
                fg=self.theme.text_primary, font=FONTS.body(),
                anchor="w"
            ).pack(side=tk.LEFT)
            
            tk.Label(
                row, text=str(count), bg=self.theme.bg_primary,
                fg=self.theme.text_muted, font=FONTS.body()
            ).pack(side=tk.RIGHT)

    def _load_statistics(self) -> DashboardStatisticsViewModel:
        """Return a complete dashboard state even when statistics fail."""
        try:
            return build_dashboard_statistics(self.manager.get_statistics())
        except Exception:
            return build_dashboard_statistics(
                degraded_message=(
                    "Statistics are temporarily unavailable. Showing safe defaults."
                )
            )
    
    def _create_stat_card(self, parent, icon: str, label: str, value: int) -> tk.Frame:
        """Create a stat card widget"""
        card = tk.Frame(parent, bg=self.theme.bg_secondary, padx=15, pady=12)
        
        # Icon
        tk.Label(
            card, text=icon, bg=self.theme.bg_secondary,
            font=FONTS.title(bold=False)
        ).pack(anchor="w")
        
        # Value
        tk.Label(
            card, text=str(value), bg=self.theme.bg_secondary,
            fg=self.theme.text_primary, font=FONTS.hero(bold=True)
        ).pack(anchor="w")
        
        # Label
        tk.Label(
            card, text=label, bg=self.theme.bg_secondary,
            fg=self.theme.text_muted, font=FONTS.body()
        ).pack(anchor="w")
        
        return card
    
    def _create_bar(self, parent, label: str, value: int, total: int):
        """Create a horizontal bar chart item"""
        row = tk.Frame(parent, bg=self.theme.bg_primary)
        row.pack(fill=tk.X, padx=10, pady=4)
        
        # Label
        label_text = label[:25] + "..." if len(label) > 25 else label
        tk.Label(
            row, text=label_text, bg=self.theme.bg_primary,
            fg=self.theme.text_primary, font=FONTS.small(),
            width=25, anchor="w"
        ).pack(side=tk.LEFT)
        
        # Bar
        bar_frame = tk.Frame(row, bg=self.theme.bg_tertiary, height=16)
        bar_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        bar_frame.pack_propagate(False)
        
        pct = (value / total * 100) if total > 0 else 0
        bar = tk.Frame(bar_frame, bg=self.theme.accent_primary, height=16)
        bar.place(relwidth=min(1.0, value/total) if total > 0 else 0, relheight=1.0)
        
        # Count
        tk.Label(
            row, text=f"{value} ({pct:.1f}%)", bg=self.theme.bg_primary,
            fg=self.theme.text_muted, font=FONTS.small(), width=12
        ).pack(side=tk.RIGHT)
    
    def refresh(self):
        """Refresh dashboard data"""
        for widget in self.winfo_children():
            widget.destroy()
        self._build_ui()
