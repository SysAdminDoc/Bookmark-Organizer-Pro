"""Core themed controls used across the Tk desktop UI."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import Callable, List, Optional

from bookmark_organizer_pro.search import SearchEngine

from .foundation import FONTS, DesignTokens, readable_text_on
from .theme import ThemeColors
from .tk_interactions import make_keyboard_activatable
from .widget_runtime import get_theme

# =============================================================================
# Themed Widget Base
# =============================================================================
class ThemedWidget:
    """
        Mixin class for theme-aware widgets.
        
        Provides common functionality for widgets that need
        to respond to theme changes.
        
        Attributes:
            theme: Current ThemeColors instance
        
        Methods:
            update_theme(theme): Update widget colors
            get_theme(): Get current theme colors
        """
    
    def apply_theme(self, theme: ThemeColors):
        """Override in subclasses to apply theme"""
        pass
    
    def get_theme(self) -> ThemeColors:
        """Get current theme colors"""
        return get_theme()


# =============================================================================
# Tooltip Helper Class
# =============================================================================
class Tooltip:
    """
        Hover tooltip for widgets.
        
        Displays a tooltip after hovering over a widget for
        a configurable delay period.
        
        Attributes:
            widget: Target widget
            text: Tooltip text
            delay: Delay before showing (ms)
            tooltip_window: The tooltip toplevel window
        
        Features:
            - Configurable delay
            - Auto-positioning near cursor
            - Theme-aware styling
            - Click-to-dismiss
        
        Example:
            >>> Tooltip(button, "Click to save", delay=500)
        """
    
    def __init__(self, widget, text: str, delay: int = 350):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tooltip_window = None
        self.scheduled_id = None
        
        # Use add='+' to ADD bindings instead of replacing existing ones
        # This prevents overwriting click handlers on buttons
        widget.bind("<Enter>", self._schedule_show, add='+')
        widget.bind("<Leave>", self._hide, add='+')
        widget.bind("<FocusIn>", self._schedule_show, add='+')
        widget.bind("<FocusOut>", self._hide, add='+')
        widget.bind("<Button-1>", self._hide, add='+')
    
    def _schedule_show(self, event=None):
        """Schedule tooltip to show after delay"""
        self._hide()
        self.scheduled_id = self.widget.after(self.delay, self._show)
    
    def _show(self, event=None):
        """Display the tooltip"""
        if self.tooltip_window or not self.text:
            return
        
        theme = get_theme()
        
        # Get widget position
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        
        # Create tooltip window
        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        try:
            tw.attributes("-topmost", True)
            tw.attributes("-alpha", 0.96)
        except Exception:
            pass

        # Style the tooltip with subtle shadow border
        outer = tk.Frame(tw, bg=theme.text_muted, bd=0, padx=1, pady=1)
        outer.pack()
        frame = tk.Frame(outer, bg=theme.border, bd=0, padx=1, pady=1)
        frame.pack()

        label = tk.Label(
            frame, text=self.text, bg=theme.bg_dark, fg=theme.text_primary,
            font=FONTS.small(), padx=DesignTokens.SPACE_SM, pady=DesignTokens.SPACE_SM,
            justify=tk.LEFT, wraplength=300
        )
        label.pack()
        
        # Keep tooltip on screen
        tw.update_idletasks()
        screen_width = tw.winfo_screenwidth()
        screen_height = tw.winfo_screenheight()
        tip_width = tw.winfo_width()
        tip_height = tw.winfo_height()
        
        if x + tip_width > screen_width:
            x = screen_width - tip_width - 5
        if y + tip_height > screen_height:
            y = self.widget.winfo_rooty() - tip_height - 5
        
        tw.wm_geometry(f"+{x}+{y}")
    
    def _hide(self, event=None):
        """Hide the tooltip"""
        if self.scheduled_id:
            self.widget.after_cancel(self.scheduled_id)
            self.scheduled_id = None
        
        if self.tooltip_window:
            if self.tooltip_window and self.tooltip_window.winfo_exists():
                self.tooltip_window.destroy()
            self.tooltip_window = None
    
    def update_text(self, new_text: str):
        """Update tooltip text"""
        self.text = new_text


def create_tooltip(widget, text: str, delay: int = 350) -> Tooltip:
    """Helper function to create tooltips"""
    return Tooltip(widget, text, delay)


# =============================================================================
# Modern Button (Themed)
# =============================================================================
class ModernButton(tk.Frame, ThemedWidget):
    """
        Modern styled button with hover effects.
        
        Custom button widget with rounded appearance, hover states,
        and optional icon support.
        
        Attributes:
            text: Button text
            command: Click callback
            style: Button style (primary, secondary, danger, success)
            icon: Optional icon text (emoji)
            state: Button state (normal, disabled)
        
        Methods:
            configure(**kwargs): Update button properties
            invoke(): Programmatically trigger click
        """
    
    def __init__(self, parent, text="", command=None,
                 bg=None, fg=None, hover_bg=None,
                 width=None, font=FONTS.small(), icon=None,
                 state='normal', padx=12, pady=7, style="default",
                 tooltip: str = None):
        
        theme = get_theme()
        
        # Determine colors based on style
        if style == "primary":
            bg = bg or theme.accent_primary
            hover_bg = hover_bg or theme.selected
            fg = fg or readable_text_on(bg)
        elif style == "success":
            bg = bg or theme.accent_success
            hover_bg = hover_bg or theme.status_success
            fg = fg or readable_text_on(bg)
        elif style == "danger":
            bg = bg or theme.accent_error
            hover_bg = hover_bg or theme.status_error
            fg = fg or readable_text_on(bg)
        elif style == "warning":
            bg = bg or theme.accent_warning
            hover_bg = hover_bg or theme.status_warning
            fg = fg or readable_text_on(bg)
        else:
            bg = bg or theme.bg_secondary
            hover_bg = hover_bg or theme.bg_hover
            fg = fg or theme.text_primary

        super().__init__(
            parent, bg=bg, takefocus=1 if state == 'normal' else 0,
            highlightthickness=DesignTokens.FOCUS_RING_WIDTH,
            highlightbackground=theme.border_muted if style == "default" else bg,
            highlightcolor=theme.border_active
        )
        self.command = command
        self.text = text
        self.icon = icon
        self.default_bg = bg
        self.hover_bg = hover_bg
        self.fg = fg
        self.hover_fg = readable_text_on(hover_bg) if style in {"primary", "success", "danger", "warning"} else fg
        self.state = state
        self.style = style
        self.focus_bg = hover_bg
        self._pressed_bg = theme.selection if style == "default" else hover_bg
        self._is_hovered = False
        self._is_focused = False
        self._normal_border = theme.border_muted if style == "default" else bg
        self._disabled_bg = theme.bg_tertiary
        self._disabled_fg = theme.text_muted
        
        # Icon + text
        display_text = self._display_text()
        
        self.label = tk.Label(
            self, text=display_text, bg=bg,
            fg=fg if state == 'normal' else self._disabled_fg,
            font=font, cursor="hand2" if state == 'normal' else "arrow",
            anchor="center"
        )
        effective_pady = max(pady, 9) if style == "primary" else pady
        self.label.pack(padx=padx, pady=effective_pady)
        
        if width:
            self.configure(width=width)
        
        # Add tooltip if provided
        if tooltip:
            self.tooltip = Tooltip(self, tooltip)
        
        for widget in [self, self.label]:
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
            widget.bind("<ButtonPress-1>", self._on_press)
            widget.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Return>", self._on_key_activate)
        self.bind("<KP_Enter>", self._on_key_activate)
        self.bind("<space>", self._on_key_activate)

    def _display_text(self):
        return f"{self.icon} {self.text}" if self.icon else self.text

    def _on_enter(self, e):
        if self.state == 'normal':
            self._is_hovered = True
            theme = get_theme()
            self.configure(bg=self.hover_bg, highlightbackground=theme.border_active)
            self.label.configure(bg=self.hover_bg, fg=self.hover_fg)

    def _on_leave(self, e):
        if self.state == 'normal':
            self._is_hovered = False
            border = get_theme().border_active if self._is_focused else self._normal_border
            self.configure(bg=self.default_bg, highlightbackground=border)
            self.label.configure(bg=self.default_bg, fg=self.fg)

    def _on_focus_in(self, e):
        if self.state == 'normal':
            theme = get_theme()
            self._is_focused = True
            self.configure(highlightbackground=theme.accent_primary)

    def _on_focus_out(self, e):
        if self.state == 'normal':
            self._is_focused = False
            border = get_theme().border_active if self._is_hovered else self._normal_border
            self.configure(highlightbackground=border)

    def _on_press(self, e):
        if self.state == 'normal':
            self.configure(bg=self._pressed_bg)
            self.label.configure(bg=self._pressed_bg, fg=readable_text_on(self._pressed_bg))

    def _on_release(self, e):
        if self.state != 'normal':
            return
        bg = self.hover_bg if self._is_hovered else self.default_bg
        fg = self.hover_fg if self._is_hovered else self.fg
        self.configure(bg=bg)
        self.label.configure(bg=bg, fg=fg)
        if self.command:
            self.command()

    def _on_key_activate(self, e):
        if self.state == 'normal':
            self._on_press(e)
            self.after(100, lambda: self._on_release_and_fire(e))
        return "break"

    def _on_release_and_fire(self, e):
        bg = self.hover_bg if self._is_hovered else self.default_bg
        fg = self.hover_fg if self._is_hovered else self.fg
        self.configure(bg=bg)
        self.label.configure(bg=bg, fg=fg)
        if self.command:
            self.command()
    
    def set_state(self, state):
        self.state = state
        theme = get_theme()
        if state == 'normal':
            self.label.configure(fg=self.fg, cursor="hand2")
            bg = self.hover_bg if self._is_hovered else self.default_bg
            fg = self.hover_fg if self._is_hovered else self.fg
            border = theme.border_active if self._is_hovered or self._is_focused else self._normal_border
            self.configure(bg=bg, highlightbackground=border, cursor="hand2", takefocus=1)
            self.label.configure(bg=bg, fg=fg)
        else:
            self.label.configure(fg=self._disabled_fg, cursor="arrow")
            self.configure(
                bg=self._disabled_bg, highlightbackground=theme.border_muted,
                cursor="arrow", takefocus=0,
            )
            self.label.configure(bg=self._disabled_bg)
    
    def set_text(self, text):
        self.text = text
        self.label.configure(text=self._display_text())


# =============================================================================
# Modern Search Bar (Themed)
# =============================================================================
class ModernSearch(tk.Frame, ThemedWidget):
    """
        Modern search input with clear button and icon.
        
        Enhanced search entry with:
            - Search icon prefix
            - Clear (X) button
            - Placeholder text
            - Theme-aware styling
        
        Attributes:
            entry: The actual Entry widget
            placeholder: Placeholder text
            on_search: Callback when search triggered
            on_clear: Callback when cleared
        
        Methods:
            get(): Get current search text
            set(text): Set search text
            clear(): Clear search
            focus(): Focus the entry
        """
    
    def __init__(self, parent, textvariable, placeholder="Search…",
                 on_search=None, on_change=None, show_syntax_help=True):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_secondary)
        
        self.configure(padx=12, pady=8)
        self.on_search = on_search
        self.on_change = on_change
        self.placeholder = placeholder
        self.textvariable = textvariable
        self.theme = theme
        
        self.inner = tk.Frame(self, bg=theme.bg_secondary)
        self.inner.pack(fill=tk.BOTH, expand=True)
        
        # Search icon
        self.icon_label = tk.Label(
            self.inner, text="Search", bg=theme.bg_secondary,
            fg=theme.text_muted, font=FONTS.body()
        )
        self.icon_label.pack(side=tk.LEFT, padx=(0, 10))
        
        # Entry
        self.entry = tk.Entry(
            self.inner, textvariable=textvariable,
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            font=FONTS.body(), highlightthickness=0
        )
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Help button
        if show_syntax_help:
            self.help_btn = tk.Label(
                self.inner, text="?", bg=theme.bg_secondary,
                fg=theme.text_muted, font=FONTS.small(),
                cursor="hand2"
            )
            self.help_btn.pack(side=tk.RIGHT, padx=(8, 0))
            make_keyboard_activatable(self.help_btn, self._show_help)
            Tooltip(self.help_btn, "Show Search Syntax")
        
        # Clear button
        self.clear_btn = tk.Label(
            self.inner, text="Clear", bg=theme.bg_secondary,
            fg=theme.text_muted, font=FONTS.body(), cursor="hand2"
        )
        make_keyboard_activatable(self.clear_btn, self._clear)
        Tooltip(self.clear_btn, "Clear Search")
        
        # Border line
        self.border = tk.Frame(self, bg=theme.border, height=2)
        self.border.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Bindings
        self.entry.bind("<FocusIn>", self._on_focus)
        self.entry.bind("<FocusOut>", self._on_unfocus)
        self.entry.bind("<Return>", lambda e: self.on_search() if self.on_search else None)
        self.entry.bind("<Escape>", lambda e: self._clear())
        textvariable.trace_add('write', self._on_text_change)
    
    def _on_focus(self, e):
        theme = get_theme()
        self.border.configure(bg=theme.accent_primary)
        self.icon_label.configure(fg=theme.accent_primary)

    def _on_unfocus(self, e):
        theme = get_theme()
        self.border.configure(bg=theme.border)
        self.icon_label.configure(fg=theme.text_muted)
    
    def _on_text_change(self, *args):
        if self.textvariable.get():
            self.clear_btn.pack(side=tk.RIGHT, padx=(8, 0))
        else:
            self.clear_btn.pack_forget()
        
        if self.on_change:
            self.on_change()
    
    def _clear(self, e=None):
        self.textvariable.set("")
        self.entry.focus_set()
    
    def _show_help(self, e=None):
        help_text = SearchEngine.get_syntax_help()
        messagebox.showinfo("Search Syntax", help_text)
    
    def focus_set(self):
        self.entry.focus_set()


# =============================================================================
# Tag Widget (for displaying and editing tags)
# =============================================================================
class TagWidget(tk.Frame, ThemedWidget):
    """Visual tag chip displaying a tag name with optional remove button.

    Attributes:
        tag_name: The tag string to display.
        color: Accent color for the tag text.
        on_remove: Callback invoked with the tag name when removed.
    """
    
    def __init__(self, parent, tag_name: str, color: str = None,
                 on_remove: Callable = None, removable: bool = True,
                 show_remove: Optional[bool] = None):
        theme = get_theme()
        if show_remove is not None:
            removable = show_remove
        
        # Generate color if not provided
        if not color:
            colors = [
                theme.accent_primary, theme.accent_success, theme.accent_warning,
                theme.accent_purple, theme.accent_cyan, theme.accent_pink
            ]
            hash_val = sum(ord(c) for c in tag_name)
            color = colors[hash_val % len(colors)]
        
        super().__init__(parent, bg=theme.bg_primary)
        
        self.tag_name = tag_name
        self.color = color
        self.on_remove = on_remove
        
        # Tag label
        self.label = tk.Label(
            self, text=f"#{tag_name}", bg=theme.bg_secondary,
            fg=color, font=FONTS.small(), padx=6, pady=2
        )
        self.label.pack(side=tk.LEFT)
        
        # Remove button
        if removable and on_remove:
            self.remove_btn = tk.Label(
                self, text="×", bg=theme.bg_secondary,
                fg=theme.text_muted, font=FONTS.small(),
                cursor="hand2", padx=4
            )
            self.remove_btn.pack(side=tk.LEFT)
            make_keyboard_activatable(self.remove_btn, lambda: on_remove(tag_name))
            self.remove_btn.bind("<Enter>", lambda e: self.remove_btn.configure(fg=theme.accent_error))
            self.remove_btn.bind("<Leave>", lambda e: self.remove_btn.configure(fg=theme.text_muted))
            Tooltip(self.remove_btn, f"Remove #{tag_name}")


class TagEditor(tk.Frame, ThemedWidget):
    """Inline tag editor with entry field, add button, and removable tag chips.

    Attributes:
        tags: Current list of tag strings.
        available_tags: Suggestions for autocomplete (not yet wired).
        on_change: Callback invoked with the updated tag list on add/remove.
    """
    
    def __init__(self, parent, tags: List[str] = None, 
                 available_tags: List[str] = None,
                 on_change: Callable = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_primary)
        
        self.tags = list(tags or [])
        self.available_tags = available_tags or []
        self.on_change = on_change
        self.theme = theme
        
        # Tags display area
        self.tags_frame = tk.Frame(self, bg=theme.bg_primary)
        self.tags_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Add tag entry
        self.entry_frame = tk.Frame(self, bg=theme.bg_primary)
        self.entry_frame.pack(fill=tk.X)
        
        self.entry_var = tk.StringVar()
        self._placeholder = "Add a tag…"
        self._placeholder_active = True
        self.entry = tk.Entry(
            self.entry_frame, textvariable=self.entry_var,
            bg=theme.bg_secondary, fg=theme.text_muted,
            insertbackground=theme.text_primary, bd=0,
            font=FONTS.small()
        )
        self.entry.insert(0, self._placeholder)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.entry.bind("<FocusIn>", self._on_entry_focus_in)
        self.entry.bind("<FocusOut>", self._on_entry_focus_out)
        self.entry.bind("<Return>", self._add_tag)

        self.add_btn = tk.Label(
            self.entry_frame, text="+", bg=theme.bg_secondary,
            fg=theme.accent_primary, font=FONTS.body(bold=True),
            cursor="hand2", padx=6
        )
        self.add_btn.pack(side=tk.RIGHT)
        make_keyboard_activatable(self.add_btn, self._add_tag)
        Tooltip(self.add_btn, "Add tag (Enter)")
        
        # Suggestions dropdown (hidden by default)
        self.suggestions_list = None
        
        self._refresh_tags()
    
    def _on_entry_focus_in(self, event=None):
        if self._placeholder_active:
            self.entry.delete(0, tk.END)
            self.entry.configure(fg=self.theme.text_primary)
            self._placeholder_active = False

    def _on_entry_focus_out(self, event=None):
        if not self.entry_var.get().strip():
            self.entry.insert(0, self._placeholder)
            self.entry.configure(fg=self.theme.text_muted)
            self._placeholder_active = True

    def _refresh_tags(self):
        """Refresh the tags display"""
        for widget in self.tags_frame.winfo_children():
            widget.destroy()
        
        for tag in self.tags:
            tag_widget = TagWidget(
                self.tags_frame, tag,
                on_remove=self._remove_tag
            )
            tag_widget.pack(side=tk.LEFT, padx=(0, 5), pady=2)
    
    def _add_tag(self, e=None):
        """Add a new tag"""
        if self._placeholder_active:
            return
        tag = self.entry_var.get().strip().lower()
        if tag and tag not in self.tags:
            self.tags.append(tag)
            self.entry_var.set("")
            self._refresh_tags()
            if self.on_change:
                self.on_change(self.tags)
    
    def _remove_tag(self, tag: str):
        """Remove a tag"""
        if tag in self.tags:
            self.tags.remove(tag)
            self._refresh_tags()
            if self.on_change:
                self.on_change(self.tags)
    
    def get_tags(self) -> List[str]:
        """Get current tags"""
        return self.tags.copy()
    
    def set_tags(self, tags: List[str]):
        """Set tags"""
        self.tags = list(tags)
        self._refresh_tags()
    
    def add_tag(self, tag: str):
        """Add a single tag (public method)"""
        tag = tag.strip().lower()
        if tag and tag not in self.tags:
            self.tags.append(tag)
            self._refresh_tags()
            if self.on_change:
                self.on_change(self.tags)
