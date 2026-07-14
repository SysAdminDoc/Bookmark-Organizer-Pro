"""Shell-level widgets used by the Bookmark Organizer desktop window."""

from __future__ import annotations

import tkinter as tk
from enum import Enum
from typing import Callable, List, Tuple

from .foundation import DesignTokens, FONTS
from .tk_interactions import make_keyboard_activatable, route_pointer_to_control
from .widget_controls import ThemedWidget
from .widget_runtime import get_theme


# =============================================================================
# Command Palette
# =============================================================================
class CommandPalette(tk.Toplevel, ThemedWidget):
    """
        Quick command palette (Ctrl+P).
        
        Fuzzy-searchable list of all application commands
        for keyboard-driven navigation.
        
        Features:
            - Fuzzy search matching
            - Keyboard navigation
            - Recent commands
            - Keyboard shortcut hints
        
        Example Commands:
            - Add Bookmark
            - Import/Export
            - Change Theme
            - Open Settings
        """
    
    def __init__(self, parent, commands: List[Tuple[str, str, Callable]]):
        super().__init__(parent)
        self.commands = commands  # [(name, shortcut, callback), ...]
        self.filtered_commands = commands.copy()
        self.selected_index = 0
        
        theme = get_theme()
        
        self.title("")
        self.overrideredirect(True)
        self.configure(bg=theme.border)
        
        # Position in center top
        self.geometry("560x430")
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - 560) // 2
        y = parent.winfo_rooty() + 100
        self.geometry(f"+{x}+{y}")
        
        # Border
        self.configure(highlightbackground=theme.border, highlightthickness=1)

        shell = tk.Frame(self, bg=theme.bg_secondary, padx=14, pady=14)
        shell.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        tk.Label(
            shell, text="Command Palette", bg=theme.bg_secondary,
            fg=theme.text_primary, font=FONTS.header(bold=True), anchor="w"
        ).pack(fill=tk.X)

        tk.Label(
            shell, text="Type to filter actions. Use ↑/↓ and Enter.",
            bg=theme.bg_secondary, fg=theme.text_secondary,
            font=FONTS.small(), anchor="w"
        ).pack(fill=tk.X, pady=(3, 12))
        
        # Search entry
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', self._filter)
        
        self.search_entry = tk.Entry(
            shell, textvariable=self.search_var,
            bg=theme.bg_tertiary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            font=FONTS.body()
        )
        self.search_entry.pack(fill=tk.X, ipady=8)
        self.search_entry.focus_set()
        
        # Separator
        tk.Frame(shell, bg=theme.border, height=1).pack(fill=tk.X, pady=(14, 8))
        
        # Commands list
        self.list_frame = tk.Frame(shell, bg=theme.bg_secondary)
        self.list_frame.pack(fill=tk.BOTH, expand=True)
        
        self._render_commands()
        
        # Bindings
        self.search_entry.bind("<Return>", self._execute)
        self.search_entry.bind("<Escape>", lambda e: self.destroy())
        self.search_entry.bind("<Up>", self._move_up)
        self.search_entry.bind("<Down>", self._move_down)
        self.bind("<FocusOut>", lambda e: self.after(150, self._check_focus_lost))

        self.grab_set()

    def _check_focus_lost(self):
        """Destroy only if focus actually left the palette (not to a child widget)."""
        try:
            focused = self.focus_get()
            if focused is None or not str(focused).startswith(str(self)):
                self.destroy()
        except Exception:
            self.destroy()
    
    def _filter(self, *args):
        """Filter commands based on search"""
        query = self.search_var.get().lower()
        
        if query:
            self.filtered_commands = [
                cmd for cmd in self.commands
                if query in cmd[0].lower()
            ]
        else:
            self.filtered_commands = self.commands.copy()
        
        self.selected_index = 0
        self._render_commands()
    
    def _render_commands(self):
        """Render the commands list"""
        theme = get_theme()
        
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        if not self.filtered_commands:
            empty = tk.Frame(self.list_frame, bg=theme.bg_secondary)
            empty.pack(fill=tk.BOTH, expand=True, pady=26)
            tk.Label(
                empty, text="No Matching Commands",
                bg=theme.bg_secondary, fg=theme.text_secondary,
                font=FONTS.body(bold=True)
            ).pack(fill=tk.X)
            tk.Label(
                empty, text="Try Add, Import, Export, Search, Theme, or Settings.",
                bg=theme.bg_secondary, fg=theme.text_muted,
                font=FONTS.small(), pady=6
            ).pack(fill=tk.X)
            return
        
        for i, (name, shortcut, callback) in enumerate(self.filtered_commands[:10]):
            is_selected = i == self.selected_index
            
            item = tk.Frame(
                self.list_frame,
                bg=theme.bg_tertiary if is_selected else theme.bg_secondary,
                highlightbackground=theme.accent_primary if is_selected else theme.bg_secondary,
                highlightthickness=1
            )
            item.pack(fill=tk.X, pady=2)

            accent = tk.Frame(
                item,
                bg=theme.accent_primary if is_selected else item.cget('bg'),
                width=3
            )
            accent.pack(side=tk.LEFT, fill=tk.Y)
            
            name_label = tk.Label(
                item, text=name, bg=item.cget('bg'),
                fg=theme.text_primary, font=FONTS.body(bold=is_selected),
                anchor="w"
            )
            name_label.pack(side=tk.LEFT, padx=10, pady=9)
            
            shortcut_label = None
            if shortcut:
                shortcut_label = tk.Label(
                    item, text=shortcut, bg=item.cget('bg'),
                    fg=theme.text_secondary, font=FONTS.tiny()
                )
                shortcut_label.pack(side=tk.RIGHT, padx=10)

            make_keyboard_activatable(
                item,
                lambda idx=i: self._select_and_execute(idx),
                accessible_name=name,
            )
            route_pointer_to_control(item, name_label, shortcut_label)
    
    def _move_up(self, e):
        if self.selected_index > 0:
            self.selected_index -= 1
            self._render_commands()
    
    def _move_down(self, e):
        if self.selected_index < len(self.filtered_commands) - 1:
            self.selected_index += 1
            self._render_commands()
    
    def _select_and_execute(self, index: int):
        self.selected_index = index
        self._execute()
    
    def _execute(self, e=None):
        if self.filtered_commands and 0 <= self.selected_index < len(self.filtered_commands):
            _, _, callback = self.filtered_commands[self.selected_index]
            self.destroy()
            if callback:
                callback()


