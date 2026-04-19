"""Dashboard, summary, selection bar, and status UI for the app coordinator."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict

from bookmark_organizer_pro.constants import APP_VERSION
from bookmark_organizer_pro.ui.foundation import FONTS, DesignTokens, format_compact_count, pluralize, truncate_middle
from bookmark_organizer_pro.ui.tk_interactions import make_keyboard_activatable
from bookmark_organizer_pro.ui.view_models import build_collection_summary
from bookmark_organizer_pro.ui.widgets import ModernButton, Tooltip, get_theme


class DashboardActionsMixin:
    """Collection summary, right-side analytics, selection bar, and status widgets."""

    def _create_collection_summary(self):
        """Create the premium summary strip above the bookmark list."""
        theme = get_theme()
        self.collection_summary_frame = tk.Frame(
            self.content_area, bg=theme.bg_card, height=DesignTokens.SUMMARY_STRIP_HEIGHT,
            highlightbackground=theme.card_border, highlightthickness=1
        )
        self.collection_summary_frame.pack(
            fill=tk.X, padx=DesignTokens.CONTENT_PAD_X, pady=(0, 12)
        )
        self.collection_summary_frame.pack_propagate(False)

        left = tk.Frame(self.collection_summary_frame, bg=theme.bg_card)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(18, 10), pady=14)

        self.summary_title_label = tk.Label(
            left, text="Library Overview", bg=theme.bg_card,
            fg=theme.text_primary, font=FONTS.header(bold=True), anchor="w"
        )
        self.summary_title_label.pack(anchor="w")

        self.summary_detail_label = tk.Label(
            left, text="Import bookmarks or add one manually to begin.",
            bg=theme.bg_card, fg=theme.text_secondary,
            font=FONTS.small(), anchor="w", wraplength=520, justify=tk.LEFT
        )
        self.summary_detail_label.pack(anchor="w", pady=(5, 0))

        metrics = tk.Frame(self.collection_summary_frame, bg=theme.bg_card)
        metrics.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 18), pady=12)
        self.summary_metric_labels = {}
        for key, label, color in [
            ("visible", "Visible", theme.text_primary),
            ("pinned", "Pinned", theme.accent_primary),
            ("broken", "Review", theme.accent_error),
            ("untagged", "Untagged", theme.accent_warning),
        ]:
            self._create_summary_metric(metrics, key, label, color)

    def _create_summary_metric(self, parent, key: str, label: str, color: str):
        """Create one compact metric in the summary strip."""
        theme = get_theme()
        block = tk.Frame(parent, bg=theme.bg_card)
        block.pack(side=tk.LEFT, padx=(14, 0))
        value_lbl = tk.Label(
            block, text="0", bg=theme.bg_card, fg=color,
            font=FONTS.custom(18, bold=True), width=5, anchor="e"
        )
        value_lbl.pack(anchor="e")
        label_lbl = tk.Label(
            block, text=label, bg=theme.bg_card, fg=theme.text_muted,
            font=FONTS.tiny(bold=True), anchor="e"
        )
        label_lbl.pack(anchor="e", pady=(2, 0))
        self.summary_metric_labels[key] = (value_lbl, label_lbl)

    def _refresh_collection_summary(self, visible_count: int, total_count: int, query: str, quick_filter: str):
        """Refresh the summary strip with current view and collection signals."""
        if not getattr(self, 'collection_summary_frame', None):
            return
        all_bookmarks = self.bookmark_manager.get_all_bookmarks()
        summary = build_collection_summary(
            visible_count=visible_count,
            total_count=total_count,
            stats=self.bookmark_manager.get_statistics(),
            all_bookmarks=all_bookmarks,
            query=query,
            quick_filter=quick_filter,
            current_category=self.current_category,
        )
        for key, value in summary.metrics.items():
            labels = self.summary_metric_labels.get(key)
            if labels:
                labels[0].configure(text=format_compact_count(value))

        self.summary_title_label.configure(text=summary.title)
        self.summary_detail_label.configure(text=summary.detail)

    def _set_collection_summary_visible(self, visible: bool):
        """Keep the empty-library state uncluttered while preserving list context."""
        frame = getattr(self, 'collection_summary_frame', None)
        if not frame:
            return
        if visible:
            if frame.winfo_ismapped():
                return
            pack_options = {
                "fill": tk.X,
                "padx": DesignTokens.CONTENT_PAD_X,
                "pady": (0, 12),
            }
            try:
                if getattr(self, 'list_frame', None):
                    frame.pack(**pack_options, before=self.list_frame)
                else:
                    frame.pack(**pack_options)
            except tk.TclError:
                frame.pack(**pack_options)
        else:
            frame.pack_forget()

    def _create_selection_bar(self):
        """Create the contextual action bar shown when rows are selected."""
        theme = get_theme()
        self.selection_bar = tk.Frame(
            self.content_area, bg=theme.bg_tertiary,
            highlightbackground=theme.border_muted, highlightthickness=1
        )

        self.selection_count_label = tk.Label(
            self.selection_bar, text="", bg=theme.bg_tertiary,
            fg=theme.text_primary, font=FONTS.small(bold=True)
        )
        self.selection_count_label.pack(side=tk.LEFT, padx=(14, 10), pady=8)

        ModernButton(
            self.selection_bar, text="Open", icon="🔗",
            command=self._open_selected, padx=12, pady=6
        ).pack(side=tk.RIGHT, padx=(4, 10), pady=6)
        ModernButton(
            self.selection_bar, text="Edit", icon="✏️",
            command=self._edit_selected, padx=12, pady=6
        ).pack(side=tk.RIGHT, padx=4, pady=6)
        ModernButton(
            self.selection_bar, text="Pin", icon="★",
            command=self._toggle_pin, padx=12, pady=6
        ).pack(side=tk.RIGHT, padx=4, pady=6)
        ModernButton(
            self.selection_bar, text="Delete", icon="🗑️",
            command=self._delete_selected, style="danger", padx=12, pady=6
        ).pack(side=tk.RIGHT, padx=4, pady=6)

    def _update_selection_bar(self):
        """Show or hide the contextual action bar based on selection."""
        if not getattr(self, 'selection_bar', None):
            return
        count = len(self.selected_bookmarks)
        if count:
            self.selection_count_label.configure(text=f"{pluralize(count, 'bookmark')} Selected")
            if not self.selection_bar.winfo_ismapped():
                self.selection_bar.pack(
                    fill=tk.X,
                    padx=DesignTokens.CONTENT_PAD_X,
                    pady=(0, 8),
                    before=self.list_frame
                )
        else:
            self.selection_bar.pack_forget()

    def _create_analytics_panel(self):
        """Create analytics panel in right sidebar"""
        theme = get_theme()
        
        # Header
        header = tk.Frame(self.right_scroll.inner, bg=theme.bg_secondary)
        header.pack(fill=tk.X)
        
        tk.Label(
            header, text="Signals", bg=theme.bg_secondary,
            fg=theme.text_primary, font=("Segoe UI", 11, "bold"),
            padx=15, pady=12
        ).pack(side=tk.LEFT)
        
        refresh_btn = tk.Label(
            header, text="↻", bg=theme.bg_secondary,
            fg=theme.text_muted, font=("Segoe UI", 14),
            cursor="hand2", padx=15
        )
        refresh_btn.pack(side=tk.RIGHT)
        make_keyboard_activatable(refresh_btn, self._refresh_analytics)
        Tooltip(refresh_btn, "Refresh Signals")
        
        # Stats container
        self.analytics_frame = tk.Frame(self.right_scroll.inner, bg=theme.bg_secondary)
        self.analytics_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
    
    def _refresh_analytics(self):
        """Refresh analytics display with clear health and empty states."""
        theme = get_theme()
        
        # Clear existing
        for widget in self.analytics_frame.winfo_children():
            widget.destroy()
        
        stats = self.bookmark_manager.get_statistics()
        total = stats.get('total_bookmarks', 0)
        
        # Health Score
        health = self._calculate_health_score(stats)
        if total == 0:
            health_color = theme.text_muted
            health_label = "Not Started"
            health_value = "Ready"
        else:
            health_color = theme.accent_success if health >= 70 else (theme.accent_warning if health >= 40 else theme.accent_error)
            health_label = "Excellent" if health >= 85 else ("Healthy" if health >= 70 else ("Needs review" if health >= 40 else "At risk"))
            health_value = f"{health}%"

        def section_label(text: str, top_pad: int = 14):
            tk.Label(
                self.analytics_frame, text=text, bg=theme.bg_secondary,
                fg=theme.text_muted, font=FONTS.tiny(bold=True)
            ).pack(anchor="w", pady=(top_pad, 6))

        def empty_note(text: str):
            tk.Label(
                self.analytics_frame, text=text, bg=theme.bg_secondary,
                fg=theme.text_secondary, font=FONTS.small(),
                wraplength=235, justify=tk.LEFT
            ).pack(anchor="w", pady=(2, 8))
        
        # Health card
        health_card = tk.Frame(
            self.analytics_frame, bg=theme.bg_card,
            padx=16, pady=14,
            highlightbackground=theme.card_border, highlightthickness=1
        )
        health_card.pack(fill=tk.X, pady=(0, 12))

        health_header = tk.Frame(health_card, bg=theme.bg_card)
        health_header.pack(fill=tk.X)
        
        tk.Label(
            health_header, text="Collection Health", bg=theme.bg_card,
            fg=theme.text_secondary, font=FONTS.small()
        ).pack(side=tk.LEFT)

        tk.Label(
            health_header, text=health_label, bg=theme.bg_card,
            fg=health_color, font=FONTS.small(bold=True)
        ).pack(side=tk.RIGHT)
        
        tk.Label(
            health_card, text=health_value, bg=theme.bg_card,
            fg=health_color, font=FONTS.custom(26, bold=True)
        ).pack(anchor="w", pady=(4, 4))
        
        # Health bar
        bar_bg = tk.Frame(health_card, bg=theme.bg_primary, height=6)
        bar_bg.pack(fill=tk.X, pady=(0, 6))
        bar_fill = tk.Frame(bar_bg, bg=health_color, height=6)
        bar_fill.place(x=0, y=0, relheight=1.0, relwidth=0 if total == 0 else health/100)

        issue_parts = []
        if stats.get('broken', 0):
            issue_parts.append(f"{stats['broken']} broken")
        if stats.get('uncategorized', 0):
            issue_parts.append(f"{stats['uncategorized']} uncategorized")
        if stats.get('duplicate_bookmarks', 0):
            issue_parts.append(f"{stats['duplicate_bookmarks']} duplicate")

        if total == 0:
            summary = "Import or add bookmarks to start measuring collection quality."
        elif issue_parts:
            summary = "Review " + ", ".join(issue_parts) + " bookmark signals."
        else:
            summary = "No major collection issues detected."

        tk.Label(
            health_card, text=summary, bg=theme.bg_card,
            fg=theme.text_secondary, font=FONTS.small(),
            wraplength=235, justify=tk.LEFT
        ).pack(anchor="w")
        
        # Quick stats grid - streamlined (removed With Notes, Pinned, With Tags)
        section_label("Overview", top_pad=6)
        
        active_category_count = (
            sum(1 for count in stats.get('category_counts', {}).values() if count > 0)
            if total > 0 else 0
        )
        stats_data = [
            ("Bookmarks", total, theme.text_primary),
            ("Categories", active_category_count, theme.accent_primary),
            ("Unique tags", stats.get('total_tags', 0), theme.accent_purple),
            ("Broken links", stats.get('broken', 0), theme.accent_error),
            ("Uncategorized", stats.get('uncategorized', 0), theme.accent_warning),
        ]
        
        for label, value, color in stats_data:
            row = tk.Frame(self.analytics_frame, bg=theme.bg_secondary)
            row.pack(fill=tk.X, pady=3)
            
            tk.Label(
                row, text=label, bg=theme.bg_secondary,
                fg=theme.text_secondary, font=FONTS.small()
            ).pack(side=tk.LEFT)
            
            tk.Label(
                row, text=format_compact_count(value), bg=theme.bg_secondary,
                fg=color, font=FONTS.small(bold=True)
            ).pack(side=tk.RIGHT)
        
        # Top categories (compact) - clickable like domains
        section_label("Top Categories")
        
        sorted_cats = [
            item for item in sorted(
                stats.get('category_counts', {}).items(),
                key=lambda x: -x[1]
            )
            if item[1] > 0
        ][:5]
        max_count = max(sorted_cats[0][1], 1) if sorted_cats else 1
        
        if not sorted_cats:
            empty_note("Categories will appear here once bookmarks are imported.")

        for cat, count in sorted_cats:
            cat_frame = tk.Frame(self.analytics_frame, bg=theme.bg_secondary, cursor="hand2")
            cat_frame.pack(fill=tk.X, pady=3)

            top = tk.Frame(cat_frame, bg=theme.bg_secondary)
            top.pack(fill=tk.X)
            
            cat_lbl = tk.Label(
                top, text=truncate_middle(cat, 30), bg=theme.bg_secondary,
                fg=theme.accent_primary, font=FONTS.small(),
                cursor="hand2", anchor="w"
            )
            cat_lbl.pack(side=tk.LEFT)
            
            tk.Label(
                top, text=format_compact_count(count), bg=theme.bg_secondary,
                fg=theme.text_secondary, font=FONTS.small(bold=True)
            ).pack(side=tk.RIGHT)

            bar = tk.Frame(cat_frame, bg=theme.bg_tertiary, height=3)
            bar.pack(fill=tk.X, pady=(3, 0))
            fill = tk.Frame(bar, bg=theme.accent_primary, height=3)
            fill.place(x=0, y=0, relheight=1.0, relwidth=max(0.05, count / max_count))
            
            # Bind click to select category (like clicking in left panel)
            make_keyboard_activatable(cat_frame, lambda c=cat: self._select_category(c))
            for widget in [top, cat_lbl]:
                widget.bind("<Button-1>", lambda e, c=cat: self._select_category(c))
                widget.bind("<Enter>", lambda e, lbl=cat_lbl: lbl.configure(fg=theme.accent_success))
                widget.bind("<Leave>", lambda e, lbl=cat_lbl: lbl.configure(fg=theme.accent_primary))
        
        # Top domains - show up to 20 (clickable for filtering)
        top_domains = [(d, c) for d, c in stats.get('top_domains', []) if c > 0]
        num_domains = min(20, len(top_domains)) if len(top_domains) >= 20 else len(top_domains)
        
        section_label(f"Top Domains ({num_domains})")
        
        # Create scrollable frame for domains if many
        domains_frame = tk.Frame(self.analytics_frame, bg=theme.bg_secondary)
        domains_frame.pack(fill=tk.X)

        if not top_domains:
            empty_note("Frequent domains will appear after bookmarks are added.")
        
        for domain, count in top_domains[:20]:
            row = tk.Frame(domains_frame, bg=theme.bg_secondary, cursor="hand2")
            row.pack(fill=tk.X, pady=2)
            
            domain_lbl = tk.Label(
                row, text=truncate_middle(domain, 28), bg=theme.bg_secondary,
                fg=theme.accent_primary, font=FONTS.small(),
                cursor="hand2"
            )
            domain_lbl.pack(side=tk.LEFT)
            
            tk.Label(
                row, text=format_compact_count(count), bg=theme.bg_secondary,
                fg=theme.text_secondary, font=FONTS.small()
            ).pack(side=tk.RIGHT)
            
            # Bind click to filter by domain
            make_keyboard_activatable(row, lambda d=domain: self._filter_by_domain(d))
            for widget in [domain_lbl]:
                widget.bind("<Button-1>", lambda e, d=domain: self._filter_by_domain(d))
                widget.bind("<Enter>", lambda e, lbl=domain_lbl: lbl.configure(fg=theme.accent_success))
                widget.bind("<Leave>", lambda e, lbl=domain_lbl: lbl.configure(fg=theme.accent_primary))
    
    def _calculate_health_score(self, stats: Dict) -> int:
        """Calculate collection health score"""
        if stats.get('total_bookmarks', 0) == 0:
            return 0
        score = 100
        total = stats['total_bookmarks'] or 1
        
        broken_pct = (stats['broken'] / total) * 100
        uncat_pct = (stats['uncategorized'] / total) * 100
        dupe_pct = (stats['duplicate_bookmarks'] / total) * 100
        
        score -= min(30, broken_pct * 3)
        score -= min(20, uncat_pct * 0.5)
        score -= min(15, dupe_pct * 2)
        
        tagged_pct = (stats['with_tags'] / total) * 100
        noted_pct = (stats['with_notes'] / total) * 100
        
        score += min(10, tagged_pct * 0.1)
        score += min(5, noted_pct * 0.1)
        
        return max(0, min(100, int(score)))
    
    def _create_status_bar(self):
        """Create enhanced status bar with counts and progress"""
        theme = get_theme()
        
        self.status_bar = tk.Frame(self.root, bg=theme.bg_dark, height=DesignTokens.STATUS_BAR_HEIGHT)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_bar.pack_propagate(False)
        
        # Left section: status message
        left_frame = tk.Frame(self.status_bar, bg=theme.bg_dark)
        left_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        self.status_label = tk.Label(
            left_frame, text="Ready", bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.small()
        )
        self.status_label.pack(side=tk.LEFT, padx=DesignTokens.SPACE_MD, pady=DesignTokens.SPACE_SM)
        
        # Progress indicator (hidden by default)
        self.status_progress = ttk.Progressbar(
            left_frame, mode="indeterminate", length=80
        )
        
        # Favicon progress
        self.favicon_status = FaviconStatusDisplay(self.status_bar)
        
        # Progress bar for long operations
        self.main_progress = EnhancedProgressBar(
            self.status_bar, height=32, show_label=True, show_percentage=True
        )
        
        # Right section: counts and version
        right_frame = tk.Frame(self.status_bar, bg=theme.bg_dark)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Separator
        sep = tk.Frame(right_frame, bg=theme.border, width=1)
        sep.pack(side=tk.LEFT, fill=tk.Y, padx=DesignTokens.SPACE_SM, pady=DesignTokens.SPACE_SM)
        
        # Selected count
        self.status_selected_label = tk.Label(
            right_frame, text="", bg=theme.bg_dark,
            fg=theme.accent_primary, font=FONTS.small()
        )
        self.status_selected_label.pack(side=tk.LEFT, padx=DesignTokens.SPACE_SM)
        
        # Total count
        self.status_total_label = tk.Label(
            right_frame, text="0 items", bg=theme.bg_dark,
            fg=theme.text_secondary, font=FONTS.small()
        )
        self.status_total_label.pack(side=tk.LEFT, padx=DesignTokens.SPACE_SM)
        
        # Separator
        sep2 = tk.Frame(right_frame, bg=theme.border, width=1)
        sep2.pack(side=tk.LEFT, fill=tk.Y, padx=DesignTokens.SPACE_SM, pady=DesignTokens.SPACE_SM)
        
        # Version
        tk.Label(
            right_frame, text=f"v{APP_VERSION}", bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.tiny()
        ).pack(side=tk.LEFT, padx=DesignTokens.SPACE_MD)

