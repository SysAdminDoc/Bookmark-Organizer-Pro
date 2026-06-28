"""About dialog and build metadata for the desktop UI."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import tkinter as tk
from tkinter import ttk

try:
    import PIL  # noqa: F401
    HAS_PIL = True
except ImportError:  # pragma: no cover - optional runtime dependency
    HAS_PIL = False

try:
    import pystray  # noqa: F401
    HAS_TRAY = True
except ImportError:  # pragma: no cover - optional runtime dependency
    HAS_TRAY = False

from bookmark_organizer_pro.constants import (
    APP_DIR,
    APP_NAME,
    APP_SUBTITLE,
    APP_VERSION,
    LOG_FILE,
    MASTER_BOOKMARKS_FILE,
    SETTINGS_FILE,
)
from bookmark_organizer_pro.services.local_state import (
    build_diagnostics_snapshot,
    export_redacted_support_bundle,
    format_diagnostics,
)

from .foundation import FONTS, readable_text_on
from .widgets import ModernButton, get_theme


# Build information
BUILD_DATE = "April 2026"
BUILD_TYPE = "Release"
COPYRIGHT_YEAR = "2026"
AUTHOR = "SysAdminDoc"
WEBSITE = "https://github.com/SysAdminDoc/Bookmark-Organizer-Pro"
LICENSE = "MIT License"


class AboutDialog(tk.Toplevel):
    """
    Professional About dialog with version info, credits, and system information.
    
    Features tabbed interface with:
    - About: General information and description
    - Features: List of application features
    - System: Technical system information
    - Credits: Acknowledgments and license
    """
    
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        theme = get_theme()
        self.status_var = tk.StringVar(value="")
        
        self.title(f"About {APP_NAME}")
        self.geometry("700x640")
        self.resizable(False, False)
        self.configure(bg=theme.bg_primary)
        
        # Make modal
        self.transient(parent)
        self.grab_set()
        
        # Center on parent
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - 700) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - 640) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        
        self._create_ui(theme)
        
        # Keyboard handling
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self.destroy())
        self.focus_set()
    
    def _create_ui(self, theme):
        """Create the About dialog UI"""
        
        # Header with icon and title
        header = tk.Frame(self, bg=theme.bg_secondary)
        header.pack(fill=tk.X)
        
        header_content = tk.Frame(header, bg=theme.bg_secondary)
        header_content.pack(pady=20)
        
        # App icon
        icon_label = tk.Label(
            header_content, text="B", font=FONTS.display(),
            bg=theme.accent_primary, fg=readable_text_on(theme.accent_primary),
            padx=12, pady=2
        )
        icon_label.pack()
        
        # App name
        tk.Label(
            header_content, text=APP_NAME,
            font=FONTS.title(), bg=theme.bg_secondary, fg=theme.text_primary
        ).pack(pady=(8, 0))
        
        # Version
        tk.Label(
            header_content, text=f"Version {APP_VERSION}",
            font=FONTS.body(), bg=theme.bg_secondary, fg=theme.text_secondary
        ).pack()
        
        # Subtitle
        tk.Label(
            header_content, text=APP_SUBTITLE,
            font=FONTS.small(), bg=theme.bg_secondary, fg=theme.text_muted
        ).pack(pady=(4, 0))
        
        # Tab notebook
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        # Create tabs
        self._create_about_tab(notebook, theme)
        self._create_features_tab(notebook, theme)
        self._create_system_tab(notebook, theme)
        self._create_credits_tab(notebook, theme)
        
        # Footer
        footer = tk.Frame(self, bg=theme.bg_secondary)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        
        footer_content = tk.Frame(footer, bg=theme.bg_secondary)
        footer_content.pack(pady=12, padx=15, fill=tk.X)
        
        actions = tk.Frame(footer_content, bg=theme.bg_secondary)
        actions.pack(fill=tk.X)

        logs_btn = ModernButton(
            actions, text="Open Logs",
            font=FONTS.small(), command=self._open_logs,
            padx=12, pady=6
        )
        logs_btn.pack(side=tk.LEFT, padx=(0, 8))

        copy_btn = ModernButton(
            actions, text="Copy Diagnostics",
            font=FONTS.small(), command=self._copy_system_info,
            padx=12, pady=6
        )
        copy_btn.pack(side=tk.LEFT, padx=(0, 8))

        bundle_btn = ModernButton(
            actions, text="Export Redacted Bundle",
            font=FONTS.small(), command=self._export_support_bundle,
            padx=12, pady=6
        )
        bundle_btn.pack(side=tk.LEFT)

        close_btn = ModernButton(
            actions, text="Close", style="primary",
            font=FONTS.body(), command=self.destroy,
            padx=20, pady=6
        )
        close_btn.pack(side=tk.RIGHT)

        tk.Label(
            footer_content, textvariable=self.status_var, bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.small(), anchor="w",
            wraplength=650, justify=tk.LEFT
        ).pack(fill=tk.X, pady=(8, 0))
    
    def _create_about_tab(self, notebook, theme):
        """Create About tab"""
        frame = tk.Frame(notebook, bg=theme.bg_primary)
        notebook.add(frame, text="  About  ")
        
        text = tk.Text(
            frame, bg=theme.bg_primary, fg=theme.text_primary,
            font=FONTS.body(), relief=tk.FLAT, padx=15, pady=15,
            wrap=tk.WORD, cursor="arrow", highlightthickness=0
        )
        text.pack(fill=tk.BOTH, expand=True)
        
        content = f"""
{APP_NAME} is a powerful, professional-grade bookmark manager designed for users who need advanced organization capabilities.