# =============================================================================
# View Mode Enum
# =============================================================================
class ViewMode(Enum):
    """
        Enumeration of bookmark view modes.

        Values:
            LIST: Traditional list/table view
        """
    LIST = "list"


# =============================================================================
# Main Status Bar
# =============================================================================
class StatusBar(tk.Frame, ThemedWidget):
    """Status bar at the bottom of the window"""
    
    def __init__(self, parent):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_dark, height=DesignTokens.STATUS_BAR_HEIGHT)
        self.pack_propagate(False)
        self.theme = theme
        
        # Left: Status message
        self.status_label = tk.Label(
            self, text="Ready", bg=theme.bg_dark,
            fg=theme.text_secondary, font=FONTS.small()
        )
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # Right: Counts
        self.counts_label = tk.Label(
            self, text="", bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.small()
        )
        self.counts_label.pack(side=tk.RIGHT, padx=10)
        
        # Progress bar (hidden by default)
        self.progress_frame = tk.Frame(self, bg=theme.bg_dark)
        self.progress_bar = tk.Frame(self.progress_frame, bg=theme.accent_primary, height=4)
        self.progress_bar.pack(side=tk.LEFT, fill=tk.Y)
        
        self._progress_value = 0
    
    def set_status(self, message: str):
        """Set status message"""
        self.status_label.configure(text=message)
    
    def set_counts(self, total: int, selected: int = 0, filtered: int = None):
        """Set bookmark counts"""
        if filtered is not None and filtered != total:
            text = f"{selected} selected • {filtered} shown • {total} total"
        elif selected > 0:
            text = f"{selected} selected • {total} total"
        else:
            text = f"{total} bookmarks"
        self.counts_label.configure(text=text)
    
    def show_progress(self, value: float, message: str = ""):
        """Show progress bar"""
        if not self.progress_frame.winfo_ismapped():
            self.progress_frame.pack(side=tk.LEFT, fill=tk.Y, padx=20)
            self.progress_frame.configure(width=200)
        
        self._progress_value = max(0, min(1, value))
        self.progress_bar.place(relwidth=self._progress_value, relheight=1)
        
        if message:
            self.set_status(message)
    
    def hide_progress(self):
        """Hide progress bar"""
        self.progress_frame.pack_forget()
