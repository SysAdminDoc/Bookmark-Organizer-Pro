"""Small reusable view components for the desktop UI."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List

from .foundation import FONTS, DesignTokens
from .theme import ThemeManager
from .tk_interactions import make_keyboard_activatable
from .widgets import ModernButton, ThemedWidget, Tooltip, get_theme


# =============================================================================
# ENHANCED PROGRESS BAR WIDGET
# =============================================================================
class EnhancedProgressBar(tk.Frame, ThemedWidget):
    """Enhanced progress bar with label, percentage, and animation"""
    
    def __init__(self, parent, height: int = 24, show_label: bool = True,
                 show_percentage: bool = True):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_primary, height=height)
        
        self.show_label = show_label
        self.show_percentage = show_percentage
        self._progress = 0
        self._max = 100
        self._label_text = ""
        self._animating = False
        
        # Container
        self.inner = tk.Frame(self, bg=theme.bg_primary)
        self.inner.pack(fill=tk.X, expand=True)
        
        # Label
        if show_label:
            self.label = tk.Label(
                self.inner, text="", bg=theme.bg_primary,
                fg=theme.text_secondary, font=FONTS.small(),
                anchor="w"
            )
            self.label.pack(side=tk.LEFT, padx=(0, 10))
        
        # Progress bar background
        self.bar_bg = tk.Frame(self.inner, bg=theme.bg_tertiary, height=8)
        self.bar_bg.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=8)
        
        # Progress bar fill
        self.bar_fill = tk.Frame(self.bar_bg, bg=theme.accent_primary, height=8)
        self.bar_fill.place(x=0, y=0, relheight=1.0, relwidth=0)
        
        # Percentage label
        if show_percentage:
            self.pct_label = tk.Label(
                self.inner, text="0%", bg=theme.bg_primary,
                fg=theme.text_muted, font=FONTS.small(),
                width=5
            )
            self.pct_label.pack(side=tk.RIGHT, padx=(10, 0))
    
    def set_progress(self, value: int, maximum: int = None, label: str = None):
        """Set progress value"""
        if maximum is not None:
            self._max = maximum
        
        self._progress = max(0, min(value, self._max))
        
        # Calculate percentage
        pct = (self._progress / self._max * 100) if self._max > 0 else 0
        
        # Update bar width
        self.bar_fill.place(relwidth=pct/100)
        
        # Update percentage text
        if self.show_percentage:
            self.pct_label.configure(text=f"{int(pct)}%")
        
        # Update label
        if label and self.show_label:
            self._label_text = label
            self.label.configure(text=label[:40])
    
    def set_indeterminate(self, active: bool = True):
        """Set indeterminate (animated) mode"""
        theme = get_theme()
        
        if active and not self._animating:
            self._animating = True
            self._animate_indeterminate()
        elif not active:
            self._animating = False
            self.bar_fill.configure(bg=theme.accent_primary)
            self.bar_fill.place(relx=0, relwidth=max(0, min(1, self._progress / self._max if self._max else 0)))
    
    def _animate_indeterminate(self):
        """Animate indeterminate progress"""
        if not self._animating:
            return
        
        theme = get_theme()
        
        # Simple back-and-forth animation
        current_pos = float(self.bar_fill.place_info().get('relx', 0))
        current_width = 0.3
        
        # Move position
        new_pos = current_pos + 0.05
        if new_pos > 0.7:
            new_pos = 0
        
        self.bar_fill.place(relx=new_pos, relwidth=current_width)
        
        if self._animating:
            self.after(50, self._animate_indeterminate)
    
    def reset(self):
        """Reset progress bar"""
        self._progress = 0
        self._animating = False
        self.bar_fill.place(relwidth=0)
        
        if self.show_percentage:
            self.pct_label.configure(text="0%")
        if self.show_label:
            self.label.configure(text="")
    
    def complete(self, label: str = "Complete"):
        """Mark as complete"""
        theme = get_theme()
        self._animating = False
        self.bar_fill.place(relwidth=1.0)
        self.bar_fill.configure(bg=theme.accent_success)
        
        if self.show_percentage:
            self.pct_label.configure(text="100%")
        if self.show_label:
            self.label.configure(text=label)


# =============================================================================
# DRAG & DROP IMPORT AREA
# =============================================================================
class DragDropImportArea(tk.Frame, ThemedWidget):
    """
    Drag & drop area for importing bookmark files.
    Supports: HTML, JSON, CSV, OPML, and more.
    """
    
    SUPPORTED_FORMATS = {
        ".html": "HTML Bookmarks",
        ".htm": "HTML Bookmarks",
        ".json": "JSON Export",
        ".csv": "CSV File",
        ".opml": "OPML/RSS",
        ".txt": "Text File (URLs)",
    }
    
    def __init__(self, parent, on_files_dropped: Callable = None):
        theme = get_theme()
        super().__init__(
            parent, bg=theme.bg_secondary, padx=18, pady=16,
            takefocus=1, cursor="hand2"
        )
        
        self.on_files_dropped = on_files_dropped
        self._drag_active = False
        self._compact = False
        self.compact_row = None
        self.compact_title_label = None
        self.compact_detail_label = None
        self.compact_action = None
        
        self.configure(
            highlightbackground=theme.border_muted,
            highlightcolor=theme.border_active,
            highlightthickness=DesignTokens.FOCUS_RING_WIDTH
        )
        
        # Icon
        self.icon_label = tk.Label(
            self, text="↓", bg=theme.bg_secondary,
            fg=theme.accent_primary, font=FONTS.custom(26, bold=True)
        )
        self.icon_label.pack(pady=(8, 5))
        
        # Main text
        self.main_label = tk.Label(
            self, text="Bring bookmarks in", bg=theme.bg_secondary,
            fg=theme.text_primary, font=FONTS.body(bold=True)
        )
        self.main_label.pack()
        
        # Supported formats
        formats_text = "HTML, JSON, CSV, OPML, and text URL files"
        self.formats_label = tk.Label(
            self, text=formats_text, bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.small()
        )
        self.formats_label.pack(pady=(5, 0), padx=4)
        
        # Browse button
        self.browse_btn = ModernButton(
            self, text="Choose files",
            command=self._browse_files
        )
        self.browse_btn.pack(pady=(14, 6))
        
        # Bind events (note: true drag-drop requires tkinterdnd2 or similar)
        # For now, we'll use click-to-browse and simulated drop
        self.bind("<Button-1>", lambda e: self._browse_files())
        self.bind("<Return>", lambda e: self._browse_files())
        self.bind("<space>", lambda e: self._browse_files())
        self.bind("<FocusIn>", self._on_enter)
        self.bind("<FocusOut>", self._on_leave)
        for child in (self.icon_label, self.main_label, self.formats_label):
            child.bind("<Button-1>", lambda e: self._browse_files())
        
        # Visual feedback on hover
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
    
    def _on_enter(self, e):
        """Mouse enter - highlight"""
        theme = get_theme()
        self._apply_surface(theme.bg_hover)
        self.configure(highlightbackground=theme.accent_primary if not self._compact else theme.bg_dark)

    def _on_leave(self, e):
        """Mouse leave - reset"""
        theme = get_theme()
        self._apply_surface(theme.bg_dark if self._compact else theme.bg_secondary)
        self.configure(highlightbackground=theme.bg_dark if self._compact else theme.border_muted)

    def _apply_surface(self, bg: str):
        """Keep the import affordance visually unified across child widgets."""
        widgets = [self, self.icon_label, self.main_label, self.formats_label]
        if self.compact_row:
            widgets.extend([self.compact_row, self.compact_title_label, self.compact_detail_label])
        for widget in widgets:
            try:
                widget.configure(bg=bg)
            except Exception:
                pass
    
    def _browse_files(self):
        """Open file browser for multiple files"""
        filetypes = [
            ("All Bookmark Files", "*.html *.htm *.json *.csv *.opml *.txt"),
            ("HTML Files", "*.html *.htm"),
            ("JSON Files", "*.json"),
            ("CSV Files", "*.csv"),
            ("OPML Files", "*.opml"),
            ("Text Files", "*.txt"),
            ("All Files", "*.*"),
        ]
        
        files = filedialog.askopenfilenames(
            title="Select Bookmark Files to Import",
            filetypes=filetypes
        )
        
        if files:
            self._process_files(list(files))
    
    def _process_files(self, filepaths: List[str]):
        """Process dropped/selected files"""
        valid_files = []
        
        for filepath in filepaths:
            ext = Path(filepath).suffix.lower()
            if ext in self.SUPPORTED_FORMATS:
                valid_files.append(filepath)
        
        if valid_files and self.on_files_dropped:
            self.on_files_dropped(valid_files)
        elif not valid_files:
            messagebox.showwarning(
                "No Supported Bookmark Files",
                "Choose an HTML, JSON, CSV, OPML, or text file containing bookmark URLs.\n\n" +
                "Supported extensions: " + ", ".join(sorted(self.SUPPORTED_FORMATS.keys()))
            )
    
    def set_importing(self, is_importing: bool):
        """Visual feedback during import"""
        theme = get_theme()
        
        if is_importing:
            self.icon_label.configure(text="⏳")
            self.main_label.configure(text="Importing bookmarks…")
            self.formats_label.configure(text="Please keep the app open while files are processed.")
            self.browse_btn.set_state("disabled")
            if self.compact_title_label:
                self.compact_title_label.configure(text="Importing…")
            if self.compact_detail_label:
                self.compact_detail_label.configure(text="Processing selected files")
            if self.compact_action:
                self.compact_action.set_state("disabled")
        else:
            self.icon_label.configure(text="↓")
            self.main_label.configure(
                text="Import library" if self._compact else "Bring bookmarks in"
            )
            if not self._compact:
                self.formats_label.configure(text="HTML, JSON, CSV, OPML, and text URL files")
            self.browse_btn.set_state("normal")
            if self.compact_title_label:
                self.compact_title_label.configure(text="Import")
            if self.compact_detail_label:
                self.compact_detail_label.configure(text="Files or browser export")
            if self.compact_action:
                self.compact_action.set_state("normal")

    def set_compact(self, compact: bool = True):
        """Collapse the import affordance after the first successful import."""
        self._compact = compact
        theme = get_theme()
        if compact:
            self.configure(
                bg=theme.bg_dark, padx=0, pady=0,
                highlightthickness=DesignTokens.FOCUS_RING_WIDTH,
                highlightbackground=theme.bg_dark,
                highlightcolor=theme.border_active
            )
            self.icon_label.pack_forget()
            self.main_label.pack_forget()
            self.formats_label.pack_forget()
            self.browse_btn.pack_forget()

            if self.compact_row is None:
                self.compact_row = tk.Frame(self, bg=theme.bg_dark, cursor="hand2")
                copy = tk.Frame(self.compact_row, bg=theme.bg_dark, cursor="hand2")
                copy.pack(side=tk.LEFT, fill=tk.X, expand=True)
                self.compact_title_label = tk.Label(
                    copy, text="Import", bg=theme.bg_dark,
                    fg=theme.text_primary, font=FONTS.body(bold=True),
                    cursor="hand2", anchor="w"
                )
                self.compact_title_label.pack(anchor="w")
                self.compact_detail_label = tk.Label(
                    copy, text="Files or browser export", bg=theme.bg_dark,
                    fg=theme.text_muted, font=FONTS.tiny(),
                    cursor="hand2", anchor="w"
                )
                self.compact_detail_label.pack(anchor="w", pady=(2, 0))
                self.compact_action = ModernButton(
                    self.compact_row, text="Choose", command=self._browse_files,
                    style="primary", padx=12, pady=6, font=FONTS.tiny(bold=True)
                )
                self.compact_action.pack(side=tk.RIGHT, padx=(8, 0))
                for widget in (self.compact_row, copy, self.compact_title_label, self.compact_detail_label):
                    widget.bind("<Button-1>", lambda e: self._browse_files())
                    widget.bind("<Enter>", self._on_enter)
                    widget.bind("<Leave>", self._on_leave)
            self.compact_row.pack(fill=tk.X)
        else:
            self.configure(
                bg=theme.bg_secondary, padx=18, pady=16,
                highlightthickness=DesignTokens.FOCUS_RING_WIDTH,
                highlightbackground=theme.border_muted
            )
            if self.compact_row:
                self.compact_row.pack_forget()
            self.icon_label.pack(pady=(8, 5))
            self.main_label.pack()
            self.formats_label.pack(pady=(5, 0), padx=4, after=self.main_label)
            self.browse_btn.pack(pady=(14, 6))
            self.main_label.configure(text="Bring bookmarks in")
            self.formats_label.configure(text="HTML, JSON, CSV, OPML, and text URL files")
            self.browse_btn.pack_configure(pady=(14, 6))





# =============================================================================
# MINI ANALYTICS DASHBOARD (for main UI)
# =============================================================================
class MiniAnalyticsDashboard(tk.Frame, ThemedWidget):
    """Compact analytics dashboard for main UI sidebar"""
    
    def __init__(self, parent, bookmark_manager: BookmarkManager):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_secondary)
        
        self.bookmark_manager = bookmark_manager
        
        # Header
        header = tk.Frame(self, bg=theme.bg_tertiary)
        header.pack(fill=tk.X)
        
        tk.Label(
            header, text="📊 Analytics", bg=theme.bg_tertiary,
            fg=theme.text_primary, font=("Segoe UI", 10, "bold"),
            padx=10, pady=8
        ).pack(side=tk.LEFT)
        
        self.refresh_btn = tk.Label(
            header, text="↻", bg=theme.bg_tertiary,
            fg=theme.text_muted, font=FONTS.header(bold=False),
            cursor="hand2", padx=10
        )
        self.refresh_btn.pack(side=tk.RIGHT)
        make_keyboard_activatable(self.refresh_btn, self.refresh)
        Tooltip(self.refresh_btn, "Refresh Analytics")
        
        # Stats container
        self.stats_frame = tk.Frame(self, bg=theme.bg_secondary)
        self.stats_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.refresh()
    
    def refresh(self):
        """Refresh analytics"""
        theme = get_theme()
        
        # Clear existing
        for widget in self.stats_frame.winfo_children():
            widget.destroy()
        
        stats = self.bookmark_manager.get_statistics()
        
        # Health Score
        health = self._calculate_health_score(stats)
        health_color = theme.accent_success if health >= 70 else (theme.accent_warning if health >= 40 else theme.accent_error)
        
        health_frame = tk.Frame(self.stats_frame, bg=theme.bg_secondary)
        health_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(
            health_frame, text="Health Score", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.small()
        ).pack(side=tk.LEFT)
        
        tk.Label(
            health_frame, text=f"{health}%", bg=theme.bg_secondary,
            fg=health_color, font=FONTS.title(bold=False)
        ).pack(side=tk.RIGHT)
        
        # Health bar
        bar_bg = tk.Frame(self.stats_frame, bg=theme.bg_tertiary, height=6)
        bar_bg.pack(fill=tk.X, pady=(0, 15))
        
        bar_fill = tk.Frame(bar_bg, bg=health_color, height=6)
        bar_fill.place(x=0, y=0, relheight=1.0, relwidth=health/100)
        
        # Quick stats
        quick_stats = [
            ("Total", stats['total_bookmarks'], theme.text_primary),
            ("Categories", stats['total_categories'], theme.accent_primary),
            ("Tags", stats['total_tags'], theme.accent_purple),
            ("Broken", stats['broken'], theme.accent_error),
            ("Uncategorized", stats['uncategorized'], theme.accent_warning),
        ]
        
        for label, value, color in quick_stats:
            row = tk.Frame(self.stats_frame, bg=theme.bg_secondary)
            row.pack(fill=tk.X, pady=2)
            
            tk.Label(
                row, text=label, bg=theme.bg_secondary,
                fg=theme.text_muted, font=FONTS.small()
            ).pack(side=tk.LEFT)
            
            tk.Label(
                row, text=str(value), bg=theme.bg_secondary,
                fg=color, font=("Segoe UI", 9, "bold")
            ).pack(side=tk.RIGHT)
        
        # Top categories chart (mini)
        tk.Label(
            self.stats_frame, text="Top Categories", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.small(bold=True),
            anchor="w"
        ).pack(fill=tk.X, pady=(15, 5))
        
        sorted_cats = sorted(stats['category_counts'].items(), key=lambda x: -x[1])[:5]
        max_count = max(sorted_cats[0][1], 1) if sorted_cats else 1
        
        for cat, count in sorted_cats:
            cat_row = tk.Frame(self.stats_frame, bg=theme.bg_secondary)
            cat_row.pack(fill=tk.X, pady=1)
            
            # Mini bar
            bar_width = int((count / max_count) * 100)
            
            tk.Label(
                cat_row, text=cat[:15], bg=theme.bg_secondary,
                fg=theme.text_muted, font=FONTS.tiny(),
                width=15, anchor="w"
            ).pack(side=tk.LEFT)
            
            bar_frame = tk.Frame(cat_row, bg=theme.bg_tertiary, height=8, width=80)
            bar_frame.pack(side=tk.LEFT, padx=5)
            bar_frame.pack_propagate(False)
            
            fill = tk.Frame(bar_frame, bg=theme.accent_primary, height=8)
            fill.place(x=0, y=0, relheight=1.0, relwidth=bar_width/100)
            
            tk.Label(
                cat_row, text=str(count), bg=theme.bg_secondary,
                fg=theme.text_muted, font=FONTS.tiny()
            ).pack(side=tk.RIGHT)
    
    def _calculate_health_score(self, stats: Dict) -> int:
        """Calculate health score"""
        score = 100
        total = stats['total_bookmarks'] or 1
        
        # Penalties
        broken_pct = (stats['broken'] / total) * 100
        uncat_pct = (stats['uncategorized'] / total) * 100
        dupe_pct = (stats['duplicate_bookmarks'] / total) * 100
        
        score -= min(30, broken_pct * 3)
        score -= min(20, uncat_pct * 0.5)
        score -= min(15, dupe_pct * 2)
        
        # Bonuses
        tagged_pct = (stats['with_tags'] / total) * 100
        noted_pct = (stats['with_notes'] / total) * 100
        
        score += min(10, tagged_pct * 0.1)
        score += min(5, noted_pct * 0.1)
        
        return max(0, min(100, int(score)))


# =============================================================================
# FAVICON STATUS DISPLAY
# =============================================================================
class FaviconStatusDisplay(tk.Frame, ThemedWidget):
    """Shows favicon download status in status bar"""
    
    def __init__(self, parent):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_dark)
        
        self.icon_label = tk.Label(
            self, text="🌐", bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.body()
        )
        self.icon_label.pack(side=tk.LEFT, padx=(5, 3))
        
        self.status_label = tk.Label(
            self, text="Icons ready", bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.small()
        )
        self.status_label.pack(side=tk.LEFT, padx=(0, 10))
        
        # Mini progress
        self.progress_frame = tk.Frame(self, bg=theme.bg_tertiary, width=50, height=4)
        self.progress_frame.pack(side=tk.LEFT, padx=(0, 5))
        self.progress_frame.pack_propagate(False)
        
        self.progress_fill = tk.Frame(self.progress_frame, bg=theme.accent_primary, height=4)
        self.progress_fill.place(x=0, y=0, relheight=1.0, relwidth=0)
        
        self._visible = False
    
    def update_status(self, completed: int, total: int, current: str = ""):
        """Update the status display"""
        theme = get_theme()
        
        if total == 0:
            self.hide()
            return
        
        if not self._visible:
            self.show()
        
        pct = (completed / total) * 100 if total > 0 else 0
        
        self.status_label.configure(text=f"Icons {completed}/{total}")
        self.progress_fill.place(relwidth=pct/100)
        
        if completed >= total:
            self.status_label.configure(text=f"Icons ready ({completed})")
            self.progress_fill.configure(bg=theme.accent_success)
            # Auto-hide after a delay
            self.after(3000, self.hide)
    
    def show(self):
        """Show the status display"""
        self._visible = True
        self.pack(side=tk.LEFT, padx=10)
    
    def hide(self):
        """Hide the status display"""
        self._visible = False
        self.pack_forget()

# =============================================================================
# SCROLLABLE FRAME WIDGET
# =============================================================================
class ScrollableFrame(tk.Frame):
    """A scrollable frame widget that properly handles content overflow"""
    
    def __init__(self, parent, bg=None, **kwargs):
        theme = get_theme()
        bg = bg or theme.bg_secondary
        
        super().__init__(parent, bg=bg, **kwargs)
        
        # Create canvas and scrollbar
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        
        # Create inner frame
        self.inner = tk.Frame(self.canvas, bg=bg)
        
        # Create window in canvas
        self.canvas_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        
        # Configure scrolling
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # Pack widgets
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind events
        self.inner.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        
        # Mouse wheel scrolling
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.inner.bind("<MouseWheel>", self._on_mousewheel)
        
        # Bind to all children
        self.inner.bind_all("<MouseWheel>", self._on_mousewheel_global, add="+")
    
    def _on_frame_configure(self, event):
        """Update scroll region when inner frame changes"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    
    def _on_canvas_configure(self, event):
        """Update inner frame width when canvas resizes"""
        self.canvas.itemconfig(self.canvas_window, width=event.width)
    
    def _on_mousewheel(self, event):
        """Handle mouse wheel scrolling"""
        self.canvas.yview_scroll(-1 * (event.delta // 120), "units")
    
    def _on_mousewheel_global(self, event):
        """Handle mouse wheel when over child widgets"""
        # Check if mouse is over this frame
        widget = event.widget
        while widget:
            if widget == self.inner or widget == self.canvas:
                self.canvas.yview_scroll(-1 * (event.delta // 120), "units")
                break
            try:
                widget = widget.master
            except Exception:
                break
    
    def scroll_to_top(self):
        """Scroll to top"""
        self.canvas.yview_moveto(0)
    
    def scroll_to_bottom(self):
        """Scroll to bottom"""
        self.canvas.yview_moveto(1)


# =============================================================================
# THEME DROPDOWN MENU
# =============================================================================
class ThemeDropdown(tk.Frame):
    """Theme selector dropdown for toolbar"""
    
    def __init__(self, parent, theme_manager: ThemeManager, on_change: Callable = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_dark)
        
        self.theme_manager = theme_manager
        self.on_change = on_change
        
        # Current theme display
        self.current_var = tk.StringVar(value=theme_manager.current_theme.name)
        
        # Create dropdown button
        display = theme_manager.current_theme.display_name or theme_manager.current_theme.name
        self.btn = tk.Label(
            self, text=display[:18],
            bg=theme.bg_secondary, fg=theme.text_primary,
            font=FONTS.small(), padx=10, pady=6,
            cursor="hand2"
        )
        self.btn.pack(fill=tk.X)
        
        make_keyboard_activatable(self.btn, lambda: self._show_menu())
        self.btn.bind("<Enter>", lambda e: self.btn.configure(bg=theme.bg_hover))
        self.btn.bind("<Leave>", lambda e: self.btn.configure(bg=theme.bg_secondary))
    
    def _show_menu(self, event=None):
        """Show theme selection menu"""
        theme = get_theme()
        
        menu = tk.Menu(self, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                      font=FONTS.body())
        
        for theme_name, theme_info in self.theme_manager.get_all_themes().items():
            display = theme_info.display_name or theme_name
            mode = "Dark" if theme_info.is_dark else "Light"
            check = " ✓" if theme_name == self.theme_manager.current_theme.name else ""
            menu.add_command(
                label=f"  {mode}  {display}{check}",
                command=lambda t=theme_name: self._select_theme(t)
            )
        
        # Position below button
        x = self.btn.winfo_rootx()
        y = self.btn.winfo_rooty() + self.btn.winfo_height()
        menu.tk_popup(x, y)
    
    def _select_theme(self, theme_name: str):
        """Select a theme"""
        self.theme_manager.set_theme(theme_name)
        self.current_var.set(theme_name)
        info = self.theme_manager.get_all_themes().get(theme_name)
        display = info.display_name if info else theme_name
        self.btn.configure(text=display[:18])
        
        if self.on_change:
            self.on_change(theme_name)