Built with Python and Tkinter, this application offers a modern, themeable interface with features typically found in commercial software.

Key Highlights:
• Import bookmarks from Chrome, Firefox, Edge, Safari
• AI-powered categorization and tagging
• Advanced search with boolean operators
• Beautiful themes (10+ built-in)
• Full undo/redo support

Build: {BUILD_TYPE}
Date: {BUILD_DATE}
License: {LICENSE}
"""
        text.insert(tk.END, content.strip())
        text.configure(state=tk.DISABLED)
    
    def _create_features_tab(self, notebook, theme):
        """Create Features tab"""
        frame = tk.Frame(notebook, bg=theme.bg_primary)
        notebook.add(frame, text="  Features  ")
        
        # Scrollable list
        canvas = tk.Canvas(frame, bg=theme.bg_primary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=canvas.yview)
        inner = tk.Frame(canvas, bg=theme.bg_primary)
        
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw", width=470)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        features = [
            ("Import/Export", "HTML, JSON, CSV, and OPML formats"),
            ("Categories", "Nested hierarchy with auto-categorization"),
            ("Tags", "User tags plus AI suggestions"),
            ("Search", "Advanced syntax with filters and highlighting"),
            ("AI Features", "Auto-categorize, generate tags, and summarize"),
            ("Themes", "Built-in themes and a custom theme creator"),
            ("Analytics", "Collection health, cleanup signals, and insights"),
            ("Navigation", "Keyboard-friendly navigation and command actions"),
            ("Undo/Redo", "Bookmark-level action history"),
            ("Link Checker", "Validate bookmark URLs"),
            ("Favicons", "Automatic favicon downloading and caching"),
        ]
        
        for i, (name, desc) in enumerate(features):
            row = tk.Frame(inner, bg=theme.bg_secondary if i % 2 == 0 else theme.bg_primary)
            row.pack(fill=tk.X, pady=1)
            
            tk.Label(row, text=name, font=FONTS.body(bold=True),
                    bg=row.cget("bg"), fg=theme.text_primary, width=14,
                    anchor="w").pack(side=tk.LEFT, padx=(12, 8), pady=8)
            tk.Label(row, text=desc, font=FONTS.body(),
                    bg=row.cget("bg"), fg=theme.text_secondary,
                    anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10), pady=8)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def _create_system_tab(self, notebook, theme):
        """Create System info tab"""
        frame = tk.Frame(notebook, bg=theme.bg_primary)
        notebook.add(frame, text="  System  ")
        
        text = tk.Text(
            frame, bg=theme.bg_primary, fg=theme.text_primary,
            font=FONTS.mono(),
            relief=tk.FLAT, padx=15, pady=15, wrap=tk.WORD,
            cursor="arrow", highlightthickness=0
        )
        text.pack(fill=tk.BOTH, expand=True)
        
        info = f"""
