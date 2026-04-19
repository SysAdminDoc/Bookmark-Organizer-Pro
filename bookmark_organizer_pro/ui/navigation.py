"""Reusable Tk interaction helpers for the desktop shell."""

from __future__ import annotations

import html as html_module
import re
import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional, Tuple


# =============================================================================
# Clipboard Monitor
# =============================================================================
class ClipboardMonitor:
    """Monitor clipboard for URLs and offer to add them"""
    
    URL_PATTERN = re.compile(
        r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[^\s]*',
        re.IGNORECASE
    )
    
    def __init__(self, root: tk.Tk, on_url_detected: Callable):
        self.root = root
        self.on_url_detected = on_url_detected
        self._last_clipboard = ""
        self._running = False
        self._check_interval = 1000  # ms
    
    def start(self):
        """Start monitoring clipboard"""
        self._running = True
        self._check()
    
    def stop(self):
        """Stop monitoring clipboard"""
        self._running = False
    
    def _check(self):
        """Check clipboard for URLs"""
        if not self._running:
            return
        
        try:
            current = self.root.clipboard_get()
            
            if current != self._last_clipboard:
                self._last_clipboard = current
                
                # Check if it's a URL
                match = self.URL_PATTERN.match(current.strip())
                if match:
                    url = match.group(0)
                    self.on_url_detected(url)
        except tk.TclError:
            # Clipboard empty or unavailable
            pass
        except Exception:
            pass
        
        # Schedule next check
        if self._running:
            self.root.after(self._check_interval, self._check)
    
    @property
    def is_running(self) -> bool:
        return self._running


# =============================================================================
# Vim-Style Navigation
# =============================================================================
class VimNavigator:
    """Vim-style keyboard navigation for bookmark list"""
    
    def __init__(self, tree: ttk.Treeview, on_open: Callable = None):
        self.tree = tree
        self.on_open = on_open
        self._enabled = False
        self._visual_mode = False
        self._visual_start = None
        
        self._commands = {
            'j': self._move_down,
            'k': self._move_up,
            'g': self._go_top,  # gg
            'G': self._go_bottom,
            'o': self._open_bookmark,
            'Enter': self._open_bookmark,
            'd': self._delete,  # dd
            'y': self._yank,    # yy (copy URL)
            'p': self._toggle_pin,
            'a': self._toggle_archive,
            'e': self._edit,
            '/': self._search,
            'n': self._next_search,
            'N': self._prev_search,
            'v': self._visual_mode_toggle,
            'Escape': self._escape,
            'space': self._page_down,
            'b': self._page_up,
        }
        
        self._pending_command = None
        self._search_pattern = ""
        self._search_matches: List[str] = []
        self._search_index = 0
    
    def enable(self):
        """Enable vim navigation"""
        self._enabled = True
        self._bind_keys()
    
    def disable(self):
        """Disable vim navigation"""
        self._enabled = False
        self._unbind_keys()
    
    def _bind_keys(self):
        """Bind keyboard events"""
        self.tree.bind('<Key>', self._on_key)
        self.tree.focus_set()
    
    def _unbind_keys(self):
        """Unbind keyboard events"""
        self.tree.unbind('<Key>')
    
    def _on_key(self, event):
        """Handle key press"""
        if not self._enabled:
            return
        
        key = event.char or event.keysym
        
        # Handle pending commands (like gg, dd, yy)
        if self._pending_command:
            combined = self._pending_command + key
            self._pending_command = None
            
            if combined == 'gg':
                self._go_top()
            elif combined == 'dd':
                self._delete()
            elif combined == 'yy':
                self._yank()
            return "break"
        
        # Check for command that needs second key
        if key in ['g', 'd', 'y']:
            self._pending_command = key
            return "break"
        
        # Execute single-key command
        if key in self._commands:
            self._commands[key]()
            return "break"
    
    def _get_current(self) -> Optional[str]:
        """Get currently selected item"""
        selection = self.tree.selection()
        return selection[0] if selection else None
    
    def _get_all_items(self) -> List[str]:
        """Get all items in order"""
        return list(self.tree.get_children())
    
    def _select(self, item: str):
        """Select an item"""
        if item:
            self.tree.selection_set(item)
            self.tree.focus(item)
            self.tree.see(item)
    
    def _move_down(self):
        """Move selection down (j)"""
        items = self._get_all_items()
        current = self._get_current()
        
        if not items:
            return
        
        if current:
            try:
                idx = items.index(current)
                if idx < len(items) - 1:
                    self._select(items[idx + 1])
            except ValueError:
                self._select(items[0])
        else:
            self._select(items[0])
    
    def _move_up(self):
        """Move selection up (k)"""
        items = self._get_all_items()
        current = self._get_current()
        
        if not items:
            return
        
        if current:
            try:
                idx = items.index(current)
                if idx > 0:
                    self._select(items[idx - 1])
            except ValueError:
                self._select(items[-1])
        else:
            self._select(items[-1])
    
    def _go_top(self):
        """Go to first item (gg)"""
        items = self._get_all_items()
        if items:
            self._select(items[0])
    
    def _go_bottom(self):
        """Go to last item (G)"""
        items = self._get_all_items()
        if items:
            self._select(items[-1])
    
    def _page_down(self):
        """Page down (space)"""
        for _ in range(10):
            self._move_down()
    
    def _page_up(self):
        """Page up (b)"""
        for _ in range(10):
            self._move_up()
    
    def _open_bookmark(self):
        """Open selected bookmark (o/Enter)"""
        if self.on_open:
            current = self._get_current()
            if current:
                self.on_open(int(current))
    
    def _delete(self):
        """Delete selected (dd)"""
        # This would trigger the main app's delete
        event = type('Event', (), {'widget': self.tree})()
        self.tree.event_generate('<<Delete>>')
    
    def _yank(self):
        """Copy URL to clipboard (yy)"""
        self.tree.event_generate('<<Copy>>')
    
    def _toggle_pin(self):
        """Toggle pin status (p)"""
        self.tree.event_generate('<<TogglePin>>')
    
    def _toggle_archive(self):
        """Toggle archive status (a)"""
        self.tree.event_generate('<<ToggleArchive>>')
    
    def _edit(self):
        """Edit bookmark (e)"""
        self.tree.event_generate('<<Edit>>')
    
    def _search(self):
        """Start search (/)"""
        self.tree.event_generate('<<StartSearch>>')
    
    def _next_search(self):
        """Next search result (n)"""
        if self._search_matches and self._search_index < len(self._search_matches) - 1:
            self._search_index += 1
            self._select(self._search_matches[self._search_index])
    
    def _prev_search(self):
        """Previous search result (N)"""
        if self._search_matches and self._search_index > 0:
            self._search_index -= 1
            self._select(self._search_matches[self._search_index])
    
    def _visual_mode_toggle(self):
        """Toggle visual selection mode (v)"""
        self._visual_mode = not self._visual_mode
        if self._visual_mode:
            self._visual_start = self._get_current()
        else:
            self._visual_start = None
    
    def _escape(self):
        """Cancel current operation"""
        self._visual_mode = False
        self._visual_start = None
        self._pending_command = None
    
    def search_items(self, pattern: str):
        """Search items and store matches"""
        self._search_pattern = pattern.lower()
        self._search_matches = []
        self._search_index = 0
        
        for item in self._get_all_items():
            values = self.tree.item(item, 'values')
            if values:
                text = ' '.join(str(v) for v in values).lower()
                if self._search_pattern in text:
                    self._search_matches.append(item)
        
        if self._search_matches:
            self._select(self._search_matches[0])


