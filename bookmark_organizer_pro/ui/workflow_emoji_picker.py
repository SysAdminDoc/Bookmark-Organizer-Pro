"""Emoji picker dialog for category icons."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from .foundation import FONTS
from .widget_controls import ThemedWidget
from .widget_runtime import apply_window_chrome, get_theme

# =============================================================================
# Emoji Picker
# =============================================================================
class EmojiPicker(tk.Toplevel, ThemedWidget):
    """Emoji picker dialog for category icons"""
    
    # Common useful emojis organized by category
    EMOJIS = {
        "Folders": "📁📂🗂️📋📄📑🗃️🗄️💼🎒",
        "Tech": "💻🖥️📱⌨️🖱️💾📀🔌🔋📡🌐🔗",
        "Work": "📧✉️📨📩📝📃✏️🖊️📌📍🔖",
        "Media": "📷📸📹🎬🎥📽️🎵🎶🎤🎧📺📻",
        "Objects": "🔧🔨⚙️🔩🛠️💡🔦🔬🔭📐📏",
        "Symbols": "⭐🌟✨💫🔥❤️💜💙💚💛🧡",
        "Nature": "🌍🌎🌏🌲🌳🌴🌵🌾🌻🌺🌸",
        "Food": "🍕🍔🍟🌭🥪🌮🍜🍝🍣🍱🍩",
        "Travel": "✈️🚀🚁🚂🚃🚌🚎🚐🚗🏠🏢",
        "Finance": "💰💵💶💷💴💸💳📈📉📊💹",
        "Sports": "⚽🏀🏈⚾🎾🏐🏉🎱🏓🏸🥊",
        "Education": "📚📖📕📗📘📙📓📔📒✏️🎓",
        "Health": "💊💉🩺🩹🏥🚑❤️‍🩹🧬🔬💪",
        "Shopping": "🛒🛍️🏪🏬💳🎁📦🏷️💵🛒",
        "Social": "👥👤💬💭🗣️📢📣🔔🔕✋",
    }
    
    def __init__(self, parent, on_select: Callable = None):
        super().__init__(parent)
        self.on_select = on_select
        self.result = None
        
        theme = get_theme()
        
        self.title("Choose Emoji")
        self.geometry("400x450")
        self.configure(bg=theme.bg_primary)
        self.transient(parent)
        self.grab_set()
        
        apply_window_chrome(self)
        
        # Search
        search_frame = tk.Frame(self, bg=theme.bg_primary)
        search_frame.pack(fill=tk.X, padx=15, pady=15)
        
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', self._filter_emojis)
        
        search_entry = tk.Entry(
            search_frame, textvariable=self.search_var,
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            font=FONTS.body()
        )
        search_entry.pack(fill=tk.X, ipady=8)
        search_entry.insert(0, "Search emojis...")
        search_entry.bind("<FocusIn>", lambda e: search_entry.delete(0, tk.END) 
                          if search_entry.get().startswith("Search") else None)
        
        # Emoji grid with scrolling
        container = tk.Frame(self, bg=theme.bg_primary)
        container.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(container, bg=theme.bg_primary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.emoji_frame = tk.Frame(canvas, bg=theme.bg_primary)
        
        self.emoji_frame.bind("<Configure>", 
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.emoji_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        canvas.bind("<MouseWheel>", 
            lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        
        self._render_emojis()
        
        self.center_window()
    
    def _render_emojis(self, filter_text: str = ""):
        """Render emoji grid"""
        theme = get_theme()
        
        for widget in self.emoji_frame.winfo_children():
            widget.destroy()
        
        for category, emojis in self.EMOJIS.items():
            if filter_text:
                # Filter by category name or emoji
                if filter_text.lower() not in category.lower():
                    emojis = ''.join(e for e in emojis if filter_text in e)
                    if not emojis:
                        continue
            
            # Category header
            tk.Label(
                self.emoji_frame, text=category, bg=theme.bg_primary,
                fg=theme.text_secondary, font=FONTS.small(bold=True),
                anchor="w"
            ).pack(fill=tk.X, padx=10, pady=(10, 5))
            
            # Emoji grid
            grid_frame = tk.Frame(self.emoji_frame, bg=theme.bg_primary)
            grid_frame.pack(fill=tk.X, padx=10)
            
            for i, emoji in enumerate(emojis):
                btn = tk.Label(
                    grid_frame, text=emoji, bg=theme.bg_primary,
                    font=("Segoe UI Emoji", 20), cursor="hand2"
                )
                btn.grid(row=i // 10, column=i % 10, padx=2, pady=2)
                btn.bind("<Button-1>", lambda e, em=emoji: self._select(em))
                
                # Hover effect
                btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=theme.bg_secondary))
                btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=theme.bg_primary))
    
    def _filter_emojis(self, *args):
        """Filter emojis based on search"""
        search_text = self.search_var.get()
        if not search_text.startswith("Search"):
            self._render_emojis(search_text)
    
    def _select(self, emoji: str):
        """Select an emoji"""
        self.result = emoji
        if self.on_select:
            self.on_select(emoji)
        self.destroy()
    
    def center_window(self):
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')