APPLICATION
───────────────────────────────────
Name:           {APP_NAME}
Version:        {APP_VERSION}
Build:          {BUILD_TYPE}
Build Date:     {BUILD_DATE}

ENVIRONMENT
───────────────────────────────────
Python:         {sys.version.split()[0]}
Platform:       {platform.system()} {platform.release()}
Architecture:   {platform.machine()}
Tk Version:     {tk.TkVersion}

OPTIONAL FEATURES
───────────────────────────────────
PIL (Pillow):   {'Available' if HAS_PIL else 'Not installed'}
System Tray:    {'Available' if HAS_TRAY else 'Not installed'}

DATA LOCATIONS
───────────────────────────────────
Data Directory: {APP_DIR}
Bookmarks:      {MASTER_BOOKMARKS_FILE.name}
Settings:       {SETTINGS_FILE.name}
Logs:           {LOG_FILE.name}
"""
        text.insert(tk.END, info.strip())
        text.configure(state=tk.DISABLED)
    
    def _create_credits_tab(self, notebook, theme):
        """Create Credits tab"""
        frame = tk.Frame(notebook, bg=theme.bg_primary)
        notebook.add(frame, text="  Credits  ")
        
        text = tk.Text(
            frame, bg=theme.bg_primary, fg=theme.text_primary,
            font=FONTS.body(), relief=tk.FLAT, padx=15, pady=15,
            wrap=tk.WORD, cursor="arrow", highlightthickness=0
        )
        text.pack(fill=tk.BOTH, expand=True)
        
        credits = f"""
TECHNOLOGIES
───────────────────────────────────
• Python 3.10+
• Tkinter/ttk (GUI framework)
• BeautifulSoup (HTML parsing)
• Pillow (Image processing)
• Requests (HTTP client)

THEME INSPIRATIONS
───────────────────────────────────
GitHub • Dracula • Nord • Monokai Pro
One Dark • Tokyo Night • Gruvbox
Solarized • Catppuccin

LICENSE
───────────────────────────────────
{LICENSE}
Copyright © {COPYRIGHT_YEAR}

Permission is hereby granted, free of charge, 
to any person obtaining a copy of this software
to deal in the Software without restriction.
"""
        text.insert(tk.END, credits.strip())
        text.configure(state=tk.DISABLED)
    
    def _copy_system_info(self):
        """Copy system info to clipboard"""
        info = format_diagnostics(build_diagnostics_snapshot())
        
        self.clipboard_clear()
        self.clipboard_append(info)
        self._set_status("Diagnostics copied to clipboard.")

    def _open_logs(self):
        """Open the logs directory in the OS file manager."""
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(LOG_FILE.parent)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(LOG_FILE.parent)])
            else:
                subprocess.Popen(["xdg-open", str(LOG_FILE.parent)])
            self._set_status(f"Opened logs: {LOG_FILE.parent}")
        except Exception as exc:
            self._set_status(f"Could not open logs: {exc}")

    def _export_support_bundle(self):
        """Export a redacted support bundle."""
        try:
            bundle_path = export_redacted_support_bundle()
            self._set_status(f"Redacted support bundle exported: {bundle_path}")
        except Exception as exc:
            self._set_status(f"Support bundle export failed: {exc}")

    def _set_status(self, message: str):
        self.status_var.set(message)
