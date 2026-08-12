"""About dialog and build metadata for the desktop UI."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, ttk

try:
    import PIL  # noqa: F401
    HAS_PIL = True
except ImportError:  # pragma: no cover - optional runtime dependency
    HAS_PIL = False

from bookmark_organizer_pro.constants import (
    APP_DIR,
    APP_NAME,
    APP_SUBTITLE,
    APP_VERSION,
    LOG_FILE,
    MASTER_BOOKMARKS_FILE,
    SETTINGS_FILE,
    SUPPORT_BUNDLES_DIR,
)
from bookmark_organizer_pro.i18n import _, layout_anchor, layout_side
from bookmark_organizer_pro.services.local_state import (
    build_diagnostics_snapshot,
    build_support_bundle_preview,
    export_redacted_support_bundle,
    format_diagnostics,
)

from .foundation import FONTS, readable_text_on
from .tk_interactions import bind_scoped_mousewheel
from .widgets import ModernButton, get_theme
from .window_geometry import apply_screen_aware_geometry

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
        
        self.title(_("About {app_name}").format(app_name=APP_NAME))
        apply_screen_aware_geometry(self, 700, 640)
        self.minsize(520, 420)
        self.resizable(True, True)
        self.configure(bg=theme.bg_primary)
        
        # Make modal
        self.transient(parent)
        self.grab_set()
        
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
            header_content, text=_("B"), font=FONTS.display(),
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
            header_content, text=_("Version {version}").format(version=APP_VERSION),
            font=FONTS.body(), bg=theme.bg_secondary, fg=theme.text_secondary
        ).pack()
        
        # Subtitle
        tk.Label(
            header_content, text=APP_SUBTITLE,
            font=FONTS.small(), bg=theme.bg_secondary, fg=theme.text_muted
        ).pack(pady=(4, 0))
        
        # Pack the fixed footer before the expanding notebook so the action
        # row always receives its requested height on short displays.
        self.footer = tk.Frame(self, bg=theme.bg_secondary)
        self.footer.pack(fill=tk.X, side=tk.BOTTOM)
        
        footer_content = tk.Frame(self.footer, bg=theme.bg_secondary)
        footer_content.pack(pady=12, padx=15, fill=tk.X)
        self._about_footer_content = footer_content

        actions = tk.Frame(footer_content, bg=theme.bg_secondary)
        actions.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._about_actions = actions

        self.about_action_buttons = {}
        logs_btn = ModernButton(
            actions, text=_("Open Logs"),
            font=FONTS.small(), command=self._open_logs,
            padx=12, pady=6
        )
        logs_btn.pack(side=layout_side(tk.LEFT), padx=(0, 8))
        self.about_action_buttons["logs"] = logs_btn

        copy_btn = ModernButton(
            actions, text=_("Copy Diagnostics"),
            font=FONTS.small(), command=self._copy_system_info,
            padx=12, pady=6
        )
        copy_btn.pack(side=layout_side(tk.LEFT), padx=(0, 8))
        self.about_action_buttons["copy"] = copy_btn

        bundle_btn = ModernButton(
            actions, text=_("Preview Support Bundle"),
            font=FONTS.small(), command=self._export_support_bundle,
            padx=12, pady=6
        )
        bundle_btn.pack(side=layout_side(tk.LEFT))
        self.about_action_buttons["bundle"] = bundle_btn

        close_btn = ModernButton(
            footer_content, text=_("Close"), style="primary",
            font=FONTS.body(), command=self.destroy,
            padx=20, pady=6
        )
        close_btn.pack(side=layout_side(tk.RIGHT))
        self.about_action_buttons["close"] = close_btn
        self._about_close_button = close_btn

        tk.Label(
            footer_content, textvariable=self.status_var, bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.small(), anchor=layout_anchor("w"),
            wraplength=650, justify=tk.LEFT
        ).pack(fill=tk.X, pady=(8, 0))

        self._about_footer_wrapped = False
        self.after_idle(self._fit_footer_actions)
        self.bind("<Configure>", lambda _event: self.after_idle(self._fit_footer_actions), add="+")

        # Tab notebook
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

        # Create tabs
        self._create_about_tab(notebook, theme)
        self._create_features_tab(notebook, theme)
        self._create_system_tab(notebook, theme)
        self._create_credits_tab(notebook, theme)

    def _fit_footer_actions(self) -> None:
        """Reflow the Close action when DPI-scaled utility buttons need room."""
        if not self.winfo_exists() or not hasattr(self, "_about_close_button"):
            return
        self._about_footer_content.update_idletasks()
        available_width = self._about_footer_content.winfo_width()
        primary_width = 0
        for button in self.about_action_buttons.values():
            if button is self._about_close_button:
                continue
            pack_info = button.pack_info()
            try:
                horizontal_pad = int(pack_info.get("padx", 0)) * 2
            except (TypeError, ValueError):
                horizontal_pad = 0
            primary_width += max(button.winfo_width(), button.winfo_reqwidth()) + horizontal_pad
        required_width = (
            primary_width
            + max(
                self._about_close_button.winfo_width(),
                self._about_close_button.winfo_reqwidth(),
            )
            + 8
        )
        should_wrap = required_width > available_width
        if should_wrap == self._about_footer_wrapped:
            return
        self._about_actions.pack_forget()
        self._about_close_button.pack_forget()
        if should_wrap:
            self._about_actions.pack(side=tk.TOP, fill=tk.X, expand=False)
            self._about_close_button.pack(side=tk.TOP, anchor="e", pady=(8, 0))
        else:
            self._about_actions.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._about_close_button.pack(side=layout_side(tk.RIGHT))
        self._about_footer_wrapped = should_wrap
    
    def _create_about_tab(self, notebook, theme):
        """Create About tab"""
        frame = tk.Frame(notebook, bg=theme.bg_primary)
        notebook.add(frame, text="  " + _("About") + "  ")
        
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
        notebook.add(frame, text="  " + _("Features") + "  ")
        
        # Scrollable list
        canvas = tk.Canvas(frame, bg=theme.bg_primary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=canvas.yview)
        inner = tk.Frame(canvas, bg=theme.bg_primary)
        
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw", width=470)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        features = [
            (_("Import/Export"), _("HTML, JSON, CSV, and OPML formats")),
            (_("Categories"), _("Nested hierarchy with auto-categorization")),
            (_("Tags"), _("User tags plus AI suggestions")),
            (_("Search"), _("Advanced syntax with filters and highlighting")),
            (_("AI Features"), _("Auto-categorize, generate tags, and summarize")),
            (_("Themes"), _("Built-in themes and a custom theme creator")),
            (_("Analytics"), _("Collection health, cleanup signals, and insights")),
            (_("Navigation"), _("Keyboard-friendly navigation and command actions")),
            (_("Undo/Redo"), _("Bookmark-level action history")),
            (_("Link Checker"), _("Validate bookmark URLs")),
            (
                _("Favicons"),
                _("Opt-in site icons with same-origin-first fetching and named proxy consent"),
            ),
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
        bind_scoped_mousewheel(
            canvas, lambda units, _event: canvas.yview_scroll(units, "units")
        )
    
    def _create_system_tab(self, notebook, theme):
        """Create System info tab"""
        frame = tk.Frame(notebook, bg=theme.bg_primary)
        notebook.add(frame, text="  " + _("System") + "  ")
        
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
        notebook.add(frame, text="  " + _("Credits") + "  ")
        
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
        self._set_status(_("Diagnostics copied to clipboard."))

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
            self._set_status(_("Opened logs: {path}").format(path=LOG_FILE.parent))
        except Exception as exc:
            self._set_status(_("Could not open logs: {error}").format(error=exc))

    def _export_support_bundle(self):
        """Preview every exact text payload before offering a save destination."""
        theme = get_theme()
        preview_window = tk.Toplevel(self)
        preview_window.title(_("Content-private support bundle preview"))
        apply_screen_aware_geometry(preview_window, 840, 680)
        preview_window.minsize(640, 480)
        preview_window.configure(bg=theme.bg_primary)
        preview_window.transient(self)
        preview_window.grab_set()

        header = tk.Frame(preview_window, bg=theme.bg_secondary, padx=18, pady=14)
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text=_("Review the exact files before saving"),
            bg=theme.bg_secondary,
            fg=theme.text_primary,
            font=FONTS.header(bold=True),
            anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            header,
            text=_(
                "Nothing is written until Save Bundle. Free-form log messages, "
                "bookmark content, local paths, and URL details are excluded."
            ),
            bg=theme.bg_secondary,
            fg=theme.text_secondary,
            font=FONTS.small(),
            anchor="w",
            justify=tk.LEFT,
            wraplength=790,
        ).pack(fill=tk.X, pady=(5, 0))

        retain_hosts = tk.BooleanVar(value=False)
        host_option = tk.Checkbutton(
            preview_window,
            text=_("Include website hostnames (paths, queries, and fragments stay excluded)"),
            variable=retain_hosts,
            bg=theme.bg_primary,
            fg=theme.text_primary,
            activebackground=theme.bg_primary,
            activeforeground=theme.text_primary,
            selectcolor=theme.bg_secondary,
            font=FONTS.small(),
            anchor="w",
        )
        host_option.pack(fill=tk.X, padx=18, pady=(12, 6))

        text_frame = tk.Frame(preview_window, bg=theme.bg_primary)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 10))
        preview_text = tk.Text(
            text_frame,
            wrap=tk.NONE,
            bg=theme.bg_dark,
            fg=theme.text_primary,
            insertbackground=theme.text_primary,
            selectbackground=theme.accent_primary,
            selectforeground=readable_text_on(theme.accent_primary),
            font=FONTS.mono(),
            relief=tk.FLAT,
            padx=10,
            pady=10,
        )
        y_scroll = ttk.Scrollbar(
            text_frame,
            orient=tk.VERTICAL,
            command=preview_text.yview,
        )
        x_scroll = ttk.Scrollbar(
            text_frame,
            orient=tk.HORIZONTAL,
            command=preview_text.xview,
        )
        preview_text.configure(
            yscrollcommand=y_scroll.set,
            xscrollcommand=x_scroll.set,
        )
        preview_text.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        status_var = tk.StringVar(value="")
        preview_payload = {"value": None}

        def refresh_preview():
            try:
                payload = build_support_bundle_preview(
                    retain_url_hosts=bool(retain_hosts.get())
                )
                preview_payload["value"] = payload
                preview_text.configure(state=tk.NORMAL)
                preview_text.delete("1.0", tk.END)
                preview_text.insert("1.0", payload.render())
                preview_text.configure(state=tk.DISABLED)
                status_var.set(
                    _("{count} allowlisted text files ready for review").format(
                        count=len(payload.files)
                    )
                )
            except Exception as exc:
                preview_payload["value"] = None
                status_var.set(
                    _("Could not build support preview: {error}").format(error=exc)
                )

        host_option.configure(command=refresh_preview)

        footer = tk.Frame(preview_window, bg=theme.bg_secondary, padx=18, pady=12)
        text_frame.pack_forget()
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 10))
        tk.Label(
            footer,
            textvariable=status_var,
            bg=theme.bg_secondary,
            fg=theme.text_secondary,
            font=FONTS.small(),
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        def close_preview():
            try:
                preview_window.grab_release()
            except tk.TclError:
                pass
            preview_window.destroy()
            if self.winfo_exists():
                self.grab_set()

        def save_preview():
            payload = preview_payload["value"]
            if payload is None:
                return
            SUPPORT_BUNDLES_DIR.mkdir(parents=True, exist_ok=True)
            destination = filedialog.asksaveasfilename(
                parent=preview_window,
                title=_("Save content-private support bundle"),
                initialdir=str(SUPPORT_BUNDLES_DIR),
                initialfile=f"support_bundle_{datetime.now():%Y%m%d_%H%M%S}.zip",
                defaultextension=".zip",
                filetypes=[(_("ZIP archive"), "*.zip")],
            )
            if not destination:
                return
            try:
                bundle_path = export_redacted_support_bundle(
                    destination,
                    preview=payload,
                )
                self._set_status(
                    _("Content-private support bundle exported: {path}").format(
                        path=bundle_path
                    )
                )
                close_preview()
            except Exception as exc:
                status_var.set(
                    _("Support bundle export failed: {error}").format(error=exc)
                )

        ModernButton(
            footer,
            text=_("Save Bundle…"),
            command=save_preview,
            style="primary",
            padx=16,
            pady=6,
        ).pack(side=tk.RIGHT, padx=(8, 0))
        ModernButton(
            footer,
            text=_("Cancel"),
            command=close_preview,
            padx=14,
            pady=6,
        ).pack(side=tk.RIGHT)

        preview_window.protocol("WM_DELETE_WINDOW", close_preview)
        preview_window.bind("<Escape>", lambda _event: close_preview())
        refresh_preview()
        preview_text.focus_set()

    def _set_status(self, message: str):
        self.status_var.set(_(message))
