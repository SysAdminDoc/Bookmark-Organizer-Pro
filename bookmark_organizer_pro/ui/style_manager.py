"""Centralized ttk styling for the desktop UI."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict

from bookmark_organizer_pro.logging_config import log

from .foundation import FONTS, DesignTokens


# =============================================================================
# STYLE MANAGER - Centralized ttk styling
# =============================================================================
class StyleManager:
    """
        Centralized ttk.Style configuration manager.
        
        Implements singleton pattern to manage all ttk widget styling
        consistently across the application. Applies theme colors to
        all standard and custom ttk styles.
        
        Attributes:
            style: The ttk.Style instance
            _current_theme_colors: Currently applied theme colors
        
        Methods:
            initialize(root): Initialize with root window
            apply_theme(colors): Apply theme colors to all styles
            get_treeview_tag_config(colors): Get treeview tag configuration
        
        Styled Widgets:
            - Treeview (rows, headings, selection)
            - TButton (default, Primary, Success, Danger)
            - TEntry, TCombobox (with focus states)
            - TScrollbar (vertical and horizontal)
            - TNotebook (tabs)
            - TCheckbutton, TRadiobutton
            - TProgressbar, TSeparator, TLabelframe
            - Custom: Sidebar, Card, StatusBar, Toolbar styles
        
        Example:
            >>> style_manager.initialize(root)
            >>> style_manager.apply_theme(theme.colors)
        """
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, root: tk.Tk = None):
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        self._initialized = True
        self.root = root
        self.style = ttk.Style() if root else None
        self._current_theme_colors = None
    
    def initialize(self, root: tk.Tk):
        """Initialize with root window"""
        self.root = root
        self.style = ttk.Style(root)
        
        # Use clam theme as base for better customization
        try:
            self.style.theme_use('clam')
        except tk.TclError:
            try:
                self.style.theme_use('default')
            except tk.TclError:
                pass
    
    def apply_theme(self, colors):
        """Apply theme colors to all ttk widgets"""
        if not self.style:
            return
        
        self._current_theme_colors = colors
        
        # ===== GENERAL WIDGET STYLING =====
        self.style.configure(".",
            background=colors.bg_primary,
            foreground=colors.text_primary,
            fieldbackground=colors.bg_secondary,
            font=FONTS.body(),
            borderwidth=0,
            focuscolor=colors.accent_primary
        )
        
        # ===== TREEVIEW STYLING =====
        self.style.configure("Treeview",
            background=colors.bg_primary,
            foreground=colors.text_primary,
            fieldbackground=colors.bg_primary,
            borderwidth=0,
            rowheight=DesignTokens.TREEVIEW_ROW_HEIGHT,
            font=FONTS.body()
        )
        
        self.style.configure("Treeview.Heading",
            background=colors.bg_secondary,
            foreground=colors.text_secondary,
            borderwidth=0,
            font=FONTS.small(bold=True),
            padding=(DesignTokens.SPACE_SM, DesignTokens.SPACE_SM)
        )
        
        self.style.map("Treeview",
            background=[
                ("selected", colors.selection),
                ("!selected", colors.bg_primary)
            ],
            foreground=[
                ("selected", colors.text_primary),
                ("!selected", colors.text_primary)
            ]
        )
        
        self.style.map("Treeview.Heading",
            background=[
                ("active", colors.bg_tertiary),
                ("!active", colors.bg_secondary)
            ]
        )
        
        # ===== BUTTON STYLING =====
        self.style.configure("TButton",
            background=colors.bg_tertiary,
            foreground=colors.text_primary,
            borderwidth=1,
            focusthickness=0,
            padding=(DesignTokens.SPACE_MD, DesignTokens.SPACE_SM),
            font=FONTS.body()
        )
        
        self.style.map("TButton",
            background=[
                ("pressed", colors.bg_hover),
                ("active", colors.bg_hover),
                ("disabled", colors.bg_secondary)
            ],
            foreground=[
                ("disabled", colors.text_muted)
            ]
        )
        
        # Primary button style
        self.style.configure("Primary.TButton",
            background=colors.accent_primary,
            foreground="#ffffff",
            borderwidth=0,
            padding=(DesignTokens.SPACE_LG, DesignTokens.SPACE_SM)
        )
        
        self.style.map("Primary.TButton",
            background=[
                ("pressed", colors.selected),
                ("active", colors.selected),
                ("disabled", colors.bg_tertiary)
            ]
        )
        
        # Success button style
        self.style.configure("Success.TButton",
            background=colors.accent_success,
            foreground="#ffffff",
            borderwidth=0
        )
        
        self.style.map("Success.TButton",
            background=[
                ("pressed", colors.status_success),
                ("active", colors.status_success)
            ]
        )
        
        # Danger button style
        self.style.configure("Danger.TButton",
            background=colors.accent_error,
            foreground="#ffffff",
            borderwidth=0
        )
        
        self.style.map("Danger.TButton",
            background=[
                ("pressed", colors.status_error),
                ("active", colors.status_error)
            ]
        )
        
        # ===== ENTRY STYLING =====
        self.style.configure("TEntry",
            fieldbackground=colors.bg_secondary,
            foreground=colors.text_primary,
            borderwidth=1,
            padding=DesignTokens.SPACE_SM,
            font=FONTS.body()
        )
        
        self.style.map("TEntry",
            fieldbackground=[
                ("focus", colors.bg_tertiary),
                ("!focus", colors.bg_secondary)
            ],
            bordercolor=[
                ("focus", colors.accent_primary),
                ("!focus", colors.border)
            ]
        )
        
        # ===== COMBOBOX STYLING =====
        self.style.configure("TCombobox",
            fieldbackground=colors.bg_secondary,
            background=colors.bg_secondary,
            foreground=colors.text_primary,
            arrowcolor=colors.text_secondary,
            borderwidth=1,
            padding=DesignTokens.SPACE_SM,
            font=FONTS.body()
        )
        
        self.style.map("TCombobox",
            fieldbackground=[
                ("readonly", colors.bg_secondary),
                ("focus", colors.bg_tertiary)
            ],
            selectbackground=[("!focus", colors.selection)],
            selectforeground=[("!focus", colors.text_primary)]
        )
        
        # ===== SCROLLBAR STYLING =====
        self.style.configure("Vertical.TScrollbar",
            background=colors.scrollbar_bg,
            troughcolor=colors.bg_primary,
            borderwidth=0,
            arrowsize=0,
            width=10
        )
        
        self.style.map("Vertical.TScrollbar",
            background=[
                ("pressed", colors.scrollbar_thumb_hover),
                ("active", colors.scrollbar_thumb_hover),
                ("!active", colors.scrollbar_thumb)
            ]
        )
        
        self.style.configure("Horizontal.TScrollbar",
            background=colors.scrollbar_bg,
            troughcolor=colors.bg_primary,
            borderwidth=0,
            arrowsize=0,
            height=10
        )
        
        self.style.map("Horizontal.TScrollbar",
            background=[
                ("pressed", colors.scrollbar_thumb_hover),
                ("active", colors.scrollbar_thumb_hover),
                ("!active", colors.scrollbar_thumb)
            ]
        )
        
        # ===== NOTEBOOK (TAB) STYLING =====
        self.style.configure("TNotebook",
            background=colors.bg_primary,
            borderwidth=0,
            tabmargins=[0, 0, 0, 0]
        )
        
        self.style.configure("TNotebook.Tab",
            background=colors.bg_secondary,
            foreground=colors.text_secondary,
            padding=(DesignTokens.SPACE_LG, DesignTokens.SPACE_SM),
            font=FONTS.body()
        )
        
        self.style.map("TNotebook.Tab",
            background=[
                ("selected", colors.bg_primary),
                ("!selected", colors.bg_secondary)
            ],
            foreground=[
                ("selected", colors.text_primary),
                ("!selected", colors.text_secondary)
            ],
            expand=[("selected", [0, 0, 0, 2])]
        )
        
        # ===== CHECKBUTTON STYLING =====
        self.style.configure("TCheckbutton",
            background=colors.bg_primary,
            foreground=colors.text_primary,
            font=FONTS.body(),
            indicatorbackground=colors.bg_secondary,
            indicatorforeground=colors.accent_primary
        )
        
        self.style.map("TCheckbutton",
            background=[
                ("active", colors.bg_hover),
                ("!active", colors.bg_primary)
            ],
            indicatorbackground=[
                ("selected", colors.accent_primary),
                ("!selected", colors.bg_secondary)
            ]
        )
        
        # ===== RADIOBUTTON STYLING =====
        self.style.configure("TRadiobutton",
            background=colors.bg_primary,
            foreground=colors.text_primary,
            font=FONTS.body(),
            indicatorbackground=colors.bg_secondary
        )
        
        self.style.map("TRadiobutton",
            background=[
                ("active", colors.bg_hover),
                ("!active", colors.bg_primary)
            ],
            indicatorbackground=[
                ("selected", colors.accent_primary),
                ("!selected", colors.bg_secondary)
            ]
        )
        
        # ===== PROGRESSBAR STYLING =====
        self.style.configure("TProgressbar",
            background=colors.accent_primary,
            troughcolor=colors.bg_tertiary,
            borderwidth=0,
            thickness=6
        )
        
        self.style.configure("Horizontal.TProgressbar",
            background=colors.accent_primary,
            troughcolor=colors.bg_tertiary
        )
        
        # ===== SEPARATOR STYLING =====
        self.style.configure("TSeparator",
            background=colors.border
        )
        
        # ===== LABELFRAME STYLING =====
        self.style.configure("TLabelframe",
            background=colors.bg_primary,
            borderwidth=1,
            relief="solid"
        )
        
        self.style.configure("TLabelframe.Label",
            background=colors.bg_primary,
            foreground=colors.text_primary,
            font=FONTS.small(bold=True)
        )
        
        # ===== SPINBOX STYLING =====
        self.style.configure("TSpinbox",
            fieldbackground=colors.bg_secondary,
            background=colors.bg_tertiary,
            foreground=colors.text_primary,
            arrowcolor=colors.text_secondary,
            borderwidth=1,
            padding=DesignTokens.SPACE_SM
        )
        
        # ===== SCALE STYLING =====
        self.style.configure("TScale",
            background=colors.bg_primary,
            troughcolor=colors.bg_tertiary,
            sliderthickness=16
        )
        
        # ===== PANEDWINDOW STYLING =====
        self.style.configure("TPanedwindow",
            background=colors.bg_primary
        )
        
        # ===== CUSTOM STYLES =====
        
        # Sidebar style
        self.style.configure("Sidebar.TFrame",
            background=colors.bg_secondary
        )
        
        # Card style
        self.style.configure("Card.TFrame",
            background=colors.card_bg,
            borderwidth=1,
            relief="solid"
        )
        
        # Status bar style
        self.style.configure("StatusBar.TFrame",
            background=colors.bg_secondary
        )
        
        self.style.configure("StatusBar.TLabel",
            background=colors.bg_secondary,
            foreground=colors.text_secondary,
            font=FONTS.small()
        )
        
        # Toolbar style
        self.style.configure("Toolbar.TFrame",
            background=colors.bg_secondary
        )
        
        self.style.configure("Toolbar.TButton",
            background=colors.bg_secondary,
            foreground=colors.text_primary,
            borderwidth=0,
            padding=(DesignTokens.SPACE_SM, DesignTokens.SPACE_SM)
        )
        
        self.style.map("Toolbar.TButton",
            background=[
                ("pressed", colors.bg_hover),
                ("active", colors.bg_tertiary)
            ]
        )
        
        # Header label style
        self.style.configure("Header.TLabel",
            background=colors.bg_primary,
            foreground=colors.text_primary,
            font=FONTS.header()
        )
        
        # Muted label style
        self.style.configure("Muted.TLabel",
            background=colors.bg_primary,
            foreground=colors.text_muted,
            font=FONTS.small()
        )
        
        # Link label style
        self.style.configure("Link.TLabel",
            background=colors.bg_primary,
            foreground=colors.text_link,
            font=FONTS.body()
        )
        
        log.debug("Theme styles applied successfully")
    
    def get_treeview_tag_config(self, colors) -> Dict[str, Dict]:
        """Get tag configuration for treeview alternating rows and states"""
        return {
            "oddrow": {"background": colors.bg_primary},
            "evenrow": {"background": colors.bg_secondary},
            "selected": {"background": colors.selection},
            "pinned": {"foreground": colors.accent_warning},
            "broken": {"foreground": colors.accent_error},
            "ai_processed": {"foreground": colors.ai_accent}
        }


# Global style manager instance
style_manager = StyleManager()

