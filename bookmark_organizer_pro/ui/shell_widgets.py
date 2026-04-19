"""Shell-level widgets used by the Bookmark Organizer desktop window."""

from __future__ import annotations

import threading
import tkinter as tk
from enum import Enum
from typing import Callable, List, Optional, Tuple

try:
    from PIL import Image, ImageDraw, ImageTk
    Image.MAX_IMAGE_PIXELS = 20_000_000
    HAS_PIL = True
except ImportError:  # pragma: no cover - optional runtime dependency
    Image = None
    ImageDraw = None
    ImageTk = None
    HAS_PIL = False

try:
    import pystray
    from pystray import MenuItem as TrayItem
    HAS_TRAY = True
except ImportError:  # pragma: no cover - optional runtime dependency
    pystray = None
    TrayItem = None
    HAS_TRAY = False

from bookmark_organizer_pro.constants import APP_NAME
from bookmark_organizer_pro.models import Bookmark

from .foundation import FONTS
from .tk_interactions import make_keyboard_activatable
from .widget_controls import ThemedWidget
from .widget_runtime import get_theme


# =============================================================================
# Grid View Card
# =============================================================================
class BookmarkCard(tk.Frame, ThemedWidget):
    """
        Card widget for displaying a single bookmark.
        
        Rich display of bookmark with favicon, title, URL,
        tags, and action buttons.
        
        Attributes:
            bookmark: The Bookmark object to display
            on_click: Callback when card clicked
            on_edit: Callback for edit action
            on_delete: Callback for delete action
            selected: Whether card is selected
        
        Features:
            - Favicon display with fallback
            - Truncated title and URL
            - Tag chips
            - Hover highlighting
            - Selection state
            - Context menu
        """
    
    def __init__(self, parent, bookmark: Bookmark, 
                 on_click: Callable = None,
                 on_double_click: Callable = None,
                 on_right_click: Callable = None,
                 favicon_manager=None):
        theme = get_theme()
        super().__init__(parent, bg=theme.card_bg, cursor="hand2")
        
        self.bookmark = bookmark
        self.on_click = on_click
        self.on_double_click = on_double_click
        self.on_right_click = on_right_click
        self.is_selected = False
        self.theme = theme
        
        self.configure(highlightbackground=theme.card_border, highlightthickness=1)
        
        # Favicon / domain icon
        icon_frame = tk.Frame(self, bg=theme.card_bg, width=48, height=48)
        icon_frame.pack(pady=(15, 10))
        icon_frame.pack_propagate(False)
        
        # Try to load favicon or create placeholder
        self.icon_label = tk.Label(icon_frame, bg=theme.card_bg)
        self.icon_label.pack(expand=True)
        
        if favicon_manager and HAS_PIL:
            cached = favicon_manager.get_cached_path(bookmark.url)
            if cached:
                try:
                    img = Image.open(cached)
                    img = img.resize((32, 32), Image.Resampling.LANCZOS)
                    self._photo = ImageTk.PhotoImage(img)
                    self.icon_label.configure(image=self._photo)
                except Exception:
                    self._set_placeholder()
            else:
                self._set_placeholder()
                if hasattr(favicon_manager, "fetch_favicon"):
                    favicon_manager.fetch_favicon(bookmark.url, self._on_favicon_loaded)
                elif hasattr(favicon_manager, "download_async"):
                    favicon_manager.download_async(bookmark.domain, bookmark.id)
        else:
            self._set_placeholder()
        
        # Title
        title_text = bookmark.title[:40] + "..." if len(bookmark.title) > 43 else bookmark.title
        self.title_label = tk.Label(
            self, text=title_text, bg=theme.card_bg,
            fg=theme.text_primary, font=("Segoe UI", 10, "bold"),
            wraplength=150
        )
        self.title_label.pack(padx=10)
        
        # Domain
        self.domain_label = tk.Label(
            self, text=bookmark.domain, bg=theme.card_bg,
            fg=theme.text_secondary, font=FONTS.small()
        )
        self.domain_label.pack(pady=(2, 5))
        
        # Tags
        if bookmark.tags:
            tags_text = " ".join(f"#{t}" for t in bookmark.tags[:3])
            self.tags_label = tk.Label(
                self, text=tags_text, bg=theme.card_bg,
                fg=theme.accent_primary, font=FONTS.tiny()
            )
            self.tags_label.pack(pady=(0, 5))
        
        # Status indicators
        status_frame = tk.Frame(self, bg=theme.card_bg)
        status_frame.pack(pady=(5, 15))
        
        if bookmark.is_pinned:
            tk.Label(status_frame, text="📌", bg=theme.card_bg).pack(side=tk.LEFT, padx=2)
        if not bookmark.is_valid:
            tk.Label(status_frame, text="⚠️", bg=theme.card_bg).pack(side=tk.LEFT, padx=2)
        if bookmark.is_archived:
            tk.Label(status_frame, text="📦", bg=theme.card_bg).pack(side=tk.LEFT, padx=2)
        
        # Bindings
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Button-3>", self._on_right_click)
        self.bind("<Double-1>", self._on_double_click)
        
        for child in self.winfo_children():
            child.bind("<Button-1>", self._on_click)
            child.bind("<Button-3>", self._on_right_click)
            child.bind("<Double-1>", self._on_double_click)
    
    def _set_placeholder(self):
        """Set placeholder icon"""
        letter = self.bookmark.domain[0].upper() if self.bookmark.domain else "?"
        self.icon_label.configure(
            text=letter, fg=self.theme.accent_primary,
            font=FONTS.title()
        )
    
    def _on_favicon_loaded(self, url: str, path: str):
        """Callback when favicon is loaded"""
        if HAS_PIL and path:
            try:
                img = Image.open(path)
                img = img.resize((32, 32), Image.Resampling.LANCZOS)
                self._photo = ImageTk.PhotoImage(img)
                self.icon_label.configure(image=self._photo, text="")
            except Exception:
                pass
    
    def _on_enter(self, e):
        if not self.is_selected:
            self.configure(bg=self.theme.card_hover)
            for child in self.winfo_children():
                if isinstance(child, tk.Label):
                    child.configure(bg=self.theme.card_hover)
                elif isinstance(child, tk.Frame):
                    child.configure(bg=self.theme.card_hover)
                    for subchild in child.winfo_children():
                        if isinstance(subchild, tk.Label):
                            subchild.configure(bg=self.theme.card_hover)
    
    def _on_leave(self, e):
        if not self.is_selected:
            self.configure(bg=self.theme.card_bg)
            for child in self.winfo_children():
                if isinstance(child, tk.Label):
                    child.configure(bg=self.theme.card_bg)
                elif isinstance(child, tk.Frame):
                    child.configure(bg=self.theme.card_bg)
                    for subchild in child.winfo_children():
                        if isinstance(subchild, tk.Label):
                            subchild.configure(bg=self.theme.card_bg)
    
    def _on_click(self, e):
        if self.on_click:
            self.on_click(self.bookmark)
    
    def _on_double_click(self, e):
        if self.on_double_click:
            self.on_double_click(self.bookmark)

    def _on_right_click(self, e):
        if self.on_right_click:
            self.on_right_click(e, self.bookmark)
    
    def set_selected(self, selected: bool):
        """Set selection state"""
        self.is_selected = selected
        bg = self.theme.selection if selected else self.theme.card_bg
        border = self.theme.accent_primary if selected else self.theme.card_border
        
        self.configure(bg=bg, highlightbackground=border)
        for child in self.winfo_children():
            if isinstance(child, tk.Label):
                child.configure(bg=bg)
            elif isinstance(child, tk.Frame):
                child.configure(bg=bg)
                for subchild in child.winfo_children():
                    if isinstance(subchild, tk.Label):
                        subchild.configure(bg=bg)


