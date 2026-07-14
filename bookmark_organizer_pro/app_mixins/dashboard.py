"""Dashboard, summary, selection bar, and status UI for the app coordinator."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict

from bookmark_organizer_pro.constants import APP_VERSION
from bookmark_organizer_pro.i18n import _
from bookmark_organizer_pro.ui.foundation import FONTS, DesignTokens, format_compact_count, pluralize, truncate_middle
from bookmark_organizer_pro.ui.tk_interactions import make_keyboard_activatable, route_pointer_to_control
from bookmark_organizer_pro.ui.view_models import build_collection_pulse, build_collection_summary
from bookmark_organizer_pro.ui.components import EnhancedProgressBar, FaviconStatusDisplay
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
            left, text=_("Library Overview"), bg=theme.bg_card,
            fg=theme.text_primary, font=FONTS.header(bold=True), anchor="w"
        )
        self.summary_title_label.pack(anchor="w")

        self.summary_detail_label = tk.Label(
            left, text=_("Import bookmarks or add one manually to begin."),
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
        block.pack(side=tk.LEFT, padx=(8, 0))
        value_lbl = tk.Label(
            block, text="0", bg=theme.bg_card, fg=color,
            font=FONTS.title(bold=True), width=3, anchor="e"
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
            self.selection_bar, text=_("Open"),
            command=self._open_selected, padx=12, pady=6,
            tooltip=_("Open selected bookmarks in browser")
        ).pack(side=tk.RIGHT, padx=(4, 10), pady=6)
        ModernButton(
            self.selection_bar, text=_("Edit"),
            command=self._edit_selected, padx=12, pady=6,
            tooltip=_("Edit the selected bookmark")
        ).pack(side=tk.RIGHT, padx=4, pady=6)
        ModernButton(
            self.selection_bar, text=_("Organize"),
            command=self._organize_selected, padx=12, pady=6, style="primary",
            tooltip=_("Auto-categorize and tag selected bookmarks with the pattern engine")
        ).pack(side=tk.RIGHT, padx=4, pady=6)
        ModernButton(
            self.selection_bar, text=_("Clear Tags"),
            command=self._clear_all_tags, padx=12, pady=6,
            tooltip=_("Remove all tags from selected bookmarks")
        ).pack(side=tk.RIGHT, padx=4, pady=6)
        ModernButton(
            self.selection_bar, text=_("Pin"),
            command=self._toggle_pin, padx=12, pady=6,
            tooltip=_("Pin or unpin selected bookmarks")
        ).pack(side=tk.RIGHT, padx=4, pady=6)
        ModernButton(
            self.selection_bar, text=_("Delete"),
            command=self._delete_selected, style="danger", padx=12, pady=6,
            tooltip=_("Delete selected bookmarks")
        ).pack(side=tk.RIGHT, padx=4, pady=6)

    def _update_selection_bar(self):
        """Show or hide the contextual action bar based on selection."""
        if not getattr(self, 'selection_bar', None):
            return
        count = len(self.selected_bookmarks)
        if count:
            self.selection_count_label.configure(text=f"{pluralize(count, 'bookmark')} selected")
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
        """Create the compact collection pulse shown in the right rail."""
        theme = get_theme()

        header = tk.Frame(self.right_scroll.inner, bg=theme.bg_dark)
        header.pack(fill=tk.X)
        tk.Label(
            header, text=_("Collection pulse"), bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.subtitle(bold=True),
            padx=DesignTokens.PANEL_PAD, pady=14,
        ).pack(side=tk.LEFT)
        refresh_btn = tk.Label(
            header, text="↻", bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.subtitle(),
            cursor="hand2", padx=DesignTokens.SPACE_SM,
        )
        refresh_btn.pack(side=tk.RIGHT)
        make_keyboard_activatable(refresh_btn, self._refresh_analytics)
        Tooltip(refresh_btn, _("Refresh collection pulse"))

        self.collection_pulse_frame = tk.Frame(self.right_scroll.inner, bg=theme.bg_dark)
        self.collection_pulse_frame.pack(fill=tk.X, padx=DesignTokens.PANEL_PAD)

        # Kept as an unmounted compatibility surface for the legacy detailed
        # renderer; full analytics remain available from Tools > Analytics.
        self.analytics_frame = tk.Frame(self.right_scroll.inner, bg=theme.bg_secondary)

    def _refresh_collection_pulse(self, stats, all_bookmarks):
        """Render health, trustworthy zero-state metrics, and one next action."""
        theme = get_theme()
        frame = self.collection_pulse_frame
        for widget in frame.winfo_children():
            widget.destroy()

        pulse = build_collection_pulse(
            stats=stats,
            all_bookmarks=all_bookmarks,
            health_score=self._calculate_health_score(stats),
        )
        health_color = (
            theme.text_muted if pulse.metrics["total"] == 0
            else theme.accent_success if pulse.health_score >= 70
            else theme.accent_warning if pulse.health_score >= 40
            else theme.accent_error
        )

        card = tk.Frame(
            frame, bg=theme.bg_card,
            highlightbackground=theme.card_border, highlightthickness=1,
        )
        card.pack(fill=tk.X)
        summary = tk.Frame(card, bg=theme.bg_card)
        summary.pack(fill=tk.X, padx=12, pady=12)

        ring = tk.Canvas(
            summary, width=114, height=114, bg=theme.bg_card,
            highlightthickness=0, bd=0,
        )
        ring.pack(side=tk.LEFT, padx=(0, 10))
        ring.create_oval(13, 13, 101, 101, outline=theme.bg_tertiary, width=11)
        if pulse.health_score:
            ring.create_arc(
                13, 13, 101, 101, start=90,
                extent=-(pulse.health_score / 100) * 359.9,
                style=tk.ARC, outline=health_color, width=11,
            )
        ring.create_text(
            57, 49, text=f"{pulse.health_score}%",
            fill=health_color, font=FONTS.title(bold=True),
        )
        ring.create_text(
            57, 70, text=_(pulse.health_label),
            fill=theme.text_secondary, font=FONTS.tiny(),
        )

        legend = tk.Frame(summary, bg=theme.bg_card)
        legend.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=8)
        for label, value, color in (
            (_("Healthy"), pulse.healthy, theme.accent_success),
            (_("Needs review"), pulse.needs_review, theme.accent_warning),
            (_("Issues"), pulse.issues, theme.accent_error),
        ):
            row = tk.Frame(legend, bg=theme.bg_card)
            row.pack(fill=tk.X, pady=4)
            tk.Label(
                row, text="■", bg=theme.bg_card, fg=color,
                font=FONTS.tiny(),
            ).pack(side=tk.LEFT, padx=(0, 6))
            tk.Label(
                row, text=label, bg=theme.bg_card, fg=theme.text_secondary,
                font=FONTS.small(), anchor="w",
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)
            tk.Label(
                row, text=format_compact_count(value), bg=theme.bg_card,
                fg=theme.text_primary, font=FONTS.small(bold=True),
            ).pack(side=tk.RIGHT)

        metrics = tk.Frame(card, bg=theme.card_border)
        metrics.pack(fill=tk.X, pady=(0, 0))
        metric_specs = (
            ("total", _("Total bookmarks")),
            ("tagged", _("Tagged")),
            ("collections", _("Collections")),
            ("broken", _("Broken links")),
        )
        for index, (key, label) in enumerate(metric_specs):
            metrics.grid_columnconfigure(index % 2, weight=1, uniform="pulse-metrics")
            cell = tk.Frame(
                metrics, bg=theme.bg_card,
                highlightbackground=theme.card_border, highlightthickness=1,
            )
            cell.grid(row=index // 2, column=index % 2, sticky="nsew")
            tk.Label(
                cell, text=label, bg=theme.bg_card, fg=theme.text_muted,
                font=FONTS.tiny(), anchor="w",
            ).pack(fill=tk.X, padx=12, pady=(10, 2))
            tk.Label(
                cell, text=format_compact_count(pulse.metrics[key]),
                bg=theme.bg_card, fg=theme.text_primary,
                font=FONTS.subtitle(bold=True), anchor="w",
            ).pack(fill=tk.X, padx=12, pady=(0, 10))

        tk.Label(
            frame, text=_("Next best action"), bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.subtitle(bold=True),
        ).pack(anchor="w", pady=(18, 9))

        action_card = tk.Frame(
            frame, bg=theme.bg_card, cursor="hand2",
            highlightbackground=theme.card_border, highlightthickness=1,
        )
        action_card.pack(fill=tk.X)
        tk.Label(
            action_card, text="◎", bg=theme.bg_tertiary,
            fg=theme.accent_primary, font=FONTS.title(bold=True),
            width=3, pady=7,
        ).pack(side=tk.LEFT, padx=12, pady=12)
        action_copy = tk.Frame(action_card, bg=theme.bg_card)
        action_copy.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=12)
        tk.Label(
            action_copy, text=_(pulse.action_title), bg=theme.bg_card,
            fg=theme.text_primary, font=FONTS.small(bold=True), anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            action_copy, text=_(pulse.action_detail), bg=theme.bg_card,
            fg=theme.text_secondary, font=FONTS.tiny(),
            wraplength=210, justify=tk.LEFT, anchor="w",
        ).pack(fill=tk.X, pady=(3, 0))
        tk.Label(
            action_card, text="›", bg=theme.bg_card,
            fg=theme.text_secondary, font=FONTS.title(),
        ).pack(side=tk.RIGHT, padx=12)
        callback = lambda: self._run_pulse_action(pulse.action_key)
        make_keyboard_activatable(action_card, callback)

        action_children = []

        def bind_action(widget):
            widget.configure(cursor="hand2")
            action_children.append(widget)
            for child in widget.winfo_children():
                bind_action(child)

        for child in action_card.winfo_children():
            bind_action(child)
        route_pointer_to_control(action_card, *action_children)

        if pulse.metrics["total"]:
            ModernButton(
                frame, text=_("View detailed analytics"),
                command=self._show_analytics, padx=10, pady=6,
                tooltip=_("Open category, age, domain, and issue analytics"),
            ).pack(fill=tk.X, pady=(8, 0))

    def _run_pulse_action(self, action_key: str):
        actions = {
            "import": self._show_import_dialog,
            "broken": lambda: self._apply_filter("Broken"),
            "duplicates": self._find_duplicates,
            "snapshots": self._view_snapshot_failures,
            "untagged": lambda: self._apply_filter("Untagged"),
            "search": self._focus_search,
        }
        action = actions.get(action_key, self._focus_search)
        action()
    
    def _refresh_analytics(self):
        """Refresh analytics display with clear health and empty states."""
        theme = get_theme()

        stats = self.bookmark_manager.get_statistics()
        all_bookmarks = self.bookmark_manager.get_all_bookmarks()
        try:
            from bookmark_organizer_pro.services.snapshot import SnapshotFailureStore
            snapshot_failures = SnapshotFailureStore().list_failures()
        except Exception:
            snapshot_failures = []
        try:
            from bookmark_organizer_pro.services.job_ledger import JobLedger
            job_health = JobLedger().health()
        except Exception:
            job_health = {"jobs": 0, "failures": 0, "failure_rate": 0.0,
                          "retryable_failures": 0, "storage_growth_7d_bytes": 0}
        pulse_stats = dict(stats)
        pulse_stats["snapshot_failures"] = len(snapshot_failures)
        self._refresh_collection_pulse(pulse_stats, all_bookmarks)

        analytics_signature = (
            stats,
            len(snapshot_failures),
            sum(1 for record in snapshot_failures if record.retry_eligible),
            job_health.get("jobs", 0),
            job_health.get("failures", 0),
        )
        if hasattr(self, '_last_analytics_stats') and self._last_analytics_stats == analytics_signature:
            return
        self._last_analytics_stats = analytics_signature

        for widget in self.analytics_frame.winfo_children():
            widget.destroy()
        total = stats.get('total_bookmarks', 0)
        
        # Health Score
        health = self._calculate_health_score(stats)
        if total == 0:
            health_color = theme.text_muted
            health_label = "Ready"
            health_value = "Ready"
        else:
            health_color = theme.accent_success if health >= 70 else (theme.accent_warning if health >= 40 else theme.accent_error)
            health_label = "Excellent" if health >= 85 else ("Healthy" if health >= 70 else ("Needs Review" if health >= 40 else "At Risk"))
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
            health_header, text=_("Collection Health"), bg=theme.bg_card,
            fg=theme.text_secondary, font=FONTS.small()
        ).pack(side=tk.LEFT)

        tk.Label(
            health_header, text=health_label, bg=theme.bg_card,
            fg=health_color, font=FONTS.small(bold=True)
        ).pack(side=tk.RIGHT)
        
        tk.Label(
            health_card, text=health_value, bg=theme.bg_card,
            fg=health_color, font=FONTS.hero(bold=True)
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
            summary = "Review " + ", ".join(issue_parts) + " signals."
        else:
            summary = "No major collection issues detected."

        tk.Label(
            health_card, text=summary, bg=theme.bg_card,
            fg=theme.text_secondary, font=FONTS.small(),
            wraplength=235, justify=tk.LEFT
        ).pack(anchor="w")
        
        # Quick stats grid - streamlined (removed With Notes, Pinned, With Tags)
        section_label(_("Overview"), top_pad=6)
        
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
        section_label(_("Top Categories"))
        
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
                widget.bind("<Enter>", lambda e, lbl=cat_lbl: lbl.configure(fg=theme.accent_success))
                widget.bind("<Leave>", lambda e, lbl=cat_lbl: lbl.configure(fg=theme.accent_primary))
            route_pointer_to_control(cat_frame, top, cat_lbl)
        
        # Recent bookmarks (clickable)
        section_label(_("Recent Saves"))
        recent = sorted(all_bookmarks, key=lambda b: b.created_at or "", reverse=True)[:8]
        if not recent:
            empty_note("Bookmarks will appear here as you add them.")
        for bm in recent:
            row = tk.Frame(self.analytics_frame, bg=theme.bg_secondary, cursor="hand2")
            row.pack(fill=tk.X, pady=2)
            title_lbl = tk.Label(
                row, text=truncate_middle(bm.title or bm.url, 32), bg=theme.bg_secondary,
                fg=theme.text_primary, font=FONTS.small(), cursor="hand2", anchor="w",
            )
            title_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            make_keyboard_activatable(row, lambda bid=bm.id: self._select_bookmark_by_id(bid))
            route_pointer_to_control(row, title_lbl)

        # Pinned bookmarks
        pinned = [b for b in all_bookmarks if b.is_pinned]
        if pinned:
            section_label(f"Pinned ({len(pinned)})")
            for bm in pinned[:8]:
                row = tk.Frame(self.analytics_frame, bg=theme.bg_secondary, cursor="hand2")
                row.pack(fill=tk.X, pady=2)
                title_lbl = tk.Label(
                    row, text=truncate_middle(bm.title or bm.url, 32), bg=theme.bg_secondary,
                    fg=theme.accent_warning, font=FONTS.small(), cursor="hand2", anchor="w",
                )
                title_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
                make_keyboard_activatable(row, lambda bid=bm.id: self._select_bookmark_by_id(bid))
                route_pointer_to_control(row, title_lbl)

        # Read Later queue
        read_later = sorted(
            [b for b in all_bookmarks if b.read_later],
            key=lambda b: b.read_later_position,
        )
        if read_later:
            section_label(f"Read Later ({len(read_later)})")
            for bm in read_later[:6]:
                row = tk.Frame(self.analytics_frame, bg=theme.bg_secondary, cursor="hand2")
                row.pack(fill=tk.X, pady=2)
                title_lbl = tk.Label(
                    row, text=truncate_middle(bm.title or bm.url, 32), bg=theme.bg_secondary,
                    fg=theme.accent_primary, font=FONTS.small(), cursor="hand2", anchor="w",
                )
                title_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
                make_keyboard_activatable(row, lambda bid=bm.id: self._select_bookmark_by_id(bid))
                route_pointer_to_control(row, title_lbl)

        # Dead links badge
        dead_count = stats.get("broken", 0)
        if dead_count > 0:
            section_label(f"Dead Links ({dead_count})")
            dead_row = tk.Frame(self.analytics_frame, bg=theme.bg_secondary, cursor="hand2")
            dead_row.pack(fill=tk.X, pady=2)
            dead_lbl = tk.Label(
                dead_row, text=f"Review {dead_count} broken link(s)", bg=theme.bg_secondary,
                fg=theme.accent_error, font=FONTS.small(bold=True), cursor="hand2",
            )
            dead_lbl.pack(side=tk.LEFT)
            make_keyboard_activatable(dead_row, lambda: self._apply_filter("Broken"))
            route_pointer_to_control(dead_row, dead_lbl)

        # Snapshot failures badge
        if snapshot_failures and hasattr(self, "_view_snapshot_failures"):
            retryable = sum(1 for record in snapshot_failures if record.retry_eligible)
            section_label(f"Snapshot Failures ({len(snapshot_failures)})")
            snap_row = tk.Frame(self.analytics_frame, bg=theme.bg_secondary, cursor="hand2")
            snap_row.pack(fill=tk.X, pady=2)
            snap_lbl = tk.Label(
                snap_row,
                text=f"Review {retryable} retryable failure(s)",
                bg=theme.bg_secondary,
                fg=theme.accent_warning,
                font=FONTS.small(bold=True),
                cursor="hand2",
            )
            snap_lbl.pack(side=tk.LEFT)
            make_keyboard_activatable(snap_row, self._view_snapshot_failures)
            route_pointer_to_control(snap_row, snap_lbl)

        if job_health.get("jobs"):
            section_label(_("Local Job Health"))
            failures = int(job_health.get("failures", 0))
            rate = float(job_health.get("failure_rate", 0.0))
            retryable = int(job_health.get("retryable_failures", 0))
            growth = int(job_health.get("storage_growth_7d_bytes", 0))
            health_text = (
                f"{job_health['jobs']} completed · {failures} failed ({rate:.0%})\n"
                f"{retryable} retryable · {growth / 1024:.1f} KB processed in 7 days"
            )
            tk.Label(
                self.analytics_frame, text=health_text, bg=theme.bg_secondary,
                fg=theme.accent_error if failures else theme.accent_success,
                font=FONTS.small(), justify=tk.LEFT, wraplength=235,
            ).pack(anchor="w", pady=(1, 8))

        # Daily digest — rediscover forgotten bookmarks
        try:
            from bookmark_organizer_pro.services.digest import DailyDigestService
            digest_svc = DailyDigestService()
            digest = digest_svc.build(all_bookmarks, rediscover_count=4, read_later_count=0)
            for sec in digest.sections:
                if not sec.bookmarks:
                    continue
                section_label(sec.title)
                for bm in sec.bookmarks[:4]:
                    row = tk.Frame(self.analytics_frame, bg=theme.bg_secondary, cursor="hand2")
                    row.pack(fill=tk.X, pady=2)
                    title_lbl = tk.Label(
                        row, text=truncate_middle(bm.title or bm.url, 32), bg=theme.bg_secondary,
                        fg=theme.accent_primary, font=FONTS.small(), cursor="hand2", anchor="w",
                    )
                    title_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
                    make_keyboard_activatable(row, lambda bid=bm.id: self._select_bookmark_by_id(bid))
                    route_pointer_to_control(row, title_lbl)
        except Exception:
            pass

        # Spaced repetition — highlights due for review
        try:
            from bookmark_organizer_pro.services.reader_annotations import ReaderAnnotationStore
            sr_store = ReaderAnnotationStore()
            due_highlights = sr_store.due_for_review()
            if due_highlights:
                section_label(_("Highlights Due") + f" ({len(due_highlights)})")
                for hl in due_highlights[:5]:
                    preview = (hl.text or "")[:50].replace("\n", " ")
                    row = tk.Frame(self.analytics_frame, bg=theme.bg_secondary, cursor="hand2")
                    row.pack(fill=tk.X, pady=2)
                    hl_lbl = tk.Label(
                        row, text=truncate_middle(preview, 32), bg=theme.bg_secondary,
                        fg=theme.accent_warning, font=FONTS.small(), cursor="hand2", anchor="w",
                    )
                    hl_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
                    day_label = f"{hl.sr_interval}d" if hl.sr_interval else _("new")
                    tk.Label(
                        row, text=day_label, bg=theme.bg_secondary,
                        fg=theme.text_muted, font=FONTS.small(),
                    ).pack(side=tk.RIGHT)
                    make_keyboard_activatable(row, lambda bid=hl.bookmark_id: self._select_bookmark_by_id(bid))
                    route_pointer_to_control(row, hl_lbl)
        except Exception:
            pass

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
                widget.bind("<Enter>", lambda e, lbl=domain_lbl: lbl.configure(fg=theme.accent_success))
                widget.bind("<Leave>", lambda e, lbl=domain_lbl: lbl.configure(fg=theme.accent_primary))
            route_pointer_to_control(row, domain_lbl)
    
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
            left_frame, text=_("✓ Library ready"), bg=theme.bg_dark,
            fg=theme.text_secondary, font=FONTS.small()
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