# ADDITIONAL FEATURES - BATCH 2
# =============================================================================


# =============================================================================
# STYLED DROPDOWN MENU
# =============================================================================
class StyledDropdownMenu(tk.Toplevel):
    """Professional styled dropdown menu that appears near the triggering button"""
    
    def __init__(self, parent, items: List[Tuple[str, Callable]], x: int, y: int):
        """
        Create a styled dropdown menu.
        
        Args:
            parent: Parent widget
            items: List of (label, command) tuples. Use (None, None) for separator.
            x, y: Screen coordinates for menu position
        """
        super().__init__(parent)
        
        theme = get_theme()
        
        # Remove window decorations
        self.overrideredirect(True)
        self.configure(bg=theme.border)
        
        # Main frame with border effect
        main_frame = tk.Frame(self, bg=theme.bg_secondary, padx=2, pady=2)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Add menu items
        for label, command in items:
            if label is None:
                # Separator
                sep = tk.Frame(main_frame, bg=theme.border, height=1)
                sep.pack(fill=tk.X, padx=10, pady=5)
            else:
                item = tk.Label(
                    main_frame, text=label, bg=theme.bg_secondary,
                    fg=theme.text_primary, font=FONTS.body(),
                    anchor="w", padx=15, pady=8, cursor="hand2"
                )
                item.pack(fill=tk.X)
                
                # Hover effects
                item.bind("<Enter>", lambda e, w=item: w.configure(bg=theme.bg_hover))
                item.bind("<Leave>", lambda e, w=item: w.configure(bg=theme.bg_secondary))
                
                # Click handler
                if command:
                    make_keyboard_activatable(
                        item,
                        lambda cmd=command: self._on_click(cmd),
                        accessible_name=label,
                    )
        
        # Position the menu
        self.update_idletasks()
        menu_width = self.winfo_reqwidth()
        menu_height = self.winfo_reqheight()
        
        # Ensure menu stays on screen
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        if x + menu_width > screen_width:
            x = screen_width - menu_width - 10
        if y + menu_height > screen_height:
            y = screen_height - menu_height - 10
        
        self.geometry(f"+{x}+{y}")
        
        # Close on click outside or Escape
        self.bind("<FocusOut>", lambda e: self.after(50, self._check_focus))
        self.bind("<Escape>", lambda e: self.destroy())

        # Take focus without modal grab (grab_set can lock the app if
        # the menu fails to destroy itself).
        self.focus_set()
    
    def _check_focus(self):
        """Destroy only if focus has truly left the dropdown."""
        try:
            focused = self.focus_get()
            if focused is None or not str(focused).startswith(str(self)):
                self.destroy()
        except Exception:
            self.destroy()

    def _on_click(self, command: Callable):
        """Handle menu item click"""
        self.destroy()
        if command:
            command()


def show_styled_menu(parent, button_widget, items: List[Tuple[str, Callable]]):
    """
    Show a styled dropdown menu below a button widget.
    
    Args:
        parent: Parent window
        button_widget: The button that triggered the menu
        items: List of (label, command) tuples
    """
    # Get button position
    button_widget.update_idletasks()
    x = button_widget.winfo_rootx()
    y = button_widget.winfo_rooty() + button_widget.winfo_height() + 2
    
    return StyledDropdownMenu(parent, items, x, y)