# =============================================================================
# Search Highlighting
# =============================================================================
class SearchHighlighter:
    """Highlights search terms in text"""
    
    def __init__(self, highlight_color: str = "#ffeb3b", 
                 text_color: str = "#000000"):
        self.highlight_color = highlight_color
        self.text_color = text_color
    
    def highlight_in_text_widget(self, text_widget: tk.Text, 
                                  search_term: str,
                                  tag_name: str = "highlight"):
        """Apply highlighting to a Text widget"""
        # Configure highlight tag
        text_widget.tag_configure(
            tag_name,
            background=self.highlight_color,
            foreground=self.text_color
        )
        
        # Remove old highlights
        text_widget.tag_remove(tag_name, "1.0", tk.END)
        
        if not search_term:
            return
        
        # Find and highlight all occurrences
        start = "1.0"
        while True:
            pos = text_widget.search(
                search_term, start, tk.END, nocase=True
            )
            if not pos:
                break
            
            end = f"{pos}+{len(search_term)}c"
            text_widget.tag_add(tag_name, pos, end)
            start = end
    
    def get_highlighted_html(self, text: str, search_term: str) -> str:
        """Return HTML with highlighted search terms"""
        text = str(text or "")
        search_term = str(search_term or "")
        if not search_term:
            return html_module.escape(text)
        
        pattern = re.compile(re.escape(search_term), re.IGNORECASE)
        background = html_module.escape(str(self.highlight_color), quote=True)
        color = html_module.escape(str(self.text_color), quote=True)

        pieces = []
        last_end = 0
        for match in pattern.finditer(text):
            pieces.append(html_module.escape(text[last_end:match.start()]))
            pieces.append(
                f'<mark style="background:{background};color:{color}">'
                f'{html_module.escape(match.group(0))}</mark>'
            )
            last_end = match.end()
        pieces.append(html_module.escape(text[last_end:]))
        return "".join(pieces)
    
    def highlight_in_label(self, text: str, search_term: str) -> Tuple[str, List[Tuple[int, int]]]:
        """
        Returns text and list of (start, end) positions to highlight.
        For use with custom label rendering.
        """
        if not search_term:
            return text, []
        
        positions = []
        search_lower = search_term.lower()
        text_lower = text.lower()
        
        start = 0
        while True:
            pos = text_lower.find(search_lower, start)
            if pos == -1:
                break
            positions.append((pos, pos + len(search_term)))
            start = pos + 1
        
        return text, positions
