"""Analytics dashboard dialog widgets."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Dict

from .foundation import FONTS, truncate_middle
from .widget_controls import ModernButton, ThemedWidget
from .widget_runtime import apply_window_chrome, get_theme

# =============================================================================
# Analytics Dashboard Dialog
# =============================================================================
class AnalyticsDashboard(tk.Toplevel, ThemedWidget):
    """Dashboard showing bookmark analytics and statistics"""
    
    def __init__(self, parent, stats: Dict[str, Any]):
        super().__init__(parent)
        if hasattr(stats, "get_statistics"):
            stats = stats.get_statistics()
        self.stats = stats
        theme = get_theme()
        
        self.title("Analytics")
        self.geometry("800x650")
        self.configure(bg=theme.bg_primary)
        self.transient(parent)
        
        apply_window_chrome(self)
        
        # Header
        header = tk.Frame(self, bg=theme.bg_dark, height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(
            header, text="Collection Analytics", bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.title(bold=True)
        ).pack(side=tk.LEFT, padx=20, pady=15)
        
        # Stats summary cards
        cards_frame = tk.Frame(self, bg=theme.bg_primary)
        cards_frame.pack(fill=tk.X, padx=20, pady=15)
        
        active_categories = (
            sum(1 for count in stats.get("category_counts", {}).values() if count > 0)
            if stats["total_bookmarks"] > 0 else 0
        )
        self._create_stat_card(cards_frame, "Bookmarks", str(stats["total_bookmarks"]), "", 0)
        self._create_stat_card(cards_frame, "Categories", str(active_categories), "", 1)
        self._create_stat_card(cards_frame, "Tags", str(stats["total_tags"]), "", 2)
        self._create_stat_card(cards_frame, "Duplicates", str(stats["duplicate_bookmarks"]), "", 3)
        
        for i in range(4):
            cards_frame.columnconfigure(i, weight=1)
        
        # Main content with scrollable area
        main_frame = tk.Frame(self, bg=theme.bg_primary)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20)
        
        # Create canvas for scrolling
        canvas = tk.Canvas(main_frame, bg=theme.bg_primary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        content = tk.Frame(canvas, bg=theme.bg_primary)
        
        content.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=content, anchor="nw", width=760)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Health Score
        health_frame = tk.Frame(content, bg=theme.bg_secondary)
        health_frame.pack(fill=tk.X, pady=(0, 15))
        
        health_score = self._calculate_health_score()
        if stats["total_bookmarks"] == 0:
            health_color = theme.text_muted
            health_label = "Ready"
            health_state = "Not Started"
            health_width = 0
        else:
            health_color = (theme.accent_success if health_score >= 80
                           else theme.accent_warning if health_score >= 50
                           else theme.accent_error)
            health_label = f"{health_score}%"
            health_state = "Excellent" if health_score >= 85 else ("Healthy" if health_score >= 70 else "Needs Review")
            health_width = health_score / 100
        
        tk.Label(
            health_frame, text=f"Collection Health · {health_state}", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.body()
        ).pack(anchor="w", padx=15, pady=(10, 5))
        
        score_frame = tk.Frame(health_frame, bg=theme.bg_secondary)
        score_frame.pack(fill=tk.X, padx=15, pady=(0, 10))
        
        tk.Label(
            score_frame, text=health_label, bg=theme.bg_secondary,
            fg=health_color, font=("Segoe UI", 28, "bold")
        ).pack(side=tk.LEFT)
        
        # Progress bar
        bar_frame = tk.Frame(score_frame, bg=theme.bg_tertiary, height=10)
        bar_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=20)
        
        bar_fill = tk.Frame(bar_frame, bg=health_color, height=10)
        bar_fill.place(relwidth=health_width, relheight=1)
        
        # Category Distribution
        self._create_section(content, "Top Categories", self._get_category_chart())
        
        # Age Distribution
        self._create_section(content, "Bookmark Age Distribution", self._get_age_chart())
        
        # Top Domains
        self._create_section(content, "Top Domains", self._get_domains_list())
        
        # Issues section
        issues = self._get_issues()
        if issues:
            self._create_section(content, "Issues to Address", issues)
        
        # Close button
        btn_frame = tk.Frame(self, bg=theme.bg_primary)
        btn_frame.pack(fill=tk.X, padx=20, pady=15)
        
        ModernButton(
            btn_frame, text="Close", command=self.destroy
        ).pack(side=tk.RIGHT)
        
        self.center_window()
    
    def _create_stat_card(self, parent, title: str, value: str, icon: str, col: int):
        """Create a stat card"""
        theme = get_theme()
        
        card = tk.Frame(parent, bg=theme.bg_secondary)
        card.grid(row=0, column=col, padx=5, pady=5, sticky="nsew")
        
        if icon:
            tk.Label(
                card, text=icon, bg=theme.bg_secondary,
                fg=theme.accent_primary, font=("Segoe UI", 20)
            ).pack(pady=(15, 5))
        
        tk.Label(
            card, text=value, bg=theme.bg_secondary,
            fg=theme.text_primary, font=("Segoe UI", 24, "bold")
        ).pack(pady=(16 if not icon else 0, 0))
        
        tk.Label(
            card, text=title, bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.small()
        ).pack(pady=(0, 15))
    
    def _create_section(self, parent, title: str, content_text: str):
        """Create a section with title and content"""
        theme = get_theme()
        
        frame = tk.Frame(parent, bg=theme.bg_secondary)
        frame.pack(fill=tk.X, pady=(0, 15))
        
        tk.Label(
            frame, text=title, bg=theme.bg_secondary,
            fg=theme.text_primary, font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", padx=15, pady=(10, 5))
        
        tk.Label(
            frame, text=content_text, bg=theme.bg_secondary,
            fg=theme.text_secondary, font=("Consolas", 9),
            justify=tk.LEFT
        ).pack(anchor="w", padx=15, pady=(0, 10))
    
    def _calculate_health_score(self) -> int:
        """Calculate collection health score"""
        total = self.stats["total_bookmarks"]
        if total == 0:
            return 0
        
        score = 100
        
        # Penalize for uncategorized
        uncategorized_pct = (self.stats["uncategorized"] / total) * 100
        score -= min(30, uncategorized_pct)
        
        # Penalize for duplicates
        duplicate_pct = (self.stats["duplicate_bookmarks"] / total) * 100
        score -= min(20, duplicate_pct * 2)
        
        # Penalize for broken links
        broken_pct = (self.stats["broken"] / total) * 100
        score -= min(20, broken_pct * 3)
        
        # Penalize for stale bookmarks
        stale_pct = (self.stats["stale"] / total) * 100
        score -= min(15, stale_pct / 3)
        
        # Bonus for organized (has tags, notes)
        organized_pct = ((self.stats["with_tags"] + self.stats["with_notes"]) / (total * 2)) * 100
        score += min(15, organized_pct / 5)
        
        return max(0, min(100, int(score)))
    
    def _get_category_chart(self) -> str:
        """Get text-based category chart"""
        counts = self.stats["category_counts"]
        total = self.stats["total_bookmarks"]
        
        if not counts or total == 0:
            return "Import or add bookmarks to populate category signals."
        
        # Sort and take top 8
        sorted_cats = [item for item in sorted(counts.items(), key=lambda x: -x[1]) if item[1] > 0][:8]
        if not sorted_cats:
            return "No active categories yet."

        lines = []
        for cat, count in sorted_cats:
            pct = (count / total) * 100
            name = truncate_middle(cat, 30)
            lines.append(f"{name:<34} {count:>4}  {pct:>5.1f}%")
        
        return "\n".join(lines)
    
    def _get_age_chart(self) -> str:
        """Get text-based age distribution"""
        age_dist = self.stats["age_distribution"]
        total = self.stats["total_bookmarks"]
        
        if total == 0:
            return "Import or add bookmarks to populate age distribution."
        
        lines = []
        for period, count in age_dist.items():
            pct = (count / total) * 100
            lines.append(f"{period:<16} {count:>4}  {pct:>5.1f}%")
        
        return "\n".join(lines)
    
    def _get_domains_list(self) -> str:
        """Get top domains list"""
        domains = self.stats["top_domains"][:10]
        
        if not domains:
            return "Import or add bookmarks to populate domain signals."
        
        lines = []
        for domain, count in domains:
            lines.append(f"  {domain:35} {count:4}")
        
        return "\n".join(lines)
    
    def _get_issues(self) -> str:
        """Get issues to address"""
        issues = []
        
        if self.stats["uncategorized"] > 0:
            issues.append(f"• {self.stats['uncategorized']} uncategorized bookmarks")
        
        if self.stats["duplicate_bookmarks"] > 0:
            issues.append(f"• {self.stats['duplicate_bookmarks']} duplicate bookmarks in {self.stats['duplicate_groups']} groups")
        
        if self.stats["broken"] > 0:
            issues.append(f"• {self.stats['broken']} broken links")
        
        if self.stats["stale"] > 0:
            issues.append(f"• {self.stats['stale']} stale bookmarks (not visited in 90+ days)")
        
        return "\n".join(issues) if issues else ""
    
    def center_window(self):
        """Center the dialog"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')