# =============================================================================
# System Tray Integration
# =============================================================================
class SystemTray:
    """System tray integration"""
    
    def __init__(self, app, on_show: Callable, on_quit: Callable):
        self.app = app
        self.on_show = on_show
        self.on_quit = on_quit
        self._tray = None
        self._icon = None
    
    def create_icon(self) -> Optional["Image.Image"]:
        """Create a tray icon"""
        if not HAS_PIL:
            return None
        
        # Create a simple bookmark icon
        size = 64
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Draw bookmark shape
        theme = get_theme()
        color = theme.accent_primary
        
        # Simple bookmark ribbon shape
        points = [
            (size * 0.2, size * 0.1),
            (size * 0.8, size * 0.1),
            (size * 0.8, size * 0.9),
            (size * 0.5, size * 0.7),
            (size * 0.2, size * 0.9),
        ]
        draw.polygon(points, fill=color)
        
        return img
    
    def start(self):
        """Start the system tray"""
        if not HAS_TRAY or not HAS_PIL:
            return
        
        self._icon = self.create_icon()
        if not self._icon:
            return
        
        menu = pystray.Menu(
            TrayItem("Show Window", lambda: self.on_show()),
            TrayItem("Quick Add URL", lambda: self._quick_add()),
            pystray.Menu.SEPARATOR,
            TrayItem("Quit", lambda: self.on_quit())
        )
        
        self._tray = pystray.Icon(
            APP_NAME,
            self._icon,
            APP_NAME,
            menu
        )
        
        thread = threading.Thread(target=self._tray.run, daemon=True)
        thread.start()
    
    def _quick_add(self):
        """Quick add URL from clipboard"""
        self.on_show()
        # The main app will handle clipboard monitoring
    
    def stop(self):
        """Stop the system tray"""
        if self._tray:
            self._tray.stop()
            self._tray = None
    
    def update_icon(self):
        """Update the tray icon"""
        if self._tray and HAS_PIL:
            self._icon = self.create_icon()
            self._tray.icon = self._icon


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
            font=FONTS.custom(12)
        )
        self.search_entry.pack(fill=tk.X, ipady=9)
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
        self.bind("<FocusOut>", lambda e: self.destroy())
        
        self.grab_set()
    
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
                    fg=theme.text_secondary, font=("Consolas", 9)
                )
                shortcut_label.pack(side=tk.RIGHT, padx=10)

            make_keyboard_activatable(item, lambda idx=i: self._select_and_execute(idx))
            for widget in [name_label, shortcut_label]:
                if widget:
                    widget.bind("<Button-1>", lambda e, idx=i: self._select_and_execute(idx))
    
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
            GRID: Card grid view
            COMPACT: Condensed list view
        """
    LIST = "list"
    GRID = "grid"


# =============================================================================
# Main Status Bar
# =============================================================================
class StatusBar(tk.Frame, ThemedWidget):
    """Status bar at the bottom of the window"""
    
    def __init__(self, parent):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_dark, height=30)
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
                    item.bind("<Button-1>", lambda e, cmd=command: self._on_click(cmd))
        
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
        
        # Close on click outside
        self.bind("<FocusOut>", lambda e: self.destroy())
        self.bind("<Escape>", lambda e: self.destroy())
        
        # Take focus
        self.focus_set()
        self.grab_set()
    
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

