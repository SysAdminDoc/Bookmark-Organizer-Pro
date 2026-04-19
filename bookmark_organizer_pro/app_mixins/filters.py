"""Search, category selection, and quick-filter actions for the app coordinator."""

from __future__ import annotations

import tkinter as tk

from bookmark_organizer_pro.ui import build_filter_counts
from bookmark_organizer_pro.ui.foundation import format_compact_count
from bookmark_organizer_pro.ui.widgets import get_theme


class FilterActionsMixin:
    """Search box, sidebar quick-filter, and category-selection behavior."""

    def _on_search_focus_in(self, e):
        """Clear placeholder when search entry gains focus"""
        if hasattr(self, 'search_frame') and self.search_frame:
            theme = get_theme()
            self.search_frame.configure(highlightbackground=theme.accent_primary)
        if self.search_entry.get() == self._search_placeholder:
            self._suppress_search_callback = True
            self.search_entry.delete(0, tk.END)
            self._suppress_search_callback = False
            self.search_entry.configure(fg=get_theme().text_primary)

    def _on_search_focus_out(self, e):
        """Restore placeholder when search entry loses focus and is empty"""
        if hasattr(self, 'search_frame') and self.search_frame:
            theme = get_theme()
            self.search_frame.configure(highlightbackground=theme.border_muted)
        if not self.search_entry.get():
            self._suppress_search_callback = True
            self.search_entry.insert(0, self._search_placeholder)
            self._suppress_search_callback = False
            self.search_entry.configure(fg=get_theme().text_muted)
            if hasattr(self, 'clear_search_btn') and self.clear_search_btn:
                self.clear_search_btn.pack_forget()

    def _on_search_change(self, *args):
        """Handle search change with debounce"""
        # Skip if suppressed (programmatic change) or placeholder is showing
        if getattr(self, '_suppress_search_callback', False):
            return

        if not self.search_var:
            return

        val = self.search_var.get()
        # Ignore placeholder text as a real query
        if val == getattr(self, '_search_placeholder', ''):
            if hasattr(self, 'clear_search_btn') and self.clear_search_btn:
                self.clear_search_btn.pack_forget()
            return
        self.search_query = val
        if hasattr(self, 'clear_search_btn') and self.clear_search_btn:
            if val:
                if not self.clear_search_btn.winfo_ismapped():
                    self.clear_search_btn.pack(side=tk.LEFT, padx=(5, 0))
            else:
                self.clear_search_btn.pack_forget()
        
        # When user types in search, clear quick filter and reset filter buttons
        if self.search_query:
            self.quick_filter = None
            self.active_filter = None
            for name in self.filter_buttons:
                self._set_filter_visual(name, False)
        
        # Cancel any pending refresh
        self._cancel_search_debounce()
        
        # Schedule debounced refresh
        self._search_after = self.root.after(200, self._refresh_bookmark_list)

    def _set_filter_visual(self, filter_name: str, active: bool, hover: bool = False):
        """Apply one consistent visual state to a quick-filter row."""
        parts = getattr(self, 'filter_button_parts', {}).get(filter_name)
        if not parts:
            return
        theme = get_theme()
        row, name_lbl, count_lbl = parts
        bg = theme.selection if active else (theme.bg_hover if hover else theme.bg_dark)
        badge_bg = theme.bg_tertiary if active or hover else theme.bg_primary
        fg = theme.text_primary if active else theme.text_secondary
        for widget in (row, name_lbl):
            try:
                widget.configure(bg=bg)
            except Exception:
                pass
        try:
            row.configure(highlightbackground=theme.border_muted if active else bg)
            count_lbl.configure(bg=badge_bg, fg=fg)
        except Exception:
            pass

    def _refresh_filter_counts(self):
        """Refresh quick-filter badges so the sidebar feels alive and trustworthy."""
        if not getattr(self, 'filter_button_parts', None):
            return
        counts = build_filter_counts(self.bookmark_manager.get_all_bookmarks()).as_dict()
        for name, count in counts.items():
            parts = self.filter_button_parts.get(name)
            if parts:
                parts[2].configure(text=format_compact_count(count))

    def _clear_search(self):
        """Clear search bar and show all bookmarks"""
        # Cancel any pending search refresh
        self._cancel_search_debounce()
        
        # Set suppress flag
        self._suppress_search_callback = True
        
        # Clear search entry directly (belt and suspenders)
        if self.search_entry:
            self.search_entry.delete(0, tk.END)
        if self.search_var:
            self.search_var.set("")
        
        # Clear search state
        self.search_query = ""
        self.quick_filter = None
        self.current_category = None
        self.active_filter = "All"
        if hasattr(self, 'clear_search_btn') and self.clear_search_btn:
            self.clear_search_btn.pack_forget()
        
        # Reset filter button highlighting
        for name in self.filter_buttons:
            self._set_filter_visual(name, name == "All")
        
        # Reset suppress flag after a brief delay
        def reset_flag():
            self._suppress_search_callback = False
        self.root.after(50, reset_flag)
        
        self._refresh_bookmark_list()
        self._set_status("Showing all bookmarks")
    
    def _filter_by_domain(self, domain: str):
        """Filter bookmarks by domain"""
        # Cancel any pending search refresh
        self._cancel_search_debounce()
        
        # Set suppress flag
        self._suppress_search_callback = True
        
        # Clear quick filter
        self.quick_filter = None
        self.active_filter = None
        self.current_category = None
        
        # Update filter buttons
        for name in self.filter_buttons:
            self._set_filter_visual(name, False)
        
        # Set search query directly in entry
        if self.search_entry:
            self.search_entry.delete(0, tk.END)
            self.search_entry.insert(0, f"domain:{domain}")
        if self.search_var:
            self.search_var.set(f"domain:{domain}")
        self.search_query = f"domain:{domain}"
        if hasattr(self, 'clear_search_btn') and self.clear_search_btn and not self.clear_search_btn.winfo_ismapped():
            self.clear_search_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        # Reset suppress flag after a brief delay
        def reset_flag():
            self._suppress_search_callback = False
        self.root.after(50, reset_flag)
        
        self._refresh_bookmark_list()
        self._set_status(f"Filtering by domain: {domain}")
    
    def _select_category(self, category: str):
        """Select category"""
        # Cancel pending search and set suppress flag
        self._cancel_search_debounce()
        self._suppress_search_callback = True
        
        # Clear search bar directly
        if self.search_entry:
            self.search_entry.delete(0, tk.END)
        if self.search_var:
            self.search_var.set("")
        self.search_query = ""
        self.quick_filter = None
        if hasattr(self, 'clear_search_btn') and self.clear_search_btn:
            self.clear_search_btn.pack_forget()
        
        # Clear quick filter button highlighting
        for name in self.filter_buttons:
            self._set_filter_visual(name, False)
        self.active_filter = None
        
        # Toggle category selection
        self.current_category = category if category != self.current_category else None
        self._refresh_category_list()
        self._refresh_bookmark_list()
        
        # Reset suppress flag after a brief delay
        def reset_flag():
            self._suppress_search_callback = False
        self.root.after(50, reset_flag)
        
        if self.current_category:
            self._set_status(f"Category: {category}")
        else:
            self._set_status("Showing all bookmarks")
    
    def _apply_filter(self, filter_name: str):
        """Apply quick filter - clean and direct"""
        # Cancel any pending search refresh first
        self._cancel_search_debounce()
        
        # Set suppress flag
        self._suppress_search_callback = True
        
        # Update active filter tracking
        self.active_filter = filter_name
        
        # Update all button states immediately
        for name in self.filter_buttons:
            self._set_filter_visual(name, name == filter_name)
        
        # Clear the search bar directly
        if self.search_entry:
            self.search_entry.delete(0, tk.END)
        if self.search_var:
            self.search_var.set("")
        if hasattr(self, 'clear_search_btn') and self.clear_search_btn:
            self.clear_search_btn.pack_forget()
        
        # Set the quick filter type
        if filter_name == "All":
            self.quick_filter = None
        elif filter_name == "Pinned":
            self.quick_filter = "pinned"
        elif filter_name == "Recent":
            self.quick_filter = "recent"
        elif filter_name == "Broken":
            self.quick_filter = "broken"
        elif filter_name == "Untagged":
            self.quick_filter = "untagged"
        
        # Clear category selection (so All shows ALL bookmarks)
        self.current_category = None
        self.search_query = ""
        
        # Reset suppress flag after a brief delay
        def reset_flag():
            self._suppress_search_callback = False
        self.root.after(50, reset_flag)
        
        # Refresh both category list (to clear selection) and bookmark list
        self._refresh_category_list()
        self._refresh_bookmark_list()
        
        # Update status with count
        if filter_name == "All":
            self._set_status("Showing all bookmarks")
        else:
            self._set_status(f"Filter: {filter_name}")
    
    def _cancel_search_debounce(self):
        """Cancel any pending search debounce"""
        if hasattr(self, '_search_after') and self._search_after is not None:
            try:
                self.root.after_cancel(self._search_after)
            except (ValueError, tk.TclError):
                pass
            self._search_after = None
    
    def _set_search_silent(self, text: str):
        """Set search bar text without triggering search callback"""
        self._suppress_search_callback = True
        
        # Clear any pending callbacks first
        self._cancel_search_debounce()
        
        if self.search_entry:
            self.search_entry.delete(0, tk.END)
            if text:
                self.search_entry.insert(0, text)
        if hasattr(self, 'clear_search_btn') and self.clear_search_btn:
            if text and not self.clear_search_btn.winfo_ismapped():
                self.clear_search_btn.pack(side=tk.LEFT, padx=(5, 0))
            elif not text:
                self.clear_search_btn.pack_forget()
        
        # Set StringVar - this will trigger trace but flag is set
        if self.search_var:
            self.search_var.set(text)
        
        # Keep flag set for a brief moment to catch any queued callbacks
        def reset_flag():
            self._suppress_search_callback = False
        self.root.after(50, reset_flag)

