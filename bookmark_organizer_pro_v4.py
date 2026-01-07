#!/usr/bin/env python3
"""
Bookmark Organizer Pro - Ultimate Edition v4.1.0
=================================================
A powerful, modern bookmark manager with:
- Multi-theme system with 10+ built-in themes
- Nested category hierarchy
- Full tagging system
- Grid/Card and List views
- Advanced search syntax
- Analytics dashboard
- System tray integration
- Enhanced favicon caching
- Professional UI with DPI awareness

Version 4.1.0 - January 2026
"""

# =============================================================================
# IMPORTS - Core Python
# =============================================================================
import multiprocessing
import subprocess
import sys
import os
import platform
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser
from pathlib import Path
import webbrowser
import threading
import time
import json
import re
import hashlib
import html as html_module
import queue
import csv
import urllib.parse
import shutil
import tempfile
import importlib
import logging
import traceback
import ctypes
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Callable, Tuple, Set, Union
from enum import Enum
from datetime import datetime, timedelta
from collections import OrderedDict, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import base64
from io import BytesIO

# =============================================================================
# Application Constants
# =============================================================================
APP_NAME = "Bookmark Organizer Pro"
APP_VERSION = "4.1.0"
APP_SUBTITLE = "Ultimate Bookmark Management"

# =============================================================================
# Path Constants
# =============================================================================
APP_DIR = Path.home() / ".bookmark_organizer"
APP_DIR.mkdir(exist_ok=True)
FAVICON_DIR = APP_DIR / "favicons"
FAVICON_DIR.mkdir(exist_ok=True)
CACHE_DIR = APP_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)
BACKUP_DIR = APP_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)
THEMES_DIR = APP_DIR / "themes"
THEMES_DIR.mkdir(exist_ok=True)
SCREENSHOTS_DIR = APP_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)
LOGS_DIR = APP_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

DATA_DIR = APP_DIR
MASTER_BOOKMARKS_FILE = DATA_DIR / "master_bookmarks.json"
FAILED_FAVICONS_FILE = DATA_DIR / "failed_favicons.json"
CATEGORIES_FILE = DATA_DIR / "categories.json"
AI_CONFIG_FILE = DATA_DIR / "ai_config.json"
PATTERNS_FILE = DATA_DIR / "patterns.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
TAGS_FILE = DATA_DIR / "tags.json"
LOG_FILE = LOGS_DIR / "bookmark_organizer.log"

# Platform detection
IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

# =============================================================================
# LOGGING SYSTEM - Professional structured logging
# =============================================================================
class AppLogger:
    """
        Centralized logging system for the application.
        
        Provides structured logging to both file and optional console output.
        Implements singleton pattern to ensure consistent logging throughout
        the application.
        
        Attributes:
            logger: The underlying Python logger instance
            console_handler: Handler for console output (optional)
        
        Configuration:
            Set BOOKMARK_DEBUG=1 environment variable to enable console logging.
            Logs are written to ~/.bookmark_organizer/logs/bookmark_organizer.log
        
        Example:
            >>> log = AppLogger()
            >>> log.info("Application started")
            >>> log.error("Something went wrong", exc_info=True)
        """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if AppLogger._initialized:
            return
        
        AppLogger._initialized = True
        
        # Create logger
        self.logger = logging.getLogger("BookmarkOrganizer")
        self.logger.setLevel(logging.DEBUG)
        
        # File handler - always log to file
        try:
            file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_format = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_format)
            self.logger.addHandler(file_handler)
        except Exception:
            pass  # Fail silently if can't write to log file
        
        # Console handler - only in debug mode
        self.console_handler = None
        if os.environ.get('BOOKMARK_DEBUG', '').lower() in ('1', 'true', 'yes'):
            self.enable_console()
    
    def enable_console(self):
        """Enable console logging"""
        if self.console_handler is None:
            self.console_handler = logging.StreamHandler(sys.stdout)
            self.console_handler.setLevel(logging.INFO)
            console_format = logging.Formatter('%(levelname)s: %(message)s')
            self.console_handler.setFormatter(console_format)
            self.logger.addHandler(self.console_handler)
    
    def disable_console(self):
        """Disable console logging"""
        if self.console_handler:
            self.logger.removeHandler(self.console_handler)
            self.console_handler = None
    
    def debug(self, msg, *args, **kwargs):
        self.logger.debug(msg, *args, **kwargs)
    
    def info(self, msg, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)
    
    def warning(self, msg, *args, **kwargs):
        self.logger.warning(msg, *args, **kwargs)
    
    def error(self, msg, *args, **kwargs):
        self.logger.error(msg, *args, **kwargs)
    
    def exception(self, msg, *args, **kwargs):
        self.logger.exception(msg, *args, **kwargs)
    
    def critical(self, msg, *args, **kwargs):
        self.logger.critical(msg, *args, **kwargs)


# Global logger instance
log = AppLogger()
log.info(f"Starting {APP_NAME} v{APP_VERSION}")

# =============================================================================
# DPI AWARENESS - Windows High DPI support
# =============================================================================
def setup_dpi_awareness():
    """Configure DPI awareness for crisp rendering on high-DPI displays"""
    if IS_WINDOWS:
        try:
            # Try Windows 10 1703+ API first
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
            log.debug("DPI awareness set: Per-monitor DPI aware v2")
        except AttributeError:
            try:
                # Fall back to Windows 8.1+ API
                ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE
                log.debug("DPI awareness set: System DPI aware")
            except AttributeError:
                try:
                    # Fall back to Windows Vista+ API
                    ctypes.windll.user32.SetProcessDPIAware()
                    log.debug("DPI awareness set: DPI aware (legacy)")
                except Exception as e:
                    log.warning(f"Could not set DPI awareness: {e}")
        except Exception as e:
            log.warning(f"Could not set DPI awareness: {e}")

# Apply DPI awareness early
setup_dpi_awareness()

# =============================================================================
# FONT SYSTEM - Cross-platform typography
# =============================================================================
@dataclass
class FontConfig:
    """
        Centralized font configuration for consistent typography.
        
        Provides standardized font sizes and styles across the application,
        with platform-specific font family selection.
        
        Attributes:
            family: The font family name (platform-dependent)
            size_title: Font size for titles (16pt)
            size_header: Font size for headers (12pt)
            size_body: Font size for body text (10pt)
            size_small: Font size for small text (9pt)
            size_tiny: Font size for tiny text (8pt)
        
        Example:
            >>> fonts = FontConfig(family="Segoe UI")
            >>> label.configure(font=fonts.body())
            >>> header.configure(font=fonts.header(bold=True))
        """
    family: str
    size_title: int = 16
    size_header: int = 12
    size_body: int = 10
    size_small: int = 9
    size_tiny: int = 8
    
    def title(self, bold: bool = True) -> Tuple[str, int, str]:
        return (self.family, self.size_title, "bold" if bold else "normal")
    
    def header(self, bold: bool = True) -> Tuple[str, int, str]:
        return (self.family, self.size_header, "bold" if bold else "normal")
    
    def body(self, bold: bool = False) -> Tuple[str, int, str]:
        return (self.family, self.size_body, "bold" if bold else "normal")
    
    def small(self, bold: bool = False) -> Tuple[str, int, str]:
        return (self.family, self.size_small, "bold" if bold else "normal")
    
    def tiny(self, bold: bool = False) -> Tuple[str, int, str]:
        return (self.family, self.size_tiny, "bold" if bold else "normal")
    
    def custom(self, size: int, bold: bool = False) -> Tuple[str, int, str]:
        return (self.family, size, "bold" if bold else "normal")


def get_system_font() -> str:
    """Get the best available system font for the platform"""
    if IS_WINDOWS:
        return "Segoe UI"
    elif IS_MAC:
        # Try SF Pro, fall back to Helvetica Neue
        return "SF Pro Display"
    else:  # Linux
        return "DejaVu Sans"


# Global font configuration
FONTS = FontConfig(family=get_system_font())

# =============================================================================
# DESIGN TOKENS - Consistent spacing and sizing
# =============================================================================
class DesignTokens:
    """
        Centralized design tokens for consistent UI spacing and sizing.
        
        Contains all spacing, sizing, and animation constants used throughout
        the application to ensure visual consistency.
        
        Class Attributes:
            SPACE_XS through SPACE_XXL: Spacing scale (4px to 32px)
            RADIUS_SM/MD/LG: Border radius values
            BUTTON_HEIGHT, INPUT_HEIGHT, ROW_HEIGHT: Component heights
            ICON_SM/MD/LG: Icon size constants
            SIDEBAR_WIDTH: Default sidebar width
            ANIMATION_FAST/NORMAL/SLOW: Animation duration in milliseconds
        
        Example:
            >>> frame.configure(padx=DesignTokens.SPACE_MD)
            >>> button.configure(height=DesignTokens.BUTTON_HEIGHT)
        """
    # Spacing scale (in pixels)
    SPACE_XS = 4
    SPACE_SM = 8
    SPACE_MD = 12
    SPACE_LG = 16
    SPACE_XL = 24
    SPACE_XXL = 32
    
    # Border radius
    RADIUS_SM = 4
    RADIUS_MD = 6
    RADIUS_LG = 8
    
    # Component heights
    BUTTON_HEIGHT = 32
    INPUT_HEIGHT = 34
    ROW_HEIGHT = 28
    TREEVIEW_ROW_HEIGHT = 26
    
    # Icon sizes
    ICON_SM = 16
    ICON_MD = 20
    ICON_LG = 24
    
    # Sidebar width
    SIDEBAR_WIDTH = 240
    SIDEBAR_MIN_WIDTH = 200
    
    # Animation durations (ms)
    ANIMATION_FAST = 100
    ANIMATION_NORMAL = 200
    ANIMATION_SLOW = 300


# =============================================================================
# DEPENDENCY MANAGEMENT - Professional first-run experience
# =============================================================================
class DependencyManager:
    """
        Manages package dependencies with installation capabilities.
        
        Handles checking for required and optional Python packages,
        installing missing packages, and tracking installation status.
        
        Attributes:
            REQUIRED_PACKAGES: Dict of packages that must be installed
            OPTIONAL_PACKAGES: Dict of packages that enhance functionality
            missing_required: List of missing required packages
            missing_optional: List of missing optional packages
            installed: Dict tracking installation status
            install_errors: Dict of installation error messages
        
        Methods:
            check_all(): Check status of all dependencies
            install_package(package): Install a single package
            install_all_missing(): Install all missing packages
        
        Example:
            >>> dm = DependencyManager()
            >>> ok, missing_req, missing_opt = dm.check_all()
            >>> if not ok:
            ...     dm.install_all_missing()
        """
    
    REQUIRED_PACKAGES = {
        "beautifulsoup4": {"import_name": "bs4", "required": True, "description": "HTML parsing for bookmark import"},
        "requests": {"import_name": "requests", "required": True, "description": "HTTP requests for favicon download"},
    }
    
    OPTIONAL_PACKAGES = {
        "Pillow": {"import_name": "PIL", "required": False, "description": "Image processing for favicons"},
        "pystray": {"import_name": "pystray", "required": False, "description": "System tray integration"},
    }
    
    def __init__(self):
        self.missing_required: List[str] = []
        self.missing_optional: List[str] = []
        self.installed: Dict[str, bool] = {}
        self.install_errors: Dict[str, str] = {}
    
    def check_all(self) -> Tuple[bool, List[str], List[str]]:
        """Check all dependencies, return (all_required_ok, missing_required, missing_optional)"""
        self.missing_required = []
        self.missing_optional = []
        
        # Check required packages
        for package, info in self.REQUIRED_PACKAGES.items():
            if not self._is_installed(info["import_name"]):
                self.missing_required.append(package)
                self.installed[package] = False
            else:
                self.installed[package] = True
        
        # Check optional packages
        for package, info in self.OPTIONAL_PACKAGES.items():
            if not self._is_installed(info["import_name"]):
                self.missing_optional.append(package)
                self.installed[package] = False
            else:
                self.installed[package] = True
        
        all_required_ok = len(self.missing_required) == 0
        return all_required_ok, self.missing_required, self.missing_optional
    
    def _is_installed(self, import_name: str) -> bool:
        """Check if a package is installed"""
        try:
            importlib.import_module(import_name)
            return True
        except ImportError:
            return False
    
    def install_package(self, package: str, progress_callback: Optional[Callable] = None) -> bool:
        """Install a single package"""
        log.info(f"Installing package: {package}")
        if progress_callback:
            progress_callback(f"Installing {package}...")
        
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", package, "--quiet"],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                log.info(f"Successfully installed {package}")
                self.installed[package] = True
                return True
            else:
                error_msg = result.stderr or "Unknown error"
                log.error(f"Failed to install {package}: {error_msg}")
                self.install_errors[package] = error_msg
                return False
        except subprocess.TimeoutExpired:
            log.error(f"Timeout installing {package}")
            self.install_errors[package] = "Installation timed out"
            return False
        except Exception as e:
            log.error(f"Error installing {package}: {e}")
            self.install_errors[package] = str(e)
            return False
    
    def install_all_missing(self, progress_callback: Optional[Callable] = None) -> bool:
        """Install all missing packages"""
        all_missing = self.missing_required + self.missing_optional
        success = True
        
        for i, package in enumerate(all_missing):
            if progress_callback:
                progress_callback(f"Installing {package} ({i+1}/{len(all_missing)})...")
            
            if not self.install_package(package):
                if package in self.missing_required:
                    success = False
        
        return success


class DependencyCheckDialog(tk.Toplevel):
    """
        Professional dialog for first-run dependency checking.
        
        Displays missing packages to the user and provides options to
        install them or continue without optional features.
        
        Attributes:
            parent: Parent Tk window
            dep_manager: DependencyManager instance
            result: Boolean indicating if OK to proceed
        
        Features:
            - Shows required packages (must install) in red
            - Shows optional packages (recommended) in yellow
            - Progress bar during installation
            - "Continue Without Optional" button when appropriate
        """
    
    def __init__(self, parent: tk.Tk, dep_manager: DependencyManager):
        super().__init__(parent)
        self.parent = parent
        self.dep_manager = dep_manager
        self.result = False  # True if OK to proceed
        
        self.title(f"{APP_NAME} - Dependency Check")
        self.geometry("500x400")
        self.resizable(False, False)
        self.configure(bg="#1e1e2e")
        
        # Make modal
        self.transient(parent)
        self.grab_set()
        
        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 500) // 2
        y = (self.winfo_screenheight() - 400) // 2
        self.geometry(f"+{x}+{y}")
        
        self._create_ui()
        
        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
    
    def _create_ui(self):
        """Create the dialog UI"""
        # Header
        header = tk.Frame(self, bg="#313244", padx=20, pady=15)
        header.pack(fill=tk.X)
        
        tk.Label(
            header, text="📦 Dependency Check",
            font=(FONTS.family, 14, "bold"),
            bg="#313244", fg="#cdd6f4"
        ).pack(anchor="w")
        
        tk.Label(
            header, text="Some packages need to be installed for full functionality.",
            font=(FONTS.family, 10),
            bg="#313244", fg="#a6adc8"
        ).pack(anchor="w", pady=(5, 0))
        
        # Content
        content = tk.Frame(self, bg="#1e1e2e", padx=20, pady=15)
        content.pack(fill=tk.BOTH, expand=True)
        
        # Required packages section
        if self.dep_manager.missing_required:
            tk.Label(
                content, text="Required Packages (must install):",
                font=(FONTS.family, 10, "bold"),
                bg="#1e1e2e", fg="#f38ba8"
            ).pack(anchor="w", pady=(0, 5))
            
            for pkg in self.dep_manager.missing_required:
                info = self.dep_manager.REQUIRED_PACKAGES[pkg]
                frame = tk.Frame(content, bg="#1e1e2e")
                frame.pack(fill=tk.X, pady=2)
                tk.Label(
                    frame, text=f"  ❌ {pkg}",
                    font=(FONTS.family, 10),
                    bg="#1e1e2e", fg="#cdd6f4"
                ).pack(side=tk.LEFT)
                tk.Label(
                    frame, text=f"- {info['description']}",
                    font=(FONTS.family, 9),
                    bg="#1e1e2e", fg="#6c7086"
                ).pack(side=tk.LEFT, padx=(10, 0))
        
        # Optional packages section
        if self.dep_manager.missing_optional:
            tk.Label(
                content, text="Optional Packages (recommended):",
                font=(FONTS.family, 10, "bold"),
                bg="#1e1e2e", fg="#f9e2af"
            ).pack(anchor="w", pady=(15, 5))
            
            for pkg in self.dep_manager.missing_optional:
                info = self.dep_manager.OPTIONAL_PACKAGES[pkg]
                frame = tk.Frame(content, bg="#1e1e2e")
                frame.pack(fill=tk.X, pady=2)
                tk.Label(
                    frame, text=f"  ⚠️ {pkg}",
                    font=(FONTS.family, 10),
                    bg="#1e1e2e", fg="#cdd6f4"
                ).pack(side=tk.LEFT)
                tk.Label(
                    frame, text=f"- {info['description']}",
                    font=(FONTS.family, 9),
                    bg="#1e1e2e", fg="#6c7086"
                ).pack(side=tk.LEFT, padx=(10, 0))
        
        # Progress area
        self.progress_frame = tk.Frame(content, bg="#1e1e2e")
        self.progress_frame.pack(fill=tk.X, pady=(20, 0))
        
        self.progress_label = tk.Label(
            self.progress_frame, text="",
            font=(FONTS.family, 9),
            bg="#1e1e2e", fg="#a6adc8"
        )
        self.progress_label.pack(anchor="w")
        
        self.progress_bar = ttk.Progressbar(
            self.progress_frame, mode="indeterminate", length=300
        )
        
        # Buttons
        btn_frame = tk.Frame(self, bg="#313244", padx=20, pady=15)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.install_btn = tk.Button(
            btn_frame, text="Install All",
            font=(FONTS.family, 10),
            bg="#89b4fa", fg="#1e1e2e",
            activebackground="#b4befe", activeforeground="#1e1e2e",
            relief=tk.FLAT, padx=20, pady=8,
            cursor="hand2",
            command=self._on_install
        )
        self.install_btn.pack(side=tk.RIGHT)
        
        # Show "Continue without optional" only if required packages are installed
        if not self.dep_manager.missing_required:
            self.skip_btn = tk.Button(
                btn_frame, text="Continue Without Optional",
                font=(FONTS.family, 10),
                bg="#45475a", fg="#cdd6f4",
                activebackground="#585b70", activeforeground="#cdd6f4",
                relief=tk.FLAT, padx=15, pady=8,
                cursor="hand2",
                command=self._on_skip
            )
            self.skip_btn.pack(side=tk.RIGHT, padx=(0, 10))
        
        tk.Button(
            btn_frame, text="Cancel",
            font=(FONTS.family, 10),
            bg="#45475a", fg="#cdd6f4",
            activebackground="#585b70", activeforeground="#cdd6f4",
            relief=tk.FLAT, padx=15, pady=8,
            cursor="hand2",
            command=self._on_cancel
        ).pack(side=tk.LEFT)
    
    def _on_install(self):
        """Handle install button click"""
        self.install_btn.configure(state=tk.DISABLED)
        self.progress_bar.pack(fill=tk.X, pady=(5, 0))
        self.progress_bar.start(10)
        
        # Run installation in background
        def do_install():
            success = self.dep_manager.install_all_missing(
                progress_callback=lambda msg: self.after(0, lambda: self.progress_label.configure(text=msg))
            )
            self.after(0, lambda: self._installation_complete(success))
        
        threading.Thread(target=do_install, daemon=True).start()
    
    def _installation_complete(self, success: bool):
        """Handle installation completion"""
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        
        if success or not self.dep_manager.missing_required:
            self.progress_label.configure(text="✅ Installation complete!", fg="#a6e3a1")
            self.result = True
            self.after(1000, self.destroy)
        else:
            errors = "\n".join([f"{pkg}: {err}" for pkg, err in self.dep_manager.install_errors.items()])
            self.progress_label.configure(
                text=f"❌ Some installations failed. Check your internet connection.",
                fg="#f38ba8"
            )
            self.install_btn.configure(state=tk.NORMAL, text="Retry")
    
    def _on_skip(self):
        """Handle skip button click"""
        self.result = True
        self.destroy()
    
    def _on_cancel(self):
        """Handle cancel/close"""
        self.result = False
        self.destroy()


def check_and_install_dependencies(root: tk.Tk) -> bool:
    """Check dependencies and show dialog if needed"""
    dep_manager = DependencyManager()
    all_ok, missing_req, missing_opt = dep_manager.check_all()
    
    if all_ok and not missing_opt:
        log.info("All dependencies satisfied")
        return True
    
    if not missing_req and not missing_opt:
        return True
    
    # Show dependency dialog
    dialog = DependencyCheckDialog(root, dep_manager)
    root.wait_window(dialog)
    
    return dialog.result


# =============================================================================
# IMPORT DEPENDENCIES (after check)
# =============================================================================
def import_dependencies():
    """Import dependencies after they've been checked/installed"""
    global BeautifulSoup, requests, HAS_PIL, HAS_TRAY, Image, ImageTk, ImageDraw, ImageFont, pystray, TrayItem
    
    from bs4 import BeautifulSoup
    import requests
    
    try:
        from PIL import Image, ImageTk, ImageDraw, ImageFont
        HAS_PIL = True
    except ImportError:
        HAS_PIL = False
        log.warning("Pillow not available - some image features disabled")
    
    try:
        import pystray
        from pystray import MenuItem as TrayItem
        HAS_TRAY = True
    except ImportError:
        HAS_TRAY = False
        log.warning("pystray not available - system tray disabled")


# Placeholder globals until import
BeautifulSoup = None
requests = None
HAS_PIL = False
HAS_TRAY = False
Image = None
ImageTk = None
ImageDraw = None
ImageFont = None
pystray = None
TrayItem = None


def ensure_package(package: str, import_name: str = None):
    """Ensure a package is installed, install if missing"""
    import_name = import_name or package
    try:
        return importlib.import_module(import_name)
    except ImportError:
        log.info(f"Installing missing package: {package}")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", package, "-q"],
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
            return importlib.import_module(import_name)
        except Exception as e:
            log.error(f"Error installing {package}: {e}")
            raise ImportError(f"Could not install {package}. Please install it manually.")


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



@dataclass
class ThemeColors:
    """
        Complete color palette for a theme.
        
        Contains all color definitions used throughout the application,
        organized by category (backgrounds, text, accents, UI elements, etc.).
        
        Color Categories:
            Backgrounds: bg_dark, bg_primary, bg_secondary, bg_tertiary, bg_hover, bg_card
            Text: text_primary, text_secondary, text_muted, text_link
            Accents: accent_primary, accent_success, accent_warning, accent_error, etc.
            UI Elements: border, border_muted, border_active, selection, selected, hover
            Drag & Drop: drag_target, drag_target_bg, drop_zone, drop_zone_active
            Status: status_success, status_warning, status_error, status_info
            Scrollbar: scrollbar_bg, scrollbar_thumb, scrollbar_thumb_hover
            Cards: card_bg, card_border, card_hover
            Special: ai_accent, tag_bg, tag_text
        
        Methods:
            to_dict(): Convert to dictionary
            from_dict(d): Create from dictionary
        """
    # Backgrounds
    bg_dark: str = "#0d1117"
    bg_primary: str = "#161b22"
    bg_secondary: str = "#21262d"
    bg_tertiary: str = "#30363d"
    bg_hover: str = "#2d4a6f"
    bg_card: str = "#1c2128"
    
    # Text
    text_primary: str = "#f0f6fc"
    text_secondary: str = "#8b949e"
    text_muted: str = "#484f58"
    text_link: str = "#58a6ff"
    
    # Accents
    accent_primary: str = "#58a6ff"
    accent_success: str = "#3fb950"
    accent_warning: str = "#d29922"
    accent_error: str = "#f85149"
    accent_purple: str = "#a371f7"
    accent_cyan: str = "#39c5cf"
    accent_pink: str = "#db61a2"
    accent_orange: str = "#f0883e"
    
    # UI Elements
    border: str = "#30363d"
    border_muted: str = "#21262d"
    border_active: str = "#58a6ff"
    selection: str = "#264f78"
    selected: str = "#1f6feb"
    hover: str = "#30363d"
    
    # Drag & Drop
    drag_target: str = "#238636"
    drag_target_bg: str = "#1c4428"
    drop_zone: str = "#1a3a5c"
    drop_zone_active: str = "#264f78"
    drop_zone_border: str = "#58a6ff"
    
    # Status
    status_success: str = "#3fb950"
    status_warning: str = "#d29922"
    status_error: str = "#f85149"
    status_info: str = "#58a6ff"
    
    # Scrollbar
    scrollbar_bg: str = "#21262d"
    scrollbar_thumb: str = "#484f58"
    scrollbar_thumb_hover: str = "#6e7681"
    
    # Cards & Grid
    card_bg: str = "#161b22"
    card_border: str = "#30363d"
    card_hover: str = "#21262d"
    
    # Special
    ai_accent: str = "#a371f7"
    tag_bg: str = "#388bfd26"
    tag_text: str = "#58a6ff"
    
    def to_dict(self) -> Dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}
    
    @classmethod
    def from_dict(cls, d: Dict) -> "ThemeColors":
        return cls(**{k: v for k, v in d.items() if hasattr(cls, k) or k in cls.__dataclass_fields__})


@dataclass
class ThemeInfo:
    """
        Theme metadata and colors container.
        
        Combines theme identification information with its color palette.
        
        Attributes:
            name: Internal theme identifier (e.g., "github_dark")
            display_name: Human-readable name (e.g., "GitHub Dark")
            author: Theme creator (default: "Built-in")
            version: Theme version string
            description: Brief theme description
            is_dark: Boolean indicating dark vs light theme
            colors: ThemeColors instance with full color palette
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
        """
    name: str
    display_name: str
    author: str = "Built-in"
    version: str = "1.0"
    description: str = ""
    is_dark: bool = True
    colors: ThemeColors = field(default_factory=ThemeColors)
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "author": self.author,
            "version": self.version,
            "description": self.description,
            "is_dark": self.is_dark,
            "colors": self.colors.to_dict()
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> "ThemeInfo":
        colors = ThemeColors.from_dict(d.get("colors", {}))
        return cls(
            name=d.get("name", "custom"),
            display_name=d.get("display_name", "Custom Theme"),
            author=d.get("author", "User"),
            version=d.get("version", "1.0"),
            description=d.get("description", ""),
            is_dark=d.get("is_dark", True),
            colors=colors
        )


# =============================================================================
# Built-in Themes
# =============================================================================
BUILT_IN_THEMES: Dict[str, ThemeInfo] = {
    "github_dark": ThemeInfo(
        name="github_dark",
        display_name="GitHub Dark",
        description="Default dark theme inspired by GitHub",
        is_dark=True,
        colors=ThemeColors()  # Default colors are GitHub Dark
    ),
    
    "github_light": ThemeInfo(
        name="github_light",
        display_name="GitHub Light",
        description="Clean light theme inspired by GitHub",
        is_dark=False,
        colors=ThemeColors(
            bg_dark="#ffffff",
            bg_primary="#f6f8fa",
            bg_secondary="#ffffff",
            bg_tertiary="#f0f0f0",
            bg_hover="#e8e8e8",
            bg_card="#ffffff",
            text_primary="#24292f",
            text_secondary="#57606a",
            text_muted="#8c959f",
            text_link="#0969da",
            accent_primary="#0969da",
            accent_success="#1a7f37",
            accent_warning="#9a6700",
            accent_error="#cf222e",
            accent_purple="#8250df",
            accent_cyan="#0891b2",
            accent_pink="#bf3989",
            accent_orange="#bc4c00",
            border="#d0d7de",
            border_muted="#d8dee4",
            border_active="#0969da",
            selection="#ddf4ff",
            selected="#0969da",
            hover="#f3f4f6",
            drag_target="#1a7f37",
            drag_target_bg="#dafbe1",
            drop_zone="#ddf4ff",
            drop_zone_active="#b6e3ff",
            drop_zone_border="#0969da",
            scrollbar_bg="#f0f0f0",
            scrollbar_thumb="#c1c4c8",
            scrollbar_thumb_hover="#8c959f",
            card_bg="#ffffff",
            card_border="#d0d7de",
            card_hover="#f6f8fa",
            tag_bg="#ddf4ff",
            tag_text="#0969da",
        )
    ),
    
    "dracula": ThemeInfo(
        name="dracula",
        display_name="Dracula",
        description="Popular dark theme with purple accents",
        is_dark=True,
        colors=ThemeColors(
            bg_dark="#21222c",
            bg_primary="#282a36",
            bg_secondary="#343746",
            bg_tertiary="#44475a",
            bg_hover="#44475a",
            bg_card="#282a36",
            text_primary="#f8f8f2",
            text_secondary="#bfbfbf",
            text_muted="#6272a4",
            text_link="#8be9fd",
            accent_primary="#bd93f9",
            accent_success="#50fa7b",
            accent_warning="#ffb86c",
            accent_error="#ff5555",
            accent_purple="#bd93f9",
            accent_cyan="#8be9fd",
            accent_pink="#ff79c6",
            accent_orange="#ffb86c",
            border="#44475a",
            border_muted="#343746",
            border_active="#bd93f9",
            selection="#44475a",
            selected="#6272a4",
            hover="#44475a",
            drag_target="#50fa7b",
            drag_target_bg="#2d4a35",
            scrollbar_bg="#343746",
            scrollbar_thumb="#6272a4",
            scrollbar_thumb_hover="#bd93f9",
            card_bg="#282a36",
            card_border="#44475a",
            card_hover="#343746",
            ai_accent="#bd93f9",
            tag_bg="#bd93f926",
            tag_text="#bd93f9",
        )
    ),
    
    "nord": ThemeInfo(
        name="nord",
        display_name="Nord",
        description="Arctic, north-bluish color palette",
        is_dark=True,
        colors=ThemeColors(
            bg_dark="#2e3440",
            bg_primary="#3b4252",
            bg_secondary="#434c5e",
            bg_tertiary="#4c566a",
            bg_hover="#4c566a",
            bg_card="#3b4252",
            text_primary="#eceff4",
            text_secondary="#d8dee9",
            text_muted="#7b88a1",
            text_link="#88c0d0",
            accent_primary="#81a1c1",
            accent_success="#a3be8c",
            accent_warning="#ebcb8b",
            accent_error="#bf616a",
            accent_purple="#b48ead",
            accent_cyan="#88c0d0",
            accent_pink="#b48ead",
            accent_orange="#d08770",
            border="#4c566a",
            border_muted="#434c5e",
            border_active="#81a1c1",
            selection="#4c566a",
            selected="#5e81ac",
            hover="#4c566a",
            drag_target="#a3be8c",
            drag_target_bg="#3d4a3a",
            scrollbar_bg="#434c5e",
            scrollbar_thumb="#4c566a",
            scrollbar_thumb_hover="#5e81ac",
            card_bg="#3b4252",
            card_border="#4c566a",
            card_hover="#434c5e",
            ai_accent="#b48ead",
            tag_bg="#81a1c126",
            tag_text="#81a1c1",
        )
    ),
    
    "monokai": ThemeInfo(
        name="monokai",
        display_name="Monokai Pro",
        description="Iconic color scheme with warm tones",
        is_dark=True,
        colors=ThemeColors(
            bg_dark="#1e1f1c",
            bg_primary="#272822",
            bg_secondary="#3e3d32",
            bg_tertiary="#49483e",
            bg_hover="#49483e",
            bg_card="#272822",
            text_primary="#f8f8f2",
            text_secondary="#cfcfc2",
            text_muted="#75715e",
            text_link="#66d9ef",
            accent_primary="#a6e22e",
            accent_success="#a6e22e",
            accent_warning="#e6db74",
            accent_error="#f92672",
            accent_purple="#ae81ff",
            accent_cyan="#66d9ef",
            accent_pink="#f92672",
            accent_orange="#fd971f",
            border="#49483e",
            border_muted="#3e3d32",
            border_active="#a6e22e",
            selection="#49483e",
            selected="#75715e",
            hover="#49483e",
            drag_target="#a6e22e",
            drag_target_bg="#3d4a32",
            scrollbar_bg="#3e3d32",
            scrollbar_thumb="#75715e",
            scrollbar_thumb_hover="#a6e22e",
            card_bg="#272822",
            card_border="#49483e",
            card_hover="#3e3d32",
            ai_accent="#ae81ff",
            tag_bg="#a6e22e26",
            tag_text="#a6e22e",
        )
    ),
    
    "one_dark": ThemeInfo(
        name="one_dark",
        display_name="One Dark Pro",
        description="Atom's iconic One Dark theme",
        is_dark=True,
        colors=ThemeColors(
            bg_dark="#1e2127",
            bg_primary="#282c34",
            bg_secondary="#2c313a",
            bg_tertiary="#3e4451",
            bg_hover="#3e4451",
            bg_card="#282c34",
            text_primary="#abb2bf",
            text_secondary="#9da5b3",
            text_muted="#5c6370",
            text_link="#61afef",
            accent_primary="#61afef",
            accent_success="#98c379",
            accent_warning="#e5c07b",
            accent_error="#e06c75",
            accent_purple="#c678dd",
            accent_cyan="#56b6c2",
            accent_pink="#c678dd",
            accent_orange="#d19a66",
            border="#3e4451",
            border_muted="#2c313a",
            border_active="#61afef",
            selection="#3e4451",
            selected="#4d78a9",
            hover="#3e4451",
            drag_target="#98c379",
            drag_target_bg="#2d4a35",
            scrollbar_bg="#2c313a",
            scrollbar_thumb="#5c6370",
            scrollbar_thumb_hover="#61afef",
            card_bg="#282c34",
            card_border="#3e4451",
            card_hover="#2c313a",
            ai_accent="#c678dd",
            tag_bg="#61afef26",
            tag_text="#61afef",
        )
    ),
    
    "tokyo_night": ThemeInfo(
        name="tokyo_night",
        display_name="Tokyo Night",
        description="Clean dark theme inspired by Tokyo at night",
        is_dark=True,
        colors=ThemeColors(
            bg_dark="#16161e",
            bg_primary="#1a1b26",
            bg_secondary="#24283b",
            bg_tertiary="#292e42",
            bg_hover="#292e42",
            bg_card="#1a1b26",
            text_primary="#c0caf5",
            text_secondary="#a9b1d6",
            text_muted="#565f89",
            text_link="#7aa2f7",
            accent_primary="#7aa2f7",
            accent_success="#9ece6a",
            accent_warning="#e0af68",
            accent_error="#f7768e",
            accent_purple="#bb9af7",
            accent_cyan="#7dcfff",
            accent_pink="#ff007c",
            accent_orange="#ff9e64",
            border="#292e42",
            border_muted="#24283b",
            border_active="#7aa2f7",
            selection="#283457",
            selected="#3d59a1",
            hover="#292e42",
            drag_target="#9ece6a",
            drag_target_bg="#2a3a2a",
            scrollbar_bg="#24283b",
            scrollbar_thumb="#565f89",
            scrollbar_thumb_hover="#7aa2f7",
            card_bg="#1a1b26",
            card_border="#292e42",
            card_hover="#24283b",
            ai_accent="#bb9af7",
            tag_bg="#7aa2f726",
            tag_text="#7aa2f7",
        )
    ),
    
    "gruvbox_dark": ThemeInfo(
        name="gruvbox_dark",
        display_name="Gruvbox Dark",
        description="Retro groove color scheme",
        is_dark=True,
        colors=ThemeColors(
            bg_dark="#1d2021",
            bg_primary="#282828",
            bg_secondary="#3c3836",
            bg_tertiary="#504945",
            bg_hover="#504945",
            bg_card="#282828",
            text_primary="#ebdbb2",
            text_secondary="#d5c4a1",
            text_muted="#928374",
            text_link="#83a598",
            accent_primary="#fabd2f",
            accent_success="#b8bb26",
            accent_warning="#fabd2f",
            accent_error="#fb4934",
            accent_purple="#d3869b",
            accent_cyan="#8ec07c",
            accent_pink="#d3869b",
            accent_orange="#fe8019",
            border="#504945",
            border_muted="#3c3836",
            border_active="#fabd2f",
            selection="#504945",
            selected="#665c54",
            hover="#504945",
            drag_target="#b8bb26",
            drag_target_bg="#3a4a2a",
            scrollbar_bg="#3c3836",
            scrollbar_thumb="#665c54",
            scrollbar_thumb_hover="#fabd2f",
            card_bg="#282828",
            card_border="#504945",
            card_hover="#3c3836",
            ai_accent="#d3869b",
            tag_bg="#fabd2f26",
            tag_text="#fabd2f",
        )
    ),
    
    "solarized_dark": ThemeInfo(
        name="solarized_dark",
        display_name="Solarized Dark",
        description="Precision colors for machines and people",
        is_dark=True,
        colors=ThemeColors(
            bg_dark="#002b36",
            bg_primary="#073642",
            bg_secondary="#0a4452",
            bg_tertiary="#1c5766",
            bg_hover="#1c5766",
            bg_card="#073642",
            text_primary="#839496",
            text_secondary="#93a1a1",
            text_muted="#586e75",
            text_link="#268bd2",
            accent_primary="#268bd2",
            accent_success="#859900",
            accent_warning="#b58900",
            accent_error="#dc322f",
            accent_purple="#6c71c4",
            accent_cyan="#2aa198",
            accent_pink="#d33682",
            accent_orange="#cb4b16",
            border="#1c5766",
            border_muted="#0a4452",
            border_active="#268bd2",
            selection="#1c5766",
            selected="#2aa198",
            hover="#1c5766",
            drag_target="#859900",
            drag_target_bg="#2a3a1a",
            scrollbar_bg="#0a4452",
            scrollbar_thumb="#586e75",
            scrollbar_thumb_hover="#268bd2",
            card_bg="#073642",
            card_border="#1c5766",
            card_hover="#0a4452",
            ai_accent="#6c71c4",
            tag_bg="#268bd226",
            tag_text="#268bd2",
        )
    ),
    
    "catppuccin_mocha": ThemeInfo(
        name="catppuccin_mocha",
        display_name="Catppuccin Mocha",
        description="Soothing pastel theme for the high-spirited",
        is_dark=True,
        colors=ThemeColors(
            bg_dark="#11111b",
            bg_primary="#1e1e2e",
            bg_secondary="#313244",
            bg_tertiary="#45475a",
            bg_hover="#45475a",
            bg_card="#1e1e2e",
            text_primary="#cdd6f4",
            text_secondary="#bac2de",
            text_muted="#6c7086",
            text_link="#89b4fa",
            accent_primary="#89b4fa",
            accent_success="#a6e3a1",
            accent_warning="#f9e2af",
            accent_error="#f38ba8",
            accent_purple="#cba6f7",
            accent_cyan="#94e2d5",
            accent_pink="#f5c2e7",
            accent_orange="#fab387",
            border="#45475a",
            border_muted="#313244",
            border_active="#89b4fa",
            selection="#45475a",
            selected="#585b70",
            hover="#45475a",
            drag_target="#a6e3a1",
            drag_target_bg="#2a4a35",
            scrollbar_bg="#313244",
            scrollbar_thumb="#6c7086",
            scrollbar_thumb_hover="#89b4fa",
            card_bg="#1e1e2e",
            card_border="#45475a",
            card_hover="#313244",
            ai_accent="#cba6f7",
            tag_bg="#89b4fa26",
            tag_text="#89b4fa",
        )
    ),
    
    "midnight_blue": ThemeInfo(
        name="midnight_blue",
        display_name="Midnight Blue",
        description="Deep blue professional theme",
        is_dark=True,
        colors=ThemeColors(
            bg_dark="#0a0e14",
            bg_primary="#0d1117",
            bg_secondary="#151b23",
            bg_tertiary="#1e2630",
            bg_hover="#263040",
            bg_card="#0d1117",
            text_primary="#e6edf3",
            text_secondary="#b0b8c1",
            text_muted="#6b7280",
            text_link="#60a5fa",
            accent_primary="#3b82f6",
            accent_success="#22c55e",
            accent_warning="#f59e0b",
            accent_error="#ef4444",
            accent_purple="#a855f7",
            accent_cyan="#06b6d4",
            accent_pink="#ec4899",
            accent_orange="#f97316",
            border="#1e2630",
            border_muted="#151b23",
            border_active="#3b82f6",
            selection="#1e3a5f",
            selected="#2563eb",
            hover="#1e2630",
            drag_target="#22c55e",
            drag_target_bg="#1a3a2a",
            scrollbar_bg="#151b23",
            scrollbar_thumb="#374151",
            scrollbar_thumb_hover="#3b82f6",
            card_bg="#0d1117",
            card_border="#1e2630",
            card_hover="#151b23",
            ai_accent="#a855f7",
            tag_bg="#3b82f626",
            tag_text="#60a5fa",
        )
    ),
}


class ThemeManager:
    """
        Manages application themes with live switching.
        
        Handles loading, saving, and switching themes. Supports both
        built-in themes and user-created custom themes.
        
        Attributes:
            current_theme: Currently active ThemeInfo
            custom_themes: Dict of user-created themes
            _theme_change_callbacks: List of callbacks to notify on theme change
        
        Methods:
            get_all_themes(): Get all available themes
            set_theme(name): Switch to a different theme
            create_custom_theme(...): Create new theme based on existing
            delete_custom_theme(name): Remove a custom theme
            export_theme(name, filepath): Export theme to file
            import_theme(filepath): Import theme from file
            add_theme_change_callback(callback): Register for theme changes
        
        Example:
            >>> tm = ThemeManager()
            >>> tm.set_theme("dracula")
            >>> tm.add_theme_change_callback(on_theme_changed)
        """
    
    def __init__(self, settings_file: Path = SETTINGS_FILE):
        self.settings_file = settings_file
        self.current_theme: ThemeInfo = BUILT_IN_THEMES["github_dark"]
        self.custom_themes: Dict[str, ThemeInfo] = {}
        self._theme_change_callbacks: List[Callable] = []
        self._load_settings()
        self._load_custom_themes()
    
    def _load_settings(self):
        """Load theme preference from settings"""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    theme_name = settings.get("theme", "github_dark")
                    if theme_name in BUILT_IN_THEMES:
                        self.current_theme = BUILT_IN_THEMES[theme_name]
                    elif theme_name in self.custom_themes:
                        self.current_theme = self.custom_themes[theme_name]
            except Exception:
                pass
    
    def _load_custom_themes(self):
        """Load user-created themes from themes directory"""
        for theme_file in THEMES_DIR.glob("*.json"):
            try:
                with open(theme_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    theme = ThemeInfo.from_dict(data)
                    self.custom_themes[theme.name] = theme
            except Exception as e:
                log.warning(f"Error loading theme {theme_file}: {e}")
    
    def save_settings(self):
        """Save current theme to settings"""
        settings = {}
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
            except Exception:
                pass
        
        settings["theme"] = self.current_theme.name
        
        with open(self.settings_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2)
    
    def get_all_themes(self) -> Dict[str, ThemeInfo]:
        """Get all available themes"""
        return {**BUILT_IN_THEMES, **self.custom_themes}
    
    def set_theme(self, theme_name: str) -> bool:
        """Switch to a different theme"""
        all_themes = self.get_all_themes()
        if theme_name in all_themes:
            self.current_theme = all_themes[theme_name]
            self.save_settings()
            self._notify_theme_change()
            return True
        return False
    
    def create_custom_theme(self, name: str, display_name: str, 
                           base_theme: str = "github_dark", 
                           color_overrides: Dict = None) -> ThemeInfo:
        """Create a new custom theme based on an existing one"""
        base = BUILT_IN_THEMES.get(base_theme, BUILT_IN_THEMES["github_dark"])
        
        # Copy base colors
        new_colors_dict = base.colors.to_dict()
        
        # Apply overrides
        if color_overrides:
            new_colors_dict.update(color_overrides)
        
        new_colors = ThemeColors.from_dict(new_colors_dict)
        
        new_theme = ThemeInfo(
            name=name,
            display_name=display_name,
            author="User",
            version="1.0",
            description="Custom theme",
            is_dark=base.is_dark,
            colors=new_colors
        )
        
        # Save to file
        theme_file = THEMES_DIR / f"{name}.json"
        with open(theme_file, 'w', encoding='utf-8') as f:
            json.dump(new_theme.to_dict(), f, indent=2)
        
        self.custom_themes[name] = new_theme
        return new_theme
    
    def delete_custom_theme(self, name: str) -> bool:
        """Delete a custom theme"""
        if name in self.custom_themes:
            theme_file = THEMES_DIR / f"{name}.json"
            if theme_file.exists():
                theme_file.unlink()
            del self.custom_themes[name]
            return True
        return False
    
    def export_theme(self, theme_name: str, filepath: str) -> bool:
        """Export a theme to a file"""
        all_themes = self.get_all_themes()
        if theme_name in all_themes:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(all_themes[theme_name].to_dict(), f, indent=2)
            return True
        return False
    
    def import_theme(self, filepath: str) -> Optional[ThemeInfo]:
        """Import a theme from a file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            theme = ThemeInfo.from_dict(data)
            
            # Ensure unique name
            base_name = theme.name
            counter = 1
            while theme.name in self.get_all_themes():
                theme.name = f"{base_name}_{counter}"
                counter += 1
            
            # Save to themes directory
            theme_file = THEMES_DIR / f"{theme.name}.json"
            with open(theme_file, 'w', encoding='utf-8') as f:
                json.dump(theme.to_dict(), f, indent=2)
            
            self.custom_themes[theme.name] = theme
            return theme
        except Exception as e:
            print(f"Error importing theme: {e}")
            return None
    
    def add_theme_change_callback(self, callback: Callable):
        """Register a callback for theme changes"""
        self._theme_change_callbacks.append(callback)
    
    def remove_theme_change_callback(self, callback: Callable):
        """Remove a theme change callback"""
        if callback in self._theme_change_callbacks:
            self._theme_change_callbacks.remove(callback)
    
    def _notify_theme_change(self):
        """Notify all callbacks of theme change"""
        # Apply theme to ttk styles
        if style_manager._initialized:
            style_manager.apply_theme(self.current_theme.colors)
        
        for callback in self._theme_change_callbacks:
            try:
                callback(self.current_theme)
            except Exception as e:
                log.error(f"Error in theme callback: {e}")
    
    @property
    def colors(self) -> ThemeColors:
        """Get current theme colors (shortcut)"""
        return self.current_theme.colors


# Global theme manager instance
_theme_manager: Optional[ThemeManager] = None

def get_theme_manager() -> ThemeManager:
    """Get the global theme manager instance"""
    global _theme_manager
    if _theme_manager is None:
        _theme_manager = ThemeManager()
    return _theme_manager

def get_theme() -> ThemeColors:
    """Get current theme colors (convenience function)"""
    return get_theme_manager().colors


# =============================================================================
# TAG SYSTEM
# =============================================================================
@dataclass
class Tag:
    """
        Represents a bookmark tag with metadata.
        
        Attributes:
            name: Tag name (unique identifier)
            color: Hex color code for display
            description: Optional tag description
            created_at: ISO timestamp of creation
            usage_count: Number of bookmarks using this tag
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
        """
    name: str
    color: str = ""
    icon: str = ""
    parent: str = ""  # For hierarchical tags like "dev/python"
    created_at: str = ""
    bookmark_count: int = 0
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.color:
            # Generate color from name
            self.color = self._generate_color()
    
    def _generate_color(self) -> str:
        """Generate a consistent color based on tag name"""
        colors = [
            "#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#a855f7",
            "#06b6d4", "#ec4899", "#f97316", "#84cc16", "#6366f1"
        ]
        hash_val = sum(ord(c) for c in self.name)
        return colors[hash_val % len(colors)]
    
    @property
    def full_path(self) -> str:
        """Get full hierarchical path"""
        if self.parent:
            return f"{self.parent}/{self.name}"
        return self.name
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "color": self.color,
            "icon": self.icon,
            "parent": self.parent,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> "Tag":
        return cls(
            name=d.get("name", ""),
            color=d.get("color", ""),
            icon=d.get("icon", ""),
            parent=d.get("parent", ""),
            created_at=d.get("created_at", ""),
        )


class TagManager:
    """
        Manages bookmark tags with persistence.
        
        Handles creating, updating, deleting, and persisting tags.
        Tags are stored in ~/.bookmark_organizer/tags.json.
        
        Attributes:
            tags: Dict mapping tag names to Tag objects
            tags_file: Path to tags storage file
        
        Methods:
            create_tag(name, color, description): Create new tag
            delete_tag(name): Remove a tag
            update_tag(name, **kwargs): Update tag properties
            get_tag(name): Get tag by name
            get_all_tags(): Get all tags as list
            get_popular_tags(limit): Get most-used tags
            search_tags(query): Search tags by name
            suggest_tags(text): AI-powered tag suggestions
        """
    
    def __init__(self, filepath: Path = TAGS_FILE):
        self.filepath = filepath
        self.tags: Dict[str, Tag] = {}
        self._load_tags()
    
    def _load_tags(self):
        """Load tags from file"""
        if self.filepath.exists():
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for tag_data in data.get("tags", []):
                    tag = Tag.from_dict(tag_data)
                    self.tags[tag.full_path] = tag
            except Exception as e:
                print(f"Error loading tags: {e}")
    
    def save_tags(self):
        """Save tags to file"""
        data = {
            "version": 1,
            "tags": [tag.to_dict() for tag in self.tags.values()]
        }
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving tags: {e}")
    
    def add_tag(self, name: str, color: str = "", parent: str = "") -> Tag:
        """Add a new tag"""
        tag = Tag(name=name, color=color, parent=parent)
        self.tags[tag.full_path] = tag
        self.save_tags()
        return tag
    
    def remove_tag(self, tag_path: str) -> bool:
        """Remove a tag"""
        if tag_path in self.tags:
            del self.tags[tag_path]
            self.save_tags()
            return True
        return False
    
    def get_tag(self, tag_path: str) -> Optional[Tag]:
        """Get a tag by path"""
        return self.tags.get(tag_path)
    
    def get_all_tags(self) -> List[Tag]:
        """Get all tags sorted by name"""
        return sorted(self.tags.values(), key=lambda t: t.full_path.lower())
    
    def get_root_tags(self) -> List[Tag]:
        """Get tags without parents"""
        return [t for t in self.tags.values() if not t.parent]
    
    def get_child_tags(self, parent: str) -> List[Tag]:
        """Get child tags of a parent"""
        return [t for t in self.tags.values() if t.parent == parent]
    
    def search_tags(self, query: str) -> List[Tag]:
        """Search tags by name"""
        query = query.lower()
        return [t for t in self.tags.values() if query in t.name.lower()]
    
    def update_tag_color(self, tag_path: str, color: str) -> bool:
        """Update tag color"""
        if tag_path in self.tags:
            self.tags[tag_path].color = color
            self.save_tags()
            return True
        return False
    
    def merge_tags(self, source_path: str, target_path: str) -> bool:
        """Merge source tag into target (for bookmark manager to handle)"""
        if source_path in self.tags and target_path in self.tags:
            # Just remove the source tag, bookmarks need to be updated separately
            del self.tags[source_path]
            self.save_tags()
            return True
        return False
    
    def get_tag_suggestions(self, partial: str, limit: int = 10) -> List[str]:
        """Get tag suggestions for autocomplete"""
        partial = partial.lower()
        matches = [t.full_path for t in self.tags.values() 
                   if partial in t.name.lower()]
        return sorted(matches)[:limit]


# =============================================================================
# Enhanced Bookmark Data Model
# =============================================================================
@dataclass
class Bookmark:
    """
        Represents a single bookmark with all metadata.
        
        Attributes:
            id: Unique integer identifier
            url: Bookmark URL
            title: Display title
            category: Category name
            tags: List of tag names
            ai_tags: List of AI-suggested tags
            description: Optional description
            favicon_url: URL to favicon image
            created_at: ISO timestamp of creation
            updated_at: ISO timestamp of last update
            visited_at: ISO timestamp of last visit
            visit_count: Number of times visited
            is_valid: Whether URL validation passed
            is_pinned: Whether bookmark is pinned
            ai_category: AI-suggested category
            ai_summary: AI-generated summary
            notes: User notes
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
            matches_search(query): Check if bookmark matches search
        """
    id: Optional[int]
    url: str
    title: str
    category: str = "Uncategorized / Needs Review"
    parent_category: str = ""  # For nested categories
    tags: List[str] = field(default_factory=list)
    notes: str = ""
    description: str = ""  # AI-generated or user description
    created_at: str = ""
    modified_at: str = ""
    add_date: str = ""
    last_visited: str = ""
    visit_count: int = 0
    favicon_path: str = ""
    favicon_url: str = ""
    icon: str = ""
    screenshot_path: str = ""
    ai_confidence: float = 0.0
    ai_tags: List[str] = field(default_factory=list)  # AI-suggested tags
    source_file: str = ""
    last_checked: str = ""
    is_valid: bool = True
    http_status: int = 0
    is_pinned: bool = False
    is_archived: bool = False
    reading_time: int = 0  # Estimated reading time in minutes
    word_count: int = 0
    language: str = ""
    custom_data: Dict = field(default_factory=dict)
    
    def __post_init__(self):
        if self.id is None:
            self.id = int(time.time() * 1000000) + hash(self.url) % 10000
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.modified_at:
            self.modified_at = self.created_at
        if isinstance(self.tags, str):
            self.tags = [t.strip() for t in self.tags.split(",") if t.strip()]
        if isinstance(self.ai_tags, str):
            self.ai_tags = [t.strip() for t in self.ai_tags.split(",") if t.strip()]
    
    @property
    def domain(self) -> str:
        try:
            return urlparse(self.url).netloc.replace("www.", "")
        except Exception:
            return ""
    
    @property
    def display_title(self) -> str:
        return self.title[:100] if self.title else self.url[:50]
    
    @property
    def full_category_path(self) -> str:
        """Get full category path including parent"""
        if self.parent_category:
            return f"{self.parent_category} / {self.category}"
        return self.category
    
    @property
    def age_days(self) -> int:
        """Days since bookmark was created"""
        try:
            created = datetime.fromisoformat(self.created_at.replace('Z', '+00:00'))
            return (datetime.now() - created.replace(tzinfo=None)).days
        except Exception:
            return 0
    
    @property
    def is_stale(self) -> bool:
        """Check if bookmark hasn't been visited in 90 days"""
        if not self.last_visited:
            return self.age_days > 90
        try:
            visited = datetime.fromisoformat(self.last_visited.replace('Z', '+00:00'))
            return (datetime.now() - visited.replace(tzinfo=None)).days > 90
        except Exception:
            return True
    
    def add_tag(self, tag: str):
        """Add a tag to the bookmark"""
        if tag and tag not in self.tags:
            self.tags.append(tag)
            self.modified_at = datetime.now().isoformat()
    
    def remove_tag(self, tag: str):
        """Remove a tag from the bookmark"""
        if tag in self.tags:
            self.tags.remove(tag)
            self.modified_at = datetime.now().isoformat()
    
    def record_visit(self):
        """Record a visit to this bookmark"""
        self.visit_count += 1
        self.last_visited = datetime.now().isoformat()
    
    def clean_url(self) -> str:
        """Get URL with tracking parameters removed"""
        try:
            parsed = urlparse(self.url)
            params = parse_qs(parsed.query)
            
            # Remove common tracking parameters
            tracking_params = {
                'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
                'fbclid', 'gclid', 'msclkid', 'ref', 'source', 'mc_cid', 'mc_eid',
                '_ga', '_gl', 'yclid', 'twclid', 'igshid'
            }
            
            cleaned_params = {k: v for k, v in params.items() 
                           if k.lower() not in tracking_params}
            
            new_query = urlencode(cleaned_params, doseq=True)
            return urlunparse((
                parsed.scheme, parsed.netloc, parsed.path,
                parsed.params, new_query, parsed.fragment
            ))
        except Exception:
            return self.url
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id, "url": self.url, "title": self.title,
            "category": self.category, "parent_category": self.parent_category,
            "tags": self.tags, "notes": self.notes, "description": self.description,
            "created_at": self.created_at, "modified_at": self.modified_at,
            "add_date": self.add_date, "last_visited": self.last_visited,
            "visit_count": self.visit_count, "favicon_path": self.favicon_path,
            "favicon_url": self.favicon_url, "icon": self.icon,
            "screenshot_path": self.screenshot_path, "ai_confidence": self.ai_confidence,
            "ai_tags": self.ai_tags, "source_file": self.source_file,
            "last_checked": self.last_checked, "is_valid": self.is_valid,
            "http_status": self.http_status, "is_pinned": self.is_pinned,
            "is_archived": self.is_archived, "reading_time": self.reading_time,
            "word_count": self.word_count, "language": self.language,
            "custom_data": self.custom_data
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> "Bookmark":
        return cls(
            id=d.get("id"),
            url=d.get("url", ""),
            title=d.get("title", ""),
            category=d.get("category", "Uncategorized / Needs Review"),
            parent_category=d.get("parent_category", ""),
            tags=d.get("tags", []),
            notes=d.get("notes", ""),
            description=d.get("description", ""),
            created_at=d.get("created_at", ""),
            modified_at=d.get("modified_at", ""),
            add_date=d.get("add_date", ""),
            last_visited=d.get("last_visited", ""),
            visit_count=d.get("visit_count", 0),
            favicon_path=d.get("favicon_path", ""),
            favicon_url=d.get("favicon_url", ""),
            icon=d.get("icon", ""),
            screenshot_path=d.get("screenshot_path", ""),
            ai_confidence=d.get("ai_confidence", 0.0),
            ai_tags=d.get("ai_tags", []),
            source_file=d.get("source_file", ""),
            last_checked=d.get("last_checked", ""),
            is_valid=d.get("is_valid", True),
            http_status=d.get("http_status", 0),
            is_pinned=d.get("is_pinned", False),
            is_archived=d.get("is_archived", False),
            reading_time=d.get("reading_time", 0),
            word_count=d.get("word_count", 0),
            language=d.get("language", ""),
            custom_data=d.get("custom_data", {})
        )


# =============================================================================
# Enhanced Favicon Manager with Multiple Sources
# =============================================================================
class FaviconManager:
    """
        Manages favicon downloading and caching.
        
        Handles asynchronous favicon downloading with caching,
        retry logic, and fallback generation.
        
        Attributes:
            cache_dir: Directory for cached favicons
            failed_favicons: Set of URLs that failed to download
            executor: ThreadPoolExecutor for async downloads
            download_queue: Queue of pending downloads
            _callbacks: Dict of completion callbacks
        
        Methods:
            get_favicon(url, callback): Get favicon for URL
            queue_bookmarks(bookmarks): Queue multiple downloads
            clear_cache(): Clear favicon cache
            shutdown(): Clean shutdown of executor
        
        Features:
            - Asynchronous downloading with ThreadPoolExecutor
            - Local file caching with hash-based filenames
            - Fallback favicon generation with PIL
            - Retry logic for failed downloads
            - Progress tracking and callbacks
        """
    
    FAVICON_SOURCES = [
        "https://www.google.com/s2/favicons?domain={domain}&sz=64",
        "https://icons.duckduckgo.com/ip3/{domain}.ico",
        "https://api.faviconkit.com/{domain}/64",
        "https://favicone.com/{domain}?s=64",
        "https://icon.horse/icon/{domain}",
        "https://www.faviconextractor.com/favicon/{domain}",
        "https://{domain}/favicon.ico",
        "https://{domain}/favicon.png",
        "https://{domain}/apple-touch-icon.png",
    ]
    
    # Common favicons bundled (as base64 or just tracked domains)
    COMMON_DOMAINS = {
        "github.com", "google.com", "youtube.com", "twitter.com", "x.com",
        "facebook.com", "amazon.com", "reddit.com", "wikipedia.org",
        "stackoverflow.com", "linkedin.com", "instagram.com", "netflix.com"
    }
    
    def __init__(self):
        self._download_queue: Set[str] = set()
        self._lock = threading.Lock()
        self._callbacks: Dict[str, List[Callable]] = {}
        self._failed_domains: Set[str] = set()
        self._placeholder_cache: Dict[str, Any] = {}
        self._processed_domains: Set[str] = set()  # Track processed domains this session
        self._load_failed_domains()
    
    def _load_failed_domains(self):
        """Load failed domains from cache file"""
        try:
            if FAILED_FAVICONS_FILE.exists():
                with open(FAILED_FAVICONS_FILE, 'r') as f:
                    data = json.load(f)
                    self._failed_domains = set(data.get('failed_domains', []))
                    print(f"Loaded {len(self._failed_domains)} failed favicon domains from cache")
        except Exception as e:
            print(f"Error loading failed favicons cache: {e}")
    
    def _save_failed_domains(self):
        """Save failed domains to cache file"""
        try:
            with open(FAILED_FAVICONS_FILE, 'w') as f:
                json.dump({'failed_domains': list(self._failed_domains)}, f)
        except Exception as e:
            print(f"Error saving failed favicons cache: {e}")
    
    def mark_domain_failed(self, domain: str):
        """Mark a domain as failed and save to cache"""
        self._failed_domains.add(domain)
        self._save_failed_domains()
    
    def clear_failed_domains(self):
        """Clear all failed domains to allow retry"""
        self._failed_domains.clear()
        self._save_failed_domains()
    
    def get_failed_domains(self) -> Set[str]:
        """Get set of failed domains"""
        return self._failed_domains.copy()
    
    def is_domain_failed(self, domain: str) -> bool:
        """Check if domain has failed before"""
        return domain in self._failed_domains
    
    def remove_from_failed(self, domain: str):
        """Remove a domain from failed list to allow retry"""
        if domain in self._failed_domains:
            self._failed_domains.discard(domain)
            self._save_failed_domains()
        
    def get_cached_path(self, url: str) -> str:
        """Get cached favicon path if it exists"""
        try:
            domain = urlparse(url).netloc
            if not domain:
                return ""
            hash_name = hashlib.md5(domain.encode()).hexdigest() + ".png"
            path = FAVICON_DIR / hash_name
            if path.exists():
                return str(path)
        except Exception:
            pass
        return ""
    
    def get_placeholder_image(self, url: str, size: int = 16) -> Optional[Image.Image]:
        """Generate a placeholder image with first letter and domain color"""
        if not HAS_PIL:
            return None
            
        try:
            domain = urlparse(url).netloc.replace("www.", "")
            if not domain:
                return None
            
            cache_key = f"{domain}_{size}"
            if cache_key in self._placeholder_cache:
                return self._placeholder_cache[cache_key]
            
            # Generate color from domain
            colors = [
                "#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#a855f7",
                "#06b6d4", "#ec4899", "#f97316", "#84cc16", "#6366f1"
            ]
            hash_val = sum(ord(c) for c in domain)
            bg_color = colors[hash_val % len(colors)]
            
            # Create image
            img = Image.new('RGBA', (size, size), bg_color)
            draw = ImageDraw.Draw(img)
            
            # Get first letter
            letter = domain[0].upper()
            
            # Draw letter (simple approach without custom font)
            text_color = "#ffffff"
            
            # Calculate position for centered text
            font_size = int(size * 0.6)
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except Exception:
                font = ImageFont.load_default()
            
            # Get text bbox
            bbox = draw.textbbox((0, 0), letter, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            x = (size - text_width) // 2
            y = (size - text_height) // 2 - bbox[1]
            
            draw.text((x, y), letter, fill=text_color, font=font)
            
            self._placeholder_cache[cache_key] = img
            return img
        except Exception as e:
            return None
    
    def fetch_favicon(self, url: str, callback: Callable = None) -> None:
        """Fetch favicon in background"""
        if not url:
            return
        
        # Check if already cached
        cached = self.get_cached_path(url)
        if cached:
            if callback:
                callback(url, cached)
            return
        
        domain = urlparse(url).netloc
        if domain in self._failed_domains:
            return
        
        with self._lock:
            if url in self._download_queue:
                if callback:
                    self._callbacks.setdefault(url, []).append(callback)
                return
            self._download_queue.add(url)
            if callback:
                self._callbacks[url] = [callback]
        
        thread = threading.Thread(target=self._worker, args=(url,), daemon=True)
        thread.start()
    
    def _worker(self, url: str):
        """Background worker to download favicon"""
        path = None
        try:
            domain = urlparse(url).netloc
            if not domain:
                return
            
            for source_template in self.FAVICON_SOURCES:
                try:
                    source_url = source_template.format(domain=domain)
                    resp = requests.get(source_url, timeout=5, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    })
                    
                    if resp.status_code == 200 and len(resp.content) > 100:
                        img_data = BytesIO(resp.content)
                        img = Image.open(img_data)
                        
                        if img.mode != 'RGBA':
                            img = img.convert('RGBA')
                        
                        # Save multiple sizes
                        for size in [16, 32, 64]:
                            resized = img.resize((size, size), Image.Resampling.LANCZOS)
                            suffix = f"_{size}" if size != 16 else ""
                            hash_name = hashlib.md5(domain.encode()).hexdigest() + suffix + ".png"
                            save_path = FAVICON_DIR / hash_name
                            resized.save(save_path, "PNG")
                            if size == 16:
                                path = str(save_path)
                        break
                except Exception:
                    continue
            
            if not path:
                self.mark_domain_failed(domain)
                
        except Exception:
            pass
        finally:
            with self._lock:
                if url in self._download_queue:
                    self._download_queue.remove(url)
                callbacks = self._callbacks.pop(url, [])
            
            for cb in callbacks:
                try:
                    if path:
                        cb(url, path)
                except Exception:
                    pass
    
    def clear_cache(self):
        """Clear the favicon cache"""
        for f in FAVICON_DIR.glob("*.png"):
            try:
                f.unlink()
            except Exception:
                pass
        self._failed_domains.clear()
        self._placeholder_cache.clear()
        self._processed_domains.clear()
        self._save_failed_domains()
    
    def get_cache_size(self) -> Tuple[int, int]:
        """Get cache size (file count, total bytes)"""
        count = 0
        total_bytes = 0
        for f in FAVICON_DIR.glob("*.png"):
            count += 1
            total_bytes += f.stat().st_size
        return count, total_bytes
    
    def refresh_favicon(self, url: str, callback: Callable = None):
        """Force refresh a favicon"""
        try:
            domain = urlparse(url).netloc
            hash_name = hashlib.md5(domain.encode()).hexdigest()
            for f in FAVICON_DIR.glob(f"{hash_name}*.png"):
                f.unlink()
        except Exception:
            pass
        
        domain = urlparse(url).netloc
        self.remove_from_failed(domain)
        self._processed_domains.discard(domain)
        self.fetch_favicon(url, callback)
    
    def redownload_all_favicons(self, bookmarks: List, callback: Callable = None, 
                                progress_callback: Callable = None):
        """Redownload all favicons (runs in thread)"""
        def worker():
            # Clear cache first
            for f in FAVICON_DIR.glob("*.png"):
                try:
                    f.unlink()
                except Exception:
                    pass
            self._failed_domains.clear()
            self._processed_domains.clear()
            self._save_failed_domains()
            
            total = len(bookmarks)
            for i, bm in enumerate(bookmarks):
                url = bm.url if hasattr(bm, 'url') else bm.get('url', '')
                if url:
                    self.fetch_favicon(url, callback)
                if progress_callback:
                    progress_callback(i + 1, total)
                time.sleep(0.1)  # Rate limit
        
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return thread
    
    def redownload_missing_favicons(self, bookmarks: List, callback: Callable = None,
                                    progress_callback: Callable = None):
        """Redownload only missing favicons (runs in thread)"""
        def worker():
            # Clear failed domains to retry them
            self._failed_domains.clear()
            self._save_failed_domains()
            
            # Find bookmarks without cached favicons
            missing = []
            for bm in bookmarks:
                url = bm.url if hasattr(bm, 'url') else bm.get('url', '')
                if url and not self.get_cached_path(url):
                    missing.append(url)
            
            total = len(missing)
            for i, url in enumerate(missing):
                self.fetch_favicon(url, callback)
                if progress_callback:
                    progress_callback(i + 1, total)
                time.sleep(0.1)  # Rate limit
        
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return thread



# =============================================================================
# ADVANCED SEARCH ENGINE with Query Syntax
# =============================================================================
class SearchQuery:
    """
        Parses and represents advanced search queries.
        
        Supports advanced search syntax including:
            - Quoted phrases: "exact phrase"
            - Field filters: title:keyword, url:domain, tag:name
            - Boolean operators: AND, OR (implicit AND)
            - Negation: -keyword, -tag:name
            - Wildcards: key* (prefix matching)
        
        Attributes:
            raw_query: Original query string
            terms: List of search terms
            filters: Dict of field-specific filters
            negations: List of negated terms
            phrases: List of exact phrases
        
        Methods:
            parse(query): Parse query string
            matches(bookmark): Check if bookmark matches query
        """
    
    def __init__(self, raw_query: str = ""):
        self.raw_query = raw_query
        self.text_terms: List[str] = []
        self.domain_filters: List[str] = []
        self.tag_filters: List[str] = []
        self.category_filters: List[str] = []
        self.date_after: Optional[datetime] = None
        self.date_before: Optional[datetime] = None
        self.has_notes: Optional[bool] = None
        self.has_tags: Optional[bool] = None
        self.is_pinned: Optional[bool] = None
        self.is_archived: Optional[bool] = None
        self.is_broken: Optional[bool] = None
        self.is_stale: Optional[bool] = None
        self.min_visits: Optional[int] = None
        self.is_regex: bool = False
        self.regex_pattern: Optional[re.Pattern] = None
        
        if raw_query:
            self._parse(raw_query)
    
    def _parse(self, query: str):
        """Parse the query string into structured filters"""
        # Check for regex mode
        if query.startswith("/") and "/" in query[1:]:
            end_idx = query.rindex("/")
            if end_idx > 0:
                try:
                    pattern = query[1:end_idx]
                    self.regex_pattern = re.compile(pattern, re.IGNORECASE)
                    self.is_regex = True
                    return
                except re.error:
                    pass
        
        # Parse structured filters
        tokens = []
        current_token = ""
        in_quotes = False
        
        for char in query:
            if char == '"':
                in_quotes = not in_quotes
            elif char == ' ' and not in_quotes:
                if current_token:
                    tokens.append(current_token)
                    current_token = ""
            else:
                current_token += char
        
        if current_token:
            tokens.append(current_token)
        
        for token in tokens:
            lower_token = token.lower()
            
            # Domain filter: domain:github.com
            if lower_token.startswith("domain:"):
                self.domain_filters.append(token[7:].lower())
            
            # Tag filter: tag:python or #python
            elif lower_token.startswith("tag:"):
                self.tag_filters.append(token[4:])
            elif token.startswith("#"):
                self.tag_filters.append(token[1:])
            
            # Category filter: category:Development or cat:AI
            elif lower_token.startswith("category:"):
                self.category_filters.append(token[9:])
            elif lower_token.startswith("cat:"):
                self.category_filters.append(token[4:])
            
            # Date filters: before:2024-01-01, after:2023-06-15
            elif lower_token.startswith("before:"):
                try:
                    self.date_before = datetime.fromisoformat(token[7:])
                except Exception:
                    pass
            elif lower_token.startswith("after:"):
                try:
                    self.date_after = datetime.fromisoformat(token[6:])
                except Exception:
                    pass
            
            # Boolean filters
            elif lower_token == "has:notes":
                self.has_notes = True
            elif lower_token == "has:tags":
                self.has_tags = True
            elif lower_token == "is:pinned":
                self.is_pinned = True
            elif lower_token == "is:archived":
                self.is_archived = True
            elif lower_token == "is:broken":
                self.is_broken = True
            elif lower_token == "is:stale":
                self.is_stale = True
            
            # Visit filter: visits:>5
            elif lower_token.startswith("visits:"):
                try:
                    val = token[7:]
                    if val.startswith(">"):
                        self.min_visits = int(val[1:])
                    else:
                        self.min_visits = int(val)
                except Exception:
                    pass
            
            # Regular text search term
            else:
                self.text_terms.append(token.strip('"'))
    
    def matches(self, bookmark: Bookmark) -> bool:
        """Check if a bookmark matches this query"""
        
        # Regex mode
        if self.is_regex and self.regex_pattern:
            searchable = f"{bookmark.title} {bookmark.url} {bookmark.notes} {' '.join(bookmark.tags)}"
            return bool(self.regex_pattern.search(searchable))
        
        # Domain filters
        for domain in self.domain_filters:
            if domain not in bookmark.domain.lower():
                return False
        
        # Tag filters
        for tag in self.tag_filters:
            tag_lower = tag.lower()
            if not any(tag_lower in t.lower() for t in bookmark.tags):
                return False
        
        # Category filters
        for cat in self.category_filters:
            cat_lower = cat.lower()
            if cat_lower not in bookmark.category.lower() and \
               cat_lower not in bookmark.parent_category.lower():
                return False
        
        # Date filters
        if self.date_after:
            try:
                created = datetime.fromisoformat(bookmark.created_at.replace('Z', '+00:00'))
                if created.replace(tzinfo=None) < self.date_after:
                    return False
            except Exception:
                pass
        
        if self.date_before:
            try:
                created = datetime.fromisoformat(bookmark.created_at.replace('Z', '+00:00'))
                if created.replace(tzinfo=None) > self.date_before:
                    return False
            except Exception:
                pass
        
        # Boolean filters
        if self.has_notes is True and not bookmark.notes:
            return False
        if self.has_tags is True and not bookmark.tags:
            return False
        if self.is_pinned is True and not bookmark.is_pinned:
            return False
        if self.is_archived is True and not bookmark.is_archived:
            return False
        if self.is_broken is True and bookmark.is_valid:
            return False
        if self.is_stale is True and not bookmark.is_stale:
            return False
        
        # Visit filter
        if self.min_visits is not None and bookmark.visit_count < self.min_visits:
            return False
        
        # Text search
        if self.text_terms:
            searchable = f"{bookmark.title} {bookmark.url} {bookmark.notes} {bookmark.description}".lower()
            for term in self.text_terms:
                if term.lower() not in searchable:
                    return False
        
        return True


class SearchEngine:
    """
        Full-text search engine for bookmarks.
        
        Provides fast searching across bookmark fields with
        relevance scoring and result highlighting.
        
        Features:
            - Multi-field search (title, URL, description, tags)
            - Relevance-based ranking
            - Search highlighting
            - Recent searches history
            - Search suggestions
        
        Methods:
            search(query, bookmarks): Search bookmarks
            get_suggestions(partial): Get query suggestions
            highlight_matches(text, query): Highlight matching text
        """
    
    def __init__(self):
        self._search_history: List[str] = []
        self._saved_searches: Dict[str, str] = {}
        self._max_history = 50
    
    def search(self, bookmarks: List[Bookmark], query: str, 
               fuzzy: bool = False) -> List[Tuple[Bookmark, float]]:
        """
        Search bookmarks with query.
        Returns list of (bookmark, relevance_score) tuples.
        """
        if not query.strip():
            return [(bm, 1.0) for bm in bookmarks]
        
        # Add to history
        self._add_to_history(query)
        
        # Parse query
        parsed = SearchQuery(query)
        
        results = []
        for bm in bookmarks:
            if parsed.matches(bm):
                score = self._calculate_relevance(bm, parsed)
                results.append((bm, score))
        
        # Sort by relevance
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results
    
    def _calculate_relevance(self, bookmark: Bookmark, query: SearchQuery) -> float:
        """Calculate relevance score for a bookmark"""
        score = 1.0
        
        # Title matches are worth more
        for term in query.text_terms:
            term_lower = term.lower()
            if term_lower in bookmark.title.lower():
                score += 2.0
            if term_lower in bookmark.url.lower():
                score += 1.0
            if term_lower == bookmark.domain.lower():
                score += 3.0
        
        # Pinned bookmarks get a boost
        if bookmark.is_pinned:
            score += 1.0
        
        # Recently visited bookmarks get a boost
        if bookmark.visit_count > 0:
            score += min(0.5, bookmark.visit_count * 0.1)
        
        # Fresher bookmarks get a small boost
        if bookmark.age_days < 7:
            score += 0.3
        elif bookmark.age_days < 30:
            score += 0.1
        
        return score
    
    def _add_to_history(self, query: str):
        """Add query to search history"""
        query = query.strip()
        if query and query not in self._search_history:
            self._search_history.insert(0, query)
            if len(self._search_history) > self._max_history:
                self._search_history.pop()
    
    def get_history(self) -> List[str]:
        """Get search history"""
        return self._search_history.copy()
    
    def clear_history(self):
        """Clear search history"""
        self._search_history.clear()
    
    def save_search(self, name: str, query: str):
        """Save a search for quick access"""
        self._saved_searches[name] = query
    
    def get_saved_searches(self) -> Dict[str, str]:
        """Get saved searches"""
        return self._saved_searches.copy()
    
    def delete_saved_search(self, name: str):
        """Delete a saved search"""
        if name in self._saved_searches:
            del self._saved_searches[name]
    
    @staticmethod
    def get_syntax_help() -> str:
        """Get help text for search syntax"""
        return """
Search Syntax:
══════════════

Basic Search:
  python flask           Search for "python" AND "flask"
  "exact phrase"         Search for exact phrase

Domain Filter:
  domain:github.com      Only bookmarks from github.com

Tag Filter:
  tag:python  or  #python   Bookmarks with tag "python"

Category Filter:
  category:Development   Bookmarks in Development category
  cat:AI                 Short form

Date Filters:
  after:2024-01-01       Created after date
  before:2024-06-01      Created before date

Status Filters:
  is:pinned              Pinned bookmarks
  is:archived            Archived bookmarks
  is:broken              Broken links
  is:stale               Not visited in 90+ days

Content Filters:
  has:notes              Has notes
  has:tags               Has tags
  visits:>5              Visited more than 5 times

Regex Search:
  /pattern/              Search with regex

Examples:
  domain:github.com python       GitHub Python repos
  #tutorial after:2024-01-01     Recent tutorials
  is:stale cat:Shopping          Stale shopping bookmarks
"""


# =============================================================================
# Nested Category System
# =============================================================================
@dataclass
class Category:
    """
        Represents a bookmark category.
        
        Attributes:
            name: Category name (unique identifier)
            parent: Parent category name (for nesting)
            icon: Emoji icon for display
            color: Optional color override
            sort_order: Order within parent
            created_at: ISO timestamp of creation
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
        """
    name: str
    parent: str = ""
    patterns: List[str] = field(default_factory=list)
    icon: str = "📁"
    color: str = ""
    description: str = ""
    is_collapsed: bool = False
    sort_order: int = 0
    
    @property
    def full_path(self) -> str:
        """Get full category path"""
        if self.parent:
            return f"{self.parent} / {self.name}"
        return self.name
    
    @property
    def depth(self) -> int:
        """Get nesting depth"""
        return self.full_path.count(" / ")
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "parent": self.parent,
            "patterns": self.patterns,
            "icon": self.icon,
            "color": self.color,
            "description": self.description,
            "is_collapsed": self.is_collapsed,
            "sort_order": self.sort_order
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> "Category":
        if isinstance(d, list):
            # Old format: just patterns
            return cls(name="Unknown", patterns=d)
        return cls(
            name=d.get("name", ""),
            parent=d.get("parent", ""),
            patterns=d.get("patterns", []),
            icon=d.get("icon", "📁"),
            color=d.get("color", ""),
            description=d.get("description", ""),
            is_collapsed=d.get("is_collapsed", False),
            sort_order=d.get("sort_order", 0)
        )


# Category icons mapping
CATEGORY_ICONS = {
    "uncategorized": "📥",
    "development": "💻",
    "programming": "💻",
    "ai": "🤖",
    "machine learning": "🤖",
    "news": "📰",
    "shopping": "🛒",
    "entertainment": "🎬",
    "social": "👥",
    "reference": "📚",
    "documentation": "📚",
    "finance": "💰",
    "health": "🏥",
    "travel": "✈️",
    "food": "🍔",
    "music": "🎵",
    "video": "🎥",
    "gaming": "🎮",
    "education": "🎓",
    "science": "🔬",
    "sports": "⚽",
    "art": "🎨",
    "design": "🎨",
    "security": "🔒",
    "tools": "🔧",
    "utilities": "🔧",
    "cloud": "☁️",
    "database": "🗄️",
    "api": "🔌",
    "mobile": "📱",
    "work": "💼",
    "personal": "👤",
    "bookmarks": "🔖",
    "reading": "📖",
    "research": "🔍",
}


def get_category_icon(category_name: str) -> str:
    """Get appropriate icon for a category name"""
    name_lower = category_name.lower()
    
    for keyword, icon in CATEGORY_ICONS.items():
        if keyword in name_lower:
            return icon
    
    return "📂"




# =============================================================================
# Pattern Engine (Enhanced)
# =============================================================================
class PatternEngine:
    """
        URL pattern matching for auto-categorization.
        
        Matches URLs against patterns to automatically suggest
        categories for new bookmarks.
        
        Attributes:
            patterns: Dict mapping patterns to categories
            patterns_file: Path to patterns storage
        
        Methods:
            match(url): Find matching category for URL
            add_pattern(pattern, category): Add new pattern
            remove_pattern(pattern): Remove a pattern
            learn_from_bookmark(bookmark): Learn pattern from categorized bookmark
        """
    
    def __init__(self, categories: Dict[str, List[str]]):
        self.rules = []
        self.compile_patterns(categories)
    
    def compile_patterns(self, categories: Dict[str, List[str]]):
        """Compile all patterns into rules"""
        self.rules = []
        for category, patterns in categories.items():
            for p in patterns:
                if not p or not p.strip():
                    continue
                rule = {"category": category, "raw": p}
                p_stripped = p.strip()
                
                try:
                    if p_stripped.startswith("regex:"):
                        rule["type"] = "regex"
                        rule["matcher"] = re.compile(p_stripped[6:], re.IGNORECASE)
                    elif p_stripped.startswith("domain:"):
                        rule["type"] = "domain"
                        rule["matcher"] = p_stripped[7:].lower().strip()
                    elif p_stripped.startswith("path:"):
                        rule["type"] = "path"
                        rule["matcher"] = p_stripped[5:].lower().strip()
                    elif p_stripped.startswith("keyword:"):
                        rule["type"] = "keyword"
                        rule["matcher"] = p_stripped[8:].lower().strip()
                    elif p_stripped.startswith("title:"):
                        rule["type"] = "title"
                        rule["matcher"] = p_stripped[6:].lower().strip()
                    elif p_stripped.startswith("ext:"):
                        rule["type"] = "extension"
                        rule["matcher"] = p_stripped[4:].lower().strip()
                    else:
                        rule["type"] = "plain"
                        rule["matcher"] = p_stripped.lower()
                    self.rules.append(rule)
                except re.error:
                    pass
    
    def match(self, url: str, title: str = "") -> Optional[str]:
        """Match URL/title against patterns"""
        url_lower = url.lower()
        title_lower = (title or "").lower()
        
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace('www.', '')
            path = parsed.path.lower()
        except Exception:
            domain = path = ""
        
        for rule in self.rules:
            matcher = rule["matcher"]
            rtype = rule["type"]
            
            try:
                if rtype == "domain" and matcher in domain:
                    return rule["category"]
                elif rtype == "path" and matcher in path:
                    return rule["category"]
                elif rtype == "keyword" and (matcher in url_lower or matcher in title_lower):
                    return rule["category"]
                elif rtype == "title" and matcher in title_lower:
                    return rule["category"]
                elif rtype == "extension":
                    if path.endswith(f".{matcher}"):
                        return rule["category"]
                elif rtype == "regex":
                    if matcher.search(url) or matcher.search(title or ""):
                        return rule["category"]
                elif rtype == "plain":
                    if matcher in domain or matcher in url_lower or matcher in title_lower:
                        return rule["category"]
            except Exception:
                continue
        
        return None


# =============================================================================
# Storage Manager
# =============================================================================
class StorageManager:
    """
        Handles persistent storage of bookmarks.
        
        Manages reading and writing bookmarks to JSON files
        with backup and recovery support.
        
        Attributes:
            data_file: Path to bookmarks JSON file
            backup_dir: Directory for backups
        
        Methods:
            load(): Load bookmarks from file
            save(bookmarks): Save bookmarks to file
            create_backup(): Create timestamped backup
            restore_backup(filepath): Restore from backup
            export_json(bookmarks, filepath): Export to JSON
            export_csv(bookmarks, filepath): Export to CSV
        
        File Format:
            JSON with structure: {"bookmarks": [...], "metadata": {...}}
        """
    CURRENT_VERSION = 4
    
    def __init__(self, filepath: Path):
        self.filepath = filepath
        self._lock = threading.Lock()
    
    def save(self, data: List[Dict], metadata: Dict = None):
        """Save data to file with atomic write"""
        payload = {
            "version": self.CURRENT_VERSION,
            "metadata": metadata or {
                "saved_at": datetime.now().isoformat(),
                "count": len(data)
            },
            "data": data
        }
        
        with self._lock:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            
            if self.filepath.exists():
                self._create_backup()
            
            fd, temp_path = tempfile.mkstemp(
                dir=self.filepath.parent, suffix='.tmp', text=True
            )
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                
                if os.name == 'nt' and self.filepath.exists():
                    os.remove(self.filepath)
                shutil.move(temp_path, self.filepath)
            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise e
    
    def _create_backup(self):
        """Create a backup of the current file"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{self.filepath.stem}_{timestamp}.json"
            backup_path = BACKUP_DIR / backup_name
            shutil.copy2(self.filepath, backup_path)
            
            # Keep only last 10 backups
            backups = sorted(BACKUP_DIR.glob(f"{self.filepath.stem}_*.json"))
            while len(backups) > 10:
                backups[0].unlink()
                backups.pop(0)
        except Exception:
            pass
    
    def load(self) -> List[Bookmark]:
        """Load bookmarks from file"""
        if not self.filepath.exists():
            return []
        
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            
            if isinstance(raw, list):
                return [Bookmark.from_dict(item) for item in raw]
            elif isinstance(raw, dict):
                data = raw.get("data", [])
                return [Bookmark.from_dict(item) for item in data]
        except Exception as e:
            log.warning(f"Warning: Could not load data: {e}")
            return []
    
    def get_backups(self) -> List[Tuple[str, datetime, int]]:
        """Get list of available backups"""
        backups = []
        for f in BACKUP_DIR.glob(f"{self.filepath.stem}_*.json"):
            try:
                stat = f.stat()
                backups.append((
                    f.name,
                    datetime.fromtimestamp(stat.st_mtime),
                    stat.st_size
                ))
            except Exception:
                pass
        return sorted(backups, key=lambda x: x[1], reverse=True)
    
    def restore_backup(self, backup_name: str) -> bool:
        """Restore from a backup"""
        backup_path = BACKUP_DIR / backup_name
        if backup_path.exists():
            try:
                shutil.copy2(backup_path, self.filepath)
                return True
            except Exception:
                pass
        return False


# =============================================================================
# Category Manager (Enhanced with Nesting)
# =============================================================================
class CategoryManager:
    """
        Manages bookmark categories with hierarchy support.
        
        Handles creating, updating, deleting categories with
        support for nested category structures.
        
        Attributes:
            categories: Dict mapping names to Category objects
            categories_file: Path to categories storage
        
        Methods:
            create_category(name, parent, icon): Create new category
            delete_category(name, reassign_to): Delete category
            rename_category(old_name, new_name): Rename category
            move_category(name, new_parent): Move in hierarchy
            get_children(name): Get child categories
            get_ancestors(name): Get parent chain
            get_sorted_categories(): Get categories in display order
        
        Features:
            - Nested category hierarchy
            - Automatic icon assignment
            - Sort order management
            - Cascade operations on children
        """
    
    DEFAULT_CATEGORIES = {
        "Uncategorized / Needs Review": ["example.com", "example.org", "test.", "demo.", "staging."],
        "Adult & Mature Content": [
            "pornhub.com", "xvideos.com", "xnxx.com", "xhamster.com", "redtube.com",
            "porn.", "xxx.", "chaturbate.com", "onlyfans.com", "fansly.com"
        ],
        "Redirects, Trackers & Shorteners": [
            "bit.ly", "bitly.com", "tinyurl.com", "t.co", "goo.gl", "ow.ly",
            "linktr.ee", "linkin.bio", "redirect.", "track.", "tracking.", "click.",
            "utm_source=", "fbclid=", "gclid="
        ],
        "Internal Tools & Dashboards": [
            "localhost", "127.0.0.1", "192.168.", "10.0.", "172.16.", ".local",
            ".internal", ".lan", ":3000", ":8080", "/admin", "/dashboard",
            "admin.", "dashboard.", "internal.", "intranet."
        ],
        "Privacy & Security": [
            "1password.com", "lastpass.com", "bitwarden.com", "protonmail.com",
            "proton.me", "nordvpn.com", "expressvpn.com", "mullvad.net",
            "torproject.org", "duckduckgo.com", "signal.org", "haveibeenpwned.com"
        ],
        "Self-Hosted & Homelab": [
            "pfsense.org", "opnsense.org", "proxmox.com", "truenas.com", "unraid.net",
            "synology.com", "home-assistant.io", "jellyfin.org", "plex.tv",
            "sonarr.tv", "radarr.video", "nextcloud.com", "pi-hole.net", "portainer.io"
        ],
        "Development & Programming": [
            "github.com", "gitlab.com", "bitbucket.org", "stackoverflow.com", "dev.to",
            "codepen.io", "jsfiddle.net", "replit.com", "codesandbox.io",
            "hackerrank.com", "leetcode.com", "codeforces.com"
        ],
        "AI & Machine Learning": [
            "openai.com", "anthropic.com", "claude.ai", "chatgpt.com", "huggingface.co",
            "kaggle.com", "tensorflow.org", "pytorch.org", "colab.research.google.com",
            "midjourney.com", "stability.ai", "replicate.com"
        ],
        "Cloud & Infrastructure": [
            "aws.amazon.com", "console.aws.amazon.com", "azure.microsoft.com",
            "cloud.google.com", "digitalocean.com", "linode.com", "vultr.com",
            "heroku.com", "netlify.com", "vercel.com", "cloudflare.com"
        ],
        "News & Media": [
            "cnn.com", "bbc.com", "reuters.com", "apnews.com", "nytimes.com",
            "washingtonpost.com", "theguardian.com", "bloomberg.com", "techcrunch.com"
        ],
        "Social Media": [
            "twitter.com", "x.com", "facebook.com", "instagram.com", "linkedin.com",
            "reddit.com", "tiktok.com", "pinterest.com", "discord.com", "mastodon.social"
        ],
        "Shopping & E-commerce": [
            "amazon.com", "ebay.com", "walmart.com", "target.com", "bestbuy.com",
            "etsy.com", "aliexpress.com", "shopify.com", "newegg.com"
        ],
        "Entertainment & Streaming": [
            "youtube.com", "netflix.com", "hulu.com", "disneyplus.com", "hbomax.com",
            "primevideo.com", "spotify.com", "twitch.tv", "crunchyroll.com"
        ],
        "Gaming": [
            "steam.com", "steampowered.com", "epicgames.com", "gog.com", "itch.io",
            "xbox.com", "playstation.com", "nintendo.com", "ign.com", "gamespot.com"
        ],
        "Finance & Banking": [
            "chase.com", "bankofamerica.com", "wellsfargo.com", "paypal.com",
            "venmo.com", "robinhood.com", "fidelity.com", "coinbase.com"
        ],
        "Education & Learning": [
            "coursera.org", "udemy.com", "edx.org", "khanacademy.org", "udacity.com",
            "codecademy.com", "freecodecamp.org", "duolingo.com", "masterclass.com"
        ],
        "Reference & Research": [
            "wikipedia.org", "britannica.com", "merriam-webster.com", "dictionary.com",
            "scholar.google.com", "arxiv.org", "pubmed.gov", "wolframalpha.com"
        ],
        "Travel & Transportation": [
            "booking.com", "airbnb.com", "expedia.com", "kayak.com", "tripadvisor.com",
            "uber.com", "lyft.com", "skyscanner.com", "hotels.com"
        ],
        "Food & Dining": [
            "doordash.com", "ubereats.com", "grubhub.com", "instacart.com",
            "yelp.com", "opentable.com", "allrecipes.com", "epicurious.com"
        ],
        "Health & Medical": [
            "webmd.com", "mayoclinic.org", "healthline.com", "nih.gov", "cdc.gov",
            "drugs.com", "zocdoc.com", "myfitnesspal.com", "strava.com"
        ],
        "Job Search & Career": [
            "linkedin.com/jobs", "indeed.com", "glassdoor.com", "monster.com",
            "upwork.com", "fiverr.com", "remoteok.com", "levels.fyi"
        ],
        "Real Estate": [
            "zillow.com", "realtor.com", "redfin.com", "trulia.com", "apartments.com"
        ],
        "Automotive": [
            "cars.com", "autotrader.com", "cargurus.com", "carmax.com", "kbb.com"
        ],
        "Sports": [
            "espn.com", "sports.yahoo.com", "bleacherreport.com", "nba.com", "nfl.com"
        ],
        "Forums & Communities": [
            "reddit.com/r", "quora.com", "medium.com", "substack.com",
            "news.ycombinator.com", "discord.gg", "slack.com"
        ],
        "Government & Legal": [
            ".gov", "usa.gov", "irs.gov", "law.cornell.edu", "findlaw.com"
        ],
    }
    
    def __init__(self, filepath: Path = CATEGORIES_FILE):
        self.filepath = filepath
        self.categories: Dict[str, Category] = {}
        self.pattern_engine: Optional[PatternEngine] = None
        self._load_categories()
    
    def _load_categories(self):
        """Load categories from file"""
        if self.filepath.exists():
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                
                # Handle both old and new format
                if isinstance(raw, dict):
                    for name, data in raw.items():
                        if isinstance(data, list):
                            # Old format: {name: [patterns]}
                            self.categories[name] = Category(
                                name=name,
                                patterns=data,
                                icon=get_category_icon(name)
                            )
                        else:
                            # New format: {name: {category_data}}
                            cat = Category.from_dict(data)
                            cat.name = name
                            self.categories[name] = cat
            except Exception as e:
                print(f"Error loading categories: {e}")
                self._init_defaults()
        else:
            self._init_defaults()
        
        # Ensure uncategorized exists
        if "Uncategorized / Needs Review" not in self.categories:
            self.categories["Uncategorized / Needs Review"] = Category(
                name="Uncategorized / Needs Review",
                icon="📥"
            )
        
        self._rebuild_patterns()
    
    def _init_defaults(self):
        """Initialize with default categories"""
        for name, patterns in self.DEFAULT_CATEGORIES.items():
            self.categories[name] = Category(
                name=name,
                patterns=patterns,
                icon=get_category_icon(name)
            )
        self.save_categories()
    
    def _rebuild_patterns(self):
        """Rebuild the pattern engine"""
        patterns_dict = {cat.full_path: cat.patterns for cat in self.categories.values()}
        self.pattern_engine = PatternEngine(patterns_dict)
    
    def save_categories(self):
        """Save categories to file"""
        try:
            data = {}
            for name, cat in self.categories.items():
                data[name] = cat.to_dict()
            
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving categories: {e}")
    
    def categorize_url(self, url: str, title: str = "") -> str:
        """Categorize a URL using patterns"""
        if self.pattern_engine:
            result = self.pattern_engine.match(url, title)
            if result:
                return result
        return "Uncategorized / Needs Review"
    
    def add_category(self, name: str, parent: str = "", 
                    patterns: List[str] = None, icon: str = "") -> bool:
        """Add a new category"""
        if name and name.strip() and name not in self.categories:
            cat = Category(
                name=name.strip(),
                parent=parent,
                patterns=patterns or [],
                icon=icon or get_category_icon(name)
            )
            self.categories[name.strip()] = cat
            self.save_categories()
            self._rebuild_patterns()
            return True
        return False
    
    def remove_category(self, name: str) -> bool:
        """Remove a category"""
        if name in self.categories and "Uncategorized" not in name:
            # Also remove child categories
            children = self.get_children(name)
            for child in children:
                if child in self.categories:
                    del self.categories[child]
            
            del self.categories[name]
            self.save_categories()
            self._rebuild_patterns()
            return True
        return False
    
    def rename_category(self, old_name: str, new_name: str) -> bool:
        """Rename a category"""
        if (old_name in self.categories and new_name and new_name.strip() and
            new_name not in self.categories and "Uncategorized" not in old_name):
            
            cat = self.categories.pop(old_name)
            cat.name = new_name.strip()
            self.categories[new_name.strip()] = cat
            
            # Update children
            for child_cat in self.categories.values():
                if child_cat.parent == old_name:
                    child_cat.parent = new_name.strip()
            
            self.save_categories()
            self._rebuild_patterns()
            return True
        return False
    
    def move_category(self, name: str, new_parent: str) -> bool:
        """Move a category under a new parent"""
        if name in self.categories and "Uncategorized" not in name:
            if new_parent and new_parent not in self.categories:
                return False
            
            self.categories[name].parent = new_parent
            self.save_categories()
            return True
        return False
    
    def update_patterns(self, name: str, patterns: List[str]) -> bool:
        """Update patterns for a category"""
        if name in self.categories:
            self.categories[name].patterns = patterns
            self.save_categories()
            self._rebuild_patterns()
            return True
        return False
    
    def update_icon(self, name: str, icon: str) -> bool:
        """Update icon for a category"""
        if name in self.categories:
            self.categories[name].icon = icon
            self.save_categories()
            return True
        return False
    
    def update_color(self, name: str, color: str) -> bool:
        """Update color for a category"""
        if name in self.categories:
            self.categories[name].color = color
            self.save_categories()
            return True
        return False
    
    def get_patterns(self, name: str) -> List[str]:
        """Get patterns for a category"""
        if name in self.categories:
            return self.categories[name].patterns
        return []
    
    def get_category(self, name: str) -> Optional[Category]:
        """Get a category by name"""
        return self.categories.get(name)
    
    def get_root_categories(self) -> List[Category]:
        """Get top-level categories"""
        return sorted(
            [c for c in self.categories.values() if not c.parent],
            key=lambda x: (x.sort_order, x.name.lower())
        )
    
    def get_children(self, parent: str) -> List[str]:
        """Get child category names"""
        return [c.name for c in self.categories.values() if c.parent == parent]
    
    def get_sorted_categories(self) -> List[str]:
        """Get all categories sorted with uncategorized last"""
        uncategorized = [c for c in self.categories if "Uncategorized" in c]
        regular = sorted([c for c in self.categories if "Uncategorized" not in c])
        return regular + uncategorized
    
    def get_all_categories(self) -> List[str]:
        """Get all category names"""
        return list(self.categories.keys())
    
    def get_tree(self) -> List[Tuple[Category, int]]:
        """Get categories as a tree with depth"""
        result = []
        
        def add_category(cat: Category, depth: int):
            result.append((cat, depth))
            children = sorted(
                [c for c in self.categories.values() if c.parent == cat.name],
                key=lambda x: (x.sort_order, x.name.lower())
            )
            for child in children:
                add_category(child, depth + 1)
        
        for root in self.get_root_categories():
            add_category(root, 0)
        
        return result
    
    def merge_categories(self, source: str, target: str) -> bool:
        """Merge source category into target"""
        if source in self.categories and target in self.categories:
            if source != target and "Uncategorized" not in source:
                # Move children to target
                for cat in self.categories.values():
                    if cat.parent == source:
                        cat.parent = target
                
                # Merge patterns
                source_patterns = self.categories[source].patterns
                self.categories[target].patterns.extend(source_patterns)
                
                del self.categories[source]
                self.save_categories()
                self._rebuild_patterns()
                return True
        return False
    
    def toggle_collapsed(self, name: str) -> bool:
        """Toggle collapsed state of a category"""
        if name in self.categories:
            self.categories[name].is_collapsed = not self.categories[name].is_collapsed
            self.save_categories()
            return True
        return False




# =============================================================================
# Command System (Undo/Redo)
# =============================================================================
class Command:
    """Base command for undo/redo system"""
    def execute(self): raise NotImplementedError
    def undo(self): raise NotImplementedError
    def description(self) -> str: return "Unknown"
    def can_merge(self, other: 'Command') -> bool: return False
    def merge(self, other: 'Command'): pass


class CommandStack:
    """
        Manages undo/redo functionality.
        
        Implements command pattern for reversible operations
        with support for command merging.
        
        Attributes:
            undo_stack: List of executed commands
            redo_stack: List of undone commands
            max_size: Maximum stack size (default: 50)
        
        Methods:
            execute(command): Execute and push to undo stack
            undo(): Undo last command
            redo(): Redo last undone command
            can_undo(): Check if undo available
            can_redo(): Check if redo available
            clear(): Clear all history
        
        Supported Commands:
            - MoveBookmarksCommand
            - DeleteBookmarksCommand
            - AddBookmarksCommand
            - BulkCategorizeCommand
            - TagBookmarksCommand
        """
    
    def __init__(self, max_history: int = 100):
        self._undo_stack: List[Command] = []
        self._redo_stack: List[Command] = []
        self._max_history = max_history
        self._last_command_time = 0
        self._merge_window_ms = 500
    
    def execute(self, command: Command):
        """Execute a command and add to history"""
        command.execute()
        now = time.time() * 1000
        
        if (self._undo_stack and 
            now - self._last_command_time < self._merge_window_ms and
            self._undo_stack[-1].can_merge(command)):
            self._undo_stack[-1].merge(command)
        else:
            self._undo_stack.append(command)
        
        self._last_command_time = now
        self._redo_stack.clear()
        
        while len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)
    
    def undo(self) -> Optional[str]:
        """Undo the last command"""
        if not self._undo_stack:
            return None
        command = self._undo_stack.pop()
        command.undo()
        self._redo_stack.append(command)
        return command.description()
    
    def redo(self) -> Optional[str]:
        """Redo the last undone command"""
        if not self._redo_stack:
            return None
        command = self._redo_stack.pop()
        command.execute()
        self._undo_stack.append(command)
        return command.description()
    
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0
    
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0
    
    def clear(self):
        self._undo_stack.clear()
        self._redo_stack.clear()


class MoveBookmarksCommand(Command):
    """Command to move bookmarks to a category"""
    
    def __init__(self, manager, bookmark_ids: List[int], new_category: str):
        self.manager = manager
        self.ids = bookmark_ids
        self.new_category = new_category
        self.previous_categories: Dict[int, str] = {}
    
    def execute(self):
        for bid in self.ids:
            bm = self.manager.bookmarks.get(bid)
            if bm:
                self.previous_categories[bid] = bm.category
                bm.category = self.new_category
                bm.modified_at = datetime.now().isoformat()
        self.manager.save_bookmarks()
    
    def undo(self):
        for bid, old_cat in self.previous_categories.items():
            bm = self.manager.bookmarks.get(bid)
            if bm:
                bm.category = old_cat
                bm.modified_at = datetime.now().isoformat()
        self.manager.save_bookmarks()
    
    def description(self) -> str:
        return f"Move {len(self.ids)} bookmark(s) to {self.new_category}"
    
    def can_merge(self, other: Command) -> bool:
        return isinstance(other, MoveBookmarksCommand) and other.new_category == self.new_category
    
    def merge(self, other: 'MoveBookmarksCommand'):
        for bid, cat in other.previous_categories.items():
            if bid not in self.previous_categories:
                self.previous_categories[bid] = cat
        self.ids = list(set(self.ids + other.ids))


class DeleteBookmarksCommand(Command):
    """Command to delete bookmarks"""
    
    def __init__(self, manager, bookmark_ids: List[int]):
        self.manager = manager
        self.ids = bookmark_ids
        self.deleted_bookmarks: Dict[int, Bookmark] = {}
    
    def execute(self):
        for bid in self.ids:
            bm = self.manager.bookmarks.get(bid)
            if bm:
                self.deleted_bookmarks[bid] = bm
                del self.manager.bookmarks[bid]
        self.manager.save_bookmarks()
    
    def undo(self):
        for bid, bm in self.deleted_bookmarks.items():
            self.manager.bookmarks[bid] = bm
        self.manager.save_bookmarks()
    
    def description(self) -> str:
        return f"Delete {len(self.ids)} bookmark(s)"


class AddBookmarksCommand(Command):
    """Command to add bookmarks"""
    
    def __init__(self, manager, bookmarks: List[Bookmark]):
        self.manager = manager
        self.bookmarks = bookmarks
        self.added_ids: List[int] = []
    
    def execute(self):
        self.added_ids = []
        for bm in self.bookmarks:
            self.manager.bookmarks[bm.id] = bm
            self.added_ids.append(bm.id)
        self.manager.save_bookmarks()
    
    def undo(self):
        for bid in self.added_ids:
            if bid in self.manager.bookmarks:
                del self.manager.bookmarks[bid]
        self.manager.save_bookmarks()
    
    def description(self) -> str:
        return f"Add {len(self.bookmarks)} bookmark(s)"


class BulkCategorizeCommand(Command):
    """Command for bulk categorization"""
    
    def __init__(self, manager, changes: List[Tuple[int, str, str]]):
        self.manager = manager
        self.changes = changes  # (bookmark_id, old_category, new_category)
    
    def execute(self):
        for bid, _, new_cat in self.changes:
            bm = self.manager.bookmarks.get(bid)
            if bm:
                bm.category = new_cat
                bm.modified_at = datetime.now().isoformat()
        self.manager.save_bookmarks()
    
    def undo(self):
        for bid, old_cat, _ in self.changes:
            bm = self.manager.bookmarks.get(bid)
            if bm:
                bm.category = old_cat
                bm.modified_at = datetime.now().isoformat()
        self.manager.save_bookmarks()
    
    def description(self) -> str:
        return f"Categorize {len(self.changes)} bookmark(s)"


class TagBookmarksCommand(Command):
    """
        Represents a bookmark tag with metadata.
        
        Attributes:
            name: Tag name (unique identifier)
            color: Hex color code for display
            description: Optional tag description
            created_at: ISO timestamp of creation
            usage_count: Number of bookmarks using this tag
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
        """
    
    def __init__(self, manager, bookmark_ids: List[int], 
                 add_tags: List[str] = None, remove_tags: List[str] = None):
        self.manager = manager
        self.ids = bookmark_ids
        self.add_tags = add_tags or []
        self.remove_tags = remove_tags or []
        self.previous_tags: Dict[int, List[str]] = {}
    
    def execute(self):
        for bid in self.ids:
            bm = self.manager.bookmarks.get(bid)
            if bm:
                self.previous_tags[bid] = bm.tags.copy()
                for tag in self.remove_tags:
                    if tag in bm.tags:
                        bm.tags.remove(tag)
                for tag in self.add_tags:
                    if tag not in bm.tags:
                        bm.tags.append(tag)
                bm.modified_at = datetime.now().isoformat()
        self.manager.save_bookmarks()
    
    def undo(self):
        for bid, old_tags in self.previous_tags.items():
            bm = self.manager.bookmarks.get(bid)
            if bm:
                bm.tags = old_tags
                bm.modified_at = datetime.now().isoformat()
        self.manager.save_bookmarks()
    
    def description(self) -> str:
        return f"Update tags on {len(self.ids)} bookmark(s)"


# =============================================================================
# Bookmark Manager (Enhanced)
# =============================================================================
class BookmarkManager:
    """
        Central manager for all bookmark operations.
        
        Coordinates between storage, categories, tags, and search
        to provide a unified API for bookmark management.
        
        Attributes:
            bookmarks: Dict mapping IDs to Bookmark objects
            category_manager: CategoryManager instance
            tag_manager: TagManager instance
            storage: StorageManager instance
            search_engine: SearchEngine instance
            pattern_engine: PatternEngine instance
        
        Methods:
            add_bookmark(url, title, category, tags): Add new bookmark
            update_bookmark(id, **kwargs): Update bookmark
            delete_bookmark(id): Delete bookmark
            delete_bookmarks(ids): Bulk delete
            get_bookmark(id): Get by ID
            get_all_bookmarks(): Get all bookmarks
            get_by_category(category): Filter by category
            get_by_tag(tag): Filter by tag
            search(query): Search bookmarks
            import_bookmarks(filepath): Import from file
            export_bookmarks(filepath, format): Export to file
            validate_urls(bookmarks): Check URL validity
            get_statistics(): Get bookmark statistics
            get_category_counts(): Get counts per category
        
        Events:
            Emits callbacks on add, update, delete operations
        """
    
    def __init__(self, category_manager: CategoryManager, 
                 tag_manager: TagManager,
                 filepath: Path = MASTER_BOOKMARKS_FILE):
        self.category_manager = category_manager
        self.tag_manager = tag_manager
        self.filepath = filepath
        self.storage = StorageManager(filepath)
        self.bookmarks: Dict[int, Bookmark] = OrderedDict()
        self.search_engine = SearchEngine()
        self._load_bookmarks()
    
    def _load_bookmarks(self):
        """Load all bookmarks from storage"""
        self.bookmarks.clear()
        for bm in self.storage.load():
            self.bookmarks[bm.id] = bm
    
    def reload(self):
        """Reload bookmarks from disk"""
        self._load_bookmarks()
    
    def save_bookmarks(self):
        """Save all bookmarks to storage"""
        self.storage.save([bm.to_dict() for bm in self.bookmarks.values()])
    
    def add_bookmark(self, bookmark: Bookmark, save: bool = True) -> Bookmark:
        """Add a new bookmark. Set save=False for batch operations."""
        self.bookmarks[bookmark.id] = bookmark
        if save:
            self.save_bookmarks()
        return bookmark
    
    def update_bookmark(self, bookmark_or_id, **kwargs) -> Optional[Bookmark]:
        """Update a bookmark's attributes. Can accept Bookmark object or bookmark_id."""
        # Handle both Bookmark object and ID
        if isinstance(bookmark_or_id, Bookmark):
            bookmark = bookmark_or_id
            bookmark.modified_at = datetime.now().isoformat()
            self.bookmarks[bookmark.id] = bookmark
            self.save_bookmarks()
            return bookmark
        
        # Legacy: ID with kwargs
        bm = self.bookmarks.get(bookmark_or_id)
        if bm:
            for key, value in kwargs.items():
                if hasattr(bm, key):
                    setattr(bm, key, value)
            bm.modified_at = datetime.now().isoformat()
            self.save_bookmarks()
            return bm
        return None
    
    def delete_bookmark(self, bookmark_id: int) -> bool:
        """Delete a bookmark"""
        if bookmark_id in self.bookmarks:
            del self.bookmarks[bookmark_id]
            self.save_bookmarks()
            return True
        return False
    
    def get_bookmark(self, bookmark_id: int) -> Optional[Bookmark]:
        """Get a bookmark by ID"""
        return self.bookmarks.get(bookmark_id)
    
    def import_html_file(self, filepath: str, source_name: str = "") -> Tuple[int, int]:
        """Import bookmarks from HTML file"""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading file: {e}")
            return 0, 0
        
        soup = BeautifulSoup(content, 'html.parser')
        added = duplicates = 0
        existing_urls = {bm.url for bm in self.bookmarks.values()}
        source = source_name or Path(filepath).name
        
        for a_tag in soup.find_all('a'):
            href = a_tag.get('href', '')
            if not href or not href.startswith(('http://', 'https://')):
                continue
            
            href = href.strip()
            if href in existing_urls:
                duplicates += 1
                continue
            
            title = a_tag.get_text(strip=True) or href
            category = self.category_manager.categorize_url(href, title)
            
            bm = Bookmark(
                id=None,
                title=title[:500],
                url=href,
                add_date=a_tag.get('add_date', ''),
                icon=a_tag.get('icon', ''),
                category=category,
                source_file=source
            )
            self.bookmarks[bm.id] = bm
            existing_urls.add(href)
            added += 1
        
        if added > 0:
            self.save_bookmarks()
        
        return added, duplicates
    
    def import_json_file(self, filepath: str) -> Tuple[int, int]:
        """Import bookmarks from JSON file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error reading file: {e}")
            return 0, 0
        
        added = duplicates = 0
        existing_urls = {bm.url for bm in self.bookmarks.values()}
        
        bookmarks_data = data.get("bookmarks", data.get("data", []))
        if isinstance(data, list):
            bookmarks_data = data
        
        for item in bookmarks_data:
            url = item.get("url", "")
            if not url or url in existing_urls:
                duplicates += 1
                continue
            
            bm = Bookmark.from_dict(item)
            self.bookmarks[bm.id] = bm
            existing_urls.add(url)
            added += 1
        
        if added > 0:
            self.save_bookmarks()
        
        return added, duplicates
    
    def get_bookmarks_by_category(self, category: str, 
                                   include_children: bool = True) -> List[Bookmark]:
        """Get bookmarks in a category"""
        results = []
        for bm in self.bookmarks.values():
            if bm.category == category:
                results.append(bm)
            elif include_children and bm.parent_category == category:
                results.append(bm)
        return results
    
    def get_bookmarks_by_tag(self, tag: str) -> List[Bookmark]:
        """Get bookmarks with a specific tag"""
        tag_lower = tag.lower()
        return [bm for bm in self.bookmarks.values() 
                if any(tag_lower in t.lower() for t in bm.tags)]
    
    def get_all_bookmarks(self) -> List[Bookmark]:
        """Get all bookmarks"""
        return list(self.bookmarks.values())
    
    def get_pinned_bookmarks(self) -> List[Bookmark]:
        """Get pinned bookmarks"""
        return [bm for bm in self.bookmarks.values() if bm.is_pinned]
    
    def get_archived_bookmarks(self) -> List[Bookmark]:
        """Get archived bookmarks"""
        return [bm for bm in self.bookmarks.values() if bm.is_archived]
    
    def get_recent_bookmarks(self, days: int = 7) -> List[Bookmark]:
        """Get recently added bookmarks"""
        cutoff = datetime.now() - timedelta(days=days)
        results = []
        for bm in self.bookmarks.values():
            try:
                created = datetime.fromisoformat(bm.created_at.replace('Z', '+00:00'))
                if created.replace(tzinfo=None) > cutoff:
                    results.append(bm)
            except Exception:
                pass
        return sorted(results, key=lambda x: x.created_at, reverse=True)
    
    def get_stale_bookmarks(self, days: int = 90) -> List[Bookmark]:
        """Get stale bookmarks"""
        return [bm for bm in self.bookmarks.values() if bm.is_stale]
    
    def get_frequently_visited(self, limit: int = 20) -> List[Bookmark]:
        """Get most frequently visited bookmarks"""
        visited = [bm for bm in self.bookmarks.values() if bm.visit_count > 0]
        return sorted(visited, key=lambda x: x.visit_count, reverse=True)[:limit]
    
    def get_category_counts(self) -> Dict[str, int]:
        """Get bookmark count per category"""
        counts = {cat: 0 for cat in self.category_manager.categories}
        for bm in self.bookmarks.values():
            counts[bm.category] = counts.get(bm.category, 0) + 1
        return counts
    
    def get_tag_counts(self) -> Dict[str, int]:
        """Get bookmark count per tag"""
        counts: Dict[str, int] = {}
        for bm in self.bookmarks.values():
            for tag in bm.tags:
                counts[tag] = counts.get(tag, 0) + 1
        return counts
    
    def search_bookmarks(self, query: str, category: str = None) -> List[Bookmark]:
        """Search bookmarks with advanced query"""
        if category:
            bookmarks = self.get_bookmarks_by_category(category)
        else:
            bookmarks = self.get_all_bookmarks()
        
        results = self.search_engine.search(bookmarks, query)
        return [bm for bm, score in results]
    
    def find_duplicates(self) -> Dict[str, List[Bookmark]]:
        """Find duplicate bookmarks by URL"""
        url_map: Dict[str, List[Bookmark]] = {}
        for bm in self.bookmarks.values():
            normalized = bm.url.lower().rstrip('/')
            # Remove tracking parameters
            try:
                parsed = urlparse(normalized)
                clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                url_map.setdefault(clean_url, []).append(bm)
            except Exception:
                url_map.setdefault(normalized, []).append(bm)
        
        return {url: bms for url, bms in url_map.items() if len(bms) > 1}
    
    def find_broken_links(self) -> List[Bookmark]:
        """Get bookmarks marked as broken"""
        return [bm for bm in self.bookmarks.values() if not bm.is_valid]
    
    def find_by_url(self, url: str) -> Optional[Bookmark]:
        """Find a bookmark by its URL"""
        if not url:
            return None
        
        # Normalize URL for comparison
        normalized = url.lower().rstrip('/')
        
        for bm in self.bookmarks.values():
            bm_url = bm.url.lower().rstrip('/')
            if bm_url == normalized:
                return bm
        
        return None
    
    def url_exists(self, url: str) -> bool:
        """Check if a URL already exists in bookmarks"""
        return self.find_by_url(url) is not None
    
    def get_domain_stats(self) -> List[Tuple[str, int]]:
        """Get bookmark count per domain"""
        domain_counts: Dict[str, int] = {}
        for bm in self.bookmarks.values():
            domain = bm.domain
            if domain:
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
        return sorted(domain_counts.items(), key=lambda x: -x[1])
    
    def clean_tracking_params(self) -> int:
        """Clean tracking parameters from all URLs"""
        cleaned = 0
        for bm in self.bookmarks.values():
            clean_url = bm.clean_url()
            if clean_url != bm.url:
                bm.url = clean_url
                bm.modified_at = datetime.now().isoformat()
                cleaned += 1
        
        if cleaned > 0:
            self.save_bookmarks()
        return cleaned
    
    def merge_tags(self, source_tag: str, target_tag: str) -> int:
        """Merge one tag into another across all bookmarks"""
        count = 0
        for bm in self.bookmarks.values():
            if source_tag in bm.tags:
                bm.tags.remove(source_tag)
                if target_tag not in bm.tags:
                    bm.tags.append(target_tag)
                count += 1
        
        if count > 0:
            self.save_bookmarks()
        return count
    
    def export_html(self, filepath: str, category: str = None):
        """Export bookmarks to HTML format"""
        if category:
            by_category = {category: self.get_bookmarks_by_category(category)}
        else:
            by_category: Dict[str, List[Bookmark]] = {}
            for bm in self.bookmarks.values():
                by_category.setdefault(bm.category, []).append(bm)
        
        # Sort categories
        uncategorized = [c for c in by_category if "Uncategorized" in c]
        regular = sorted([c for c in by_category if "Uncategorized" not in c])
        categories = regular + uncategorized
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write('<!DOCTYPE NETSCAPE-Bookmark-file-1>\n')
            f.write('<!-- Exported by Bookmark Organizer Pro v4 -->\n')
            f.write('<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">\n')
            f.write('<TITLE>Bookmarks</TITLE>\n<H1>Bookmarks</H1>\n<DL><p>\n')
            
            for cat in categories:
                bookmarks = by_category.get(cat, [])
                if not bookmarks:
                    continue
                
                f.write(f'    <DT><H3>{self._escape_html(cat)}</H3>\n    <DL><p>\n')
                for bm in bookmarks:
                    attrs = f'HREF="{self._escape_html(bm.url)}"'
                    if bm.add_date:
                        attrs += f' ADD_DATE="{bm.add_date}"'
                    if bm.icon:
                        attrs += f' ICON="{bm.icon}"'
                    if bm.tags:
                        attrs += f' TAGS="{",".join(bm.tags)}"'
                    f.write(f'        <DT><A {attrs}>{self._escape_html(bm.title)}</A>\n')
                f.write('    </DL><p>\n')
            
            f.write('</DL><p>\n')
    
    def export_json(self, filepath: str):
        """Export bookmarks to JSON format"""
        data = {
            "version": 4,
            "exported_at": datetime.now().isoformat(),
            "app_version": APP_VERSION,
            "categories": {name: cat.to_dict() 
                          for name, cat in self.category_manager.categories.items()},
            "tags": [tag.to_dict() for tag in self.tag_manager.tags.values()],
            "bookmarks": [bm.to_dict() for bm in self.bookmarks.values()]
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def export_csv(self, filepath: str):
        """Export bookmarks to CSV format"""
        with open(filepath, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Title', 'URL', 'Category', 'Tags', 'Notes', 
                           'Created', 'Visits', 'Is Pinned'])
            for bm in self.bookmarks.values():
                writer.writerow([
                    bm.title,
                    bm.url,
                    bm.category,
                    ','.join(bm.tags),
                    bm.notes,
                    bm.created_at,
                    bm.visit_count,
                    bm.is_pinned
                ])
    
    def export_markdown(self, filepath: str):
        """Export bookmarks to Markdown format"""
        by_category: Dict[str, List[Bookmark]] = {}
        for bm in self.bookmarks.values():
            by_category.setdefault(bm.category, []).append(bm)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f'# Bookmarks\n\n')
            f.write(f'Exported: {datetime.now().strftime("%Y-%m-%d %H:%M")}\n\n')
            f.write(f'Total: {len(self.bookmarks)} bookmarks\n\n---\n\n')
            
            for cat in sorted(by_category.keys()):
                bookmarks = by_category[cat]
                f.write(f'## {cat}\n\n')
                for bm in bookmarks:
                    tags_str = ' '.join(f'`{t}`' for t in bm.tags) if bm.tags else ''
                    f.write(f'- [{bm.title}]({bm.url})')
                    if tags_str:
                        f.write(f' {tags_str}')
                    f.write('\n')
                    if bm.notes:
                        f.write(f'  > {bm.notes}\n')
                f.write('\n')
    
    def export_txt(self, filepath: str, include_titles: bool = True):
        """Export bookmarks to text format"""
        by_category: Dict[str, List[Bookmark]] = {}
        for bm in self.bookmarks.values():
            by_category.setdefault(bm.category, []).append(bm)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            for cat in sorted(by_category.keys()):
                f.write(f"=== {cat} ===\n\n")
                for bm in by_category[cat]:
                    if include_titles:
                        f.write(f"{bm.title}\n{bm.url}\n\n")
                    else:
                        f.write(f"{bm.url}\n")
                f.write("\n")
    
    def export_urls_only(self, filepath: str):
        """Export just URLs"""
        with open(filepath, 'w', encoding='utf-8') as f:
            for bm in self.bookmarks.values():
                f.write(bm.url + '\n')
    
    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters"""
        return (text.replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;")
                   .replace('"', "&quot;"))
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        total = len(self.bookmarks)
        category_counts = self.get_category_counts()
        tag_counts = self.get_tag_counts()
        domain_stats = self.get_domain_stats()[:10]
        duplicates = self.find_duplicates()
        
        # Calculate age distribution
        age_dist = {"<7 days": 0, "7-30 days": 0, "1-6 months": 0, ">6 months": 0}
        for bm in self.bookmarks.values():
            age = bm.age_days
            if age < 7:
                age_dist["<7 days"] += 1
            elif age < 30:
                age_dist["7-30 days"] += 1
            elif age < 180:
                age_dist["1-6 months"] += 1
            else:
                age_dist[">6 months"] += 1
        
        return {
            "total_bookmarks": total,
            "total_categories": len(self.category_manager.categories),
            "total_tags": len(tag_counts),
            "category_counts": category_counts,
            "tag_counts": dict(sorted(tag_counts.items(), key=lambda x: -x[1])[:20]),
            "top_domains": domain_stats,
            "duplicate_groups": len(duplicates),
            "duplicate_bookmarks": sum(len(bms) - 1 for bms in duplicates.values()),
            "uncategorized": category_counts.get("Uncategorized / Needs Review", 0),
            "pinned": len(self.get_pinned_bookmarks()),
            "archived": len(self.get_archived_bookmarks()),
            "stale": len(self.get_stale_bookmarks()),
            "broken": len(self.find_broken_links()),
            "age_distribution": age_dist,
            "with_notes": sum(1 for bm in self.bookmarks.values() if bm.notes),
            "with_tags": sum(1 for bm in self.bookmarks.values() if bm.tags),
        }




# =============================================================================
# AI Provider Configuration
# =============================================================================
@dataclass
class AIProviderInfo:
    """Information about an AI provider"""
    name: str
    display_name: str
    api_key_url: str
    api_key_env: str
    models: List[str]
    default_model: str
    description: str
    requires_api_key: bool = True
    free_tier: bool = False
    local: bool = False


AI_PROVIDERS = {
    "openai": AIProviderInfo(
        name="openai",
        display_name="OpenAI",
        api_key_url="https://platform.openai.com/api-keys",
        api_key_env="OPENAI_API_KEY",
        models=["gpt-4o-mini", "gpt-4o", "gpt-4.1", "gpt-4.1-mini", "gpt-3.5-turbo"],
        default_model="gpt-4o-mini",
        description="GPT models - reliable and fast"
    ),
    "anthropic": AIProviderInfo(
        name="anthropic",
        display_name="Anthropic Claude",
        api_key_url="https://console.anthropic.com/settings/keys",
        api_key_env="ANTHROPIC_API_KEY",
        models=["claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022", 
                "claude-3-5-haiku-20241022", "claude-3-haiku-20240307"],
        default_model="claude-sonnet-4-20250514",
        description="Claude models - excellent reasoning"
    ),
    "google": AIProviderInfo(
        name="google",
        display_name="Google Gemini",
        api_key_url="https://aistudio.google.com/app/apikey",
        api_key_env="GOOGLE_API_KEY",
        models=["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-2.5-flash", 
                "gemini-2.5-pro", "gemini-1.5-flash"],
        default_model="gemini-2.0-flash",
        description="Free tier available, fast",
        free_tier=True
    ),
    "groq": AIProviderInfo(
        name="groq",
        display_name="Groq",
        api_key_url="https://console.groq.com/keys",
        api_key_env="GROQ_API_KEY",
        models=["llama-3.3-70b-versatile", "llama3-70b-8192", "llama3-8b-8192", 
                "gemma2-9b-it", "mixtral-8x7b-32768"],
        default_model="llama-3.3-70b-versatile",
        description="Ultra-fast inference, free tier",
        free_tier=True
    ),
    "ollama": AIProviderInfo(
        name="ollama",
        display_name="Ollama (Local)",
        api_key_url="https://ollama.com/download",
        api_key_env="",
        models=["llama3.2", "llama3.1", "mistral", "qwen2.5", "phi3", 
                "gemma2", "deepseek-coder-v2"],
        default_model="llama3.2",
        description="Run locally, completely free",
        requires_api_key=False,
        free_tier=True,
        local=True
    ),
}


class AIConfigManager:
    """
        Manages AI provider configuration.
        
        Stores and retrieves AI API settings for multiple providers
        including OpenAI, Anthropic, Google, Groq, and Ollama.
        
        Attributes:
            config_file: Path to AI config JSON
            provider: Current AI provider name
            model: Current model identifier
            api_keys: Dict of API keys per provider
        
        Methods:
            get_provider(): Get current provider
            set_provider(name): Set current provider
            get_api_key(provider): Get API key for provider
            set_api_key(provider, key): Set API key
            get_model(): Get current model
            set_model(model): Set current model
            test_connection(): Test current configuration
        
        Supported Providers:
            - OpenAI (GPT-4, GPT-3.5)
            - Anthropic (Claude)
            - Google (Gemini)
            - Groq (Mixtral, LLaMA)
            - Ollama (local models)
        """
    
    def __init__(self, filepath: Path = AI_CONFIG_FILE):
        self.filepath = filepath
        self._config: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self):
        """Load configuration from file"""
        if self.filepath.exists():
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
            except Exception:
                pass
        
        # Set defaults
        self._config.setdefault("provider", "google")
        self._config.setdefault("model", "gemini-2.0-flash")
        self._config.setdefault("api_keys", {})
        self._config.setdefault("batch_size", 20)
        self._config.setdefault("requests_per_minute", 30)
        self._config.setdefault("auto_create_categories", True)
        self._config.setdefault("fetch_metadata", False)
        self._config.setdefault("ollama_url", "http://localhost:11434")
        self._config.setdefault("min_confidence", 0.5)
        self._config.setdefault("auto_apply", False)
        self._config.setdefault("suggest_tags", True)
    
    def save_config(self):
        """Save configuration to file"""
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2)
        except Exception as e:
            print(f"Error saving AI config: {e}")
    
    def get_provider(self) -> str:
        return self._config.get("provider", "google")
    
    def get_model(self) -> str:
        return self._config.get("model", "gemini-2.0-flash")
    
    def get_batch_size(self) -> int:
        return self._config.get("batch_size", 20)
    
    def get_rate_limit(self) -> int:
        return self._config.get("requests_per_minute", 30)
    
    def get_auto_create_categories(self) -> bool:
        return self._config.get("auto_create_categories", True)
    
    def get_fetch_metadata(self) -> bool:
        return self._config.get("fetch_metadata", False)
    
    def get_ollama_url(self) -> str:
        return self._config.get("ollama_url", "http://localhost:11434")
    
    def get_min_confidence(self) -> float:
        return self._config.get("min_confidence", 0.5)
    
    def get_auto_apply(self) -> bool:
        return self._config.get("auto_apply", False)
    
    def get_suggest_tags(self) -> bool:
        return self._config.get("suggest_tags", True)
    
    def get_api_key(self, provider: str = None) -> str:
        provider = provider or self.get_provider()
        key = self._config.get("api_keys", {}).get(provider, "")
        if not key:
            info = AI_PROVIDERS.get(provider)
            if info and info.api_key_env:
                key = os.environ.get(info.api_key_env, "")
        return key
    
    def set_provider(self, v):
        self._config["provider"] = v
        self.save_config()
    
    def set_model(self, v):
        self._config["model"] = v
        self.save_config()
    
    def set_api_key(self, provider: str, key: str):
        self._config.setdefault("api_keys", {})[provider] = key
        self.save_config()
    
    def set_batch_size(self, v):
        self._config["batch_size"] = max(5, min(50, v))
        self.save_config()
    
    def set_rate_limit(self, v):
        self._config["requests_per_minute"] = max(1, min(120, v))
        self.save_config()
    
    def set_auto_create_categories(self, v):
        self._config["auto_create_categories"] = bool(v)
        self.save_config()
    
    def set_fetch_metadata(self, v):
        self._config["fetch_metadata"] = bool(v)
        self.save_config()
    
    def set_min_confidence(self, v):
        self._config["min_confidence"] = max(0.0, min(1.0, float(v)))
        self.save_config()
    
    def set_auto_apply(self, v):
        self._config["auto_apply"] = bool(v)
        self.save_config()
    
    def set_suggest_tags(self, v):
        self._config["suggest_tags"] = bool(v)
        self.save_config()
    
    def is_configured(self) -> bool:
        """Check if AI is configured and ready"""
        provider = self.get_provider()
        info = AI_PROVIDERS.get(provider)
        if info and not info.requires_api_key:
            return True
        return bool(self.get_api_key())
    
    def get_provider_info(self) -> Optional[AIProviderInfo]:
        return AI_PROVIDERS.get(self.get_provider())


# =============================================================================
# AI Client Base Class and Implementations
# =============================================================================
class AIClient:
    """
        Base class for AI provider clients.
        
        Defines the interface for AI operations that specific
        provider clients must implement.
        
        Methods (abstract):
            categorize(bookmarks): Suggest categories for bookmarks
            generate_tags(bookmarks): Generate tags for bookmarks
            summarize(bookmark): Generate summary for bookmark
            improve_title(bookmark): Suggest improved title
            test_connection(): Verify API connectivity
        """
    
    def categorize_bookmarks(self, bookmarks: List[Dict], categories: List[str],
                            allow_new: bool = True, suggest_tags: bool = True) -> List[Dict]:
        raise NotImplementedError
    
    def test_connection(self) -> Tuple[bool, str]:
        raise NotImplementedError
    
    def _parse_response(self, text: str, original: List[Dict]) -> List[Dict]:
        """Parse AI response into structured results"""
        try:
            cleaned_text = text.strip()
            
            # Extract JSON from markdown code blocks
            if "```json" in cleaned_text:
                match = re.search(r"```json\s*([\s\S]*?)\s*```", cleaned_text)
                if match:
                    cleaned_text = match.group(1)
            elif "```" in cleaned_text:
                match = re.search(r"```\s*([\s\S]*?)\s*```", cleaned_text)
                if match:
                    cleaned_text = match.group(1)
            
            # Find JSON object
            start = cleaned_text.find('{')
            end = cleaned_text.rfind('}')
            
            if start != -1 and end != -1:
                json_str = cleaned_text[start:end+1]
                data = json.loads(json_str)
                results = data.get("results", [])
            else:
                data = json.loads(cleaned_text)
                results = data.get("results", [])
            
            cleaned = []
            for r in results:
                if "url" in r and "category" in r:
                    cleaned.append({
                        "url": r["url"],
                        "category": str(r["category"]).strip(),
                        "confidence": min(1.0, max(0.0, float(r.get("confidence", 0.5)))),
                        "new_category": bool(r.get("new_category", False)),
                        "tags": r.get("tags", []),
                        "reasoning": r.get("reasoning", "")
                    })
            
            # Add missing URLs
            found_urls = {r["url"] for r in cleaned}
            for bm in original:
                if bm["url"] not in found_urls:
                    cleaned.append({
                        "url": bm["url"],
                        "category": "Uncategorized / Needs Review",
                        "confidence": 0.0,
                        "new_category": False,
                        "tags": []
                    })
            
            return cleaned
        except Exception as e:
            print(f"JSON Parse Error: {e}")
            return [{
                "url": bm["url"],
                "category": "Uncategorized / Needs Review",
                "confidence": 0.0,
                "new_category": False,
                "tags": []
            } for bm in original]
    
    def _build_prompt(self, bookmarks: List[Dict], categories: List[str],
                     allow_new: bool, suggest_tags: bool) -> str:
        """Build the prompt for categorization"""
        cats_str = ', '.join(f'"{c}"' for c in categories[:50])
        
        tags_instruction = ""
        if suggest_tags:
            tags_instruction = """
5. Suggest 1-3 relevant tags for each bookmark (short, lowercase, no spaces)
6. Suggest a better title if the current one is poor (too generic, has junk like "Home |", etc.)"""
        
        return f"""You are a bookmark categorization expert. Analyze each bookmark and assign the most appropriate category.

AVAILABLE CATEGORIES:
{cats_str}

{"You MAY suggest a new category if none fit well. Set 'new_category': true for suggested categories." if allow_new else "Use ONLY the categories listed above."}

BOOKMARKS TO CATEGORIZE:
{json.dumps(bookmarks, indent=2)}

INSTRUCTIONS:
1. Analyze each bookmark's URL and title to determine content type
2. Match to the most specific relevant category
3. Assign a confidence score (0.0-1.0)
4. If the URL is clearly technical (github, stackoverflow, etc.) categorize as Development{tags_instruction}

Respond with ONLY valid JSON in this exact format (no markdown, no explanation):
{{"results": [{{"url": "https://example.com", "category": "Category Name", "confidence": 0.9, "new_category": false, "tags": ["tag1", "tag2"], "suggested_title": "Better Title Here or null if current is fine"}}]}}"""


class OpenAIClient(AIClient):
    """OpenAI API client"""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self._client = None
    
    @property
    def client(self):
        if self._client is None:
            if not self.api_key:
                raise ValueError("OpenAI API key is required. Get one at platform.openai.com/api-keys")
            openai = ensure_package("openai")
            self._client = openai.OpenAI(api_key=self.api_key)
        return self._client
    
    def categorize_bookmarks(self, bookmarks: List[Dict], categories: List[str],
                            allow_new: bool = True, suggest_tags: bool = True) -> List[Dict]:
        prompt = self._build_prompt(bookmarks, categories, allow_new, suggest_tags)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You categorize bookmarks. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        return self._parse_response(response.choices[0].message.content, bookmarks)
    
    def test_connection(self) -> Tuple[bool, str]:
        try:
            if not self.api_key:
                return False, "OpenAI API key is required. Get one at platform.openai.com/api-keys"
            self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Say OK"}],
                max_tokens=10
            )
            return True, f"Connected to OpenAI ({self.model})"
        except Exception as e:
            return False, f"Error: {str(e)[:200]}"


class AnthropicClient(AIClient):
    """Anthropic Claude API client"""
    
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key
        self.model = model
        self._client = None
    
    @property
    def client(self):
        if self._client is None:
            if not self.api_key:
                raise ValueError("Anthropic API key is required. Get one at console.anthropic.com/settings/keys")
            anthropic = ensure_package("anthropic")
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client
    
    def categorize_bookmarks(self, bookmarks: List[Dict], categories: List[str],
                            allow_new: bool = True, suggest_tags: bool = True) -> List[Dict]:
        prompt = self._build_prompt(bookmarks, categories, allow_new, suggest_tags)
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        return self._parse_response(response.content[0].text, bookmarks)
    
    def test_connection(self) -> Tuple[bool, str]:
        try:
            if not self.api_key:
                return False, "Anthropic API key is required. Get one at console.anthropic.com/settings/keys"
            self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "Say OK"}]
            )
            return True, f"Connected to Anthropic ({self.model})"
        except Exception as e:
            return False, f"Error: {str(e)[:200]}"


class GoogleClient(AIClient):
    """Google Gemini API client"""
    
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model
        self._client = None
        self._genai = None
    
    @property
    def client(self):
        if self._client is None:
            if not self.api_key:
                raise ValueError("Google API key is required. Get one at aistudio.google.com/app/apikey")
            self._genai = ensure_package("google-generativeai", "google.generativeai")
            self._genai.configure(api_key=self.api_key)
            self._client = self._genai.GenerativeModel(self.model)
        return self._client
    
    def categorize_bookmarks(self, bookmarks: List[Dict], categories: List[str],
                            allow_new: bool = True, suggest_tags: bool = True) -> List[Dict]:
        prompt = self._build_prompt(bookmarks, categories, allow_new, suggest_tags)
        response = self.client.generate_content(prompt)
        return self._parse_response(response.text, bookmarks)
    
    def test_connection(self) -> Tuple[bool, str]:
        try:
            if not self.api_key:
                return False, "Google API key is required. Get one at aistudio.google.com/app/apikey"
            self.client.generate_content("Say OK")
            return True, f"Connected to Google Gemini ({self.model})"
        except Exception as e:
            return False, f"Error: {str(e)[:200]}"


class GroqClient(AIClient):
    """Groq API client"""
    
    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key
        self.model = model
        self._client = None
    
    @property
    def client(self):
        if self._client is None:
            if not self.api_key:
                raise ValueError("Groq API key is required. Get one at console.groq.com/keys")
            groq = ensure_package("groq")
            self._client = groq.Groq(api_key=self.api_key)
        return self._client
    
    def categorize_bookmarks(self, bookmarks: List[Dict], categories: List[str],
                            allow_new: bool = True, suggest_tags: bool = True) -> List[Dict]:
        prompt = self._build_prompt(bookmarks, categories, allow_new, suggest_tags)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You categorize bookmarks. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        return self._parse_response(response.choices[0].message.content, bookmarks)
    
    def test_connection(self) -> Tuple[bool, str]:
        try:
            if not self.api_key:
                return False, "Groq API key is required. Get one at console.groq.com/keys"
            self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Say OK"}],
                max_tokens=10
            )
            return True, f"Connected to Groq ({self.model})"
        except Exception as e:
            return False, f"Error: {str(e)[:200]}"


class OllamaClient(AIClient):
    """Ollama local API client"""
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2"):
        self.base_url = base_url.rstrip('/')
        self.model = model
    
    def categorize_bookmarks(self, bookmarks: List[Dict], categories: List[str],
                            allow_new: bool = True, suggest_tags: bool = True) -> List[Dict]:
        prompt = self._build_prompt(bookmarks, categories, allow_new, suggest_tags)
        
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3}
            },
            timeout=120
        )
        response.raise_for_status()
        return self._parse_response(response.json()["response"], bookmarks)
    
    def test_connection(self) -> Tuple[bool, str]:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = [m["name"] for m in response.json().get("models", [])]
                if self.model in models or any(self.model in m for m in models):
                    return True, f"Connected to Ollama ({self.model})"
                return False, f"Model {self.model} not found. Available: {', '.join(models[:5])}"
            return False, "Ollama not responding"
        except Exception as e:
            return False, f"Error: {str(e)[:150]}"


def create_ai_client(config: AIConfigManager) -> AIClient:
    """Factory function to create the appropriate AI client"""
    provider = config.get_provider()
    model = config.get_model()
    
    if provider == "openai":
        return OpenAIClient(config.get_api_key(), model)
    elif provider == "anthropic":
        return AnthropicClient(config.get_api_key(), model)
    elif provider == "google":
        return GoogleClient(config.get_api_key(), model)
    elif provider == "groq":
        return GroqClient(config.get_api_key(), model)
    elif provider == "ollama":
        return OllamaClient(config.get_ollama_url(), model)
    else:
        raise ValueError(f"Unknown provider: {provider}")




# =============================================================================
# Helper: Dark Title Bar (Windows 10/11)
# =============================================================================
def set_dark_title_bar(window):
    """Set dark title bar on Windows"""
    if not IS_WINDOWS:
        return
    try:
        window.update()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), 4)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), 4)
    except Exception:
        pass


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
    
    def __init__(self, widget, text: str, delay: int = 500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tooltip_window = None
        self.scheduled_id = None
        
        # Use add='+' to ADD bindings instead of replacing existing ones
        # This prevents overwriting click handlers on buttons
        widget.bind("<Enter>", self._schedule_show, add='+')
        widget.bind("<Leave>", self._hide, add='+')
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
        
        # Style the tooltip
        frame = tk.Frame(tw, bg=theme.bg_dark, bd=1, relief=tk.SOLID)
        frame.pack()
        
        label = tk.Label(
            frame, text=self.text, bg=theme.bg_dark, fg=theme.text_primary,
            font=FONTS.small(), padx=8, pady=4, justify=tk.LEFT
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
            self.tooltip_window.destroy()
            self.tooltip_window = None
    
    def update_text(self, new_text: str):
        """Update tooltip text"""
        self.text = new_text


def create_tooltip(widget, text: str, delay: int = 500) -> Tooltip:
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
                 state='normal', padx=15, pady=8, style="default",
                 tooltip: str = None):
        
        theme = get_theme()
        
        # Determine colors based on style
        if style == "primary":
            bg = bg or theme.accent_primary
            hover_bg = hover_bg or theme.accent_primary
        elif style == "success":
            bg = bg or theme.accent_success
            hover_bg = hover_bg or theme.accent_success
        elif style == "danger":
            bg = bg or theme.accent_error
            hover_bg = hover_bg or theme.accent_error
        elif style == "warning":
            bg = bg or theme.accent_warning
            hover_bg = hover_bg or theme.accent_warning
        else:
            bg = bg or theme.bg_secondary
            hover_bg = hover_bg or theme.bg_hover
        
        fg = fg or theme.text_primary
        
        super().__init__(parent, bg=bg)
        self.command = command
        self.default_bg = bg
        self.hover_bg = hover_bg
        self.fg = fg
        self.state = state
        self.style = style
        
        # Icon + text
        display_text = f"{icon} {text}" if icon else text
        
        self.label = tk.Label(
            self, text=display_text, bg=bg,
            fg=fg if state == 'normal' else theme.text_muted,
            font=font, cursor="hand2" if state == 'normal' else "arrow"
        )
        self.label.pack(padx=padx, pady=pady)
        
        if width:
            self.configure(width=width)
        
        # Add tooltip if provided
        if tooltip:
            self.tooltip = Tooltip(self, tooltip)
        
        if state == 'normal':
            for widget in [self, self.label]:
                widget.bind("<Enter>", self._on_enter)
                widget.bind("<Leave>", self._on_leave)
                widget.bind("<Button-1>", self._on_click)
    
    def _on_enter(self, e):
        if self.state == 'normal':
            self.configure(bg=self.hover_bg)
            self.label.configure(bg=self.hover_bg)
    
    def _on_leave(self, e):
        if self.state == 'normal':
            self.configure(bg=self.default_bg)
            self.label.configure(bg=self.default_bg)
    
    def _on_click(self, e):
        if self.state == 'normal' and self.command:
            self.command()
    
    def set_state(self, state):
        self.state = state
        theme = get_theme()
        if state == 'normal':
            self.label.configure(fg=self.fg, cursor="hand2")
        else:
            self.label.configure(fg=theme.text_muted, cursor="arrow")
    
    def set_text(self, text):
        self.label.configure(text=text)


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
    
    def __init__(self, parent, textvariable, placeholder="Search...", 
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
            self.inner, text="🔍", bg=theme.bg_secondary,
            fg=theme.text_muted, font=FONTS.body()
        )
        self.icon_label.pack(side=tk.LEFT, padx=(0, 8))
        
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
            self.help_btn.bind("<Button-1>", self._show_help)
        
        # Clear button
        self.clear_btn = tk.Label(
            self.inner, text="✕", bg=theme.bg_secondary,
            fg=theme.text_muted, font=FONTS.body(), cursor="hand2"
        )
        self.clear_btn.bind("<Button-1>", self._clear)
        
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
        self.border.configure(bg=self.theme.accent_primary)
        self.icon_label.configure(fg=self.theme.accent_primary)
    
    def _on_unfocus(self, e):
        self.border.configure(bg=self.theme.border)
        self.icon_label.configure(fg=self.theme.text_muted)
    
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
    """
        Represents a bookmark tag with metadata.
        
        Attributes:
            name: Tag name (unique identifier)
            color: Hex color code for display
            description: Optional tag description
            created_at: ISO timestamp of creation
            usage_count: Number of bookmarks using this tag
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
        """
    
    def __init__(self, parent, tag_name: str, color: str = None,
                 on_remove: Callable = None, removable: bool = True):
        theme = get_theme()
        
        # Generate color if not provided
        if not color:
            colors = [
                theme.accent_primary, theme.accent_success, theme.accent_warning,
                theme.accent_purple, theme.accent_cyan, theme.accent_pink
            ]
            hash_val = sum(ord(c) for c in tag_name)
            color = colors[hash_val % len(colors)]
        
        # Create semi-transparent background
        bg_color = color + "26"  # Add alpha
        
        super().__init__(parent, bg=theme.bg_primary)
        
        self.tag_name = tag_name
        self.color = color
        self.on_remove = on_remove
        
        # Tag label
        self.label = tk.Label(
            self, text=f"#{tag_name}", bg=theme.bg_secondary,
            fg=color, font=FONTS.small(), padx=8, pady=2
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
            self.remove_btn.bind("<Button-1>", lambda e: on_remove(tag_name))
            self.remove_btn.bind("<Enter>", lambda e: self.remove_btn.configure(fg=theme.accent_error))
            self.remove_btn.bind("<Leave>", lambda e: self.remove_btn.configure(fg=theme.text_muted))


class TagEditor(tk.Frame, ThemedWidget):
    """
        Represents a bookmark tag with metadata.
        
        Attributes:
            name: Tag name (unique identifier)
            color: Hex color code for display
            description: Optional tag description
            created_at: ISO timestamp of creation
            usage_count: Number of bookmarks using this tag
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
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
        self.entry = tk.Entry(
            self.entry_frame, textvariable=self.entry_var,
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            font=FONTS.small()
        )
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.entry.bind("<Return>", self._add_tag)
        self.entry.bind("<KeyRelease>", self._on_key)
        
        self.add_btn = tk.Label(
            self.entry_frame, text="+", bg=theme.bg_secondary,
            fg=theme.accent_primary, font=("Segoe UI", 12),
            cursor="hand2", padx=8
        )
        self.add_btn.pack(side=tk.RIGHT)
        self.add_btn.bind("<Button-1>", self._add_tag)
        
        # Suggestions dropdown (hidden by default)
        self.suggestions_list = None
        
        self._refresh_tags()
    
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
    
    def _on_key(self, e):
        """Handle key events for autocomplete"""
        # Could implement autocomplete dropdown here
        pass
    
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




# =============================================================================
# Grid/Card View Components
# =============================================================================
class GridView(tk.Frame, ThemedWidget):
    """
        Grid/card view for displaying bookmarks.
        
        Displays bookmarks as cards in a responsive grid layout.
        
        Attributes:
            bookmarks: List of bookmarks to display
            columns: Number of columns
            card_width: Width of each card
            on_select: Selection callback
            on_open: Double-click callback
        
        Methods:
            set_bookmarks(bookmarks): Update displayed bookmarks
            get_selected(): Get selected bookmark IDs
            select_all(): Select all bookmarks
            clear_selection(): Clear selection
        
        Features:
            - Responsive column count
            - Smooth scrolling
            - Multi-select with Ctrl/Shift
            - Keyboard navigation
        """
    
    def __init__(self, parent, columns: int = 3,
                 on_select: Callable = None,
                 on_open: Callable = None,
                 on_context_menu: Callable = None,
                 favicon_manager: FaviconManager = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_primary)
        
        self.columns = columns
        self.on_select = on_select
        self.on_open = on_open
        self.on_context_menu = on_context_menu
        self.favicon_manager = favicon_manager
        self.theme = theme
        
        self.cards: Dict[int, BookmarkCard] = {}
        self.selected_ids: Set[int] = set()
        
        # Scrollable canvas
        self.canvas = tk.Canvas(self, bg=theme.bg_primary, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Inner frame for cards
        self.inner_frame = tk.Frame(self.canvas, bg=theme.bg_primary)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.inner_frame, anchor="nw")
        
        # Bindings
        self.inner_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
    
    def _on_frame_configure(self, e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    
    def _on_canvas_configure(self, e):
        # Adjust columns based on width
        card_width = 280
        new_cols = max(1, e.width // card_width)
        if new_cols != self.columns:
            self.columns = new_cols
            self._reflow_cards()
    
    def _on_mousewheel(self, e):
        self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
    
    def load_bookmarks(self, bookmarks: List[Bookmark]):
        """Load bookmarks into grid"""
        # Clear existing
        for card in self.cards.values():
            card.destroy()
        self.cards.clear()
        self.selected_ids.clear()
        
        # Create cards
        for i, bm in enumerate(bookmarks):
            card = BookmarkCard(
                self.inner_frame, bm,
                on_click=self._on_card_click,
                on_double_click=self._on_card_double_click,
                on_right_click=self._on_card_right_click,
                favicon_manager=self.favicon_manager
            )
            self.cards[bm.id] = card
            
            row = i // self.columns
            col = i % self.columns
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
        
        # Configure grid weights
        for i in range(self.columns):
            self.inner_frame.columnconfigure(i, weight=1)
    
    def _reflow_cards(self):
        """Reflow cards when column count changes"""
        cards_list = list(self.cards.values())
        for i, card in enumerate(cards_list):
            row = i // self.columns
            col = i % self.columns
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
    
    def _on_card_click(self, bookmark: Bookmark):
        # Single select for now
        for card in self.cards.values():
            card.set_selected(False)
        
        self.selected_ids = {bookmark.id}
        if bookmark.id in self.cards:
            self.cards[bookmark.id].set_selected(True)
        
        if self.on_select:
            self.on_select([bookmark])
    
    def _on_card_double_click(self, bookmark: Bookmark):
        if self.on_open:
            self.on_open(bookmark)
    
    def _on_card_right_click(self, event, bookmark: Bookmark):
        if self.on_context_menu:
            self.on_context_menu(event, bookmark)
    
    def get_selected(self) -> List[int]:
        """Get selected bookmark IDs"""
        return list(self.selected_ids)
    
    def select_all(self):
        """Select all cards"""
        self.selected_ids = set(self.cards.keys())
        for card in self.cards.values():
            card.set_selected(True)
    
    def clear_selection(self):
        """Clear selection"""
        self.selected_ids.clear()
        for card in self.cards.values():
            card.set_selected(False)


# =============================================================================
# Analytics Dashboard
# =============================================================================
class DashboardPanel(tk.Frame, ThemedWidget):
    """
        Analytics dashboard panel.
        
        Displays bookmark statistics, charts, and insights.
        
        Sections:
            - Overview: Total counts, recent additions
            - Categories: Distribution chart
            - Tags: Tag cloud
            - Domains: Top domains
            - Timeline: Activity over time
            - Health: Broken links, duplicates
        
        Methods:
            refresh(): Update all statistics
            set_bookmarks(bookmarks): Update data source
        """
    
    def __init__(self, parent, bookmark_manager: BookmarkManager):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_primary)
        
        self.manager = bookmark_manager
        self.theme = theme
        
        self._build_ui()
    
    def _build_ui(self):
        """Build dashboard UI"""
        # Title
        title = tk.Label(
            self, text="📊 Dashboard", bg=self.theme.bg_primary,
            fg=self.theme.text_primary, font=FONTS.title()
        )
        title.pack(pady=(20, 15), padx=20, anchor="w")
        
        # Stats grid
        stats_frame = tk.Frame(self, bg=self.theme.bg_primary)
        stats_frame.pack(fill=tk.X, padx=20, pady=10)
        
        stats = self.manager.get_statistics()
        
        # Stat cards
        stat_cards = [
            ("📚", "Total Bookmarks", stats["total_bookmarks"]),
            ("📁", "Categories", stats["total_categories"]),
            ("🏷️", "Tags Used", stats["total_tags"]),
            ("📌", "Pinned", stats["pinned"]),
            ("📥", "Uncategorized", stats["uncategorized"]),
            ("🔗", "Duplicates", stats["duplicate_bookmarks"]),
            ("⚠️", "Broken Links", stats["broken"]),
            ("🕐", "Stale (90+ days)", stats["stale"]),
        ]
        
        for i, (icon, label, value) in enumerate(stat_cards):
            card = self._create_stat_card(stats_frame, icon, label, value)
            row = i // 4
            col = i % 4
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
        
        for i in range(4):
            stats_frame.columnconfigure(i, weight=1)
        
        # Category distribution
        cat_frame = tk.LabelFrame(
            self, text="📊 Category Distribution", bg=self.theme.bg_primary,
            fg=self.theme.text_primary, font=("Segoe UI", 11, "bold")
        )
        cat_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        cat_counts = stats["category_counts"]
        sorted_cats = sorted(cat_counts.items(), key=lambda x: -x[1])[:10]
        
        for cat, count in sorted_cats:
            self._create_bar(cat_frame, cat, count, stats["total_bookmarks"])
        
        # Top domains
        domain_frame = tk.LabelFrame(
            self, text="🌐 Top Domains", bg=self.theme.bg_primary,
            fg=self.theme.text_primary, font=("Segoe UI", 11, "bold")
        )
        domain_frame.pack(fill=tk.X, padx=20, pady=(0, 20))
        
        for domain, count in stats["top_domains"][:5]:
            row = tk.Frame(domain_frame, bg=self.theme.bg_primary)
            row.pack(fill=tk.X, padx=10, pady=3)
            
            tk.Label(
                row, text=domain, bg=self.theme.bg_primary,
                fg=self.theme.text_primary, font=FONTS.body(),
                anchor="w"
            ).pack(side=tk.LEFT)
            
            tk.Label(
                row, text=str(count), bg=self.theme.bg_primary,
                fg=self.theme.text_muted, font=FONTS.body()
            ).pack(side=tk.RIGHT)
    
    def _create_stat_card(self, parent, icon: str, label: str, value: int) -> tk.Frame:
        """Create a stat card widget"""
        card = tk.Frame(parent, bg=self.theme.bg_secondary, padx=15, pady=12)
        
        # Icon
        tk.Label(
            card, text=icon, bg=self.theme.bg_secondary,
            font=("Segoe UI", 20)
        ).pack(anchor="w")
        
        # Value
        tk.Label(
            card, text=str(value), bg=self.theme.bg_secondary,
            fg=self.theme.text_primary, font=("Segoe UI", 24, "bold")
        ).pack(anchor="w")
        
        # Label
        tk.Label(
            card, text=label, bg=self.theme.bg_secondary,
            fg=self.theme.text_muted, font=FONTS.body()
        ).pack(anchor="w")
        
        return card
    
    def _create_bar(self, parent, label: str, value: int, total: int):
        """Create a horizontal bar chart item"""
        row = tk.Frame(parent, bg=self.theme.bg_primary)
        row.pack(fill=tk.X, padx=10, pady=4)
        
        # Label
        label_text = label[:25] + "..." if len(label) > 25 else label
        tk.Label(
            row, text=label_text, bg=self.theme.bg_primary,
            fg=self.theme.text_primary, font=FONTS.small(),
            width=25, anchor="w"
        ).pack(side=tk.LEFT)
        
        # Bar
        bar_frame = tk.Frame(row, bg=self.theme.bg_tertiary, height=16)
        bar_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        bar_frame.pack_propagate(False)
        
        pct = (value / total * 100) if total > 0 else 0
        bar = tk.Frame(bar_frame, bg=self.theme.accent_primary, height=16)
        bar.place(relwidth=min(1.0, value/total) if total > 0 else 0, relheight=1.0)
        
        # Count
        tk.Label(
            row, text=f"{value} ({pct:.1f}%)", bg=self.theme.bg_primary,
            fg=self.theme.text_muted, font=FONTS.small(), width=12
        ).pack(side=tk.RIGHT)
    
    def refresh(self):
        """Refresh dashboard data"""
        for widget in self.winfo_children():
            widget.destroy()
        self._build_ui()




# =============================================================================
# System Tray Support
# =============================================================================
class SystemTrayManager:
    """
        System tray integration manager.
        
        Provides system tray icon with menu for quick access
        to common functions.
        
        Attributes:
            app: Main application reference
            icon: pystray Icon instance
            menu: Tray menu items
        
        Features:
            - Quick add bookmark
            - Show/hide window
            - Recent bookmarks list
            - Exit application
        
        Note:
            Requires pystray package (optional dependency)
        """
    
    def __init__(self, app):
        self.app = app
        self.icon = None
        self._running = False
    
    def start(self):
        """Start system tray icon"""
        if not HAS_TRAY or not HAS_PIL:
            return False
        
        try:
            # Create icon image
            icon_image = self._create_icon()
            
            # Create menu
            menu = pystray.Menu(
                TrayItem("Show Window", self._show_window, default=True),
                TrayItem("Quick Add URL", self._quick_add),
                pystray.Menu.SEPARATOR,
                TrayItem("Recent Bookmarks", pystray.Menu(
                    *self._get_recent_menu_items()
                )),
                pystray.Menu.SEPARATOR,
                TrayItem("Exit", self._exit_app)
            )
            
            self.icon = pystray.Icon(
                APP_NAME, icon_image, APP_NAME, menu
            )
            
            # Run in thread
            self._running = True
            thread = threading.Thread(target=self.icon.run, daemon=True)
            thread.start()
            
            return True
        except Exception as e:
            print(f"Error starting system tray: {e}")
            return False
    
    def stop(self):
        """Stop system tray icon"""
        self._running = False
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
    
    def _create_icon(self) -> Image.Image:
        """Create the tray icon image"""
        size = 64
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Draw bookmark shape
        theme = get_theme()
        color = theme.accent_primary
        
        # Simple bookmark icon
        points = [
            (16, 8), (48, 8), (48, 56), (32, 44), (16, 56)
        ]
        draw.polygon(points, fill=color)
        
        return img
    
    def _show_window(self):
        """Show the main window"""
        self.app.root.after(0, self._do_show_window)
    
    def _do_show_window(self):
        self.app.root.deiconify()
        self.app.root.lift()
        self.app.root.focus_force()
    
    def _quick_add(self):
        """Quick add URL from clipboard"""
        self.app.root.after(0, self._do_quick_add)
    
    def _do_quick_add(self):
        try:
            clipboard = self.app.root.clipboard_get()
            if clipboard.startswith(('http://', 'https://')):
                self.app.add_bookmark_from_url(clipboard)
                self.app.show_notification("Bookmark Added", f"Added: {clipboard[:50]}...")
        except Exception:
            pass
    
    def _get_recent_menu_items(self) -> List[TrayItem]:
        """Get recent bookmarks for menu"""
        items = []
        recent = self.app.bookmark_manager.get_recent_bookmarks(days=7)[:5]
        
        for bm in recent:
            title = bm.title[:30] + "..." if len(bm.title) > 30 else bm.title
            items.append(TrayItem(
                title,
                lambda b=bm: self._open_bookmark(b)
            ))
        
        if not items:
            items.append(TrayItem("No recent bookmarks", None, enabled=False))
        
        return items
    
    def _open_bookmark(self, bookmark: Bookmark):
        """Open a bookmark in browser"""
        webbrowser.open(bookmark.url)
        bookmark.record_visit()
        self.app.bookmark_manager.save_bookmarks()
    
    def _exit_app(self):
        """Exit the application"""
        self.app.root.after(0, self.app.on_close)
    
    def show_notification(self, title: str, message: str):
        """Show a notification"""
        if self.icon and hasattr(self.icon, 'notify'):
            try:
                self.icon.notify(message, title)
            except Exception:
                pass


# =============================================================================
# Theme Selector Dialog
# =============================================================================
class BookmarkListView(tk.Frame, ThemedWidget):
    """
        Represents a single bookmark with all metadata.
        
        Attributes:
            id: Unique integer identifier
            url: Bookmark URL
            title: Display title
            category: Category name
            tags: List of tag names
            ai_tags: List of AI-suggested tags
            description: Optional description
            favicon_url: URL to favicon image
            created_at: ISO timestamp of creation
            updated_at: ISO timestamp of last update
            visited_at: ISO timestamp of last visit
            visit_count: Number of times visited
            is_valid: Whether URL validation passed
            is_pinned: Whether bookmark is pinned
            ai_category: AI-suggested category
            ai_summary: AI-generated summary
            notes: User notes
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
            matches_search(query): Check if bookmark matches search
        """
    
    def __init__(self, parent, on_select: Callable = None,
                 on_open: Callable = None, on_context_menu: Callable = None,
                 favicon_manager: FaviconManager = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_primary)
        
        self.on_select = on_select
        self.on_open = on_open
        self.on_context_menu = on_context_menu
        self.favicon_manager = favicon_manager
        self.theme = theme
        
        self._bookmarks: Dict[str, Bookmark] = {}  # iid -> bookmark
        self._favicon_images: Dict[str, ImageTk.PhotoImage] = {}
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the list view UI"""
        # Configure style
        style = ttk.Style()
        style.configure("Bookmark.Treeview",
            background=self.theme.bg_primary,
            foreground=self.theme.text_primary,
            fieldbackground=self.theme.bg_primary,
            rowheight=32
        )
        style.configure("Bookmark.Treeview.Heading",
            background=self.theme.bg_secondary,
            foreground=self.theme.text_primary,
            font=("Segoe UI", 9, "bold")
        )
        style.map("Bookmark.Treeview",
            background=[("selected", self.theme.selection)],
            foreground=[("selected", self.theme.text_primary)]
        )
        
        # Treeview with columns
        columns = ("title", "domain", "category", "tags", "added")
        self.tree = ttk.Treeview(
            self, columns=columns, show="headings",
            style="Bookmark.Treeview", selectmode="extended"
        )
        
        # Column configuration
        self.tree.heading("title", text="Title", anchor="w")
        self.tree.heading("domain", text="Domain", anchor="w")
        self.tree.heading("category", text="Category", anchor="w")
        self.tree.heading("tags", text="Tags", anchor="w")
        self.tree.heading("added", text="Added", anchor="w")
        
        self.tree.column("title", width=300, minwidth=150)
        self.tree.column("domain", width=150, minwidth=100)
        self.tree.column("category", width=150, minwidth=100)
        self.tree.column("tags", width=150, minwidth=80)
        self.tree.column("added", width=100, minwidth=80)
        
        # Scrollbars
        vsb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Layout
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # Bindings
        self.tree.bind("<<TreeviewSelect>>", self._on_selection)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Button-3>", self._on_right_click)
        self.tree.bind("<Return>", self._on_double_click)
        
        # Drag and drop
        self.tree.bind("<ButtonPress-1>", self._on_drag_start)
        self.tree.bind("<B1-Motion>", self._on_drag_motion)
        self.tree.bind("<ButtonRelease-1>", self._on_drag_end)
        
        self._drag_data = {"item": None, "start_y": 0}
    
    def load_bookmarks(self, bookmarks: List[Bookmark]):
        """Load bookmarks into the list"""
        # Clear existing
        self.tree.delete(*self.tree.get_children())
        self._bookmarks.clear()
        
        for bm in bookmarks:
            # Format data
            tags_str = ", ".join(bm.tags[:3])
            if len(bm.tags) > 3:
                tags_str += f" +{len(bm.tags)-3}"
            
            try:
                added = datetime.fromisoformat(bm.created_at.replace('Z', '+00:00'))
                added_str = added.strftime("%Y-%m-%d")
            except Exception:
                added_str = ""
            
            # Insert item
            iid = self.tree.insert("", "end", values=(
                bm.title[:60],
                bm.domain,
                bm.category[:30],
                tags_str,
                added_str
            ))
            
            self._bookmarks[iid] = bm
    
    def _on_selection(self, e):
        """Handle selection change"""
        if self.on_select:
            selected = self.get_selected_bookmarks()
            self.on_select(selected)
    
    def _on_double_click(self, e):
        """Handle double click"""
        if self.on_open:
            selected = self.get_selected_bookmarks()
            if selected:
                self.on_open(selected[0])
    
    def _on_right_click(self, e):
        """Handle right click"""
        # Select item under cursor
        item = self.tree.identify_row(e.y)
        if item:
            if item not in self.tree.selection():
                self.tree.selection_set(item)
        
        if self.on_context_menu:
            selected = self.get_selected_bookmarks()
            if selected:
                self.on_context_menu(e, selected)
    
    def _on_drag_start(self, e):
        """Start drag operation"""
        item = self.tree.identify_row(e.y)
        if item:
            self._drag_data["item"] = item
            self._drag_data["start_y"] = e.y
    
    def _on_drag_motion(self, e):
        """Handle drag motion"""
        pass  # Could show visual feedback
    
    def _on_drag_end(self, e):
        """End drag operation"""
        self._drag_data["item"] = None
    
    def get_selected_bookmarks(self) -> List[Bookmark]:
        """Get selected bookmarks"""
        selected = []
        for iid in self.tree.selection():
            if iid in self._bookmarks:
                selected.append(self._bookmarks[iid])
        return selected
    
    def get_selected_ids(self) -> List[int]:
        """Get selected bookmark IDs"""
        return [bm.id for bm in self.get_selected_bookmarks()]
    
    def select_all(self):
        """Select all items"""
        self.tree.selection_set(self.tree.get_children())
    
    def clear_selection(self):
        """Clear selection"""
        self.tree.selection_remove(self.tree.selection())
    
    def refresh_item(self, bookmark: Bookmark):
        """Refresh a single item"""
        for iid, bm in self._bookmarks.items():
            if bm.id == bookmark.id:
                tags_str = ", ".join(bookmark.tags[:3])
                if len(bookmark.tags) > 3:
                    tags_str += f" +{len(bookmark.tags)-3}"
                
                try:
                    added = datetime.fromisoformat(bookmark.created_at.replace('Z', '+00:00'))
                    added_str = added.strftime("%Y-%m-%d")
                except Exception:
                    added_str = ""
                
                self.tree.item(iid, values=(
                    bookmark.title[:60],
                    bookmark.domain,
                    bookmark.category[:30],
                    tags_str,
                    added_str
                ))
                self._bookmarks[iid] = bookmark
                break


# =============================================================================
# Category Sidebar
# =============================================================================
class CategorySidebar(tk.Frame, ThemedWidget):
    """
        Represents a bookmark category.
        
        Attributes:
            name: Category name (unique identifier)
            parent: Parent category name (for nesting)
            icon: Emoji icon for display
            color: Optional color override
            sort_order: Order within parent
            created_at: ISO timestamp of creation
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
        """
    
    def __init__(self, parent, category_manager: CategoryManager,
                 on_select: Callable = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_secondary, width=250)
        
        self.category_manager = category_manager
        self.on_select = on_select
        self.theme = theme
        self.selected_category = None
        
        self.pack_propagate(False)
        
        self._build_ui()
    
    def _build_ui(self):
        """Build sidebar UI"""
        # Header
        header = tk.Frame(self, bg=self.theme.bg_secondary)
        header.pack(fill=tk.X, padx=15, pady=(15, 10))
        
        tk.Label(
            header, text="Categories", bg=self.theme.bg_secondary,
            fg=self.theme.text_primary, font=FONTS.header()
        ).pack(side=tk.LEFT)
        
        # Add button
        add_btn = tk.Label(
            header, text="+", bg=self.theme.bg_secondary,
            fg=self.theme.accent_primary, font=("Segoe UI", 14),
            cursor="hand2"
        )
        add_btn.pack(side=tk.RIGHT)
        add_btn.bind("<Button-1>", lambda e: self._add_category())
        
        # Special items
        specials_frame = tk.Frame(self, bg=self.theme.bg_secondary)
        specials_frame.pack(fill=tk.X, pady=(0, 10))
        
        self._create_special_item(specials_frame, "📚", "All Bookmarks", "_all")
        self._create_special_item(specials_frame, "📌", "Pinned", "_pinned")
        self._create_special_item(specials_frame, "🕐", "Recent", "_recent")
        self._create_special_item(specials_frame, "🏷️", "Tags", "_tags")
        
        # Separator
        tk.Frame(self, bg=self.theme.border, height=1).pack(fill=tk.X, padx=15, pady=5)
        
        # Scrollable categories
        self.canvas = tk.Canvas(self, bg=self.theme.bg_secondary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.categories_frame = tk.Frame(self.canvas, bg=self.theme.bg_secondary)
        
        self.categories_frame.bind("<Configure>", 
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        
        self.canvas.create_window((0, 0), window=self.categories_frame, anchor="nw", width=235)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.refresh_categories()
    
    def _create_special_item(self, parent, icon: str, text: str, key: str):
        """Create a special category item"""
        frame = tk.Frame(parent, bg=self.theme.bg_secondary)
        frame.pack(fill=tk.X)
        
        inner = tk.Frame(frame, bg=self.theme.bg_secondary)
        inner.pack(fill=tk.X, padx=15, pady=4)
        
        tk.Label(
            inner, text=icon, bg=self.theme.bg_secondary,
            font=FONTS.body()
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        tk.Label(
            inner, text=text, bg=self.theme.bg_secondary,
            fg=self.theme.text_primary, font=FONTS.body(),
            cursor="hand2"
        ).pack(side=tk.LEFT)
        
        for widget in [frame, inner] + list(inner.winfo_children()):
            widget.bind("<Button-1>", lambda e, k=key: self._select_category(k))
            widget.bind("<Enter>", lambda e, f=frame: f.configure(bg=self.theme.bg_hover))
            widget.bind("<Leave>", lambda e, f=frame: f.configure(bg=self.theme.bg_secondary))
    
    def refresh_categories(self, counts: Dict[str, int] = None):
        """Refresh the category list"""
        for widget in self.categories_frame.winfo_children():
            widget.destroy()
        
        counts = counts or {}
        
        for cat, depth in self.category_manager.get_tree():
            self._create_category_item(cat, counts.get(cat.name, 0), depth)
    
    def _create_category_item(self, category: Category, count: int, depth: int):
        """Create a category list item"""
        is_selected = category.name == self.selected_category
        bg = self.theme.selection if is_selected else self.theme.bg_secondary
        
        frame = tk.Frame(self.categories_frame, bg=bg)
        frame.pack(fill=tk.X)
        
        inner = tk.Frame(frame, bg=bg)
        inner.pack(fill=tk.X, padx=(15 + depth * 15, 15), pady=3)
        
        # Icon
        icon = category.icon or get_category_icon(category.name)
        tk.Label(
            inner, text=icon, bg=bg,
            font=FONTS.body()
        ).pack(side=tk.LEFT, padx=(0, 8))
        
        # Name
        name = category.name
        if len(name) > 20:
            name = name[:18] + "..."
        tk.Label(
            inner, text=name, bg=bg,
            fg=self.theme.text_primary, font=FONTS.body(),
            cursor="hand2"
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Count
        if count > 0:
            tk.Label(
                inner, text=str(count), bg=bg,
                fg=self.theme.text_muted, font=FONTS.small()
            ).pack(side=tk.RIGHT)
        
        # Bindings
        for widget in [frame, inner] + list(inner.winfo_children()):
            widget.bind("<Button-1>", lambda e, c=category.name: self._select_category(c))
            if not is_selected:
                widget.bind("<Enter>", lambda e, f=frame, i=inner: self._hover_enter(f, i))
                widget.bind("<Leave>", lambda e, f=frame, i=inner: self._hover_leave(f, i))
    
    def _hover_enter(self, frame, inner):
        frame.configure(bg=self.theme.bg_hover)
        inner.configure(bg=self.theme.bg_hover)
        for child in inner.winfo_children():
            try:
                child.configure(bg=self.theme.bg_hover)
            except: pass
    
    def _hover_leave(self, frame, inner):
        frame.configure(bg=self.theme.bg_secondary)
        inner.configure(bg=self.theme.bg_secondary)
        for child in inner.winfo_children():
            try:
                child.configure(bg=self.theme.bg_secondary)
            except: pass
    
    def _select_category(self, category: str):
        """Select a category"""
        self.selected_category = category
        self.refresh_categories()
        if self.on_select:
            self.on_select(category)
    
    def _add_category(self):
        """Add a new category"""
        name = simpledialog.askstring("New Category", "Enter category name:")
        if name and name.strip():
            if self.category_manager.add_category(name.strip()):
                self.refresh_categories()
            else:
                messagebox.showerror("Error", "Category already exists")




# =============================================================================
# Main Application Class
# =============================================================================
class ThemeSelectorDialog(tk.Toplevel, ThemedWidget):
    """
        Dialog for browsing and selecting themes.
        
        Displays all available themes with previews and allows
        switching or customizing themes.
        
        Features:
            - Theme list with previews
            - Dark/light mode indicator
            - Custom theme creation
            - Theme import/export
            - Live preview
        """
    
    def __init__(self, parent, theme_manager: ThemeManager):
        super().__init__(parent)
        self.theme_manager = theme_manager
        self.result = None
        theme = get_theme()
        
        self.title("Theme Settings")
        self.geometry("500x600")
        self.configure(bg=theme.bg_primary)
        self.transient(parent)
        self.grab_set()
        
        set_dark_title_bar(self)
        
        # Header
        header = tk.Frame(self, bg=theme.bg_dark, height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(
            header, text="🎨 Theme Settings", bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.title(bold=False)
        ).pack(side=tk.LEFT, padx=20, pady=15)
        
        # Main content
        content = tk.Frame(self, bg=theme.bg_primary)
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        # Current theme label
        tk.Label(
            content, text="Select Theme:", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        ).pack(anchor="w", pady=(0, 10))
        
        # Theme list with canvas for scrolling
        list_frame = tk.Frame(content, bg=theme.bg_secondary)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(list_frame, bg=theme.bg_secondary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.themes_inner = tk.Frame(canvas, bg=theme.bg_secondary)
        
        self.themes_inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.themes_inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Populate themes
        self._populate_themes()
        
        # Buttons
        btn_frame = tk.Frame(self, bg=theme.bg_primary)
        btn_frame.pack(fill=tk.X, padx=20, pady=15)
        
        ModernButton(
            btn_frame, text="Import Theme", command=self._import_theme,
            icon="📥"
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        ModernButton(
            btn_frame, text="Close", command=self.destroy
        ).pack(side=tk.RIGHT)
        
        self.center_window()
    
    def _populate_themes(self):
        """Populate the theme list"""
        theme = get_theme()
        current_name = self.theme_manager.current_theme.name
        
        for widget in self.themes_inner.winfo_children():
            widget.destroy()
        
        all_themes = self.theme_manager.get_all_themes()
        
        for name, theme_info in all_themes.items():
            is_selected = name == current_name
            
            item_frame = tk.Frame(
                self.themes_inner,
                bg=theme.bg_tertiary if is_selected else theme.bg_secondary
            )
            item_frame.pack(fill=tk.X, padx=5, pady=3)
            
            # Color preview
            preview_frame = tk.Frame(item_frame, bg=theme.bg_secondary, width=60, height=40)
            preview_frame.pack(side=tk.LEFT, padx=10, pady=10)
            preview_frame.pack_propagate(False)
            
            # Show theme colors
            colors_preview = tk.Frame(preview_frame, bg=theme_info.colors.bg_primary)
            colors_preview.pack(fill=tk.BOTH, expand=True)
            
            accent_bar = tk.Frame(colors_preview, bg=theme_info.colors.accent_primary, height=8)
            accent_bar.pack(side=tk.BOTTOM, fill=tk.X)
            
            # Theme info
            info_frame = tk.Frame(item_frame, bg=item_frame.cget('bg'))
            info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=10)
            
            name_text = theme_info.display_name
            if is_selected:
                name_text += " ✓"
            
            tk.Label(
                info_frame, text=name_text,
                bg=info_frame.cget('bg'),
                fg=theme.text_primary if not is_selected else theme.accent_primary,
                font=("Segoe UI", 10, "bold" if is_selected else "normal")
            ).pack(anchor="w")
            
            mode_text = "🌙 Dark" if theme_info.is_dark else "☀️ Light"
            tk.Label(
                info_frame, text=f"{mode_text} • {theme_info.author}",
                bg=info_frame.cget('bg'),
                fg=theme.text_secondary,
                font=FONTS.small()
            ).pack(anchor="w")
            
            # Select button
            if not is_selected:
                select_btn = tk.Label(
                    item_frame, text="Select", bg=theme.accent_primary,
                    fg="#ffffff", font=FONTS.small(),
                    padx=12, pady=4, cursor="hand2"
                )
                select_btn.pack(side=tk.RIGHT, padx=10)
                select_btn.bind("<Button-1>", 
                              lambda e, n=name: self._select_theme(n))
            
            # Hover effect
            def on_enter(e, f=item_frame):
                if f.cget('bg') != theme.bg_tertiary:
                    f.configure(bg=theme.bg_hover)
                    for child in f.winfo_children():
                        if isinstance(child, tk.Frame):
                            for subchild in child.winfo_children():
                                if isinstance(subchild, tk.Label):
                                    subchild.configure(bg=theme.bg_hover)
            
            def on_leave(e, f=item_frame, sel=is_selected):
                bg = theme.bg_tertiary if sel else theme.bg_secondary
                f.configure(bg=bg)
                for child in f.winfo_children():
                    if isinstance(child, tk.Frame):
                        for subchild in child.winfo_children():
                            if isinstance(subchild, tk.Label):
                                subchild.configure(bg=bg)
            
            item_frame.bind("<Enter>", on_enter)
            item_frame.bind("<Leave>", on_leave)
    
    def _select_theme(self, theme_name: str):
        """Select a theme"""
        if self.theme_manager.set_theme(theme_name):
            self.result = theme_name
            self.destroy()
    
    def _import_theme(self):
        """Import a theme from file"""
        filepath = filedialog.askopenfilename(
            title="Import Theme",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filepath:
            theme = self.theme_manager.import_theme(filepath)
            if theme:
                messagebox.showinfo("Success", f"Imported theme: {theme.display_name}")
                self._populate_themes()
            else:
                messagebox.showerror("Error", "Failed to import theme")
    
    def center_window(self):
        """Center the dialog"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')


# =============================================================================
# Analytics Dashboard Dialog
# =============================================================================
class AnalyticsDashboard(tk.Toplevel, ThemedWidget):
    """Dashboard showing bookmark analytics and statistics"""
    
    def __init__(self, parent, stats: Dict[str, Any]):
        super().__init__(parent)
        self.stats = stats
        theme = get_theme()
        
        self.title("📊 Analytics Dashboard")
        self.geometry("800x650")
        self.configure(bg=theme.bg_primary)
        self.transient(parent)
        
        set_dark_title_bar(self)
        
        # Header
        header = tk.Frame(self, bg=theme.bg_dark, height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(
            header, text="📊 Collection Analytics", bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.title(bold=False)
        ).pack(side=tk.LEFT, padx=20, pady=15)
        
        # Stats summary cards
        cards_frame = tk.Frame(self, bg=theme.bg_primary)
        cards_frame.pack(fill=tk.X, padx=20, pady=15)
        
        self._create_stat_card(cards_frame, "Total Bookmarks", 
                              str(stats["total_bookmarks"]), "📚", 0)
        self._create_stat_card(cards_frame, "Categories", 
                              str(stats["total_categories"]), "📂", 1)
        self._create_stat_card(cards_frame, "Tags", 
                              str(stats["total_tags"]), "🏷️", 2)
        self._create_stat_card(cards_frame, "Duplicates", 
                              str(stats["duplicate_bookmarks"]), "📋", 3)
        
        for i in range(4):
            cards_frame.columnconfigure(i, weight=1)
        
        # Main content with scrollable area
        main_frame = tk.Frame(self, bg=theme.bg_primary)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20)
        
        # Create canvas for scrolling
        canvas = tk.Canvas(main_frame, bg=theme.bg_primary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        content = tk.Frame(canvas, bg=theme.bg_primary)
        
        content.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=content, anchor="nw", width=760)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Health Score
        health_frame = tk.Frame(content, bg=theme.bg_secondary)
        health_frame.pack(fill=tk.X, pady=(0, 15))
        
        health_score = self._calculate_health_score()
        health_color = (theme.accent_success if health_score >= 80 
                       else theme.accent_warning if health_score >= 50 
                       else theme.accent_error)
        
        tk.Label(
            health_frame, text="Collection Health Score", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.body()
        ).pack(anchor="w", padx=15, pady=(10, 5))
        
        score_frame = tk.Frame(health_frame, bg=theme.bg_secondary)
        score_frame.pack(fill=tk.X, padx=15, pady=(0, 10))
        
        tk.Label(
            score_frame, text=f"{health_score}%", bg=theme.bg_secondary,
            fg=health_color, font=("Segoe UI", 28, "bold")
        ).pack(side=tk.LEFT)
        
        # Progress bar
        bar_frame = tk.Frame(score_frame, bg=theme.bg_tertiary, height=10)
        bar_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=20)
        
        bar_fill = tk.Frame(bar_frame, bg=health_color, height=10)
        bar_fill.place(relwidth=health_score/100, relheight=1)
        
        # Category Distribution
        self._create_section(content, "📂 Top Categories", self._get_category_chart())
        
        # Age Distribution
        self._create_section(content, "📅 Bookmark Age Distribution", self._get_age_chart())
        
        # Top Domains
        self._create_section(content, "🌐 Top Domains", self._get_domains_list())
        
        # Issues section
        issues = self._get_issues()
        if issues:
            self._create_section(content, "⚠️ Issues to Address", issues)
        
        # Close button
        btn_frame = tk.Frame(self, bg=theme.bg_primary)
        btn_frame.pack(fill=tk.X, padx=20, pady=15)
        
        ModernButton(
            btn_frame, text="Close", command=self.destroy
        ).pack(side=tk.RIGHT)
        
        self.center_window()
    
    def _create_stat_card(self, parent, title: str, value: str, icon: str, col: int):
        """Create a stat card"""
        theme = get_theme()
        
        card = tk.Frame(parent, bg=theme.bg_secondary)
        card.grid(row=0, column=col, padx=5, pady=5, sticky="nsew")
        
        tk.Label(
            card, text=icon, bg=theme.bg_secondary,
            fg=theme.accent_primary, font=("Segoe UI", 20)
        ).pack(pady=(15, 5))
        
        tk.Label(
            card, text=value, bg=theme.bg_secondary,
            fg=theme.text_primary, font=("Segoe UI", 24, "bold")
        ).pack()
        
        tk.Label(
            card, text=title, bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.small()
        ).pack(pady=(0, 15))
    
    def _create_section(self, parent, title: str, content_text: str):
        """Create a section with title and content"""
        theme = get_theme()
        
        frame = tk.Frame(parent, bg=theme.bg_secondary)
        frame.pack(fill=tk.X, pady=(0, 15))
        
        tk.Label(
            frame, text=title, bg=theme.bg_secondary,
            fg=theme.text_primary, font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", padx=15, pady=(10, 5))
        
        tk.Label(
            frame, text=content_text, bg=theme.bg_secondary,
            fg=theme.text_secondary, font=("Consolas", 9),
            justify=tk.LEFT
        ).pack(anchor="w", padx=15, pady=(0, 10))
    
    def _calculate_health_score(self) -> int:
        """Calculate collection health score"""
        total = self.stats["total_bookmarks"]
        if total == 0:
            return 100
        
        score = 100
        
        # Penalize for uncategorized
        uncategorized_pct = (self.stats["uncategorized"] / total) * 100
        score -= min(30, uncategorized_pct)
        
        # Penalize for duplicates
        duplicate_pct = (self.stats["duplicate_bookmarks"] / total) * 100
        score -= min(20, duplicate_pct * 2)
        
        # Penalize for broken links
        broken_pct = (self.stats["broken"] / total) * 100
        score -= min(20, broken_pct * 3)
        
        # Penalize for stale bookmarks
        stale_pct = (self.stats["stale"] / total) * 100
        score -= min(15, stale_pct / 3)
        
        # Bonus for organized (has tags, notes)
        organized_pct = ((self.stats["with_tags"] + self.stats["with_notes"]) / (total * 2)) * 100
        score += min(15, organized_pct / 5)
        
        return max(0, min(100, int(score)))
    
    def _get_category_chart(self) -> str:
        """Get text-based category chart"""
        counts = self.stats["category_counts"]
        total = self.stats["total_bookmarks"]
        
        if not counts or total == 0:
            return "No data available"
        
        # Sort and take top 8
        sorted_cats = sorted(counts.items(), key=lambda x: -x[1])[:8]
        
        lines = []
        max_count = max(c for _, c in sorted_cats) if sorted_cats else 1
        
        for cat, count in sorted_cats:
            pct = (count / total) * 100
            bar_len = int((count / max_count) * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            name = cat[:25] + "..." if len(cat) > 28 else cat
            lines.append(f"{name:30} {bar} {count:4} ({pct:4.1f}%)")
        
        return "\n".join(lines)
    
    def _get_age_chart(self) -> str:
        """Get text-based age distribution"""
        age_dist = self.stats["age_distribution"]
        total = self.stats["total_bookmarks"]
        
        if total == 0:
            return "No data available"
        
        lines = []
        max_count = max(age_dist.values()) if age_dist else 1
        
        for period, count in age_dist.items():
            pct = (count / total) * 100
            bar_len = int((count / max_count) * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            lines.append(f"{period:15} {bar} {count:4} ({pct:4.1f}%)")
        
        return "\n".join(lines)
    
    def _get_domains_list(self) -> str:
        """Get top domains list"""
        domains = self.stats["top_domains"][:10]
        
        if not domains:
            return "No data available"
        
        lines = []
        for domain, count in domains:
            lines.append(f"  {domain:35} {count:4}")
        
        return "\n".join(lines)
    
    def _get_issues(self) -> str:
        """Get issues to address"""
        issues = []
        
        if self.stats["uncategorized"] > 0:
            issues.append(f"• {self.stats['uncategorized']} uncategorized bookmarks")
        
        if self.stats["duplicate_bookmarks"] > 0:
            issues.append(f"• {self.stats['duplicate_bookmarks']} duplicate bookmarks in {self.stats['duplicate_groups']} groups")
        
        if self.stats["broken"] > 0:
            issues.append(f"• {self.stats['broken']} broken links")
        
        if self.stats["stale"] > 0:
            issues.append(f"• {self.stats['stale']} stale bookmarks (not visited in 90+ days)")
        
        return "\n".join(issues) if issues else ""
    
    def center_window(self):
        """Center the dialog"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')




# =============================================================================
# Bookmark Editor Dialog
# =============================================================================
class BookmarkEditorDialog(tk.Toplevel, ThemedWidget):
    """
        Represents a single bookmark with all metadata.
        
        Attributes:
            id: Unique integer identifier
            url: Bookmark URL
            title: Display title
            category: Category name
            tags: List of tag names
            ai_tags: List of AI-suggested tags
            description: Optional description
            favicon_url: URL to favicon image
            created_at: ISO timestamp of creation
            updated_at: ISO timestamp of last update
            visited_at: ISO timestamp of last visit
            visit_count: Number of times visited
            is_valid: Whether URL validation passed
            is_pinned: Whether bookmark is pinned
            ai_category: AI-suggested category
            ai_summary: AI-generated summary
            notes: User notes
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
            matches_search(query): Check if bookmark matches search
        """
    
    def __init__(self, parent, bookmark: Bookmark = None, 
                 categories: List[str] = None, tag_manager: TagManager = None,
                 available_tags: List[str] = None, on_save: Callable = None):
        super().__init__(parent)
        self.bookmark = bookmark
        self.categories = categories or []
        self.tag_manager = tag_manager
        self.available_tags = available_tags or (list(tag_manager.tags.keys()) if tag_manager else [])
        self.on_save = on_save
        self.result = None
        
        theme = get_theme()
        
        self.title("Edit Bookmark" if bookmark else "Add Bookmark")
        self.geometry("550x650")
        self.configure(bg=theme.bg_primary)
        self.transient(parent)
        self.grab_set()
        
        set_dark_title_bar(self)
        
        # Header
        header = tk.Frame(self, bg=theme.bg_dark, height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        title = "✏️ Edit Bookmark" if bookmark else "➕ Add Bookmark"
        tk.Label(
            header, text=title, bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.title(bold=False)
        ).pack(side=tk.LEFT, padx=20, pady=15)
        
        # Content
        content = tk.Frame(self, bg=theme.bg_primary)
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        # URL
        self._create_field(content, "URL", 0)
        self.url_var = tk.StringVar(value=bookmark.url if bookmark else "")
        self.url_entry = tk.Entry(
            content, textvariable=self.url_var,
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            font=FONTS.body()
        )
        self.url_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 15), ipady=8, ipadx=10)
        
        # Title
        self._create_field(content, "Title", 2)
        self.title_var = tk.StringVar(value=bookmark.title if bookmark else "")
        self.title_entry = tk.Entry(
            content, textvariable=self.title_var,
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            font=FONTS.body()
        )
        self.title_entry.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 15), ipady=8, ipadx=10)
        
        # Category
        self._create_field(content, "Category", 4)
        self.category_var = tk.StringVar(value=bookmark.category if bookmark else "Uncategorized / Needs Review")
        self.category_combo = ttk.Combobox(
            content, textvariable=self.category_var,
            values=self.categories,
            font=FONTS.body()
        )
        self.category_combo.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 15))
        
        # Tags
        self._create_field(content, "Tags", 6)
        existing_tags = self.available_tags if self.available_tags else (list(tag_manager.tags.keys()) if tag_manager else [])
        self.tag_editor = TagEditor(
            content, 
            tags=bookmark.tags if bookmark else [],
            available_tags=existing_tags
        )
        self.tag_editor.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(0, 15))
        
        # Notes
        self._create_field(content, "Notes", 8)
        self.notes_text = tk.Text(
            content, bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            font=FONTS.body(), height=3, wrap=tk.WORD
        )
        self.notes_text.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(0, 15))
        if bookmark and bookmark.notes:
            self.notes_text.insert("1.0", bookmark.notes)
        
        # AI Data Section (read-only display)
        if bookmark and (bookmark.ai_tags or bookmark.ai_confidence > 0 or bookmark.description):
            ai_frame = tk.LabelFrame(
                content, text="🤖 AI Data", bg=theme.bg_primary,
                fg=theme.text_secondary, font=("Segoe UI", 9, "bold"),
                relief=tk.FLAT, bd=1
            )
            ai_frame.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(0, 15))
            
            ai_inner = tk.Frame(ai_frame, bg=theme.bg_primary)
            ai_inner.pack(fill=tk.X, padx=10, pady=10)
            
            if bookmark.ai_confidence > 0:
                conf_row = tk.Frame(ai_inner, bg=theme.bg_primary)
                conf_row.pack(fill=tk.X, pady=2)
                tk.Label(conf_row, text="Confidence:", bg=theme.bg_primary,
                        fg=theme.text_muted, font=FONTS.small(), width=12, anchor="w").pack(side=tk.LEFT)
                conf_color = theme.accent_success if bookmark.ai_confidence >= 0.7 else (
                    theme.accent_warning if bookmark.ai_confidence >= 0.4 else theme.accent_error)
                tk.Label(conf_row, text=f"{bookmark.ai_confidence:.0%}", bg=theme.bg_primary,
                        fg=conf_color, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
            
            if bookmark.ai_tags:
                tags_row = tk.Frame(ai_inner, bg=theme.bg_primary)
                tags_row.pack(fill=tk.X, pady=2)
                tk.Label(tags_row, text="AI Tags:", bg=theme.bg_primary,
                        fg=theme.text_muted, font=FONTS.small(), width=12, anchor="w").pack(side=tk.LEFT)
                tags_text = ", ".join(bookmark.ai_tags)
                tk.Label(tags_row, text=tags_text, bg=theme.bg_primary,
                        fg=theme.accent_primary, font=FONTS.small(), wraplength=350, anchor="w").pack(side=tk.LEFT, fill=tk.X)
                
                # Button to add AI tags to user tags
                def add_ai_tags():
                    current = set(t.lower() for t in self.tag_editor.get_tags())
                    for tag in bookmark.ai_tags:
                        if tag.lower() not in current:
                            self.tag_editor.add_tag(tag)
                            current.add(tag.lower())
                
                add_btn = tk.Label(tags_row, text="+ Add", bg=theme.accent_primary, fg="white",
                                  font=FONTS.tiny(), padx=5, pady=1, cursor="hand2")
                add_btn.pack(side=tk.RIGHT, padx=5)
                add_btn.bind("<Button-1>", lambda e: add_ai_tags())
            
            if bookmark.description:
                desc_row = tk.Frame(ai_inner, bg=theme.bg_primary)
                desc_row.pack(fill=tk.X, pady=2)
                tk.Label(desc_row, text="Description:", bg=theme.bg_primary,
                        fg=theme.text_muted, font=FONTS.small(), width=12, anchor="nw").pack(side=tk.LEFT, anchor="n")
                tk.Label(desc_row, text=bookmark.description[:200], bg=theme.bg_primary,
                        fg=theme.text_secondary, font=FONTS.small(), wraplength=350, 
                        anchor="w", justify=tk.LEFT).pack(side=tk.LEFT, fill=tk.X)
            
            # Adjust row numbers for remaining widgets
            checks_row = 11
        else:
            checks_row = 10
        
        # Checkboxes
        checks_frame = tk.Frame(content, bg=theme.bg_primary)
        checks_frame.grid(row=checks_row, column=0, columnspan=2, sticky="w", pady=(0, 15))
        
        self.pinned_var = tk.BooleanVar(value=bookmark.is_pinned if bookmark else False)
        self.pinned_check = ttk.Checkbutton(
            checks_frame, text="📌 Pinned", variable=self.pinned_var
        )
        self.pinned_check.pack(side=tk.LEFT, padx=(0, 20))
        
        self.archived_var = tk.BooleanVar(value=bookmark.is_archived if bookmark else False)
        self.archived_check = ttk.Checkbutton(
            checks_frame, text="📦 Archived", variable=self.archived_var
        )
        self.archived_check.pack(side=tk.LEFT)
        
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        
        # Buttons
        btn_frame = tk.Frame(self, bg=theme.bg_primary)
        btn_frame.pack(fill=tk.X, padx=20, pady=15)
        
        ModernButton(
            btn_frame, text="Cancel", command=self.destroy
        ).pack(side=tk.RIGHT, padx=(10, 0))
        
        ModernButton(
            btn_frame, text="Save", command=self._save,
            style="primary", icon="💾"
        ).pack(side=tk.RIGHT)
        
        if bookmark:
            ModernButton(
                btn_frame, text="Open URL", command=self._open_url,
                icon="🔗"
            ).pack(side=tk.LEFT)
        
        self.center_window()
        self.url_entry.focus_set()
    
    def _create_field(self, parent, label: str, row: int):
        """Create a field label"""
        theme = get_theme()
        tk.Label(
            parent, text=label, bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        ).grid(row=row, column=0, sticky="w", pady=(0, 5))
    
    def _save(self):
        """Save the bookmark"""
        url = self.url_var.get().strip()
        title = self.title_var.get().strip()
        
        if not url:
            messagebox.showerror("Error", "URL is required")
            return
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Update bookmark object if editing existing
        if self.bookmark:
            self.bookmark.url = url
            self.bookmark.title = title or url
            self.bookmark.category = self.category_var.get()
            self.bookmark.tags = self.tag_editor.get_tags()
            self.bookmark.notes = self.notes_text.get("1.0", tk.END).strip()
            self.bookmark.is_pinned = self.pinned_var.get()
            self.bookmark.is_archived = self.archived_var.get()
            self.bookmark.modified_at = datetime.now().isoformat()
            
            # Call on_save callback if provided
            if self.on_save:
                self.on_save(self.bookmark)
        
        self.result = {
            "url": url,
            "title": title or url,
            "category": self.category_var.get(),
            "tags": self.tag_editor.get_tags(),
            "notes": self.notes_text.get("1.0", tk.END).strip(),
            "is_pinned": self.pinned_var.get(),
            "is_archived": self.archived_var.get()
        }
        self.destroy()
    
    def _open_url(self):
        """Open the URL in browser"""
        url = self.url_var.get().strip()
        if url:
            webbrowser.open(url)
    
    def center_window(self):
        """Center the dialog"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')


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
                 favicon_manager: FaviconManager = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.card_bg, cursor="hand2")
        
        self.bookmark = bookmark
        self.on_click = on_click
        self.on_double_click = on_double_click
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
                favicon_manager.fetch_favicon(bookmark.url, self._on_favicon_loaded)
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
        self.bind("<Double-1>", self._on_double_click)
        
        for child in self.winfo_children():
            child.bind("<Button-1>", self._on_click)
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
# Link Checker (Background Thread)
# =============================================================================
class LinkChecker:
    """Background link checker with threading"""
    
    def __init__(self, callback: Callable = None, max_workers: int = 10):
        self.callback = callback
        self.max_workers = max_workers
        self._executor: Optional[ThreadPoolExecutor] = None
        self._running = False
        self._checked = 0
        self._total = 0
        self._lock = threading.Lock()
    
    def check_links(self, bookmarks: List[Bookmark], 
                   progress_callback: Callable = None):
        """Start checking links in background"""
        if self._running:
            return
        
        self._running = True
        self._checked = 0
        self._total = len(bookmarks)
        
        thread = threading.Thread(
            target=self._worker, 
            args=(bookmarks, progress_callback),
            daemon=True
        )
        thread.start()
    
    def _worker(self, bookmarks: List[Bookmark], progress_callback: Callable):
        """Worker thread"""
        try:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                self._executor = executor
                futures = {
                    executor.submit(self._check_url, bm): bm 
                    for bm in bookmarks
                }
                
                for future in as_completed(futures):
                    if not self._running:
                        break
                    
                    bookmark = futures[future]
                    try:
                        is_valid, status_code = future.result()
                        bookmark.is_valid = is_valid
                        bookmark.http_status = status_code
                        bookmark.last_checked = datetime.now().isoformat()
                    except Exception as e:
                        bookmark.is_valid = False
                        bookmark.http_status = 0
                    
                    with self._lock:
                        self._checked += 1
                        if progress_callback:
                            progress_callback(self._checked, self._total, bookmark)
        finally:
            self._running = False
            self._executor = None
            if self.callback:
                self.callback()
    
    def _check_url(self, bookmark: Bookmark) -> Tuple[bool, int]:
        """Check a single URL"""
        try:
            response = requests.head(
                bookmark.url, 
                timeout=10,
                allow_redirects=True,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            return response.status_code < 400, response.status_code
        except requests.exceptions.Timeout:
            return False, 408
        except requests.exceptions.SSLError:
            return False, 495
        except requests.exceptions.ConnectionError:
            return False, 0
        except Exception:
            return False, 0
    
    def stop(self):
        """Stop the checker"""
        self._running = False
        if self._executor:
            self._executor.shutdown(wait=False)
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    @property
    def progress(self) -> Tuple[int, int]:
        return self._checked, self._total




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
    
    def create_icon(self) -> Optional[Image.Image]:
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
        self.configure(bg=theme.bg_secondary)
        
        # Position in center top
        self.geometry("500x400")
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - 500) // 2
        y = parent.winfo_rooty() + 100
        self.geometry(f"+{x}+{y}")
        
        # Border
        self.configure(highlightbackground=theme.border, highlightthickness=1)
        
        # Search entry
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', self._filter)
        
        self.search_entry = tk.Entry(
            self, textvariable=self.search_var,
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            font=("Segoe UI", 12)
        )
        self.search_entry.pack(fill=tk.X, padx=15, pady=15)
        self.search_entry.focus_set()
        
        # Separator
        tk.Frame(self, bg=theme.border, height=1).pack(fill=tk.X)
        
        # Commands list
        self.list_frame = tk.Frame(self, bg=theme.bg_secondary)
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
        
        for i, (name, shortcut, callback) in enumerate(self.filtered_commands[:10]):
            is_selected = i == self.selected_index
            
            item = tk.Frame(
                self.list_frame,
                bg=theme.selection if is_selected else theme.bg_secondary
            )
            item.pack(fill=tk.X, padx=5, pady=2)
            
            tk.Label(
                item, text=name, bg=item.cget('bg'),
                fg=theme.text_primary, font=FONTS.body(),
                anchor="w"
            ).pack(side=tk.LEFT, padx=10, pady=8)
            
            if shortcut:
                tk.Label(
                    item, text=shortcut, bg=item.cget('bg'),
                    fg=theme.text_muted, font=("Consolas", 9)
                ).pack(side=tk.RIGHT, padx=10)
            
            item.bind("<Button-1>", lambda e, idx=i: self._select_and_execute(idx))
    
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




# =============================================================================
# MAIN APPLICATION CLASS
# =============================================================================
class BookmarkOrganizerApp:
    """
        Represents a single bookmark with all metadata.
        
        Attributes:
            id: Unique integer identifier
            url: Bookmark URL
            title: Display title
            category: Category name
            tags: List of tag names
            ai_tags: List of AI-suggested tags
            description: Optional description
            favicon_url: URL to favicon image
            created_at: ISO timestamp of creation
            updated_at: ISO timestamp of last update
            visited_at: ISO timestamp of last visit
            visit_count: Number of times visited
            is_valid: Whether URL validation passed
            is_pinned: Whether bookmark is pinned
            ai_category: AI-suggested category
            ai_summary: AI-generated summary
            notes: User notes
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
            matches_search(query): Check if bookmark matches search
        """
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.theme_manager = get_theme_manager()
        self.theme_manager.add_theme_change_callback(self._on_theme_change)
        
        # Initialize managers
        self.tag_manager = TagManager()
        self.category_manager = CategoryManager()
        self.bookmark_manager = BookmarkManager(
            self.category_manager, self.tag_manager
        )
        self.ai_config = AIConfigManager()
        self.favicon_manager = FaviconManager()
        self.command_stack = CommandStack()
        self.link_checker = LinkChecker(callback=self._on_link_check_complete)
        
        # State
        self.view_mode = ViewMode.LIST
        self.current_category = None
        self.selected_ids: Set[int] = set()
        self.search_query = ""
        self._bookmark_widgets: Dict[int, tk.Widget] = {}
        
        # Setup UI
        self._setup_window()
        self._setup_styles()
        self._setup_menu()
        self._setup_layout()
        self._setup_bindings()
        self._setup_system_tray()
        
        # Initial load
        self._refresh_category_list()
        self._refresh_bookmark_list()
        self._update_status()
        
        # Register commands for palette
        self._commands = self._get_commands()
    
    def _setup_window(self):
        """Setup main window"""
        theme = get_theme()
        
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("1400x900")
        self.root.minsize(1000, 600)
        self.root.configure(bg=theme.bg_primary)
        
        set_dark_title_bar(self.root)
        
        # Window icon (if possible)
        try:
            if IS_WINDOWS and HAS_PIL:
                icon = Image.new('RGBA', (32, 32), theme.accent_primary)
                self._window_icon = ImageTk.PhotoImage(icon)
                self.root.iconphoto(True, self._window_icon)
        except Exception:
            pass
    
    def _setup_styles(self):
        """Setup ttk styles"""
        theme = get_theme()
        style = ttk.Style()
        
        try:
            style.theme_use('clam')
        except Exception:
            pass
        
        # Configure ttk widgets
        style.configure(".", 
            background=theme.bg_primary,
            foreground=theme.text_primary,
            fieldbackground=theme.bg_secondary,
            troughcolor=theme.bg_dark
        )
        
        style.configure("TCombobox",
            fieldbackground=theme.bg_secondary,
            background=theme.bg_secondary,
            foreground=theme.text_primary,
            arrowcolor=theme.text_primary
        )
        
        style.map("TCombobox",
            fieldbackground=[("readonly", theme.bg_secondary)],
            background=[("readonly", theme.bg_secondary)]
        )
        
        style.configure("Treeview",
            background=theme.bg_secondary,
            foreground=theme.text_primary,
            fieldbackground=theme.bg_secondary,
            rowheight=32
        )
        
        style.configure("Treeview.Heading",
            background=theme.bg_tertiary,
            foreground=theme.text_primary
        )
        
        style.map("Treeview",
            background=[("selected", theme.selection)],
            foreground=[("selected", theme.text_primary)]
        )
        
        style.configure("TCheckbutton",
            background=theme.bg_primary,
            foreground=theme.text_primary
        )
        
        style.configure("Vertical.TScrollbar",
            background=theme.scrollbar_bg,
            troughcolor=theme.bg_secondary,
            arrowcolor=theme.text_muted
        )
    
    def _setup_menu(self):
        """Setup menu bar"""
        theme = get_theme()
        
        self.menu_bar = tk.Menu(self.root, bg=theme.bg_secondary, fg=theme.text_primary,
                               activebackground=theme.accent_primary, 
                               activeforeground=theme.text_primary)
        
        # File menu
        file_menu = tk.Menu(self.menu_bar, tearoff=0, bg=theme.bg_secondary, 
                           fg=theme.text_primary)
        file_menu.add_command(label="Import HTML...", command=self._import_html,
                             accelerator="Ctrl+I")
        file_menu.add_command(label="Import JSON...", command=self._import_json)
        file_menu.add_separator()
        file_menu.add_command(label="Export HTML...", command=self._export_html,
                             accelerator="Ctrl+E")
        file_menu.add_command(label="Export JSON...", command=self._export_json)
        file_menu.add_command(label="Export CSV...", command=self._export_csv)
        file_menu.add_command(label="Export Markdown...", command=self._export_markdown)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close, accelerator="Alt+F4")
        self.menu_bar.add_cascade(label="File", menu=file_menu)
        
        # Edit menu
        edit_menu = tk.Menu(self.menu_bar, tearoff=0, bg=theme.bg_secondary,
                           fg=theme.text_primary)
        edit_menu.add_command(label="Undo", command=self._undo, accelerator="Ctrl+Z")
        edit_menu.add_command(label="Redo", command=self._redo, accelerator="Ctrl+Y")
        edit_menu.add_separator()
        edit_menu.add_command(label="Select All", command=self._select_all,
                             accelerator="Ctrl+A")
        edit_menu.add_command(label="Delete Selected", command=self._delete_selected,
                             accelerator="Delete")
        edit_menu.add_separator()
        edit_menu.add_command(label="Find Duplicates", command=self._find_duplicates)
        edit_menu.add_command(label="Clean URLs", command=self._clean_urls)
        self.menu_bar.add_cascade(label="Edit", menu=edit_menu)
        
        # View menu
        view_menu = tk.Menu(self.menu_bar, tearoff=0, bg=theme.bg_secondary,
                           fg=theme.text_primary)
        view_menu.add_command(label="List View", command=lambda: self._set_view_mode(ViewMode.LIST))
        view_menu.add_command(label="Grid View", command=lambda: self._set_view_mode(ViewMode.GRID))
        view_menu.add_separator()
        view_menu.add_command(label="Analytics Dashboard", command=self._show_analytics,
                             accelerator="Ctrl+D")
        view_menu.add_separator()
        view_menu.add_command(label="Theme Settings...", command=self._show_theme_settings)
        self.menu_bar.add_cascade(label="View", menu=view_menu)
        
        # Tools menu
        tools_menu = tk.Menu(self.menu_bar, tearoff=0, bg=theme.bg_secondary,
                            fg=theme.text_primary)
        tools_menu.add_command(label="Check Broken Links", command=self._check_links)
        tools_menu.add_command(label="AI Categorization...", command=self._show_ai_settings)
        tools_menu.add_separator()
        tools_menu.add_command(label="Manage Categories...", command=self._manage_categories)
        tools_menu.add_command(label="Manage Tags...", command=self._manage_tags)
        tools_menu.add_separator()
        tools_menu.add_command(label="Clear Favicon Cache", command=self._clear_favicon_cache)
        self.menu_bar.add_cascade(label="Tools", menu=tools_menu)
        
        # Help menu
        help_menu = tk.Menu(self.menu_bar, tearoff=0, bg=theme.bg_secondary,
                           fg=theme.text_primary)
        help_menu.add_command(label="Search Syntax Help", command=self._show_search_help)
        help_menu.add_command(label="Keyboard Shortcuts", command=self._show_shortcuts)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self._show_about)
        self.menu_bar.add_cascade(label="Help", menu=help_menu)
        
        self.root.config(menu=self.menu_bar)
    
    def _setup_layout(self):
        """Setup main layout"""
        theme = get_theme()
        
        # Main container
        self.main_container = tk.Frame(self.root, bg=theme.bg_primary)
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        # Header
        self._setup_header()
        
        # Content area (sidebar + main)
        self.content = tk.Frame(self.main_container, bg=theme.bg_primary)
        self.content.pack(fill=tk.BOTH, expand=True)
        
        # Sidebar
        self._setup_sidebar()
        
        # Main bookmark area
        self._setup_main_area()
        
        # Status bar
        self.status_bar = StatusBar(self.main_container)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def _setup_header(self):
        """Setup header area"""
        theme = get_theme()
        
        self.header = tk.Frame(self.main_container, bg=theme.bg_dark, height=60)
        self.header.pack(fill=tk.X)
        self.header.pack_propagate(False)
        
        # Logo/Title
        title_frame = tk.Frame(self.header, bg=theme.bg_dark)
        title_frame.pack(side=tk.LEFT, padx=20)
        
        tk.Label(
            title_frame, text="🔖", bg=theme.bg_dark,
            fg=theme.accent_primary, font=("Segoe UI", 20)
        ).pack(side=tk.LEFT)
        
        tk.Label(
            title_frame, text=APP_NAME, bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.title(bold=False)
        ).pack(side=tk.LEFT, padx=(10, 0))
        
        # Search bar
        self.search_var = tk.StringVar()
        self.search_bar = ModernSearch(
            self.header, self.search_var,
            placeholder="Search bookmarks... (Ctrl+F)",
            on_change=self._on_search_change
        )
        self.search_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=40, pady=12)
        
        # View mode buttons
        view_frame = tk.Frame(self.header, bg=theme.bg_dark)
        view_frame.pack(side=tk.RIGHT, padx=20)
        
        self.list_view_btn = tk.Label(
            view_frame, text="☰", bg=theme.bg_dark,
            fg=theme.accent_primary, font=("Segoe UI", 16), cursor="hand2"
        )
        self.list_view_btn.pack(side=tk.LEFT, padx=5)
        self.list_view_btn.bind("<Button-1>", lambda e: self._set_view_mode(ViewMode.LIST))
        
        self.grid_view_btn = tk.Label(
            view_frame, text="⊞", bg=theme.bg_dark,
            fg=theme.text_muted, font=("Segoe UI", 16), cursor="hand2"
        )
        self.grid_view_btn.pack(side=tk.LEFT, padx=5)
        self.grid_view_btn.bind("<Button-1>", lambda e: self._set_view_mode(ViewMode.GRID))
    
    def _setup_sidebar(self):
        """Setup sidebar with categories"""
        theme = get_theme()
        
        self.sidebar = tk.Frame(self.content, bg=theme.bg_secondary, width=280)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)
        
        # Categories header
        cat_header = tk.Frame(self.sidebar, bg=theme.bg_secondary)
        cat_header.pack(fill=tk.X, padx=15, pady=(15, 10))
        
        tk.Label(
            cat_header, text="Categories", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=("Segoe UI", 10, "bold")
        ).pack(side=tk.LEFT)
        
        add_cat_btn = tk.Label(
            cat_header, text="+", bg=theme.bg_secondary,
            fg=theme.accent_primary, font=("Segoe UI", 14), cursor="hand2"
        )
        add_cat_btn.pack(side=tk.RIGHT)
        add_cat_btn.bind("<Button-1>", lambda e: self._add_category())
        
        # Quick filters
        filters_frame = tk.Frame(self.sidebar, bg=theme.bg_secondary)
        filters_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        self._create_quick_filter(filters_frame, "📚 All Bookmarks", None)
        self._create_quick_filter(filters_frame, "📌 Pinned", "pinned")
        self._create_quick_filter(filters_frame, "🕐 Recent", "recent")
        self._create_quick_filter(filters_frame, "⚠️ Broken", "broken")
        
        # Separator
        tk.Frame(self.sidebar, bg=theme.border, height=1).pack(fill=tk.X, padx=15, pady=10)
        
        # Category list (scrollable)
        self.cat_list_frame = tk.Frame(self.sidebar, bg=theme.bg_secondary)
        self.cat_list_frame.pack(fill=tk.BOTH, expand=True, padx=5)
        
        self.cat_canvas = tk.Canvas(
            self.cat_list_frame, bg=theme.bg_secondary,
            highlightthickness=0
        )
        self.cat_scrollbar = ttk.Scrollbar(
            self.cat_list_frame, orient="vertical",
            command=self.cat_canvas.yview
        )
        self.cat_inner = tk.Frame(self.cat_canvas, bg=theme.bg_secondary)
        
        self.cat_inner.bind(
            "<Configure>",
            lambda e: self.cat_canvas.configure(scrollregion=self.cat_canvas.bbox("all"))
        )
        
        self.cat_canvas.create_window((0, 0), window=self.cat_inner, anchor="nw")
        self.cat_canvas.configure(yscrollcommand=self.cat_scrollbar.set)
        
        self.cat_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Stats at bottom
        self.stats_frame = tk.Frame(self.sidebar, bg=theme.bg_tertiary)
        self.stats_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        self.stats_label = tk.Label(
            self.stats_frame, text="", bg=theme.bg_tertiary,
            fg=theme.text_muted, font=FONTS.small()
        )
        self.stats_label.pack(pady=8)
    
    def _create_quick_filter(self, parent, text: str, filter_type: str):
        """Create a quick filter button"""
        theme = get_theme()
        
        btn = tk.Frame(parent, bg=theme.bg_secondary, cursor="hand2")
        btn.pack(fill=tk.X, pady=2)
        
        label = tk.Label(
            btn, text=text, bg=theme.bg_secondary,
            fg=theme.text_primary, font=FONTS.body(),
            anchor="w", padx=10, pady=6
        )
        label.pack(fill=tk.X)
        
        def on_click(e, ft=filter_type):
            self.current_category = ft
            self._refresh_bookmark_list()
            self._highlight_current_filter()
        
        def on_enter(e):
            btn.configure(bg=theme.bg_hover)
            label.configure(bg=theme.bg_hover)
        
        def on_leave(e):
            btn.configure(bg=theme.bg_secondary)
            label.configure(bg=theme.bg_secondary)
        
        btn.bind("<Button-1>", on_click)
        label.bind("<Button-1>", on_click)
        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
    
    def _setup_main_area(self):
        """Setup main bookmark display area"""
        theme = get_theme()
        
        self.main_area = tk.Frame(self.content, bg=theme.bg_primary)
        self.main_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Toolbar
        self._setup_toolbar()
        
        # Bookmark list container
        self.list_container = tk.Frame(self.main_area, bg=theme.bg_primary)
        self.list_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        # For list view: Treeview
        self._setup_list_view()
        
        # For grid view: Scrollable frame
        self._setup_grid_view()
    
    def _setup_toolbar(self):
        """Setup toolbar above bookmark list"""
        theme = get_theme()
        
        self.toolbar = tk.Frame(self.main_area, bg=theme.bg_primary)
        self.toolbar.pack(fill=tk.X, padx=15, pady=10)
        
        # Add bookmark button
        ModernButton(
            self.toolbar, text="Add Bookmark", command=self._add_bookmark,
            icon="➕", style="primary"
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        # Import button
        ModernButton(
            self.toolbar, text="Import", command=self._import_html,
            icon="📥"
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        # Bulk actions (shown when items selected)
        self.bulk_frame = tk.Frame(self.toolbar, bg=theme.bg_primary)
        
        ModernButton(
            self.bulk_frame, text="Move to...", command=self._move_selected,
            icon="📂"
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ModernButton(
            self.bulk_frame, text="Delete", command=self._delete_selected,
            icon="🗑️", style="danger"
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ModernButton(
            self.bulk_frame, text="Add Tags...", command=self._tag_selected,
            icon="🏷️"
        ).pack(side=tk.LEFT)
        
        # Category dropdown for filtering
        self.filter_var = tk.StringVar(value="All Categories")
        self.filter_combo = ttk.Combobox(
            self.toolbar, textvariable=self.filter_var,
            values=["All Categories"] + self.category_manager.get_sorted_categories(),
            state="readonly", width=25
        )
        self.filter_combo.pack(side=tk.RIGHT)
        self.filter_combo.bind("<<ComboboxSelected>>", self._on_filter_change)
        
        tk.Label(
            self.toolbar, text="Filter:", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        ).pack(side=tk.RIGHT, padx=(0, 10))
    
    def _setup_list_view(self):
        """Setup the treeview for list mode"""
        theme = get_theme()
        
        self.list_frame = tk.Frame(self.list_container, bg=theme.bg_primary)
        
        # Treeview with columns
        columns = ("title", "url", "category", "tags", "added")
        self.tree = ttk.Treeview(
            self.list_frame, columns=columns, show="headings",
            selectmode="extended"
        )
        
        # Column headings
        self.tree.heading("title", text="Title", command=lambda: self._sort_by("title"))
        self.tree.heading("url", text="URL", command=lambda: self._sort_by("url"))
        self.tree.heading("category", text="Category", command=lambda: self._sort_by("category"))
        self.tree.heading("tags", text="Tags", command=lambda: self._sort_by("tags"))
        self.tree.heading("added", text="Added", command=lambda: self._sort_by("added"))
        
        # Column widths
        self.tree.column("title", width=300, minwidth=150)
        self.tree.column("url", width=250, minwidth=100)
        self.tree.column("category", width=200, minwidth=100)
        self.tree.column("tags", width=150, minwidth=80)
        self.tree.column("added", width=100, minwidth=80)
        
        # Scrollbar
        tree_scroll = ttk.Scrollbar(self.list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bindings
        self.tree.bind("<Double-1>", self._on_item_double_click)
        self.tree.bind("<Return>", self._on_item_double_click)
        self.tree.bind("<<TreeviewSelect>>", self._on_selection_change)
        self.tree.bind("<Button-3>", self._show_context_menu)
        
        # Enable drag and drop
        self.tree.bind("<ButtonPress-1>", self._on_drag_start)
        self.tree.bind("<B1-Motion>", self._on_drag_motion)
        self.tree.bind("<ButtonRelease-1>", self._on_drag_release)
        
        self._drag_data = {"items": [], "x": 0, "y": 0}
    
    def _setup_grid_view(self):
        """Setup the grid view"""
        theme = get_theme()
        
        self.grid_frame = tk.Frame(self.list_container, bg=theme.bg_primary)
        
        # Canvas for scrolling
        self.grid_canvas = tk.Canvas(
            self.grid_frame, bg=theme.bg_primary, highlightthickness=0
        )
        self.grid_scrollbar = ttk.Scrollbar(
            self.grid_frame, orient="vertical", command=self.grid_canvas.yview
        )
        self.grid_inner = tk.Frame(self.grid_canvas, bg=theme.bg_primary)
        
        self.grid_inner.bind(
            "<Configure>",
            lambda e: self.grid_canvas.configure(scrollregion=self.grid_canvas.bbox("all"))
        )
        
        self.grid_canvas.create_window((0, 0), window=self.grid_inner, anchor="nw")
        self.grid_canvas.configure(yscrollcommand=self.grid_scrollbar.set)
        
        self.grid_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.grid_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Mouse wheel scrolling
        self.grid_canvas.bind("<MouseWheel>", 
            lambda e: self.grid_canvas.yview_scroll(-1 * (e.delta // 120), "units"))
    
    def _setup_bindings(self):
        """Setup keyboard bindings"""
        self.root.bind("<Control-f>", lambda e: self.search_bar.focus_set())
        self.root.bind("<Control-i>", lambda e: self._import_html())
        self.root.bind("<Control-e>", lambda e: self._export_html())
        self.root.bind("<Control-n>", lambda e: self._add_bookmark())
        self.root.bind("<Control-z>", lambda e: self._undo())
        self.root.bind("<Control-y>", lambda e: self._redo())
        self.root.bind("<Control-a>", lambda e: self._select_all())
        self.root.bind("<Control-d>", lambda e: self._show_analytics())
        self.root.bind("<Control-p>", lambda e: self._show_command_palette())
        self.root.bind("<Delete>", lambda e: self._delete_selected())
    
    def _focus_search(self, event=None):
        """Focus the search entry and select all text"""
        if hasattr(self, 'search_entry') and self.search_entry:
            self.search_entry.focus_set()
            self.search_entry.select_range(0, tk.END)
        return "break"
        self.root.bind("<F5>", lambda e: self._refresh_all())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _setup_system_tray(self):
        """Setup system tray"""
        if HAS_TRAY and HAS_PIL:
            self.system_tray = SystemTray(
                self,
                on_show=self._show_window,
                on_quit=self._on_close
            )
            self.system_tray.start()
        else:
            self.system_tray = None


    
    # =========================================================================
    # Refresh Methods
    # =========================================================================
    
    def _refresh_category_list(self):
        """Refresh the category list in sidebar"""
        theme = get_theme()
        counts = self.bookmark_manager.get_category_counts()
        
        # Clear existing
        for widget in self.cat_inner.winfo_children():
            widget.destroy()
        
        # Get tree structure
        tree = self.category_manager.get_tree()
        
        for category, depth in tree:
            count = counts.get(category.name, 0)
            
            item = tk.Frame(self.cat_inner, bg=theme.bg_secondary, cursor="hand2")
            item.pack(fill=tk.X, pady=1)
            
            # Indent based on depth
            indent = depth * 20
            
            # Icon
            icon = category.icon or get_category_icon(category.name)
            
            label_text = f"{icon} {category.name}"
            
            label = tk.Label(
                item, text=label_text, bg=theme.bg_secondary,
                fg=theme.text_primary, font=FONTS.body(),
                anchor="w", padx=10 + indent, pady=8
            )
            label.pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            count_label = tk.Label(
                item, text=str(count), bg=theme.bg_secondary,
                fg=theme.text_muted, font=FONTS.small(),
                padx=10
            )
            count_label.pack(side=tk.RIGHT)
            
            # Click handler
            def on_click(e, cat_name=category.name):
                self.current_category = cat_name
                self._refresh_bookmark_list()
                self._highlight_current_filter()
            
            def on_enter(e, itm=item, lbl=label, cnt=count_label):
                itm.configure(bg=theme.bg_hover)
                lbl.configure(bg=theme.bg_hover)
                cnt.configure(bg=theme.bg_hover)
            
            def on_leave(e, itm=item, lbl=label, cnt=count_label):
                itm.configure(bg=theme.bg_secondary)
                lbl.configure(bg=theme.bg_secondary)
                cnt.configure(bg=theme.bg_secondary)
            
            item.bind("<Button-1>", on_click)
            label.bind("<Button-1>", on_click)
            item.bind("<Enter>", on_enter)
            item.bind("<Leave>", on_leave)
            
            # Drag drop target
            item.bind("<ButtonRelease-1>", lambda e, n=category.name: self._on_category_drop(n))
        
        # Update stats
        total = sum(counts.values())
        cats = len(self.category_manager.categories)
        self.stats_label.configure(text=f"{total} bookmarks • {cats} categories")
    
    def _refresh_bookmark_list(self):
        """Refresh the bookmark list"""
        # Get bookmarks based on current filter
        if self.current_category == "pinned":
            bookmarks = self.bookmark_manager.get_pinned_bookmarks()
        elif self.current_category == "recent":
            bookmarks = self.bookmark_manager.get_recent_bookmarks(7)
        elif self.current_category == "broken":
            bookmarks = self.bookmark_manager.find_broken_links()
        elif self.current_category and self.current_category not in ["pinned", "recent", "broken"]:
            bookmarks = self.bookmark_manager.get_bookmarks_by_category(self.current_category)
        else:
            bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        # Apply search filter
        if self.search_query:
            bookmarks = self.bookmark_manager.search_bookmarks(
                self.search_query, 
                self.current_category if self.current_category not in ["pinned", "recent", "broken"] else None
            )
        
        # Sort pinned first
        bookmarks = sorted(bookmarks, key=lambda b: (not b.is_pinned, b.title.lower()))
        
        if self.view_mode == ViewMode.LIST:
            self._populate_list_view(bookmarks)
        else:
            self._populate_grid_view(bookmarks)
        
        self._update_status(len(bookmarks))
    
    def _populate_list_view(self, bookmarks: List[Bookmark]):
        """Populate the treeview with bookmarks"""
        # Clear existing
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Add bookmarks
        for bm in bookmarks:
            # Format values
            title = bm.title[:60] + "..." if len(bm.title) > 63 else bm.title
            if bm.is_pinned:
                title = "📌 " + title
            if not bm.is_valid:
                title = "⚠️ " + title
            
            url = bm.domain
            tags = ", ".join(bm.tags[:3]) if bm.tags else ""
            
            try:
                added = datetime.fromisoformat(bm.created_at.replace('Z', '+00:00'))
                added_str = added.strftime("%Y-%m-%d")
            except Exception:
                added_str = ""
            
            self.tree.insert("", tk.END, iid=str(bm.id), values=(
                title, url, bm.category, tags, added_str
            ))
    
    def _populate_grid_view(self, bookmarks: List[Bookmark]):
        """Populate the grid view with bookmark cards"""
        # Clear existing
        for widget in self.grid_inner.winfo_children():
            widget.destroy()
        
        self._bookmark_widgets.clear()
        
        # Calculate columns based on width
        self.grid_canvas.update_idletasks()
        width = self.grid_canvas.winfo_width()
        card_width = 200
        columns = max(1, width // card_width)
        
        row = 0
        col = 0
        
        for bm in bookmarks:
            card = BookmarkCard(
                self.grid_inner, bm,
                on_click=self._on_card_click,
                on_double_click=self._on_card_double_click,
                favicon_manager=self.favicon_manager
            )
            card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
            self._bookmark_widgets[bm.id] = card
            
            col += 1
            if col >= columns:
                col = 0
                row += 1
        
        # Configure grid weights
        for i in range(columns):
            self.grid_inner.columnconfigure(i, weight=1)
    
    def _highlight_current_filter(self):
        """Highlight the currently selected category/filter"""
        # This would update visual state of sidebar items
        pass
    
    def _set_view_mode(self, mode: ViewMode):
        """Switch between list and grid view"""
        theme = get_theme()
        self.view_mode = mode
        
        if mode == ViewMode.LIST:
            self.grid_frame.pack_forget()
            self.list_frame.pack(fill=tk.BOTH, expand=True)
            self.list_view_btn.configure(fg=theme.accent_primary)
            self.grid_view_btn.configure(fg=theme.text_muted)
        else:
            self.list_frame.pack_forget()
            self.grid_frame.pack(fill=tk.BOTH, expand=True)
            self.list_view_btn.configure(fg=theme.text_muted)
            self.grid_view_btn.configure(fg=theme.accent_primary)
        
        self._refresh_bookmark_list()
    
    def _update_status(self, shown: int = None):
        """Update the status bar"""
        total = len(self.bookmark_manager.bookmarks)
        selected = len(self.selected_ids)
        
        if shown is None:
            shown = total
        
        self.status_bar.set_counts(total, selected, shown if shown != total else None)
        
        # Show/hide bulk actions
        if selected > 0:
            self.bulk_frame.pack(side=tk.LEFT, padx=20)
        else:
            self.bulk_frame.pack_forget()
    
    def _refresh_all(self):
        """Refresh everything"""
        self.bookmark_manager.reload()
        self._refresh_category_list()
        self._refresh_bookmark_list()
        self.status_bar.set_status("Refreshed")
    
    # =========================================================================
    # Event Handlers
    # =========================================================================
    
    def _on_search_change(self):
        """Handle search text change"""
        self.search_query = self.search_var.get()
        self._refresh_bookmark_list()
    
    def _on_filter_change(self, e=None):
        """Handle category filter change"""
        selected = self.filter_var.get()
        if selected == "All Categories":
            self.current_category = None
        else:
            self.current_category = selected
        self._refresh_bookmark_list()
    
    def _on_selection_change(self, e=None):
        """Handle treeview selection change"""
        selected = self.tree.selection()
        self.selected_ids = {int(iid) for iid in selected}
        self._update_status()
    
    def _on_item_double_click(self, e=None):
        """Handle double-click on bookmark"""
        selected = self.tree.selection()
        if selected:
            bm_id = int(selected[0])
            bookmark = self.bookmark_manager.get_bookmark(bm_id)
            if bookmark:
                webbrowser.open(bookmark.url)
                bookmark.record_visit()
                self.bookmark_manager.save_bookmarks()
    
    def _on_card_click(self, bookmark: Bookmark):
        """Handle card click in grid view"""
        # Toggle selection
        if bookmark.id in self.selected_ids:
            self.selected_ids.remove(bookmark.id)
            if bookmark.id in self._bookmark_widgets:
                self._bookmark_widgets[bookmark.id].set_selected(False)
        else:
            self.selected_ids.add(bookmark.id)
            if bookmark.id in self._bookmark_widgets:
                self._bookmark_widgets[bookmark.id].set_selected(True)
        
        self._update_status()
    
    def _on_card_double_click(self, bookmark: Bookmark):
        """Handle card double-click in grid view"""
        webbrowser.open(bookmark.url)
        bookmark.record_visit()
        self.bookmark_manager.save_bookmarks()
    
    def _on_drag_start(self, e):
        """Start drag operation"""
        item = self.tree.identify_row(e.y)
        if item:
            self._drag_data["items"] = list(self.tree.selection()) or [item]
            self._drag_data["x"] = e.x
            self._drag_data["y"] = e.y
    
    def _on_drag_motion(self, e):
        """Handle drag motion"""
        pass
    
    def _on_drag_release(self, e):
        """Handle drag release"""
        self._drag_data["items"] = []
    
    def _on_category_drop(self, category_name: str):
        """Handle drop on a category"""
        if self._drag_data["items"]:
            ids = [int(iid) for iid in self._drag_data["items"]]
            cmd = MoveBookmarksCommand(self.bookmark_manager, ids, category_name)
            self.command_stack.execute(cmd)
            self._refresh_category_list()
            self._refresh_bookmark_list()
            self.status_bar.set_status(f"Moved {len(ids)} bookmark(s) to {category_name}")
    
    def _show_context_menu(self, e):
        """Show context menu for bookmarks"""
        theme = get_theme()
        
        item = self.tree.identify_row(e.y)
        if not item:
            return
        
        # Select item if not already selected
        if item not in self.tree.selection():
            self.tree.selection_set(item)
        
        menu = tk.Menu(self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary)
        
        menu.add_command(label="Open in Browser", command=self._open_selected)
        menu.add_command(label="Edit...", command=self._edit_selected)
        menu.add_separator()
        menu.add_command(label="Copy URL", command=self._copy_url)
        menu.add_command(label="Copy Title", command=self._copy_title)
        menu.add_separator()
        menu.add_command(label="Toggle Pin", command=self._toggle_pin)
        menu.add_command(label="Toggle Archive", command=self._toggle_archive)
        menu.add_separator()
        menu.add_command(label="Move to...", command=self._move_selected)
        menu.add_command(label="Add Tags...", command=self._tag_selected)
        menu.add_separator()
        menu.add_command(label="Delete", command=self._delete_selected)
        
        menu.tk_popup(e.x_root, e.y_root)
    
    # =========================================================================
    # Actions
    # =========================================================================
    
    def _add_bookmark(self):
        """Add a new bookmark"""
        dialog = BookmarkEditorDialog(
            self.root,
            categories=self.category_manager.get_sorted_categories(),
            tag_manager=self.tag_manager
        )
        self.root.wait_window(dialog)
        
        if dialog.result:
            bookmark = Bookmark(
                id=None,
                url=dialog.result["url"],
                title=dialog.result["title"],
                category=dialog.result["category"],
                tags=dialog.result["tags"],
                notes=dialog.result["notes"],
                is_pinned=dialog.result["is_pinned"],
                is_archived=dialog.result["is_archived"]
            )
            
            cmd = AddBookmarksCommand(self.bookmark_manager, [bookmark])
            self.command_stack.execute(cmd)
            
            # Fetch favicon
            self.favicon_manager.fetch_favicon(bookmark.url)
            
            self._refresh_category_list()
            self._refresh_bookmark_list()
            self.status_bar.set_status(f"Added: {bookmark.title[:50]}")
    
    def _edit_selected(self):
        """Edit selected bookmark"""
        selected = list(self.selected_ids)
        if not selected:
            return
        
        bookmark = self.bookmark_manager.get_bookmark(selected[0])
        if not bookmark:
            return
        
        dialog = BookmarkEditorDialog(
            self.root, bookmark,
            categories=self.category_manager.get_sorted_categories(),
            tag_manager=self.tag_manager
        )
        self.root.wait_window(dialog)
        
        if dialog.result:
            self.bookmark_manager.update_bookmark(
                bookmark.id,
                url=dialog.result["url"],
                title=dialog.result["title"],
                category=dialog.result["category"],
                tags=dialog.result["tags"],
                notes=dialog.result["notes"],
                is_pinned=dialog.result["is_pinned"],
                is_archived=dialog.result["is_archived"]
            )
            
            self._refresh_category_list()
            self._refresh_bookmark_list()
            self.status_bar.set_status(f"Updated: {dialog.result['title'][:50]}")
    
    def _delete_selected(self):
        """Delete selected bookmarks"""
        selected = list(self.selected_ids)
        if not selected:
            return
        
        if not messagebox.askyesno(
            "Confirm Delete",
            f"Delete {len(selected)} bookmark(s)?"
        ):
            return
        
        cmd = DeleteBookmarksCommand(self.bookmark_manager, selected)
        self.command_stack.execute(cmd)
        
        self.selected_ids.clear()
        self._refresh_category_list()
        self._refresh_bookmark_list()
        self.status_bar.set_status(f"Deleted {len(selected)} bookmark(s)")
    
    def _move_selected(self):
        """Move selected bookmarks to a category"""
        selected = list(self.selected_ids)
        if not selected:
            return
        
        categories = self.category_manager.get_sorted_categories()
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Move to Category")
        dialog.geometry("350x150")
        dialog.transient(self.root)
        dialog.grab_set()
        
        theme = get_theme()
        dialog.configure(bg=theme.bg_primary)
        set_dark_title_bar(dialog)
        
        tk.Label(
            dialog, text=f"Move {len(selected)} bookmark(s) to:",
            bg=theme.bg_primary, fg=theme.text_primary,
            font=FONTS.body()
        ).pack(pady=15)
        
        cat_var = tk.StringVar()
        combo = ttk.Combobox(dialog, textvariable=cat_var, values=categories, width=35)
        combo.pack(pady=10)
        combo.set(categories[0] if categories else "")
        
        def do_move():
            target = cat_var.get()
            if target:
                cmd = MoveBookmarksCommand(self.bookmark_manager, selected, target)
                self.command_stack.execute(cmd)
                self._refresh_category_list()
                self._refresh_bookmark_list()
                self.status_bar.set_status(f"Moved {len(selected)} to {target}")
            dialog.destroy()
        
        btn_frame = tk.Frame(dialog, bg=theme.bg_primary)
        btn_frame.pack(pady=15)
        
        ModernButton(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        ModernButton(btn_frame, text="Move", command=do_move, style="primary").pack(side=tk.LEFT, padx=5)
    
    def _tag_selected(self):
        """Add tags to selected bookmarks"""
        selected = list(self.selected_ids)
        if not selected:
            return
        
        tag = simpledialog.askstring("Add Tag", "Enter tag name:")
        if tag:
            tag = tag.strip().lower()
            if tag:
                cmd = TagBookmarksCommand(self.bookmark_manager, selected, add_tags=[tag])
                self.command_stack.execute(cmd)
                self._refresh_bookmark_list()
                self.status_bar.set_status(f"Added tag '{tag}' to {len(selected)} bookmark(s)")
    
    def _open_selected(self):
        """Open selected bookmark in browser"""
        for bm_id in self.selected_ids:
            bm = self.bookmark_manager.get_bookmark(bm_id)
            if bm:
                webbrowser.open(bm.url)
                bm.record_visit()
        self.bookmark_manager.save_bookmarks()
    
    def _copy_url(self):
        """Copy selected bookmark URL"""
        if self.selected_ids:
            bm = self.bookmark_manager.get_bookmark(list(self.selected_ids)[0])
            if bm:
                self.root.clipboard_clear()
                self.root.clipboard_append(bm.url)
                self.status_bar.set_status("URL copied to clipboard")
    
    def _copy_title(self):
        """Copy selected bookmark title"""
        if self.selected_ids:
            bm = self.bookmark_manager.get_bookmark(list(self.selected_ids)[0])
            if bm:
                self.root.clipboard_clear()
                self.root.clipboard_append(bm.title)
                self.status_bar.set_status("Title copied to clipboard")
    
    def _toggle_pin(self):
        """Toggle pin status of selected bookmarks"""
        for bm_id in self.selected_ids:
            bm = self.bookmark_manager.get_bookmark(bm_id)
            if bm:
                bm.is_pinned = not bm.is_pinned
        self.bookmark_manager.save_bookmarks()
        self._refresh_bookmark_list()
    
    def _toggle_archive(self):
        """Toggle archive status of selected bookmarks"""
        for bm_id in self.selected_ids:
            bm = self.bookmark_manager.get_bookmark(bm_id)
            if bm:
                bm.is_archived = not bm.is_archived
        self.bookmark_manager.save_bookmarks()
        self._refresh_bookmark_list()
    
    def _select_all(self):
        """Select all visible bookmarks"""
        if self.view_mode == ViewMode.LIST:
            self.tree.selection_set(self.tree.get_children())
        else:
            for widget in self._bookmark_widgets.values():
                widget.set_selected(True)
            self.selected_ids = set(self._bookmark_widgets.keys())
        self._update_status()
    
    def _undo(self):
        """Undo last action"""
        desc = self.command_stack.undo()
        if desc:
            self._refresh_category_list()
            self._refresh_bookmark_list()
            self.status_bar.set_status(f"Undone: {desc}")
    
    def _redo(self):
        """Redo last undone action"""
        desc = self.command_stack.redo()
        if desc:
            self._refresh_category_list()
            self._refresh_bookmark_list()
            self.status_bar.set_status(f"Redone: {desc}")
    
    def _sort_by(self, column: str):
        """Sort bookmarks by column"""
        # Simple toggle sort direction
        self._refresh_bookmark_list()


    
    # =========================================================================
    # Import/Export
    # =========================================================================
    
    def _import_html(self):
        """Import bookmarks from HTML file"""
        filepath = filedialog.askopenfilename(
            title="Import Bookmarks",
            filetypes=[("HTML files", "*.html *.htm"), ("All files", "*.*")]
        )
        
        if filepath:
            self.status_bar.set_status("Importing...")
            self.root.update()
            
            added, duplicates = self.bookmark_manager.import_html_file(filepath)
            
            self._refresh_category_list()
            self._refresh_bookmark_list()
            
            msg = f"Imported {added} bookmarks"
            if duplicates > 0:
                msg += f" ({duplicates} duplicates skipped)"
            
            self.status_bar.set_status(msg)
            messagebox.showinfo("Import Complete", msg)
    
    def _import_json(self):
        """Import bookmarks from JSON file"""
        filepath = filedialog.askopenfilename(
            title="Import Bookmarks",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filepath:
            added, duplicates = self.bookmark_manager.import_json_file(filepath)
            
            self._refresh_category_list()
            self._refresh_bookmark_list()
            
            msg = f"Imported {added} bookmarks"
            if duplicates > 0:
                msg += f" ({duplicates} duplicates skipped)"
            
            self.status_bar.set_status(msg)
            messagebox.showinfo("Import Complete", msg)
    
    def _export_html(self):
        """Export bookmarks to HTML"""
        filepath = filedialog.asksaveasfilename(
            title="Export Bookmarks",
            defaultextension=".html",
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")]
        )
        
        if filepath:
            self.bookmark_manager.export_html(filepath)
            self.status_bar.set_status(f"Exported to {Path(filepath).name}")
            messagebox.showinfo("Export Complete", f"Exported to {filepath}")
    
    def _export_json(self):
        """Export bookmarks to JSON"""
        filepath = filedialog.asksaveasfilename(
            title="Export Bookmarks",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filepath:
            self.bookmark_manager.export_json(filepath)
            self.status_bar.set_status(f"Exported to {Path(filepath).name}")
    
    def _export_csv(self):
        """Export bookmarks to CSV"""
        filepath = filedialog.asksaveasfilename(
            title="Export Bookmarks",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if filepath:
            self.bookmark_manager.export_csv(filepath)
            self.status_bar.set_status(f"Exported to {Path(filepath).name}")
    
    def _export_markdown(self):
        """Export bookmarks to Markdown"""
        filepath = filedialog.asksaveasfilename(
            title="Export Bookmarks",
            defaultextension=".md",
            filetypes=[("Markdown files", "*.md"), ("All files", "*.*")]
        )
        
        if filepath:
            self.bookmark_manager.export_markdown(filepath)
            self.status_bar.set_status(f"Exported to {Path(filepath).name}")
    
    # =========================================================================
    # Tools & Dialogs
    # =========================================================================
    
    def _find_duplicates(self):
        """Find and show duplicate bookmarks"""
        duplicates = self.bookmark_manager.find_duplicates()
        
        if not duplicates:
            messagebox.showinfo("Duplicates", "No duplicates found!")
            return
        
        total_dups = sum(len(bms) - 1 for bms in duplicates.values())
        
        if messagebox.askyesno(
            "Duplicates Found",
            f"Found {total_dups} duplicate bookmarks in {len(duplicates)} groups.\n\n"
            "Would you like to delete the duplicates (keeping the oldest)?"
        ):
            # Delete all but the oldest in each group
            deleted = 0
            for url, bms in duplicates.items():
                sorted_bms = sorted(bms, key=lambda b: b.created_at)
                for bm in sorted_bms[1:]:
                    self.bookmark_manager.delete_bookmark(bm.id)
                    deleted += 1
            
            self._refresh_category_list()
            self._refresh_bookmark_list()
            self.status_bar.set_status(f"Deleted {deleted} duplicate bookmarks")
    
    def _clean_urls(self):
        """Clean tracking parameters from URLs"""
        cleaned = self.bookmark_manager.clean_tracking_params()
        
        if cleaned > 0:
            self._refresh_bookmark_list()
            self.status_bar.set_status(f"Cleaned {cleaned} URLs")
            messagebox.showinfo("Clean URLs", f"Removed tracking parameters from {cleaned} URLs")
        else:
            messagebox.showinfo("Clean URLs", "No tracking parameters found")
    
    def _check_links(self):
        """Start checking for broken links"""
        if self.link_checker.is_running:
            messagebox.showinfo("Link Check", "Link check already in progress")
            return
        
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        if not bookmarks:
            messagebox.showinfo("Link Check", "No bookmarks to check")
            return
        
        def progress_callback(checked, total, bookmark):
            pct = checked / total
            self.status_bar.show_progress(pct, f"Checking links: {checked}/{total}")
            self.root.update()
        
        self.status_bar.set_status("Starting link check...")
        self.link_checker.check_links(bookmarks, progress_callback)
    
    def _on_link_check_complete(self):
        """Called when link check completes"""
        self.status_bar.hide_progress()
        self.bookmark_manager.save_bookmarks()
        self._refresh_bookmark_list()
        
        broken = len(self.bookmark_manager.find_broken_links())
        self.status_bar.set_status(f"Link check complete. {broken} broken links found.")
    
    def _show_analytics(self):
        """Show analytics dashboard"""
        stats = self.bookmark_manager.get_statistics()
        AnalyticsDashboard(self.root, stats)
    
    def _show_theme_settings(self):
        """Show theme settings dialog"""
        dialog = ThemeSelectorDialog(self.root, self.theme_manager)
        self.root.wait_window(dialog)
    
    def _show_ai_settings(self):
        """Show AI configuration dialog"""
        theme = get_theme()
        
        dialog = tk.Toplevel(self.root)
        dialog.title("AI Settings")
        dialog.geometry("500x450")
        dialog.configure(bg=theme.bg_primary)
        dialog.transient(self.root)
        dialog.grab_set()
        
        set_dark_title_bar(dialog)
        
        # Header
        header = tk.Frame(dialog, bg=theme.bg_dark, height=50)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(
            header, text="🤖 AI Configuration", bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.header()
        ).pack(side=tk.LEFT, padx=20, pady=12)
        
        # Content
        content = tk.Frame(dialog, bg=theme.bg_primary)
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        # Provider selection
        tk.Label(
            content, text="Provider:", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        ).grid(row=0, column=0, sticky="w", pady=5)
        
        provider_var = tk.StringVar(value=self.ai_config.get_provider())
        provider_combo = ttk.Combobox(
            content, textvariable=provider_var,
            values=list(AI_PROVIDERS.keys()),
            state="readonly", width=30
        )
        provider_combo.grid(row=0, column=1, sticky="ew", pady=5)
        
        # Model selection
        tk.Label(
            content, text="Model:", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        ).grid(row=1, column=0, sticky="w", pady=5)
        
        model_var = tk.StringVar(value=self.ai_config.get_model())
        model_combo = ttk.Combobox(content, textvariable=model_var, width=30)
        model_combo.grid(row=1, column=1, sticky="ew", pady=5)
        
        def update_models(*args):
            provider = provider_var.get()
            info = AI_PROVIDERS.get(provider)
            if info:
                model_combo['values'] = info.models
                model_var.set(info.default_model)
        
        provider_combo.bind("<<ComboboxSelected>>", update_models)
        update_models()
        
        # API Key
        tk.Label(
            content, text="API Key:", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        ).grid(row=2, column=0, sticky="w", pady=5)
        
        key_var = tk.StringVar(value=self.ai_config.get_api_key())
        key_entry = tk.Entry(
            content, textvariable=key_var, show="*",
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0
        )
        key_entry.grid(row=2, column=1, sticky="ew", pady=5, ipady=5)
        
        # Status
        status_label = tk.Label(
            content, text="", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.small()
        )
        status_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=10)
        
        def test_connection():
            provider = provider_var.get()
            model = model_var.get()
            key = key_var.get()
            
            status_label.configure(text="Testing connection...", fg=theme.text_secondary)
            dialog.update()
            
            # Save temporarily
            old_provider = self.ai_config.get_provider()
            old_model = self.ai_config.get_model()
            
            self.ai_config.set_provider(provider)
            self.ai_config.set_model(model)
            if key:
                self.ai_config.set_api_key(provider, key)
            
            try:
                client = create_ai_client(self.ai_config)
                success, message = client.test_connection()
                
                if success:
                    status_label.configure(text=f"✓ {message}", fg=theme.accent_success)
                else:
                    status_label.configure(text=f"✗ {message}", fg=theme.accent_error)
            except Exception as e:
                status_label.configure(text=f"✗ Error: {str(e)[:50]}", fg=theme.accent_error)
                self.ai_config.set_provider(old_provider)
                self.ai_config.set_model(old_model)
        
        # Test button
        ModernButton(
            content, text="Test Connection", command=test_connection
        ).grid(row=4, column=0, columnspan=2, pady=10)
        
        content.columnconfigure(1, weight=1)
        
        # Buttons
        btn_frame = tk.Frame(dialog, bg=theme.bg_primary)
        btn_frame.pack(fill=tk.X, padx=20, pady=15)
        
        def save_config():
            self.ai_config.set_provider(provider_var.get())
            self.ai_config.set_model(model_var.get())
            if key_var.get():
                self.ai_config.set_api_key(provider_var.get(), key_var.get())
            dialog.destroy()
            self.status_bar.set_status("AI settings saved")
        
        ModernButton(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=(10, 0))
        ModernButton(btn_frame, text="Save", command=save_config, style="primary").pack(side=tk.RIGHT)
    
    def _add_category(self):
        """Add a new category"""
        name = simpledialog.askstring("New Category", "Category name:")
        if name and name.strip():
            if self.category_manager.add_category(name.strip()):
                self._refresh_category_list()
                self.filter_combo['values'] = ["All Categories"] + self.category_manager.get_sorted_categories()
                self.status_bar.set_status(f"Added category: {name}")
            else:
                messagebox.showerror("Error", "Category already exists")
    
    def _manage_categories(self):
        """Open category management dialog"""
        messagebox.showinfo("Categories", "Category management coming soon!\n\nUse right-click on categories for now.")
    
    def _manage_tags(self):
        """Open tag management dialog"""
        messagebox.showinfo("Tags", "Tag management coming soon!")
    
    def _clear_favicon_cache(self):
        """Clear the favicon cache"""
        count, size = self.favicon_manager.get_cache_size()
        
        if messagebox.askyesno(
            "Clear Cache",
            f"Clear {count} cached favicons ({size // 1024}KB)?"
        ):
            self.favicon_manager.clear_cache()
            self.status_bar.set_status("Favicon cache cleared")
    
    def _show_search_help(self):
        """Show search syntax help"""
        messagebox.showinfo("Search Syntax", SearchEngine.get_syntax_help())
    
    def _show_shortcuts(self):
        """Show keyboard shortcuts"""
        shortcuts = """
Keyboard Shortcuts
══════════════════

Ctrl+F          Focus search
Ctrl+N          Add bookmark
Ctrl+I          Import HTML
Ctrl+E          Export HTML
Ctrl+Z          Undo
Ctrl+Y          Redo
Ctrl+A          Select all
Ctrl+D          Analytics
Ctrl+P          Command palette
Delete          Delete selected
F5              Refresh
Enter           Open in browser
Escape          Clear search
"""
        messagebox.showinfo("Keyboard Shortcuts", shortcuts)
    
    def _show_about(self):
        """Show about dialog"""
        about_text = f"""
{APP_NAME}
Version {APP_VERSION}

{APP_SUBTITLE}

Features:
• Multi-theme support (10+ themes)
• Nested category hierarchy
• Full tagging system
• Grid and list views
• Advanced search syntax
• Analytics dashboard
• AI-powered categorization
• System tray integration

Made with ❤️ using Python & Tkinter
"""
        messagebox.showinfo("About", about_text)
    
    def _show_command_palette(self):
        """Show command palette"""
        CommandPalette(self.root, self._commands)
    
    def _get_commands(self) -> List[Tuple[str, str, Callable]]:
        """Get all available commands for palette"""
        return [
            ("Add Bookmark", "Ctrl+N", self._add_bookmark),
            ("Import HTML", "Ctrl+I", self._import_html),
            ("Import JSON", "", self._import_json),
            ("Export HTML", "Ctrl+E", self._export_html),
            ("Export JSON", "", self._export_json),
            ("Export CSV", "", self._export_csv),
            ("Export Markdown", "", self._export_markdown),
            ("Find Duplicates", "", self._find_duplicates),
            ("Clean URLs", "", self._clean_urls),
            ("Check Broken Links", "", self._check_links),
            ("Analytics Dashboard", "Ctrl+D", self._show_analytics),
            ("Theme Settings", "", self._show_theme_settings),
            ("AI Settings", "", self._show_ai_settings),
            ("Add Category", "", self._add_category),
            ("List View", "", lambda: self._set_view_mode(ViewMode.LIST)),
            ("Grid View", "", lambda: self._set_view_mode(ViewMode.GRID)),
            ("Refresh", "F5", self._refresh_all),
            ("Undo", "Ctrl+Z", self._undo),
            ("Redo", "Ctrl+Y", self._redo),
            ("Search Syntax Help", "", self._show_search_help),
            ("Keyboard Shortcuts", "", self._show_shortcuts),
            ("About", "", self._show_about),
        ]
    
    # =========================================================================
    # Theme & Window Management
    # =========================================================================
    
    def _on_theme_change(self, new_theme: ThemeInfo):
        """Handle theme change"""
        # Recreate the UI with new theme
        # For now, just show a message
        messagebox.showinfo(
            "Theme Changed",
            f"Theme changed to {new_theme.display_name}.\n\n"
            "Please restart the application for full effect."
        )
    
    def _show_window(self):
        """Show the main window"""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
    
    def _on_close(self):
        """Handle window close"""
        if self.system_tray:
            self.system_tray.stop()
        self.root.destroy()

# =============================================================================
# ADDITIONAL FEATURES - BATCH 2
# =============================================================================

# =============================================================================
# Fuzzy Search with Levenshtein Distance
# =============================================================================
def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings"""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def fuzzy_match(query: str, text: str, threshold: float = 0.6) -> Tuple[bool, float]:
    """
    Check if query fuzzy matches text.
    Returns (matches, similarity_score)
    """
    query = query.lower()
    text = text.lower()
    
    # Exact match
    if query in text:
        return True, 1.0
    
    # Check each word
    query_words = query.split()
    text_words = text.split()
    
    total_score = 0
    matched_words = 0
    
    for qword in query_words:
        best_score = 0
        for tword in text_words:
            # Calculate similarity
            max_len = max(len(qword), len(tword))
            if max_len == 0:
                continue
            distance = levenshtein_distance(qword, tword)
            similarity = 1 - (distance / max_len)
            best_score = max(best_score, similarity)
        
        if best_score >= threshold:
            matched_words += 1
            total_score += best_score
    
    if len(query_words) == 0:
        return False, 0.0
    
    match_ratio = matched_words / len(query_words)
    avg_score = total_score / len(query_words) if query_words else 0
    
    return match_ratio >= 0.8, avg_score


class FuzzySearchEngine:
    """Enhanced search engine with fuzzy matching"""
    
    def __init__(self):
        self._cache: Dict[str, List[Tuple[int, float]]] = {}
        self._search_history: List[str] = []
        self._saved_searches: Dict[str, SearchQuery] = {}
    
    def search(self, bookmarks: List[Bookmark], query: str, 
               fuzzy: bool = True, threshold: float = 0.6) -> List[Tuple[Bookmark, float]]:
        """
        Search bookmarks with optional fuzzy matching.
        Returns list of (bookmark, relevance_score) sorted by relevance.
        """
        if not query.strip():
            return [(bm, 1.0) for bm in bookmarks]
        
        # Add to history
        if query not in self._search_history:
            self._search_history.insert(0, query)
            self._search_history = self._search_history[:50]
        
        # Check if structured query
        if any(x in query for x in [':', '#', '/', 'is:', 'has:']):
            parsed = SearchQuery(query)
            return [(bm, 1.0) for bm in bookmarks if parsed.matches(bm)]
        
        results = []
        query_lower = query.lower()
        
        for bm in bookmarks:
            # Build searchable text
            searchable = f"{bm.title} {bm.url} {bm.notes} {' '.join(bm.tags)}"
            
            # Exact match first
            if query_lower in searchable.lower():
                # Calculate relevance based on where match occurs
                score = 1.0
                if query_lower in bm.title.lower():
                    score += 0.5
                if query_lower in bm.domain.lower():
                    score += 0.3
                results.append((bm, score))
                continue
            
            # Fuzzy match if enabled
            if fuzzy:
                matches, score = fuzzy_match(query, searchable, threshold)
                if matches:
                    results.append((bm, score * 0.8))  # Slightly lower score for fuzzy
        
        # Sort by relevance
        results.sort(key=lambda x: x[1], reverse=True)
        return results
    
    def get_suggestions(self, partial: str, bookmarks: List[Bookmark], limit: int = 5) -> List[str]:
        """Get search suggestions based on partial input"""
        suggestions = set()
        partial_lower = partial.lower()
        
        # Add from history
        for hist in self._search_history:
            if partial_lower in hist.lower():
                suggestions.add(hist)
        
        # Add matching titles
        for bm in bookmarks:
            if partial_lower in bm.title.lower():
                # Extract relevant portion
                words = bm.title.split()
                for word in words:
                    if partial_lower in word.lower():
                        suggestions.add(word)
        
        # Add matching tags
        for bm in bookmarks:
            for tag in bm.tags:
                if partial_lower in tag.lower():
                    suggestions.add(f"#{tag}")
        
        return list(suggestions)[:limit]


# =============================================================================
# Custom Theme Creator Dialog
# =============================================================================
class ThemeCreatorDialog(tk.Toplevel, ThemedWidget):
    """Dialog for creating and editing custom themes"""
    
    COLOR_FIELDS = [
        ("Background", [
            ("bg_dark", "Dark Background"),
            ("bg_primary", "Primary Background"),
            ("bg_secondary", "Secondary Background"),
            ("bg_tertiary", "Tertiary Background"),
            ("bg_hover", "Hover Background"),
        ]),
        ("Text", [
            ("text_primary", "Primary Text"),
            ("text_secondary", "Secondary Text"),
            ("text_muted", "Muted Text"),
            ("text_link", "Link Text"),
        ]),
        ("Accents", [
            ("accent_primary", "Primary Accent"),
            ("accent_success", "Success"),
            ("accent_warning", "Warning"),
            ("accent_error", "Error"),
            ("accent_purple", "Purple"),
            ("accent_cyan", "Cyan"),
        ]),
        ("UI Elements", [
            ("border", "Border"),
            ("selection", "Selection"),
            ("scrollbar_thumb", "Scrollbar"),
        ]),
    ]
    
    def __init__(self, parent, theme_manager: ThemeManager, 
                 base_theme: ThemeInfo = None):
        super().__init__(parent)
        self.theme_manager = theme_manager
        self.base_theme = base_theme or theme_manager.current_theme
        self.result = None
        self.color_vars: Dict[str, tk.StringVar] = {}
        self.color_buttons: Dict[str, tk.Button] = {}
        
        theme = get_theme()
        
        self.title("Theme Creator")
        self.geometry("700x650")
        self.configure(bg=theme.bg_primary)
        self.transient(parent)
        self.grab_set()
        
        set_dark_title_bar(self)
        
        # Header
        header = tk.Frame(self, bg=theme.bg_dark, height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(
            header, text="🎨 Create Custom Theme", bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.title(bold=False)
        ).pack(side=tk.LEFT, padx=20, pady=15)
        
        # Main content with scrolling
        main = tk.Frame(self, bg=theme.bg_primary)
        main.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(main, bg=theme.bg_primary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main, orient="vertical", command=canvas.yview)
        content = tk.Frame(canvas, bg=theme.bg_primary)
        
        content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=content, anchor="nw", width=680)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Theme name
        name_frame = tk.Frame(content, bg=theme.bg_primary)
        name_frame.pack(fill=tk.X, pady=15, padx=10)
        
        tk.Label(
            name_frame, text="Theme Name:", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        ).pack(side=tk.LEFT)
        
        self.name_var = tk.StringVar(value="My Custom Theme")
        name_entry = tk.Entry(
            name_frame, textvariable=self.name_var,
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            font=FONTS.body(), width=30
        )
        name_entry.pack(side=tk.LEFT, padx=10, ipady=5)
        
        # Dark mode toggle
        self.is_dark_var = tk.BooleanVar(value=self.base_theme.is_dark)
        dark_check = ttk.Checkbutton(
            name_frame, text="Dark Theme", variable=self.is_dark_var
        )
        dark_check.pack(side=tk.RIGHT)
        
        # Base theme selector
        base_frame = tk.Frame(content, bg=theme.bg_primary)
        base_frame.pack(fill=tk.X, pady=(0, 15), padx=10)
        
        tk.Label(
            base_frame, text="Base Theme:", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        ).pack(side=tk.LEFT)
        
        self.base_var = tk.StringVar(value=self.base_theme.name)
        base_combo = ttk.Combobox(
            base_frame, textvariable=self.base_var,
            values=list(BUILT_IN_THEMES.keys()),
            state="readonly", width=25
        )
        base_combo.pack(side=tk.LEFT, padx=10)
        base_combo.bind("<<ComboboxSelected>>", self._on_base_change)
        
        # Color sections
        for section_name, fields in self.COLOR_FIELDS:
            self._create_color_section(content, section_name, fields)
        
        # Preview section
        preview_frame = tk.LabelFrame(
            content, text="Preview", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        )
        preview_frame.pack(fill=tk.X, padx=10, pady=15)
        
        self.preview_canvas = tk.Canvas(
            preview_frame, width=640, height=100,
            bg=theme.bg_secondary, highlightthickness=0
        )
        self.preview_canvas.pack(padx=10, pady=10)
        self._update_preview()
        
        # Buttons
        btn_frame = tk.Frame(self, bg=theme.bg_primary)
        btn_frame.pack(fill=tk.X, padx=20, pady=15)
        
        ModernButton(
            btn_frame, text="Reset to Base", command=self._reset_to_base
        ).pack(side=tk.LEFT)
        
        ModernButton(
            btn_frame, text="Cancel", command=self.destroy
        ).pack(side=tk.RIGHT, padx=(10, 0))
        
        ModernButton(
            btn_frame, text="Create Theme", command=self._create_theme,
            style="primary", icon="✨"
        ).pack(side=tk.RIGHT)
        
        # Initialize colors from base theme
        self._load_base_colors()
        
        self.center_window()
    
    def _create_color_section(self, parent, title: str, fields: List[Tuple[str, str]]):
        """Create a color section"""
        theme = get_theme()
        
        frame = tk.LabelFrame(
            parent, text=title, bg=theme.bg_primary,
            fg=theme.text_secondary, font=("Segoe UI", 10, "bold")
        )
        frame.pack(fill=tk.X, padx=10, pady=5)
        
        inner = tk.Frame(frame, bg=theme.bg_primary)
        inner.pack(fill=tk.X, padx=10, pady=10)
        
        row = 0
        col = 0
        
        for field_name, display_name in fields:
            # Create color variable
            var = tk.StringVar()
            self.color_vars[field_name] = var
            
            # Label
            tk.Label(
                inner, text=display_name, bg=theme.bg_primary,
                fg=theme.text_secondary, font=FONTS.small(),
                width=15, anchor="w"
            ).grid(row=row, column=col*3, sticky="w", pady=3)
            
            # Color button
            btn = tk.Button(
                inner, text="", width=3, height=1,
                command=lambda f=field_name: self._pick_color(f)
            )
            btn.grid(row=row, column=col*3+1, padx=5, pady=3)
            self.color_buttons[field_name] = btn
            
            # Hex entry
            entry = tk.Entry(
                inner, textvariable=var, width=8,
                bg=theme.bg_secondary, fg=theme.text_primary,
                insertbackground=theme.text_primary, bd=0,
                font=("Consolas", 9)
            )
            entry.grid(row=row, column=col*3+2, padx=(0, 20), pady=3)
            var.trace_add('write', lambda *args, f=field_name: self._on_color_change(f))
            
            col += 1
            if col >= 2:
                col = 0
                row += 1
    
    def _load_base_colors(self):
        """Load colors from base theme"""
        for field_name, var in self.color_vars.items():
            color = getattr(self.base_theme.colors, field_name, "#000000")
            var.set(color)
            self._update_button_color(field_name, color)
    
    def _on_base_change(self, e=None):
        """Handle base theme change"""
        base_name = self.base_var.get()
        if base_name in BUILT_IN_THEMES:
            self.base_theme = BUILT_IN_THEMES[base_name]
            self._load_base_colors()
            self._update_preview()
    
    def _pick_color(self, field_name: str):
        """Open color picker for a field"""
        current = self.color_vars[field_name].get()
        color = colorchooser.askcolor(color=current, title=f"Choose {field_name}")
        if color[1]:
            self.color_vars[field_name].set(color[1])
    
    def _on_color_change(self, field_name: str):
        """Handle color value change"""
        color = self.color_vars[field_name].get()
        if re.match(r'^#[0-9A-Fa-f]{6}$', color):
            self._update_button_color(field_name, color)
            self._update_preview()
    
    def _update_button_color(self, field_name: str, color: str):
        """Update button background to show color"""
        if field_name in self.color_buttons:
            try:
                self.color_buttons[field_name].configure(bg=color)
            except Exception:
                pass
    
    def _update_preview(self):
        """Update the preview canvas"""
        self.preview_canvas.delete("all")
        
        # Get current colors
        bg_primary = self.color_vars.get("bg_primary", tk.StringVar()).get() or "#161b22"
        bg_secondary = self.color_vars.get("bg_secondary", tk.StringVar()).get() or "#21262d"
        text_primary = self.color_vars.get("text_primary", tk.StringVar()).get() or "#f0f6fc"
        accent = self.color_vars.get("accent_primary", tk.StringVar()).get() or "#58a6ff"
        
        # Draw preview
        self.preview_canvas.configure(bg=bg_primary)
        
        # Sidebar preview
        self.preview_canvas.create_rectangle(0, 0, 150, 100, fill=bg_secondary, outline="")
        self.preview_canvas.create_text(75, 20, text="Sidebar", fill=text_primary, font=FONTS.small())
        
        # Accent bar
        self.preview_canvas.create_rectangle(0, 40, 150, 45, fill=accent, outline="")
        
        # Main area text
        self.preview_canvas.create_text(350, 30, text="Main Content Area", fill=text_primary, font=FONTS.body())
        self.preview_canvas.create_text(350, 60, text="Preview of your theme colors", fill=text_primary, font=FONTS.small())
        
        # Accent button
        self.preview_canvas.create_rectangle(300, 75, 400, 95, fill=accent, outline="")
        self.preview_canvas.create_text(350, 85, text="Button", fill="#ffffff", font=FONTS.small())
    
    def _reset_to_base(self):
        """Reset all colors to base theme"""
        self._load_base_colors()
        self._update_preview()
    
    def _create_theme(self):
        """Create the custom theme"""
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Please enter a theme name")
            return
        
        # Generate safe name
        safe_name = re.sub(r'[^a-z0-9_]', '_', name.lower())
        
        # Collect color overrides
        overrides = {}
        for field_name, var in self.color_vars.items():
            color = var.get()
            if re.match(r'^#[0-9A-Fa-f]{6}$', color):
                overrides[field_name] = color
        
        # Create the theme
        try:
            new_theme = self.theme_manager.create_custom_theme(
                name=safe_name,
                display_name=name,
                base_theme=self.base_var.get(),
                color_overrides=overrides
            )
            
            self.result = new_theme
            messagebox.showinfo("Success", f"Theme '{name}' created successfully!")
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create theme: {e}")
    
    def center_window(self):
        """Center the dialog"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')




# =============================================================================
# Smart Filters Panel
# =============================================================================
class SmartFiltersPanel(tk.Frame, ThemedWidget):
    """Collapsible smart filters sidebar panel"""
    
    def __init__(self, parent, on_filter_change: Callable = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_secondary, width=250)
        
        self.on_filter_change = on_filter_change
        self.is_collapsed = False
        self.filters: Dict[str, Any] = {}
        
        # Header
        header = tk.Frame(self, bg=theme.bg_tertiary)
        header.pack(fill=tk.X)
        
        self.toggle_btn = tk.Label(
            header, text="◀", bg=theme.bg_tertiary,
            fg=theme.text_primary, font=FONTS.body(),
            cursor="hand2", padx=10, pady=8
        )
        self.toggle_btn.pack(side=tk.LEFT)
        self.toggle_btn.bind("<Button-1>", self._toggle)
        
        tk.Label(
            header, text="Smart Filters", bg=theme.bg_tertiary,
            fg=theme.text_primary, font=("Segoe UI", 10, "bold"),
            pady=8
        ).pack(side=tk.LEFT)
        
        self.clear_btn = tk.Label(
            header, text="Clear", bg=theme.bg_tertiary,
            fg=theme.accent_primary, font=FONTS.small(),
            cursor="hand2", padx=10
        )
        self.clear_btn.pack(side=tk.RIGHT)
        self.clear_btn.bind("<Button-1>", self._clear_filters)
        
        # Content
        self.content = tk.Frame(self, bg=theme.bg_secondary)
        self.content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self._create_filters()
    
    def _create_filters(self):
        """Create all filter controls"""
        theme = get_theme()
        
        # Date Range
        self._create_section("📅 Date Range")
        
        date_frame = tk.Frame(self.content, bg=theme.bg_secondary)
        date_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(
            date_frame, text="From:", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.small()
        ).pack(side=tk.LEFT)
        
        self.date_from_var = tk.StringVar()
        date_from = tk.Entry(
            date_frame, textvariable=self.date_from_var, width=12,
            bg=theme.bg_tertiary, fg=theme.text_primary, bd=0
        )
        date_from.pack(side=tk.LEFT, padx=5)
        date_from.insert(0, "YYYY-MM-DD")
        date_from.bind("<FocusIn>", lambda e: date_from.delete(0, tk.END) if date_from.get() == "YYYY-MM-DD" else None)
        
        tk.Label(
            date_frame, text="To:", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.small()
        ).pack(side=tk.LEFT, padx=(10, 0))
        
        self.date_to_var = tk.StringVar()
        date_to = tk.Entry(
            date_frame, textvariable=self.date_to_var, width=12,
            bg=theme.bg_tertiary, fg=theme.text_primary, bd=0
        )
        date_to.pack(side=tk.LEFT, padx=5)
        
        # Quick date buttons
        quick_dates = tk.Frame(self.content, bg=theme.bg_secondary)
        quick_dates.pack(fill=tk.X, pady=(0, 10))
        
        for label, days in [("Today", 1), ("Week", 7), ("Month", 30), ("Year", 365)]:
            btn = tk.Label(
                quick_dates, text=label, bg=theme.bg_tertiary,
                fg=theme.text_primary, font=FONTS.tiny(),
                padx=8, pady=3, cursor="hand2"
            )
            btn.pack(side=tk.LEFT, padx=2)
            btn.bind("<Button-1>", lambda e, d=days: self._set_date_range(d))
        
        # Status Filters
        self._create_section("📊 Status")
        
        self.status_vars = {}
        for status, label in [("valid", "✓ Valid"), ("broken", "⚠ Broken"), 
                              ("unchecked", "? Unchecked")]:
            var = tk.BooleanVar(value=True)
            self.status_vars[status] = var
            cb = ttk.Checkbutton(
                self.content, text=label, variable=var,
                command=self._on_change
            )
            cb.pack(anchor="w", pady=2)
        
        # Bookmark Attributes
        self._create_section("📌 Attributes")
        
        self.attr_vars = {}
        for attr, label in [("pinned", "📌 Pinned Only"), 
                            ("archived", "📦 Archived Only"),
                            ("has_notes", "📝 Has Notes"),
                            ("has_tags", "🏷️ Has Tags")]:
            var = tk.BooleanVar(value=False)
            self.attr_vars[attr] = var
            cb = ttk.Checkbutton(
                self.content, text=label, variable=var,
                command=self._on_change
            )
            cb.pack(anchor="w", pady=2)
        
        # Domain Filter
        self._create_section("🌐 Domain")
        
        self.domain_var = tk.StringVar()
        domain_entry = tk.Entry(
            self.content, textvariable=self.domain_var,
            bg=theme.bg_tertiary, fg=theme.text_primary, bd=0
        )
        domain_entry.pack(fill=tk.X, pady=5, ipady=5)
        domain_entry.bind("<KeyRelease>", lambda e: self._on_change())
        
        # AI Confidence Slider
        self._create_section("🤖 AI Confidence")
        
        self.confidence_var = tk.DoubleVar(value=0.0)
        confidence_frame = tk.Frame(self.content, bg=theme.bg_secondary)
        confidence_frame.pack(fill=tk.X, pady=5)
        
        self.confidence_label = tk.Label(
            confidence_frame, text="Min: 0%", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.small()
        )
        self.confidence_label.pack(side=tk.LEFT)
        
        confidence_scale = ttk.Scale(
            confidence_frame, from_=0, to=100, variable=self.confidence_var,
            command=self._on_confidence_change
        )
        confidence_scale.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=10)
    
    def _create_section(self, title: str):
        """Create a section header"""
        theme = get_theme()
        tk.Label(
            self.content, text=title, bg=theme.bg_secondary,
            fg=theme.text_primary, font=("Segoe UI", 10, "bold"),
            anchor="w"
        ).pack(fill=tk.X, pady=(15, 5))
    
    def _toggle(self, e=None):
        """Toggle panel collapsed state"""
        theme = get_theme()
        self.is_collapsed = not self.is_collapsed
        
        if self.is_collapsed:
            self.content.pack_forget()
            self.toggle_btn.configure(text="▶")
            self.configure(width=40)
        else:
            self.content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            self.toggle_btn.configure(text="◀")
            self.configure(width=250)
    
    def _clear_filters(self, e=None):
        """Clear all filters"""
        self.date_from_var.set("")
        self.date_to_var.set("")
        self.domain_var.set("")
        self.confidence_var.set(0.0)
        
        for var in self.status_vars.values():
            var.set(True)
        for var in self.attr_vars.values():
            var.set(False)
        
        self._on_change()
    
    def _set_date_range(self, days: int):
        """Set date range to last N days"""
        end = datetime.now()
        start = end - timedelta(days=days)
        self.date_from_var.set(start.strftime("%Y-%m-%d"))
        self.date_to_var.set(end.strftime("%Y-%m-%d"))
        self._on_change()
    
    def _on_confidence_change(self, value):
        """Handle confidence slider change"""
        self.confidence_label.configure(text=f"Min: {int(float(value))}%")
        self._on_change()
    
    def _on_change(self):
        """Notify of filter change"""
        self.filters = self.get_filters()
        if self.on_filter_change:
            self.on_filter_change(self.filters)
    
    def get_filters(self) -> Dict[str, Any]:
        """Get current filter settings"""
        filters = {
            "date_from": self.date_from_var.get() if self.date_from_var.get() != "YYYY-MM-DD" else "",
            "date_to": self.date_to_var.get(),
            "domain": self.domain_var.get(),
            "min_confidence": self.confidence_var.get() / 100,
            "status": {k: v.get() for k, v in self.status_vars.items()},
            "attributes": {k: v.get() for k, v in self.attr_vars.items()},
        }
        return filters
    
    def apply_filters(self, bookmarks: List[Bookmark]) -> List[Bookmark]:
        """Apply current filters to bookmark list"""
        filters = self.get_filters()
        result = []
        
        for bm in bookmarks:
            # Date filter
            if filters["date_from"]:
                try:
                    from_date = datetime.fromisoformat(filters["date_from"])
                    created = datetime.fromisoformat(bm.created_at.replace('Z', '+00:00'))
                    if created.replace(tzinfo=None) < from_date:
                        continue
                except Exception:
                    pass
            
            if filters["date_to"]:
                try:
                    to_date = datetime.fromisoformat(filters["date_to"])
                    created = datetime.fromisoformat(bm.created_at.replace('Z', '+00:00'))
                    if created.replace(tzinfo=None) > to_date:
                        continue
                except Exception:
                    pass
            
            # Domain filter
            if filters["domain"] and filters["domain"].lower() not in bm.domain.lower():
                continue
            
            # Status filter
            if bm.is_valid and not filters["status"].get("valid", True):
                continue
            if not bm.is_valid and bm.http_status > 0 and not filters["status"].get("broken", True):
                continue
            if bm.http_status == 0 and not filters["status"].get("unchecked", True):
                continue
            
            # Attribute filters
            if filters["attributes"].get("pinned") and not bm.is_pinned:
                continue
            if filters["attributes"].get("archived") and not bm.is_archived:
                continue
            if filters["attributes"].get("has_notes") and not bm.notes:
                continue
            if filters["attributes"].get("has_tags") and not bm.tags:
                continue
            
            # AI Confidence
            if filters["min_confidence"] > 0 and bm.ai_confidence < filters["min_confidence"]:
                continue
            
            result.append(bm)
        
        return result


# =============================================================================
# Tag Cloud View
# =============================================================================
class TagCloudView(tk.Frame, ThemedWidget):
    """
        Represents a bookmark tag with metadata.
        
        Attributes:
            name: Tag name (unique identifier)
            color: Hex color code for display
            description: Optional tag description
            created_at: ISO timestamp of creation
            usage_count: Number of bookmarks using this tag
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
        """
    
    def __init__(self, parent, tag_counts: Dict[str, int], 
                 on_tag_click: Callable = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_primary)
        
        self.on_tag_click = on_tag_click
        self.tag_counts = tag_counts
        
        self._render_cloud()
    
    def _render_cloud(self):
        """Render the tag cloud"""
        theme = get_theme()
        
        if not self.tag_counts:
            tk.Label(
                self, text="No tags yet", bg=theme.bg_primary,
                fg=theme.text_muted, font=FONTS.body()
            ).pack(pady=20)
            return
        
        # Calculate font sizes
        max_count = max(self.tag_counts.values())
        min_count = min(self.tag_counts.values())
        count_range = max_count - min_count or 1
        
        # Sort by count descending
        sorted_tags = sorted(self.tag_counts.items(), key=lambda x: -x[1])
        
        # Create tag labels
        current_row = tk.Frame(self, bg=theme.bg_primary)
        current_row.pack(fill=tk.X, pady=5)
        row_width = 0
        max_width = 600
        
        for tag, count in sorted_tags:
            # Calculate size (8-18pt based on frequency)
            size_ratio = (count - min_count) / count_range
            font_size = int(8 + (size_ratio * 10))
            
            # Generate color
            colors = [
                theme.accent_primary, theme.accent_success, theme.accent_warning,
                theme.accent_purple, theme.accent_cyan, theme.accent_pink
            ]
            color = colors[hash(tag) % len(colors)]
            
            # Create label
            label = tk.Label(
                current_row, text=f"#{tag}", bg=theme.bg_primary,
                fg=color, font=("Segoe UI", font_size),
                cursor="hand2", padx=5, pady=3
            )
            
            # Estimate width
            est_width = len(tag) * font_size
            
            if row_width + est_width > max_width:
                current_row = tk.Frame(self, bg=theme.bg_primary)
                current_row.pack(fill=tk.X, pady=5)
                row_width = 0
            
            label.pack(side=tk.LEFT, padx=3, pady=2)
            row_width += est_width + 20
            
            # Bindings
            def on_enter(e, l=label, c=color):
                l.configure(bg=theme.bg_secondary)
            
            def on_leave(e, l=label):
                l.configure(bg=theme.bg_primary)
            
            def on_click(e, t=tag):
                if self.on_tag_click:
                    self.on_tag_click(t)
            
            label.bind("<Enter>", on_enter)
            label.bind("<Leave>", on_leave)
            label.bind("<Button-1>", on_click)
    
    def update_counts(self, tag_counts: Dict[str, int]):
        """Update tag counts and re-render"""
        self.tag_counts = tag_counts
        for widget in self.winfo_children():
            widget.destroy()
        self._render_cloud()


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
        except Exception as e:
            pass
        
        # Schedule next check
        if self._running:
            self.root.after(self._check_interval, self._check)
    
    @property
    def is_running(self) -> bool:
        return self._running




# =============================================================================
# Kanban View
# =============================================================================
class KanbanColumn(tk.Frame, ThemedWidget):
    """A single column in the Kanban view"""
    
    def __init__(self, parent, category: str, bookmarks: List[Bookmark],
                 on_bookmark_click: Callable = None,
                 on_bookmark_drop: Callable = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_secondary, width=280)
        
        self.category = category
        self.bookmarks = bookmarks
        self.on_bookmark_click = on_bookmark_click
        self.on_bookmark_drop = on_bookmark_drop
        
        self.pack_propagate(False)
        self.configure(highlightbackground=theme.border, highlightthickness=1)
        
        # Header
        header = tk.Frame(self, bg=theme.bg_tertiary)
        header.pack(fill=tk.X)
        
        # Get icon
        icon = get_category_icon(category)
        
        tk.Label(
            header, text=f"{icon} {category}", bg=theme.bg_tertiary,
            fg=theme.text_primary, font=("Segoe UI", 10, "bold"),
            anchor="w", padx=10, pady=10
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        tk.Label(
            header, text=str(len(bookmarks)), bg=theme.bg_tertiary,
            fg=theme.text_muted, font=FONTS.body(),
            padx=10
        ).pack(side=tk.RIGHT)
        
        # Cards container with scrolling
        container = tk.Frame(self, bg=theme.bg_secondary)
        container.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(container, bg=theme.bg_secondary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.cards_frame = tk.Frame(canvas, bg=theme.bg_secondary)
        
        self.cards_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.cards_frame, anchor="nw", width=270)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Mouse wheel
        canvas.bind("<MouseWheel>", 
            lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        
        # Enable drop
        self.bind("<ButtonRelease-1>", self._on_drop)
        canvas.bind("<ButtonRelease-1>", self._on_drop)
        self.cards_frame.bind("<ButtonRelease-1>", self._on_drop)
        
        self._render_cards()
    
    def _render_cards(self):
        """Render bookmark cards"""
        theme = get_theme()
        
        for bm in self.bookmarks[:50]:  # Limit for performance
            card = tk.Frame(
                self.cards_frame, bg=theme.card_bg,
                cursor="hand2"
            )
            card.pack(fill=tk.X, padx=8, pady=4)
            card.configure(highlightbackground=theme.card_border, highlightthickness=1)
            
            # Title
            title = bm.title[:35] + "..." if len(bm.title) > 38 else bm.title
            if bm.is_pinned:
                title = "📌 " + title
            
            tk.Label(
                card, text=title, bg=theme.card_bg,
                fg=theme.text_primary, font=FONTS.small(),
                anchor="w", padx=8, pady=(8, 4)
            ).pack(fill=tk.X)
            
            # Domain
            tk.Label(
                card, text=bm.domain, bg=theme.card_bg,
                fg=theme.text_muted, font=FONTS.tiny(),
                anchor="w", padx=8, pady=(0, 4)
            ).pack(fill=tk.X)
            
            # Tags
            if bm.tags:
                tags_text = " ".join(f"#{t}" for t in bm.tags[:3])
                tk.Label(
                    card, text=tags_text, bg=theme.card_bg,
                    fg=theme.accent_primary, font=FONTS.tiny(),
                    anchor="w", padx=8, pady=(0, 8)
                ).pack(fill=tk.X)
            
            # Click handler
            def on_click(e, bookmark=bm):
                if self.on_bookmark_click:
                    self.on_bookmark_click(bookmark)
            
            card.bind("<Button-1>", on_click)
            for child in card.winfo_children():
                child.bind("<Button-1>", on_click)
            
            # Hover effect
            def on_enter(e, c=card):
                c.configure(bg=theme.card_hover)
                for child in c.winfo_children():
                    child.configure(bg=theme.card_hover)
            
            def on_leave(e, c=card):
                c.configure(bg=theme.card_bg)
                for child in c.winfo_children():
                    child.configure(bg=theme.card_bg)
            
            card.bind("<Enter>", on_enter)
            card.bind("<Leave>", on_leave)
    
    def _on_drop(self, e):
        """Handle drop on this column"""
        if self.on_bookmark_drop:
            self.on_bookmark_drop(self.category)


class KanbanView(tk.Frame, ThemedWidget):
    """Kanban board view for bookmarks"""
    
    def __init__(self, parent, bookmark_manager: BookmarkManager,
                 on_bookmark_click: Callable = None,
                 on_move: Callable = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_primary)
        
        self.bookmark_manager = bookmark_manager
        self.on_bookmark_click = on_bookmark_click
        self.on_move = on_move
        self.columns: Dict[str, KanbanColumn] = {}
        
        # Scrollable container
        self.canvas = tk.Canvas(self, bg=theme.bg_primary, highlightthickness=0)
        self.h_scrollbar = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.inner = tk.Frame(self.canvas, bg=theme.bg_primary)
        
        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(xscrollcommand=self.h_scrollbar.set)
        
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Mouse wheel horizontal scroll
        self.canvas.bind("<Shift-MouseWheel>", 
            lambda e: self.canvas.xview_scroll(-1 * (e.delta // 120), "units"))
    
    def refresh(self, categories: List[str] = None):
        """Refresh the Kanban board"""
        theme = get_theme()
        
        # Clear existing columns
        for widget in self.inner.winfo_children():
            widget.destroy()
        self.columns.clear()
        
        # Get categories
        if categories is None:
            categories = self.bookmark_manager.category_manager.get_sorted_categories()
        
        # Create columns
        for cat in categories:
            bookmarks = self.bookmark_manager.get_bookmarks_by_category(cat)
            
            column = KanbanColumn(
                self.inner, cat, bookmarks,
                on_bookmark_click=self.on_bookmark_click,
                on_bookmark_drop=lambda c: self._on_column_drop(c)
            )
            column.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=10)
            self.columns[cat] = column
    
    def _on_column_drop(self, category: str):
        """Handle drop on a category column"""
        if self.on_move:
            self.on_move(category)


# =============================================================================
# Display Density (Compact/Comfortable/Spacious)
# =============================================================================
class DisplayDensity(Enum):
    """
        Enumeration of display density options.
        
        Values:
            COMPACT: Minimal spacing, more items visible
            NORMAL: Standard spacing
            COMFORTABLE: Extra spacing, easier reading
        """
    COMPACT = "compact"
    COMFORTABLE = "comfortable"
    SPACIOUS = "spacious"


DENSITY_SETTINGS = {
    DisplayDensity.COMPACT: {
        "row_height": 24,
        "padding_y": 4,
        "font_size": 9,
        "card_padding": 6,
        "icon_size": 14,
    },
    DisplayDensity.COMFORTABLE: {
        "row_height": 32,
        "padding_y": 8,
        "font_size": 10,
        "card_padding": 10,
        "icon_size": 16,
    },
    DisplayDensity.SPACIOUS: {
        "row_height": 44,
        "padding_y": 12,
        "font_size": 11,
        "card_padding": 15,
        "icon_size": 20,
    },
}


class DensityManager:
    """Manages display density settings"""
    
    def __init__(self):
        self._density = DisplayDensity.COMFORTABLE
        self._callbacks: List[Callable] = []
        self._load_settings()
    
    def _load_settings(self):
        """Load density from settings"""
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, 'r') as f:
                    data = json.load(f)
                    density_name = data.get("display_density", "comfortable")
                    self._density = DisplayDensity(density_name)
            except Exception:
                pass
    
    def _save_settings(self):
        """Save density to settings"""
        data = {}
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, 'r') as f:
                    data = json.load(f)
            except Exception:
                pass
        
        data["display_density"] = self._density.value
        
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    
    @property
    def density(self) -> DisplayDensity:
        return self._density
    
    @density.setter
    def density(self, value: DisplayDensity):
        if self._density != value:
            self._density = value
            self._save_settings()
            self._notify_callbacks()
    
    def get_setting(self, key: str) -> Any:
        """Get a density-specific setting"""
        return DENSITY_SETTINGS[self._density].get(key)
    
    def add_callback(self, callback: Callable):
        """Add density change callback"""
        self._callbacks.append(callback)
    
    def remove_callback(self, callback: Callable):
        """Remove density change callback"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def _notify_callbacks(self):
        """Notify all callbacks of density change"""
        for cb in self._callbacks:
            try:
                cb(self._density)
            except Exception:
                pass


# =============================================================================
# System Theme Detection
# =============================================================================
class SystemThemeDetector:
    """Detect system dark/light mode preference"""
    
    def __init__(self, on_theme_change: Callable = None):
        self.on_theme_change = on_theme_change
        self._last_is_dark: Optional[bool] = None
        self._running = False
        self._check_interval = 5000  # Check every 5 seconds
    
    def get_system_theme_is_dark(self) -> bool:
        """Detect if system is in dark mode"""
        if IS_WINDOWS:
            return self._check_windows_dark_mode()
        elif IS_MAC:
            return self._check_macos_dark_mode()
        else:
            return self._check_linux_dark_mode()
    
    def _check_windows_dark_mode(self) -> bool:
        """Check Windows dark mode setting"""
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return value == 0
        except Exception:
            return True  # Default to dark
    
    def _check_macos_dark_mode(self) -> bool:
        """Check macOS dark mode setting"""
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True
            )
            return "dark" in result.stdout.lower()
        except Exception:
            return True
    
    def _check_linux_dark_mode(self) -> bool:
        """Check Linux dark mode (GNOME/GTK)"""
        try:
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                capture_output=True, text=True
            )
            return "dark" in result.stdout.lower()
        except Exception:
            return True
    
    def start_monitoring(self, root: tk.Tk):
        """Start monitoring for system theme changes"""
        self._running = True
        self._root = root
        self._check_theme()
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self._running = False
    
    def _check_theme(self):
        """Check for theme change"""
        if not self._running:
            return
        
        is_dark = self.get_system_theme_is_dark()
        
        if self._last_is_dark is not None and is_dark != self._last_is_dark:
            if self.on_theme_change:
                self.on_theme_change(is_dark)
        
        self._last_is_dark = is_dark
        
        if self._running:
            self._root.after(self._check_interval, self._check_theme)


# =============================================================================
# Reading List Queue View
# =============================================================================
class ReadingListView(tk.Frame, ThemedWidget):
    """View for managing a reading list queue"""
    
    def __init__(self, parent, bookmarks: List[Bookmark],
                 on_open: Callable = None,
                 on_mark_read: Callable = None,
                 on_remove: Callable = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_primary)
        
        self.bookmarks = bookmarks
        self.on_open = on_open
        self.on_mark_read = on_mark_read
        self.on_remove = on_remove
        
        # Header
        header = tk.Frame(self, bg=theme.bg_dark)
        header.pack(fill=tk.X)
        
        tk.Label(
            header, text="📖 Reading List", bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.header(),
            padx=15, pady=12
        ).pack(side=tk.LEFT)
        
        self.count_label = tk.Label(
            header, text=f"{len(bookmarks)} items", bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.body(),
            padx=15
        )
        self.count_label.pack(side=tk.RIGHT)
        
        # List container
        container = tk.Frame(self, bg=theme.bg_primary)
        container.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(container, bg=theme.bg_primary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.list_frame = tk.Frame(canvas, bg=theme.bg_primary)
        
        self.list_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        canvas.bind("<MouseWheel>", 
            lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        
        self._render_list()
    
    def _render_list(self):
        """Render the reading list"""
        theme = get_theme()
        
        for i, bm in enumerate(self.bookmarks):
            item = tk.Frame(self.list_frame, bg=theme.bg_secondary)
            item.pack(fill=tk.X, padx=10, pady=5)
            
            # Number
            tk.Label(
                item, text=f"{i+1}.", bg=theme.bg_secondary,
                fg=theme.text_muted, font=FONTS.body(),
                width=4
            ).pack(side=tk.LEFT, padx=(10, 5), pady=10)
            
            # Content
            content = tk.Frame(item, bg=theme.bg_secondary)
            content.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=10)
            
            # Title
            title = bm.title[:60] + "..." if len(bm.title) > 63 else bm.title
            tk.Label(
                content, text=title, bg=theme.bg_secondary,
                fg=theme.text_primary, font=FONTS.body(),
                anchor="w"
            ).pack(fill=tk.X)
            
            # Meta info
            meta = f"{bm.domain}"
            if bm.reading_time > 0:
                meta += f" • {bm.reading_time} min read"
            
            tk.Label(
                content, text=meta, bg=theme.bg_secondary,
                fg=theme.text_muted, font=FONTS.small(),
                anchor="w"
            ).pack(fill=tk.X)
            
            # Actions
            actions = tk.Frame(item, bg=theme.bg_secondary)
            actions.pack(side=tk.RIGHT, padx=10)
            
            # Open button
            open_btn = tk.Label(
                actions, text="📖", bg=theme.bg_secondary,
                fg=theme.accent_primary, font=("Segoe UI", 12),
                cursor="hand2"
            )
            open_btn.pack(side=tk.LEFT, padx=5)
            open_btn.bind("<Button-1>", lambda e, b=bm: self._on_open(b))
            
            # Mark read button
            done_btn = tk.Label(
                actions, text="✓", bg=theme.bg_secondary,
                fg=theme.accent_success, font=("Segoe UI", 12),
                cursor="hand2"
            )
            done_btn.pack(side=tk.LEFT, padx=5)
            done_btn.bind("<Button-1>", lambda e, b=bm: self._on_mark_read(b))
            
            # Remove button
            remove_btn = tk.Label(
                actions, text="✕", bg=theme.bg_secondary,
                fg=theme.accent_error, font=("Segoe UI", 12),
                cursor="hand2"
            )
            remove_btn.pack(side=tk.LEFT, padx=5)
            remove_btn.bind("<Button-1>", lambda e, b=bm: self._on_remove(b))
    
    def _on_open(self, bookmark: Bookmark):
        if self.on_open:
            self.on_open(bookmark)
    
    def _on_mark_read(self, bookmark: Bookmark):
        if self.on_mark_read:
            self.on_mark_read(bookmark)
    
    def _on_remove(self, bookmark: Bookmark):
        if self.on_remove:
            self.on_remove(bookmark)
    
    def refresh(self, bookmarks: List[Bookmark]):
        """Refresh the reading list"""
        self.bookmarks = bookmarks
        self.count_label.configure(text=f"{len(bookmarks)} items")
        
        for widget in self.list_frame.winfo_children():
            widget.destroy()
        
        self._render_list()


# =============================================================================
# Export Reports (PDF/HTML Analytics)
# =============================================================================
class ReportGenerator:
    """Generate analytics reports in various formats"""
    
    def __init__(self, bookmark_manager: BookmarkManager):
        self.bookmark_manager = bookmark_manager
    
    def generate_html_report(self, filepath: str):
        """Generate HTML analytics report"""
        stats = self.bookmark_manager.get_statistics()
        theme = get_theme()
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Bookmark Analytics Report</title>
    <style>
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            background: {theme.bg_primary};
            color: {theme.text_primary};
            margin: 0;
            padding: 40px;
        }}
        .container {{
            max-width: 1000px;
            margin: 0 auto;
        }}
        h1 {{
            color: {theme.accent_primary};
            border-bottom: 2px solid {theme.border};
            padding-bottom: 10px;
        }}
        h2 {{
            color: {theme.text_secondary};
            margin-top: 30px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin: 30px 0;
        }}
        .stat-card {{
            background: {theme.bg_secondary};
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 32px;
            font-weight: bold;
            color: {theme.accent_primary};
        }}
        .stat-label {{
            color: {theme.text_muted};
            margin-top: 5px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid {theme.border};
        }}
        th {{
            background: {theme.bg_secondary};
            color: {theme.text_secondary};
        }}
        .bar {{
            background: {theme.bg_tertiary};
            height: 20px;
            border-radius: 4px;
            overflow: hidden;
        }}
        .bar-fill {{
            background: {theme.accent_primary};
            height: 100%;
        }}
        .footer {{
            margin-top: 50px;
            color: {theme.text_muted};
            text-align: center;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Bookmark Analytics Report</h1>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{stats['total_bookmarks']}</div>
                <div class="stat-label">Total Bookmarks</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats['total_categories']}</div>
                <div class="stat-label">Categories</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats['total_tags']}</div>
                <div class="stat-label">Tags</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats['duplicate_bookmarks']}</div>
                <div class="stat-label">Duplicates</div>
            </div>
        </div>
        
        <h2>📂 Categories</h2>
        <table>
            <tr><th>Category</th><th>Count</th><th>Distribution</th></tr>
"""
        
        total = stats['total_bookmarks'] or 1
        for cat, count in sorted(stats['category_counts'].items(), key=lambda x: -x[1]):
            pct = (count / total) * 100
            html += f"""
            <tr>
                <td>{cat}</td>
                <td>{count}</td>
                <td><div class="bar"><div class="bar-fill" style="width: {pct}%"></div></div></td>
            </tr>
"""
        
        html += """
        </table>
        
        <h2>🌐 Top Domains</h2>
        <table>
            <tr><th>Domain</th><th>Count</th></tr>
"""
        
        for domain, count in stats['top_domains'][:15]:
            html += f"            <tr><td>{domain}</td><td>{count}</td></tr>\n"
        
        html += f"""
        </table>
        
        <h2>📅 Age Distribution</h2>
        <table>
            <tr><th>Period</th><th>Count</th></tr>
"""
        
        for period, count in stats['age_distribution'].items():
            html += f"            <tr><td>{period}</td><td>{count}</td></tr>\n"
        
        html += f"""
        </table>
        
        <div class="footer">
            Generated by {APP_NAME} v{APP_VERSION}
        </div>
    </div>
</body>
</html>
"""
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)
    
    def generate_text_report(self, filepath: str):
        """Generate plain text report"""
        stats = self.bookmark_manager.get_statistics()
        
        lines = [
            "=" * 60,
            f"BOOKMARK ANALYTICS REPORT",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "=" * 60,
            "",
            "SUMMARY",
            "-" * 40,
            f"Total Bookmarks:  {stats['total_bookmarks']}",
            f"Categories:       {stats['total_categories']}",
            f"Tags:             {stats['total_tags']}",
            f"Duplicates:       {stats['duplicate_bookmarks']}",
            f"Broken Links:     {stats['broken']}",
            f"Uncategorized:    {stats['uncategorized']}",
            "",
            "CATEGORIES",
            "-" * 40,
        ]
        
        for cat, count in sorted(stats['category_counts'].items(), key=lambda x: -x[1]):
            lines.append(f"  {cat:40} {count:5}")
        
        lines.extend([
            "",
            "TOP DOMAINS",
            "-" * 40,
        ])
        
        for domain, count in stats['top_domains'][:15]:
            lines.append(f"  {domain:40} {count:5}")
        
        lines.extend([
            "",
            "=" * 60,
            f"Generated by {APP_NAME} v{APP_VERSION}",
        ])
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))




# =============================================================================
# AI Batch Processing Queue
# =============================================================================
class AIBatchProcessor:
    """Background AI processing queue for bookmarks"""
    
    def __init__(self, ai_config: AIConfigManager, 
                 on_progress: Callable = None,
                 on_complete: Callable = None):
        self.ai_config = ai_config
        self.on_progress = on_progress
        self.on_complete = on_complete
        
        self._queue: List[Bookmark] = []
        self._processed: int = 0
        self._running = False
        self._client: Optional[AIClient] = None
        self._thread: Optional[threading.Thread] = None
        self._results: Dict[int, Dict] = {}  # bookmark_id -> result
        self._errors: List[Tuple[int, str]] = []  # (bookmark_id, error_message)
    
    def add_to_queue(self, bookmarks: List[Bookmark]):
        """Add bookmarks to processing queue"""
        self._queue.extend(bookmarks)
    
    def clear_queue(self):
        """Clear the queue"""
        self._queue.clear()
    
    def start(self):
        """Start processing in background thread"""
        if self._running or not self._queue:
            return
        
        self._running = True
        self._processed = 0
        self._results.clear()
        self._errors.clear()
        
        # Create AI client
        try:
            self._client = create_ai_client(self.ai_config)
        except Exception as e:
            self._running = False
            if self.on_complete:
                self.on_complete(False, str(e))
            return
        
        # Start worker thread
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop processing"""
        self._running = False
    
    def _worker(self):
        """Worker thread for processing bookmarks"""
        batch_size = self.ai_config.settings.get("batch_size", 5)
        rate_limit_delay = self.ai_config.settings.get("rate_limit_delay", 1.0)
        
        total = len(self._queue)
        
        while self._queue and self._running:
            # Process in batches
            batch = self._queue[:batch_size]
            self._queue = self._queue[batch_size:]
            
            for bookmark in batch:
                if not self._running:
                    break
                
                try:
                    # Get AI categorization and tags
                    result = self._process_bookmark(bookmark)
                    self._results[bookmark.id] = result
                    
                    # Apply results
                    if result.get("category"):
                        bookmark.category = result["category"]
                        bookmark.ai_categorized = True
                        bookmark.ai_confidence = result.get("confidence", 0.0)
                    
                    if result.get("tags"):
                        bookmark.tags = list(set(bookmark.tags + result["tags"]))
                    
                    if result.get("summary"):
                        if not bookmark.notes:
                            bookmark.notes = result["summary"]
                    
                except Exception as e:
                    self._errors.append((bookmark.id, str(e)))
                
                self._processed += 1
                
                if self.on_progress:
                    self.on_progress(self._processed, total, bookmark)
                
                # Rate limiting
                time.sleep(rate_limit_delay)
        
        self._running = False
        if self.on_complete:
            self.on_complete(True, f"Processed {self._processed} bookmarks")
    
    def _process_bookmark(self, bookmark: Bookmark) -> Dict:
        """Process a single bookmark with AI"""
        result = {}
        
        # Build prompt for categorization + tags + summary
        prompt = f"""Analyze this bookmark and provide:
1. Best category from common bookmark categories
2. 3-5 relevant tags (single words, lowercase)
3. A brief 1-sentence summary

URL: {bookmark.url}
Title: {bookmark.title}
Current Category: {bookmark.category}
Domain: {bookmark.domain}

Respond in JSON format:
{{"category": "...", "tags": ["...", "..."], "summary": "...", "confidence": 0.0-1.0}}"""
        
        try:
            response = self._client.categorize_bookmark(
                bookmark.url, bookmark.title, []
            )
            
            if response:
                result["category"] = response.get("category", bookmark.category)
                result["confidence"] = response.get("confidence", 0.5)
                result["tags"] = response.get("tags", [])
                result["summary"] = response.get("summary", "")
        except Exception:
            pass
        
        return result
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    @property
    def progress(self) -> Tuple[int, int]:
        return self._processed, len(self._queue) + self._processed
    
    @property
    def results(self) -> Dict[int, Dict]:
        return self._results.copy()
    
    @property
    def errors(self) -> List[Tuple[int, str]]:
        return self._errors.copy()


# =============================================================================
# AI Tag Suggestions
# =============================================================================
class AITagSuggester:
    """Generate tag suggestions using AI"""
    
    def __init__(self, ai_config: AIConfigManager):
        self.ai_config = ai_config
        self._cache: Dict[str, List[str]] = {}
    
    def suggest_tags(self, bookmark: Bookmark, existing_tags: List[str] = None) -> List[str]:
        """Get AI-suggested tags for a bookmark"""
        cache_key = f"{bookmark.url}:{bookmark.title}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            client = create_ai_client(self.ai_config)
            
            prompt = f"""Suggest 5-7 relevant tags for this bookmark.
Tags should be:
- Single words or short phrases
- Lowercase
- Descriptive of content, topic, or purpose
- Not duplicate existing tags: {existing_tags or []}

URL: {bookmark.url}
Title: {bookmark.title}
Domain: {bookmark.domain}
Notes: {bookmark.notes[:200] if bookmark.notes else 'None'}

Return only a JSON array of tag strings: ["tag1", "tag2", ...]"""
            
            # Use the client's categorize method but parse for tags
            response = client.categorize_bookmark(bookmark.url, bookmark.title, [])
            
            if response and "tags" in response:
                tags = response["tags"]
                self._cache[cache_key] = tags
                return tags
        except Exception:
            pass
        
        # Fallback: generate from content
        return self._generate_fallback_tags(bookmark)
    
    def _generate_fallback_tags(self, bookmark: Bookmark) -> List[str]:
        """Generate tags without AI"""
        tags = set()
        
        # From domain
        domain_parts = bookmark.domain.replace('.', ' ').split()
        for part in domain_parts:
            if len(part) > 3 and part not in ['www', 'com', 'org', 'net', 'edu']:
                tags.add(part.lower())
        
        # From title words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        words = re.findall(r'\b[a-zA-Z]{4,}\b', bookmark.title.lower())
        for word in words[:5]:
            if word not in stop_words:
                tags.add(word)
        
        return list(tags)[:7]


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
# Category Drag & Drop Manager
# =============================================================================
class CategoryDragDropManager:
    """
        Represents a bookmark category.
        
        Attributes:
            name: Category name (unique identifier)
            parent: Parent category name (for nesting)
            icon: Emoji icon for display
            color: Optional color override
            sort_order: Order within parent
            created_at: ISO timestamp of creation
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
        """
    
    def __init__(self, container: tk.Frame, category_manager: CategoryManager,
                 on_reorder: Callable = None):
        self.container = container
        self.category_manager = category_manager
        self.on_reorder = on_reorder
        
        self._dragging = False
        self._drag_item: Optional[tk.Widget] = None
        self._drag_category: Optional[str] = None
        self._drag_start_y = 0
        self._placeholder: Optional[tk.Frame] = None
        self._item_widgets: Dict[str, tk.Widget] = {}
    
    def make_draggable(self, widget: tk.Widget, category_name: str):
        """Make a category widget draggable"""
        self._item_widgets[category_name] = widget
        
        widget.bind('<ButtonPress-1>', lambda e: self._start_drag(e, category_name))
        widget.bind('<B1-Motion>', self._on_drag)
        widget.bind('<ButtonRelease-1>', self._end_drag)
    
    def _start_drag(self, event, category_name: str):
        """Start dragging a category"""
        self._dragging = True
        self._drag_category = category_name
        self._drag_item = event.widget
        self._drag_start_y = event.y_root
        
        # Create visual feedback
        theme = get_theme()
        self._drag_item.configure(bg=theme.drag_active)
    
    def _on_drag(self, event):
        """Handle drag motion"""
        if not self._dragging or not self._drag_item:
            return
        
        # Find position among siblings
        y = event.y_root
        target_category = None
        
        for cat_name, widget in self._item_widgets.items():
            if cat_name == self._drag_category:
                continue
            
            widget_y = widget.winfo_rooty()
            widget_height = widget.winfo_height()
            
            if widget_y <= y <= widget_y + widget_height:
                target_category = cat_name
                break
        
        # Update visual indicator
        if target_category:
            self._show_drop_indicator(target_category)
    
    def _show_drop_indicator(self, target_category: str):
        """Show drop position indicator"""
        theme = get_theme()
        
        # Remove old placeholder
        if self._placeholder:
            self._placeholder.destroy()
        
        # Create new placeholder
        target_widget = self._item_widgets.get(target_category)
        if target_widget:
            self._placeholder = tk.Frame(
                self.container, bg=theme.accent_primary, height=3
            )
            # Pack before target
            self._placeholder.pack(before=target_widget, fill=tk.X, pady=2)
    
    def _end_drag(self, event):
        """End drag operation"""
        if not self._dragging:
            return
        
        theme = get_theme()
        
        # Reset visual
        if self._drag_item:
            self._drag_item.configure(bg=theme.bg_secondary)
        
        # Remove placeholder
        if self._placeholder:
            self._placeholder.destroy()
            self._placeholder = None
        
        # Find drop target
        y = event.y_root
        target_category = None
        insert_before = True
        
        for cat_name, widget in self._item_widgets.items():
            if cat_name == self._drag_category:
                continue
            
            widget_y = widget.winfo_rooty()
            widget_height = widget.winfo_height()
            
            if widget_y <= y <= widget_y + widget_height:
                target_category = cat_name
                # Determine if inserting before or after
                insert_before = y < widget_y + widget_height / 2
                break
        
        # Perform reorder
        if target_category and self._drag_category:
            self._reorder_category(self._drag_category, target_category, insert_before)
        
        self._dragging = False
        self._drag_item = None
        self._drag_category = None
    
    def _reorder_category(self, source: str, target: str, before: bool):
        """Reorder category in the manager"""
        # Get current order
        categories = self.category_manager.get_sorted_categories()
        
        if source not in categories or target not in categories:
            return
        
        # Remove source
        categories.remove(source)
        
        # Find target index
        target_idx = categories.index(target)
        
        # Insert at new position
        if before:
            categories.insert(target_idx, source)
        else:
            categories.insert(target_idx + 1, source)
        
        # Update sort orders
        for i, cat_name in enumerate(categories):
            if cat_name in self.category_manager.categories:
                self.category_manager.categories[cat_name].sort_order = i
        
        self.category_manager.save_categories()
        
        if self.on_reorder:
            self.on_reorder()


# =============================================================================
# Quick Add Dialog (Global Hotkey Support)
# =============================================================================
class QuickAddDialog(tk.Toplevel, ThemedWidget):
    """Dialog for adding a bookmark with optional custom favicon"""
    
    def __init__(self, parent, categories: List[str], 
                 initial_url: str = "",
                 on_add: Callable = None):
        super().__init__(parent)
        self.categories = categories
        self.on_add = on_add
        self.result = None
        self.custom_favicon_path = None
        
        theme = get_theme()
        
        self.title("Add Bookmark")
        self.geometry("500x320")
        self.configure(bg=theme.bg_primary)
        self.transient(parent)
        self.grab_set()
        
        # Make it appear centered and always on top
        self.attributes('-topmost', True)
        set_dark_title_bar(self)
        
        # URL field
        url_frame = tk.Frame(self, bg=theme.bg_primary)
        url_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
        
        tk.Label(
            url_frame, text="🔗", bg=theme.bg_primary,
            fg=theme.accent_primary, font=("Segoe UI", 14)
        ).pack(side=tk.LEFT)
        
        self.url_var = tk.StringVar(value=initial_url)
        self.url_entry = tk.Entry(
            url_frame, textvariable=self.url_var,
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            font=FONTS.body()
        )
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, ipady=8)
        
        # Title field (optional)
        title_frame = tk.Frame(self, bg=theme.bg_primary)
        title_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        tk.Label(
            title_frame, text="📝", bg=theme.bg_primary,
            fg=theme.text_muted, font=("Segoe UI", 14)
        ).pack(side=tk.LEFT)
        
        self.title_var = tk.StringVar()
        self.title_entry = tk.Entry(
            title_frame, textvariable=self.title_var,
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            font=FONTS.body()
        )
        self.title_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, ipady=6)
        self.title_entry.insert(0, "Title (optional, auto-fetched)")
        self.title_entry.bind("<FocusIn>", lambda e: self.title_entry.delete(0, tk.END) 
                              if self.title_entry.get().startswith("Title") else None)
        
        # Category dropdown
        cat_frame = tk.Frame(self, bg=theme.bg_primary)
        cat_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        tk.Label(
            cat_frame, text="📂", bg=theme.bg_primary,
            fg=theme.text_muted, font=("Segoe UI", 14)
        ).pack(side=tk.LEFT)
        
        self.category_var = tk.StringVar(value=categories[0] if categories else "Uncategorized")
        self.category_combo = ttk.Combobox(
            cat_frame, textvariable=self.category_var,
            values=categories, state="readonly"
        )
        self.category_combo.pack(side=tk.LEFT, padx=10)
        
        # Custom favicon field
        favicon_frame = tk.Frame(self, bg=theme.bg_primary)
        favicon_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        tk.Label(
            favicon_frame, text="🖼️", bg=theme.bg_primary,
            fg=theme.text_muted, font=("Segoe UI", 14)
        ).pack(side=tk.LEFT)
        
        tk.Label(
            favicon_frame, text="Custom Favicon (optional):", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.small()
        ).pack(side=tk.LEFT, padx=(5, 10))
        
        # Favicon URL/Path entry
        favicon_input_frame = tk.Frame(self, bg=theme.bg_primary)
        favicon_input_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        self.favicon_var = tk.StringVar()
        self.favicon_entry = tk.Entry(
            favicon_input_frame, textvariable=self.favicon_var,
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            font=FONTS.small(), width=40
        )
        self.favicon_entry.pack(side=tk.LEFT, ipady=5, padx=(35, 5))
        self.favicon_entry.insert(0, "URL or path to favicon...")
        self.favicon_entry.bind("<FocusIn>", lambda e: self.favicon_entry.delete(0, tk.END) 
                              if self.favicon_entry.get().startswith("URL") else None)
        
        # Browse button
        browse_btn = tk.Label(
            favicon_input_frame, text="📁 Browse", bg=theme.bg_secondary,
            fg=theme.text_primary, font=FONTS.small(), padx=8, pady=3, cursor="hand2"
        )
        browse_btn.pack(side=tk.LEFT, padx=5)
        browse_btn.bind("<Button-1>", lambda e: self._browse_favicon())
        
        # Favicon preview
        self.favicon_preview = tk.Label(
            favicon_input_frame, text="", bg=theme.bg_primary, width=3, height=1
        )
        self.favicon_preview.pack(side=tk.LEFT, padx=5)
        
        # Buttons
        btn_frame = tk.Frame(self, bg=theme.bg_primary)
        btn_frame.pack(fill=tk.X, padx=20, pady=(10, 20))
        
        ModernButton(
            btn_frame, text="Cancel", command=self.destroy
        ).pack(side=tk.RIGHT, padx=(10, 0))
        
        ModernButton(
            btn_frame, text="Add", command=self._add,
            style="primary", icon="➕"
        ).pack(side=tk.RIGHT)
        
        # Keyboard shortcuts
        self.bind("<Return>", lambda e: self._add())
        self.bind("<Escape>", lambda e: self.destroy())
        
        # Focus URL entry
        self.url_entry.focus_set()
        self.url_entry.select_range(0, tk.END)
        
        self.center_window()
    
    def _browse_favicon(self):
        """Browse for a local favicon image"""
        filepath = filedialog.askopenfilename(
            title="Select Favicon Image",
            filetypes=[
                ("Image files", "*.png *.ico *.jpg *.jpeg *.gif *.bmp"),
                ("All files", "*.*")
            ]
        )
        if filepath:
            self.favicon_var.set(filepath)
            self._preview_favicon(filepath)
    
    def _preview_favicon(self, path_or_url: str):
        """Show preview of favicon"""
        if not HAS_PIL:
            return
        
        try:
            if path_or_url.startswith(('http://', 'https://')):
                # Download from URL
                resp = requests.get(path_or_url, timeout=5)
                img = Image.open(BytesIO(resp.content))
            else:
                # Load from file
                img = Image.open(path_or_url)
            
            img = img.convert('RGBA')
            img = img.resize((24, 24), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.favicon_preview.configure(image=photo)
            self.favicon_preview.image = photo
        except Exception as e:
            print(f"Preview error: {e}")
    
    def _process_custom_favicon(self) -> Optional[str]:
        """Process custom favicon URL or path and save to cache"""
        favicon_input = self.favicon_var.get().strip()
        if not favicon_input or favicon_input.startswith("URL"):
            return None
        
        try:
            url = self.url_var.get().strip()
            domain = urlparse(url).netloc
            if not domain:
                return None
            
            # Load image from URL or file
            if favicon_input.startswith(('http://', 'https://')):
                resp = requests.get(favicon_input, timeout=10)
                img = Image.open(BytesIO(resp.content))
            else:
                img = Image.open(favicon_input)
            
            # Convert and resize
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # Save to cache
            hash_name = hashlib.md5(domain.encode()).hexdigest() + ".png"
            save_path = FAVICON_DIR / hash_name
            
            # Save multiple sizes
            for size in [16, 32, 64]:
                resized = img.resize((size, size), Image.Resampling.LANCZOS)
                suffix = f"_{size}" if size != 16 else ""
                size_path = FAVICON_DIR / (hashlib.md5(domain.encode()).hexdigest() + suffix + ".png")
                resized.save(size_path, "PNG")
            
            return str(save_path)
        except Exception as e:
            print(f"Error processing custom favicon: {e}")
            return None
    
    def _add(self):
        """Add the bookmark"""
        url = self.url_var.get().strip()
        if not url:
            return
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        title = self.title_var.get().strip()
        if title.startswith("Title"):
            title = ""
        
        # Process custom favicon if provided
        custom_favicon = self._process_custom_favicon()
        
        self.result = {
            "url": url,
            "title": title or url,
            "category": self.category_var.get(),
            "custom_favicon": custom_favicon
        }
        
        if self.on_add:
            self.on_add(self.result)
        
        self.destroy()
    
    def center_window(self):
        """Center the dialog on screen"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 3) - (height // 2)
        self.geometry(f'+{x}+{y}')




# =============================================================================
# Bulk Tag Editor Dialog
# =============================================================================
class BulkTagEditorDialog(tk.Toplevel, ThemedWidget):
    """Dialog for bulk editing tags on multiple bookmarks"""
    
    def __init__(self, parent, bookmarks: List[Bookmark], 
                 available_tags: List[str],
                 on_apply: Callable = None):
        super().__init__(parent)
        self.bookmarks = bookmarks
        self.available_tags = available_tags
        self.on_apply = on_apply
        self.result = None
        
        theme = get_theme()
        
        self.title("Bulk Tag Editor")
        self.geometry("500x500")
        self.configure(bg=theme.bg_primary)
        self.transient(parent)
        self.grab_set()
        
        set_dark_title_bar(self)
        
        # Header
        header = tk.Frame(self, bg=theme.bg_dark, height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(
            header, text=f"🏷️ Edit Tags for {len(bookmarks)} Bookmarks",
            bg=theme.bg_dark, fg=theme.text_primary,
            font=FONTS.header()
        ).pack(side=tk.LEFT, padx=20, pady=15)
        
        # Content
        content = tk.Frame(self, bg=theme.bg_primary)
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        # Current common tags
        tk.Label(
            content, text="Common Tags (present in all selected):",
            bg=theme.bg_primary, fg=theme.text_secondary,
            font=FONTS.body()
        ).pack(anchor="w")
        
        self.common_tags = self._get_common_tags()
        common_frame = tk.Frame(content, bg=theme.bg_primary)
        common_frame.pack(fill=tk.X, pady=(5, 15))
        
        if self.common_tags:
            for tag in self.common_tags:
                TagWidget(common_frame, tag, show_remove=False).pack(side=tk.LEFT, padx=2)
        else:
            tk.Label(
                common_frame, text="No common tags",
                bg=theme.bg_primary, fg=theme.text_muted,
                font=("Segoe UI", 9, "italic")
            ).pack(side=tk.LEFT)
        
        # Add tags section
        tk.Label(
            content, text="Add Tags:", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        ).pack(anchor="w", pady=(10, 5))
        
        self.add_tag_editor = TagEditor(content, tags=[], available_tags=available_tags)
        self.add_tag_editor.pack(fill=tk.X)
        
        # Remove tags section
        tk.Label(
            content, text="Remove Tags:", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        ).pack(anchor="w", pady=(15, 5))
        
        # Checkboxes for tags that exist on any bookmark
        self.all_tags = self._get_all_tags()
        self.remove_vars: Dict[str, tk.BooleanVar] = {}
        
        remove_frame = tk.Frame(content, bg=theme.bg_secondary)
        remove_frame.pack(fill=tk.X, pady=5)
        
        row_frame = tk.Frame(remove_frame, bg=theme.bg_secondary)
        row_frame.pack(fill=tk.X, padx=10, pady=10)
        col = 0
        
        for tag in sorted(self.all_tags):
            var = tk.BooleanVar(value=False)
            self.remove_vars[tag] = var
            
            cb = ttk.Checkbutton(
                row_frame, text=f"#{tag}", variable=var
            )
            cb.grid(row=col // 3, column=col % 3, sticky="w", padx=5, pady=2)
            col += 1
        
        # Replace all option
        self.replace_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            content, text="Replace all existing tags (instead of add/remove)",
            variable=self.replace_var
        ).pack(anchor="w", pady=(15, 10))
        
        # Buttons
        btn_frame = tk.Frame(self, bg=theme.bg_primary)
        btn_frame.pack(fill=tk.X, padx=20, pady=15)
        
        ModernButton(
            btn_frame, text="Cancel", command=self.destroy
        ).pack(side=tk.RIGHT, padx=(10, 0))
        
        ModernButton(
            btn_frame, text="Apply", command=self._apply,
            style="primary", icon="✓"
        ).pack(side=tk.RIGHT)
        
        self.center_window()
    
    def _get_common_tags(self) -> List[str]:
        """Get tags that are present in all selected bookmarks"""
        if not self.bookmarks:
            return []
        
        common = set(self.bookmarks[0].tags)
        for bm in self.bookmarks[1:]:
            common &= set(bm.tags)
        
        return sorted(common)
    
    def _get_all_tags(self) -> Set[str]:
        """Get all unique tags across selected bookmarks"""
        all_tags = set()
        for bm in self.bookmarks:
            all_tags.update(bm.tags)
        return all_tags
    
    def _apply(self):
        """Apply tag changes"""
        add_tags = self.add_tag_editor.get_tags()
        remove_tags = [tag for tag, var in self.remove_vars.items() if var.get()]
        replace_all = self.replace_var.get()
        
        self.result = {
            "add": add_tags,
            "remove": remove_tags,
            "replace_all": replace_all
        }
        
        if self.on_apply:
            self.on_apply(self.result)
        
        self.destroy()
    
    def center_window(self):
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')


# =============================================================================
# Smart Tags (Auto-Tag Rules)
# =============================================================================
@dataclass
class SmartTagRule:
    """Rule for automatic tagging"""
    name: str
    tag: str
    conditions: List[Dict[str, str]]  # [{"field": "domain", "operator": "contains", "value": "github"}]
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def matches(self, bookmark: Bookmark) -> bool:
        """Check if bookmark matches all conditions"""
        for condition in self.conditions:
            if not self._check_condition(bookmark, condition):
                return False
        return True
    
    def _check_condition(self, bookmark: Bookmark, condition: Dict) -> bool:
        """Check a single condition"""
        field = condition.get("field", "")
        operator = condition.get("operator", "")
        value = condition.get("value", "").lower()
        
        # Get field value
        if field == "domain":
            field_value = bookmark.domain.lower()
        elif field == "title":
            field_value = bookmark.title.lower()
        elif field == "url":
            field_value = bookmark.url.lower()
        elif field == "category":
            field_value = bookmark.category.lower()
        elif field == "notes":
            field_value = (bookmark.notes or "").lower()
        else:
            return False
        
        # Apply operator
        if operator == "contains":
            return value in field_value
        elif operator == "starts_with":
            return field_value.startswith(value)
        elif operator == "ends_with":
            return field_value.endswith(value)
        elif operator == "equals":
            return field_value == value
        elif operator == "regex":
            try:
                return bool(re.search(value, field_value))
            except Exception:
                return False
        
        return False


class SmartTagManager:
    """Manages smart tagging rules"""
    
    RULES_FILE = DATA_DIR / "smart_tag_rules.json"
    
    def __init__(self):
        self.rules: List[SmartTagRule] = []
        self._load_rules()
    
    def _load_rules(self):
        """Load rules from file"""
        if self.RULES_FILE.exists():
            try:
                with open(self.RULES_FILE, 'r') as f:
                    data = json.load(f)
                    self.rules = [SmartTagRule(**r) for r in data]
            except Exception:
                self.rules = []
        else:
            # Default rules
            self.rules = [
                SmartTagRule(
                    name="GitHub Repos",
                    tag="github",
                    conditions=[{"field": "domain", "operator": "contains", "value": "github.com"}]
                ),
                SmartTagRule(
                    name="Documentation",
                    tag="docs",
                    conditions=[{"field": "url", "operator": "contains", "value": "/docs"}]
                ),
                SmartTagRule(
                    name="YouTube Videos",
                    tag="video",
                    conditions=[{"field": "domain", "operator": "contains", "value": "youtube.com"}]
                ),
                SmartTagRule(
                    name="Stack Overflow",
                    tag="stackoverflow",
                    conditions=[{"field": "domain", "operator": "contains", "value": "stackoverflow.com"}]
                ),
            ]
            self._save_rules()
    
    def _save_rules(self):
        """Save rules to file"""
        DATA_DIR.mkdir(exist_ok=True)
        with open(self.RULES_FILE, 'w') as f:
            json.dump([asdict(r) for r in self.rules], f, indent=2)
    
    def add_rule(self, rule: SmartTagRule):
        """Add a new rule"""
        self.rules.append(rule)
        self._save_rules()
    
    def remove_rule(self, name: str):
        """Remove a rule by name"""
        self.rules = [r for r in self.rules if r.name != name]
        self._save_rules()
    
    def apply_rules(self, bookmark: Bookmark) -> List[str]:
        """Apply all enabled rules to a bookmark and return matched tags"""
        tags = []
        for rule in self.rules:
            if rule.enabled and rule.matches(bookmark):
                if rule.tag not in bookmark.tags:
                    tags.append(rule.tag)
        return tags
    
    def apply_to_all(self, bookmarks: List[Bookmark]) -> int:
        """Apply rules to all bookmarks, return count of tags added"""
        count = 0
        for bm in bookmarks:
            new_tags = self.apply_rules(bm)
            if new_tags:
                bm.tags.extend(new_tags)
                count += len(new_tags)
        return count


# =============================================================================
# Collections/Folders (Named Groups)
# =============================================================================
@dataclass
class Collection:
    """A named collection of bookmarks"""
    id: str
    name: str
    description: str = ""
    icon: str = "📁"
    color: str = "#58a6ff"
    bookmark_ids: List[int] = field(default_factory=list)
    is_smart: bool = False
    smart_query: str = ""  # Search query for smart collections
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    @property
    def count(self) -> int:
        return len(self.bookmark_ids)


class CollectionManager:
    """Manages bookmark collections"""
    
    COLLECTIONS_FILE = DATA_DIR / "collections.json"
    
    def __init__(self, bookmark_manager: BookmarkManager = None):
        self.bookmark_manager = bookmark_manager
        self.collections: Dict[str, Collection] = {}
        self._load_collections()
    
    def _load_collections(self):
        """Load collections from file"""
        if self.COLLECTIONS_FILE.exists():
            try:
                with open(self.COLLECTIONS_FILE, 'r') as f:
                    data = json.load(f)
                    for coll_data in data:
                        coll = Collection(**coll_data)
                        self.collections[coll.id] = coll
            except Exception:
                pass
    
    def _save_collections(self):
        """Save collections to file"""
        DATA_DIR.mkdir(exist_ok=True)
        data = [asdict(c) for c in self.collections.values()]
        with open(self.COLLECTIONS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    
    def create_collection(self, name: str, description: str = "", 
                         icon: str = "📁", color: str = "#58a6ff",
                         is_smart: bool = False, smart_query: str = "") -> Collection:
        """Create a new collection"""
        coll_id = f"coll_{int(datetime.now().timestamp() * 1000)}"
        
        collection = Collection(
            id=coll_id,
            name=name,
            description=description,
            icon=icon,
            color=color,
            is_smart=is_smart,
            smart_query=smart_query
        )
        
        self.collections[coll_id] = collection
        self._save_collections()
        return collection
    
    def delete_collection(self, coll_id: str):
        """Delete a collection"""
        if coll_id in self.collections:
            del self.collections[coll_id]
            self._save_collections()
    
    def add_to_collection(self, coll_id: str, bookmark_ids: List[int]):
        """Add bookmarks to a collection"""
        if coll_id in self.collections:
            coll = self.collections[coll_id]
            for bm_id in bookmark_ids:
                if bm_id not in coll.bookmark_ids:
                    coll.bookmark_ids.append(bm_id)
            coll.updated_at = datetime.now().isoformat()
            self._save_collections()
    
    def remove_from_collection(self, coll_id: str, bookmark_ids: List[int]):
        """Remove bookmarks from a collection"""
        if coll_id in self.collections:
            coll = self.collections[coll_id]
            coll.bookmark_ids = [bid for bid in coll.bookmark_ids if bid not in bookmark_ids]
            coll.updated_at = datetime.now().isoformat()
            self._save_collections()
    
    def get_collection_bookmarks(self, coll_id: str) -> List[Bookmark]:
        """Get all bookmarks in a collection"""
        if coll_id not in self.collections:
            return []
        
        coll = self.collections[coll_id]
        
        if coll.is_smart and self.bookmark_manager:
            # Smart collection - run query
            return self.bookmark_manager.search_bookmarks(coll.smart_query)
        else:
            # Static collection - return by IDs
            if self.bookmark_manager:
                return [
                    self.bookmark_manager.get_bookmark(bm_id)
                    for bm_id in coll.bookmark_ids
                    if self.bookmark_manager.get_bookmark(bm_id)
                ]
        return []
    
    def get_all_collections(self) -> List[Collection]:
        """Get all collections sorted by name"""
        return sorted(self.collections.values(), key=lambda c: c.name.lower())


# =============================================================================
# Frequently Used View (Visit Tracking)
# =============================================================================
class FrequentlyUsedManager:
    """Tracks and retrieves frequently used bookmarks"""
    
    def __init__(self, bookmark_manager: BookmarkManager):
        self.bookmark_manager = bookmark_manager
    
    def get_frequently_used(self, limit: int = 20, days: int = 30) -> List[Bookmark]:
        """Get most frequently visited bookmarks in time period"""
        cutoff = datetime.now() - timedelta(days=days)
        
        bookmarks_with_visits = []
        
        for bm in self.bookmark_manager.bookmarks.values():
            if bm.visit_count > 0:
                # Check if visited recently
                if bm.last_visited:
                    try:
                        last_visit = datetime.fromisoformat(bm.last_visited.replace('Z', '+00:00'))
                        if last_visit.replace(tzinfo=None) >= cutoff:
                            bookmarks_with_visits.append(bm)
                    except Exception:
                        bookmarks_with_visits.append(bm)
                else:
                    bookmarks_with_visits.append(bm)
        
        # Sort by visit count
        sorted_bms = sorted(bookmarks_with_visits, key=lambda b: b.visit_count, reverse=True)
        return sorted_bms[:limit]
    
    def get_trending(self, limit: int = 10) -> List[Bookmark]:
        """Get bookmarks with increasing visit frequency (trending)"""
        # This is a simplified version - could track daily visits for better trending
        recent = self.get_frequently_used(limit * 2, days=7)
        older = self.get_frequently_used(limit * 2, days=30)
        
        # Find bookmarks that are more popular recently
        recent_ids = {bm.id: i for i, bm in enumerate(recent)}
        older_ids = {bm.id: i for i, bm in enumerate(older)}
        
        trending = []
        for bm in recent:
            if bm.id in older_ids:
                # Higher rank in recent = trending
                rank_change = older_ids[bm.id] - recent_ids[bm.id]
                if rank_change > 0:
                    trending.append((bm, rank_change))
        
        trending.sort(key=lambda x: x[1], reverse=True)
        return [bm for bm, _ in trending[:limit]]


# =============================================================================
# Settings Profiles
# =============================================================================
@dataclass
class SettingsProfile:
    """A saved settings configuration"""
    name: str
    description: str = ""
    settings: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Settings that can be saved
    # - theme
    # - display_density
    # - default_category
    # - ai_provider
    # - view_mode
    # - sidebar_collapsed
    # - smart_filters


class SettingsProfileManager:
    """Manages settings profiles"""
    
    PROFILES_FILE = DATA_DIR / "settings_profiles.json"
    
    def __init__(self):
        self.profiles: Dict[str, SettingsProfile] = {}
        self._load_profiles()
    
    def _load_profiles(self):
        """Load profiles from file"""
        if self.PROFILES_FILE.exists():
            try:
                with open(self.PROFILES_FILE, 'r') as f:
                    data = json.load(f)
                    for name, profile_data in data.items():
                        self.profiles[name] = SettingsProfile(**profile_data)
            except Exception:
                pass
    
    def _save_profiles(self):
        """Save profiles to file"""
        DATA_DIR.mkdir(exist_ok=True)
        data = {name: asdict(p) for name, p in self.profiles.items()}
        with open(self.PROFILES_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    
    def save_profile(self, name: str, settings: Dict[str, Any], 
                     description: str = "") -> SettingsProfile:
        """Save current settings as a profile"""
        profile = SettingsProfile(
            name=name,
            description=description,
            settings=settings
        )
        self.profiles[name] = profile
        self._save_profiles()
        return profile
    
    def load_profile(self, name: str) -> Optional[Dict[str, Any]]:
        """Load a profile's settings"""
        if name in self.profiles:
            return self.profiles[name].settings.copy()
        return None
    
    def delete_profile(self, name: str):
        """Delete a profile"""
        if name in self.profiles:
            del self.profiles[name]
            self._save_profiles()
    
    def export_profile(self, name: str, filepath: str):
        """Export a profile to file"""
        if name in self.profiles:
            with open(filepath, 'w') as f:
                json.dump(asdict(self.profiles[name]), f, indent=2)
    
    def import_profile(self, filepath: str) -> Optional[SettingsProfile]:
        """Import a profile from file"""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                profile = SettingsProfile(**data)
                self.profiles[profile.name] = profile
                self._save_profiles()
                return profile
        except Exception:
            return None
    
    def get_all_profiles(self) -> List[SettingsProfile]:
        """Get all profiles"""
        return list(self.profiles.values())


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
        if not search_term:
            return html_module.escape(text) if 'html_module' in dir() else text
        
        pattern = re.compile(re.escape(search_term), re.IGNORECASE)
        
        def replace(match):
            return f'<mark style="background:{self.highlight_color};color:{self.text_color}">{match.group(0)}</mark>'
        
        return pattern.sub(replace, text)
    
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




# =============================================================================
# Browser Profile Import (Chrome, Firefox, Edge)
# =============================================================================
class BrowserProfileImporter:
    """Import bookmarks directly from browser profiles"""
    
    # Browser paths by OS
    BROWSER_PATHS = {
        "chrome": {
            "windows": Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data",
            "darwin": Path.home() / "Library/Application Support/Google/Chrome",
            "linux": Path.home() / ".config/google-chrome",
        },
        "firefox": {
            "windows": Path(os.environ.get("APPDATA", "")) / "Mozilla/Firefox/Profiles",
            "darwin": Path.home() / "Library/Application Support/Firefox/Profiles",
            "linux": Path.home() / ".mozilla/firefox",
        },
        "edge": {
            "windows": Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Edge/User Data",
            "darwin": Path.home() / "Library/Application Support/Microsoft Edge",
            "linux": Path.home() / ".config/microsoft-edge",
        },
        "brave": {
            "windows": Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware/Brave-Browser/User Data",
            "darwin": Path.home() / "Library/Application Support/BraveSoftware/Brave-Browser",
            "linux": Path.home() / ".config/BraveSoftware/Brave-Browser",
        }
    }
    
    def __init__(self):
        self.os_name = "windows" if IS_WINDOWS else ("darwin" if IS_MAC else "linux")
    
    def get_available_browsers(self) -> List[str]:
        """Get list of browsers with detected profiles"""
        available = []
        for browser, paths in self.BROWSER_PATHS.items():
            browser_path = paths.get(self.os_name)
            if browser_path and browser_path.exists():
                available.append(browser)
        return available
    
    def get_profiles(self, browser: str) -> List[Tuple[str, Path]]:
        """Get available profiles for a browser"""
        browser_path = self.BROWSER_PATHS.get(browser, {}).get(self.os_name)
        if not browser_path or not browser_path.exists():
            return []
        
        profiles = []
        
        if browser == "firefox":
            # Firefox uses profiles.ini
            for profile_dir in browser_path.iterdir():
                if profile_dir.is_dir():
                    places_db = profile_dir / "places.sqlite"
                    if places_db.exists():
                        profiles.append((profile_dir.name, profile_dir))
        else:
            # Chrome-based browsers
            # Default profile
            default = browser_path / "Default"
            if default.exists():
                profiles.append(("Default", default))
            
            # Other profiles
            for item in browser_path.iterdir():
                if item.is_dir() and item.name.startswith("Profile "):
                    profiles.append((item.name, item))
        
        return profiles
    
    def import_from_chrome(self, profile_path: Path) -> List[Bookmark]:
        """Import bookmarks from Chrome/Edge/Brave"""
        bookmarks_file = profile_path / "Bookmarks"
        if not bookmarks_file.exists():
            return []
        
        try:
            with open(bookmarks_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            bookmarks = []
            
            def process_node(node, path=""):
                if node.get("type") == "url":
                    bm = Bookmark(
                        id=None,
                        url=node.get("url", ""),
                        title=node.get("name", ""),
                        category=path or "Imported"
                    )
                    
                    # Parse date
                    date_added = node.get("date_added", "0")
                    try:
                        # Chrome uses Windows FILETIME (100ns since 1601)
                        timestamp = (int(date_added) - 11644473600000000) / 1000000
                        bm.created_at = datetime.fromtimestamp(timestamp).isoformat()
                    except Exception:
                        pass
                    
                    bookmarks.append(bm)
                
                elif node.get("type") == "folder":
                    folder_name = node.get("name", "")
                    new_path = f"{path}/{folder_name}" if path else folder_name
                    
                    for child in node.get("children", []):
                        process_node(child, new_path)
            
            # Process bookmark bar and other folders
            roots = data.get("roots", {})
            for root_name, root_node in roots.items():
                if isinstance(root_node, dict):
                    process_node(root_node, "")
            
            return bookmarks
        except Exception as e:
            print(f"Error importing Chrome bookmarks: {e}")
            return []
    
    def import_from_firefox(self, profile_path: Path) -> List[Bookmark]:
        """Import bookmarks from Firefox"""
        places_db = profile_path / "places.sqlite"
        if not places_db.exists():
            return []
        
        import sqlite3
        
        # Copy database to avoid lock issues
        temp_db = DATA_DIR / "temp_places.sqlite"
        shutil.copy2(places_db, temp_db)
        
        bookmarks = []
        
        try:
            conn = sqlite3.connect(str(temp_db))
            cursor = conn.cursor()
            
            # Query bookmarks with folder path
            query = """
            SELECT 
                b.title,
                p.url,
                b.dateAdded,
                (SELECT GROUP_CONCAT(parent_b.title, '/')
                 FROM moz_bookmarks parent_b
                 WHERE parent_b.id IN (
                     WITH RECURSIVE ancestors(id, parent) AS (
                         SELECT id, parent FROM moz_bookmarks WHERE id = b.parent
                         UNION ALL
                         SELECT mb.id, mb.parent FROM moz_bookmarks mb
                         JOIN ancestors a ON mb.id = a.parent
                     )
                     SELECT id FROM ancestors
                 ) AND parent_b.type = 2
                ) as folder_path
            FROM moz_bookmarks b
            JOIN moz_places p ON b.fk = p.id
            WHERE b.type = 1 AND p.url NOT LIKE 'place:%'
            """
            
            cursor.execute(query)
            
            for row in cursor.fetchall():
                title, url, date_added, folder_path = row
                
                bm = Bookmark(
                    id=None,
                    url=url or "",
                    title=title or url or "",
                    category=folder_path.split('/')[-1] if folder_path else "Imported"
                )
                
                if date_added:
                    try:
                        # Firefox uses microseconds since epoch
                        bm.created_at = datetime.fromtimestamp(date_added / 1000000).isoformat()
                    except Exception:
                        pass
                
                bookmarks.append(bm)
            
            conn.close()
        except Exception as e:
            print(f"Error importing Firefox bookmarks: {e}")
        finally:
            if temp_db.exists():
                temp_db.unlink()
        
        return bookmarks


# =============================================================================
# URL Utilities (Redirect Resolver, HTTPS Upgrade, Affiliate Detection)
# =============================================================================
class URLUtilities:
    """Various URL manipulation and analysis utilities"""
    
    # Known URL shorteners
    SHORTENERS = [
        'bit.ly', 'tinyurl.com', 't.co', 'goo.gl', 'ow.ly', 'is.gd',
        'buff.ly', 'j.mp', 'amzn.to', 'youtu.be', 'rb.gy', 'cutt.ly',
        'short.io', 'rebrand.ly', 'bl.ink', 'snip.ly'
    ]
    
    # Affiliate parameters
    AFFILIATE_PARAMS = [
        'ref', 'affiliate', 'aff', 'partner', 'tag', 'camp', 'src',
        'via', 'referral', 'ref_', 'aff_', 'associate', 'linkId'
    ]
    
    # Known affiliate domains
    AFFILIATE_DOMAINS = [
        'amzn.to', 'amazon.com/gp/product', 'amazon.com/dp',
        'shareasale.com', 'commission-junction.com', 'rakuten.com',
        'awin1.com', 'pepperjam.com', 'jdoqocy.com', 'tkqlhce.com'
    ]
    
    @staticmethod
    def resolve_redirect(url: str, max_redirects: int = 5) -> Tuple[str, int]:
        """
        Resolve URL redirects and return final URL.
        Returns (final_url, redirect_count)
        """
        redirect_count = 0
        current_url = url
        
        for _ in range(max_redirects):
            try:
                response = requests.head(
                    current_url,
                    allow_redirects=False,
                    timeout=5,
                    headers={'User-Agent': 'Mozilla/5.0'}
                )
                
                if response.status_code in (301, 302, 303, 307, 308):
                    next_url = response.headers.get('Location', '')
                    if next_url:
                        # Handle relative URLs
                        if next_url.startswith('/'):
                            parsed = urllib.parse.urlparse(current_url)
                            next_url = f"{parsed.scheme}://{parsed.netloc}{next_url}"
                        
                        current_url = next_url
                        redirect_count += 1
                        continue
                
                break
            except Exception:
                break
        
        return current_url, redirect_count
    
    @staticmethod
    def is_shortened_url(url: str) -> bool:
        """Check if URL is from a known shortener"""
        try:
            domain = urllib.parse.urlparse(url).netloc.lower()
            return any(shortener in domain for shortener in URLUtilities.SHORTENERS)
        except Exception:
            return False
    
    @staticmethod
    def upgrade_to_https(url: str) -> str:
        """Upgrade HTTP URL to HTTPS"""
        if url.startswith('http://'):
            return 'https://' + url[7:]
        return url
    
    @staticmethod
    def check_https_available(url: str) -> bool:
        """Check if HTTPS version of URL is available"""
        if url.startswith('https://'):
            return True
        
        https_url = URLUtilities.upgrade_to_https(url)
        
        try:
            response = requests.head(https_url, timeout=5, allow_redirects=True)
            return response.status_code < 400
        except Exception:
            return False
    
    @staticmethod
    def detect_affiliate_link(url: str) -> Tuple[bool, List[str]]:
        """
        Detect if URL is an affiliate link.
        Returns (is_affiliate, list_of_reasons)
        """
        reasons = []
        
        try:
            parsed = urllib.parse.urlparse(url)
            query_params = urllib.parse.parse_qs(parsed.query)
            
            # Check for affiliate parameters
            for param in URLUtilities.AFFILIATE_PARAMS:
                if param in query_params or param.lower() in [p.lower() for p in query_params]:
                    reasons.append(f"Contains '{param}' parameter")
            
            # Check for affiliate domains
            domain = parsed.netloc.lower()
            for aff_domain in URLUtilities.AFFILIATE_DOMAINS:
                if aff_domain in url.lower():
                    reasons.append(f"Uses affiliate domain: {aff_domain}")
            
            # Check for Amazon associate tag
            if 'amazon' in domain and 'tag' in query_params:
                reasons.append("Amazon Associate link")
        
        except Exception:
            pass
        
        return len(reasons) > 0, reasons
    
    @staticmethod
    def clean_affiliate_link(url: str) -> str:
        """Remove affiliate parameters from URL"""
        try:
            parsed = urllib.parse.urlparse(url)
            query_params = urllib.parse.parse_qs(parsed.query)
            
            # Remove affiliate parameters
            clean_params = {
                k: v for k, v in query_params.items()
                if k.lower() not in [p.lower() for p in URLUtilities.AFFILIATE_PARAMS]
            }
            
            # Rebuild URL
            clean_query = urllib.parse.urlencode(clean_params, doseq=True)
            return urllib.parse.urlunparse((
                parsed.scheme, parsed.netloc, parsed.path,
                parsed.params, clean_query, ''
            ))
        except Exception:
            return url
    
    @staticmethod
    def get_canonical_url(url: str) -> Optional[str]:
        """Try to get canonical URL from page"""
        try:
            response = requests.get(
                url, timeout=10,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            
            if response.status_code == 200:
                # Look for canonical link
                match = re.search(
                    r'<link[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']',
                    response.text, re.IGNORECASE
                )
                if match:
                    return match.group(1)
                
                # Try alternate format
                match = re.search(
                    r'<link[^>]*href=["\']([^"\']+)["\'][^>]*rel=["\']canonical["\']',
                    response.text, re.IGNORECASE
                )
                if match:
                    return match.group(1)
        except Exception:
            pass
        
        return None


# =============================================================================
# Timeline View
# =============================================================================
class TimelineView(tk.Frame, ThemedWidget):
    """Chronological timeline view of bookmarks"""
    
    def __init__(self, parent, bookmarks: List[Bookmark],
                 on_bookmark_click: Callable = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_primary)
        
        self.bookmarks = bookmarks
        self.on_bookmark_click = on_bookmark_click
        
        # Group bookmarks by date
        self.grouped = self._group_by_date()
        
        # Create scrollable container
        canvas = tk.Canvas(self, bg=theme.bg_primary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = tk.Frame(canvas, bg=theme.bg_primary)
        
        self.inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        canvas.bind("<MouseWheel>", 
            lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        
        self._render_timeline()
    
    def _group_by_date(self) -> Dict[str, List[Bookmark]]:
        """Group bookmarks by date"""
        grouped: Dict[str, List[Bookmark]] = {}
        
        for bm in self.bookmarks:
            try:
                created = datetime.fromisoformat(bm.created_at.replace('Z', '+00:00'))
                date_key = created.strftime("%Y-%m-%d")
            except Exception:
                date_key = "Unknown"
            
            if date_key not in grouped:
                grouped[date_key] = []
            grouped[date_key].append(bm)
        
        # Sort by date descending
        return dict(sorted(grouped.items(), key=lambda x: x[0], reverse=True))
    
    def _render_timeline(self):
        """Render the timeline"""
        theme = get_theme()
        
        for date_str, bms in self.grouped.items():
            # Date header
            date_frame = tk.Frame(self.inner, bg=theme.bg_primary)
            date_frame.pack(fill=tk.X, pady=(20, 10))
            
            # Timeline line
            tk.Frame(
                date_frame, bg=theme.accent_primary, width=3
            ).pack(side=tk.LEFT, fill=tk.Y, padx=(20, 0))
            
            # Date circle
            circle = tk.Frame(
                date_frame, bg=theme.accent_primary,
                width=12, height=12
            )
            circle.pack(side=tk.LEFT, padx=(0, 15))
            
            # Format date nicely
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                display_date = date_obj.strftime("%B %d, %Y")
                
                # Add relative time
                days_ago = (datetime.now() - date_obj).days
                if days_ago == 0:
                    relative = "Today"
                elif days_ago == 1:
                    relative = "Yesterday"
                elif days_ago < 7:
                    relative = f"{days_ago} days ago"
                elif days_ago < 30:
                    relative = f"{days_ago // 7} weeks ago"
                else:
                    relative = f"{days_ago // 30} months ago"
                
                display_date = f"{display_date} ({relative})"
            except Exception:
                display_date = date_str
            
            tk.Label(
                date_frame, text=display_date, bg=theme.bg_primary,
                fg=theme.text_primary, font=("Segoe UI", 11, "bold")
            ).pack(side=tk.LEFT)
            
            tk.Label(
                date_frame, text=f"{len(bms)} bookmarks", bg=theme.bg_primary,
                fg=theme.text_muted, font=FONTS.body()
            ).pack(side=tk.RIGHT, padx=20)
            
            # Bookmarks for this date
            for bm in bms:
                self._render_bookmark_item(bm)
    
    def _render_bookmark_item(self, bookmark: Bookmark):
        """Render a single bookmark in the timeline"""
        theme = get_theme()
        
        item_frame = tk.Frame(self.inner, bg=theme.bg_primary)
        item_frame.pack(fill=tk.X, padx=(35, 20), pady=3)
        
        # Timeline connector line
        connector = tk.Frame(item_frame, bg=theme.border, width=1, height=40)
        connector.pack(side=tk.LEFT, padx=(7, 15))
        
        # Content card
        card = tk.Frame(item_frame, bg=theme.bg_secondary, cursor="hand2")
        card.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=2)
        card.configure(highlightbackground=theme.border, highlightthickness=1)
        
        # Inner content
        inner = tk.Frame(card, bg=theme.bg_secondary)
        inner.pack(fill=tk.X, padx=12, pady=8)
        
        # Title with status indicators
        title = bookmark.title[:50] + "..." if len(bookmark.title) > 53 else bookmark.title
        if bookmark.is_pinned:
            title = "📌 " + title
        
        tk.Label(
            inner, text=title, bg=theme.bg_secondary,
            fg=theme.text_primary, font=FONTS.body(),
            anchor="w"
        ).pack(fill=tk.X)
        
        # Domain and category
        meta = f"{bookmark.domain} • {bookmark.category}"
        tk.Label(
            inner, text=meta, bg=theme.bg_secondary,
            fg=theme.text_muted, font=FONTS.small(),
            anchor="w"
        ).pack(fill=tk.X)
        
        # Click handler
        def on_click(e, bm=bookmark):
            if self.on_bookmark_click:
                self.on_bookmark_click(bm)
        
        card.bind("<Button-1>", on_click)
        inner.bind("<Button-1>", on_click)
        for child in inner.winfo_children():
            child.bind("<Button-1>", on_click)
        
        # Hover effects
        def on_enter(e):
            card.configure(bg=theme.bg_hover)
            inner.configure(bg=theme.bg_hover)
            for child in inner.winfo_children():
                child.configure(bg=theme.bg_hover)
        
        def on_leave(e):
            card.configure(bg=theme.bg_secondary)
            inner.configure(bg=theme.bg_secondary)
            for child in inner.winfo_children():
                child.configure(bg=theme.bg_secondary)
        
        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)


# =============================================================================
# Split View with Details Panel
# =============================================================================
class BookmarkDetailPanel(tk.Frame, ThemedWidget):
    """
        Represents a single bookmark with all metadata.
        
        Attributes:
            id: Unique integer identifier
            url: Bookmark URL
            title: Display title
            category: Category name
            tags: List of tag names
            ai_tags: List of AI-suggested tags
            description: Optional description
            favicon_url: URL to favicon image
            created_at: ISO timestamp of creation
            updated_at: ISO timestamp of last update
            visited_at: ISO timestamp of last visit
            visit_count: Number of times visited
            is_valid: Whether URL validation passed
            is_pinned: Whether bookmark is pinned
            ai_category: AI-suggested category
            ai_summary: AI-generated summary
            notes: User notes
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
            matches_search(query): Check if bookmark matches search
        """
    
    def __init__(self, parent, on_edit: Callable = None, 
                 on_open: Callable = None,
                 on_delete: Callable = None):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_secondary, width=350)
        
        self.on_edit = on_edit
        self.on_open = on_open
        self.on_delete = on_delete
        self.current_bookmark: Optional[Bookmark] = None
        
        self.pack_propagate(False)
        
        # Header
        self.header = tk.Frame(self, bg=theme.bg_tertiary)
        self.header.pack(fill=tk.X)
        
        tk.Label(
            self.header, text="Bookmark Details", bg=theme.bg_tertiary,
            fg=theme.text_primary, font=("Segoe UI", 11, "bold"),
            padx=15, pady=12
        ).pack(side=tk.LEFT)
        
        # Close button
        close_btn = tk.Label(
            self.header, text="✕", bg=theme.bg_tertiary,
            fg=theme.text_muted, font=("Segoe UI", 12),
            cursor="hand2", padx=15
        )
        close_btn.pack(side=tk.RIGHT)
        close_btn.bind("<Button-1>", lambda e: self.pack_forget())
        
        # Content
        self.content = tk.Frame(self, bg=theme.bg_secondary)
        self.content.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # Placeholder
        self.placeholder = tk.Label(
            self.content, text="Select a bookmark to view details",
            bg=theme.bg_secondary, fg=theme.text_muted,
            font=FONTS.body()
        )
        self.placeholder.pack(expand=True)
    
    def show_bookmark(self, bookmark: Bookmark):
        """Display bookmark details"""
        theme = get_theme()
        self.current_bookmark = bookmark
        
        # Clear content
        for widget in self.content.winfo_children():
            widget.destroy()
        
        # Favicon / Icon
        icon_frame = tk.Frame(self.content, bg=theme.bg_secondary)
        icon_frame.pack(fill=tk.X, pady=(0, 15))
        
        icon_label = tk.Label(
            icon_frame, text=bookmark.domain[0].upper(),
            bg=theme.accent_primary, fg="#ffffff",
            font=("Segoe UI", 24, "bold"),
            width=3, height=1
        )
        icon_label.pack(side=tk.LEFT)
        
        # Title
        title_frame = tk.Frame(icon_frame, bg=theme.bg_secondary)
        title_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=15)
        
        tk.Label(
            title_frame, text=bookmark.title,
            bg=theme.bg_secondary, fg=theme.text_primary,
            font=FONTS.header(),
            wraplength=200, justify=tk.LEFT, anchor="w"
        ).pack(fill=tk.X)
        
        tk.Label(
            title_frame, text=bookmark.domain,
            bg=theme.bg_secondary, fg=theme.text_muted,
            font=FONTS.body()
        ).pack(fill=tk.X, anchor="w")
        
        # Actions
        actions = tk.Frame(self.content, bg=theme.bg_secondary)
        actions.pack(fill=tk.X, pady=15)
        
        ModernButton(
            actions, text="Open", icon="🔗",
            command=lambda: self._open_bookmark()
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ModernButton(
            actions, text="Edit", icon="✏️",
            command=lambda: self._edit_bookmark()
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ModernButton(
            actions, text="Delete", icon="🗑️", style="danger",
            command=lambda: self._delete_bookmark()
        ).pack(side=tk.LEFT)
        
        # Separator
        tk.Frame(self.content, bg=theme.border, height=1).pack(fill=tk.X, pady=15)
        
        # Details
        self._add_detail("URL", bookmark.url, is_link=True)
        self._add_detail("Category", f"{get_category_icon(bookmark.category)} {bookmark.category}")
        
        if bookmark.tags:
            tags_text = ", ".join(f"#{t}" for t in bookmark.tags)
            self._add_detail("Tags", tags_text)
        
        self._add_detail("Added", self._format_date(bookmark.created_at))
        
        if bookmark.last_visited:
            self._add_detail("Last Visited", self._format_date(bookmark.last_visited))
        
        self._add_detail("Visits", str(bookmark.visit_count))
        
        # Status indicators
        status_parts = []
        if bookmark.is_pinned:
            status_parts.append("📌 Pinned")
        if bookmark.is_archived:
            status_parts.append("📦 Archived")
        if not bookmark.is_valid:
            status_parts.append("⚠️ Broken")
        if bookmark.ai_categorized:
            status_parts.append(f"🤖 AI ({int(bookmark.ai_confidence*100)}%)")
        
        if status_parts:
            self._add_detail("Status", " • ".join(status_parts))
        
        # Notes
        if bookmark.notes:
            tk.Frame(self.content, bg=theme.border, height=1).pack(fill=tk.X, pady=15)
            
            tk.Label(
                self.content, text="Notes:", bg=theme.bg_secondary,
                fg=theme.text_secondary, font=FONTS.body(),
                anchor="w"
            ).pack(fill=tk.X)
            
            notes_text = tk.Text(
                self.content, bg=theme.bg_tertiary, fg=theme.text_primary,
                font=FONTS.body(), height=4, wrap=tk.WORD, bd=0
            )
            notes_text.pack(fill=tk.X, pady=5)
            notes_text.insert("1.0", bookmark.notes)
            notes_text.configure(state=tk.DISABLED)
    
    def _add_detail(self, label: str, value: str, is_link: bool = False):
        """Add a detail row"""
        theme = get_theme()
        
        row = tk.Frame(self.content, bg=theme.bg_secondary)
        row.pack(fill=tk.X, pady=3)
        
        tk.Label(
            row, text=f"{label}:", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.small(),
            width=12, anchor="w"
        ).pack(side=tk.LEFT)
        
        value_label = tk.Label(
            row, text=value[:40] + "..." if len(value) > 43 else value,
            bg=theme.bg_secondary,
            fg=theme.text_link if is_link else theme.text_primary,
            font=FONTS.small(),
            anchor="w", cursor="hand2" if is_link else ""
        )
        value_label.pack(side=tk.LEFT, fill=tk.X)
        
        if is_link:
            value_label.bind("<Button-1>", lambda e: webbrowser.open(value))
    
    def _format_date(self, date_str: str) -> str:
        """Format date string nicely"""
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return date_str
    
    def _open_bookmark(self):
        if self.current_bookmark and self.on_open:
            self.on_open(self.current_bookmark)
    
    def _edit_bookmark(self):
        if self.current_bookmark and self.on_edit:
            self.on_edit(self.current_bookmark)
    
    def _delete_bookmark(self):
        if self.current_bookmark and self.on_delete:
            self.on_delete(self.current_bookmark)
    
    def clear(self):
        """Clear the panel"""
        self.current_bookmark = None
        for widget in self.content.winfo_children():
            widget.destroy()
        
        theme = get_theme()
        self.placeholder = tk.Label(
            self.content, text="Select a bookmark to view details",
            bg=theme.bg_secondary, fg=theme.text_muted,
            font=FONTS.body()
        )
        self.placeholder.pack(expand=True)




# =============================================================================
# Archive.org Wayback Machine Integration
# =============================================================================
class WaybackMachine:
    """Integration with Internet Archive's Wayback Machine"""
    
    SAVE_URL = "https://web.archive.org/save/"
    AVAILABILITY_URL = "https://archive.org/wayback/available"
    CDX_URL = "https://web.archive.org/cdx/search/cdx"
    
    @staticmethod
    def save_page(url: str) -> Tuple[bool, str]:
        """
        Save a page to the Wayback Machine.
        Returns (success, archived_url or error_message)
        """
        try:
            response = requests.get(
                WaybackMachine.SAVE_URL + url,
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=30
            )
            
            if response.status_code == 200:
                # Check for the archived URL in headers
                archived_url = response.headers.get('Content-Location', '')
                if archived_url:
                    return True, f"https://web.archive.org{archived_url}"
                
                # Try to extract from response
                if 'web.archive.org' in response.url:
                    return True, response.url
                
                return True, f"https://web.archive.org/web/{url}"
            else:
                return False, f"Failed with status {response.status_code}"
        except requests.exceptions.Timeout:
            return False, "Request timed out"
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def check_availability(url: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Check if a URL is available in the Wayback Machine.
        Returns (is_available, archived_url, timestamp)
        """
        try:
            response = requests.get(
                WaybackMachine.AVAILABILITY_URL,
                params={'url': url},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                snapshots = data.get('archived_snapshots', {})
                closest = snapshots.get('closest', {})
                
                if closest.get('available'):
                    return True, closest.get('url'), closest.get('timestamp')
            
            return False, None, None
        except Exception:
            return False, None, None
    
    @staticmethod
    def get_snapshots(url: str, limit: int = 10) -> List[Dict[str, str]]:
        """Get list of available snapshots for a URL"""
        try:
            response = requests.get(
                WaybackMachine.CDX_URL,
                params={
                    'url': url,
                    'output': 'json',
                    'limit': limit,
                    'fl': 'timestamp,original,statuscode'
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if len(data) > 1:  # First row is headers
                    snapshots = []
                    for row in data[1:]:
                        timestamp, original, status = row
                        snapshots.append({
                            'timestamp': timestamp,
                            'url': f"https://web.archive.org/web/{timestamp}/{original}",
                            'status': status,
                            'date': datetime.strptime(timestamp[:8], '%Y%m%d').strftime('%Y-%m-%d')
                        })
                    return snapshots
            return []
        except Exception:
            return []


# =============================================================================
# Local Page Archiving (Save HTML/MHTML)
# =============================================================================
class LocalArchiver:
    """Archive pages locally as HTML or MHTML"""
    
    ARCHIVE_DIR = DATA_DIR / "archives"
    
    def __init__(self):
        self.ARCHIVE_DIR.mkdir(exist_ok=True)
    
    def archive_page(self, bookmark: Bookmark, 
                     format: str = "html") -> Tuple[bool, str]:
        """
        Archive a page locally.
        format: 'html' or 'mhtml'
        Returns (success, filepath or error)
        """
        try:
            response = requests.get(
                bookmark.url,
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=30
            )
            
            if response.status_code != 200:
                return False, f"Failed to fetch: {response.status_code}"
            
            # Create safe filename
            safe_title = re.sub(r'[^\w\s-]', '', bookmark.title)[:50]
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{safe_title}_{timestamp}.{format}"
            filepath = self.ARCHIVE_DIR / filename
            
            if format == "html":
                # Save as HTML with embedded resources note
                html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="archived-from" content="{bookmark.url}">
    <meta name="archived-date" content="{datetime.now().isoformat()}">
    <meta name="original-title" content="{bookmark.title}">
    <title>{bookmark.title} (Archived)</title>
    <style>
        .archive-banner {{
            background: #1a1a2e;
            color: #eee;
            padding: 10px 20px;
            font-family: Arial, sans-serif;
            font-size: 12px;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            z-index: 99999;
        }}
        .archive-banner a {{ color: #58a6ff; }}
        body {{ margin-top: 40px !important; }}
    </style>
</head>
<body>
    <div class="archive-banner">
        📦 Archived from <a href="{bookmark.url}">{bookmark.url}</a> 
        on {datetime.now().strftime('%Y-%m-%d %H:%M')}
    </div>
    {response.text}
</body>
</html>"""
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(html_content)
            
            else:  # MHTML (simplified - full MHTML would need more work)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(response.text)
            
            # Update bookmark with archive path
            bookmark.local_archive_path = str(filepath)
            
            return True, str(filepath)
        
        except Exception as e:
            return False, str(e)
    
    def get_archived_pages(self) -> List[Dict[str, str]]:
        """Get list of all archived pages"""
        archives = []
        
        for file in self.ARCHIVE_DIR.glob("*.html"):
            archives.append({
                'filename': file.name,
                'path': str(file),
                'size': file.stat().st_size,
                'date': datetime.fromtimestamp(file.stat().st_mtime).isoformat()
            })
        
        return sorted(archives, key=lambda x: x['date'], reverse=True)
    
    def get_archive_size(self) -> Tuple[int, int]:
        """Get total archive size (file_count, bytes)"""
        files = list(self.ARCHIVE_DIR.glob("*"))
        total_size = sum(f.stat().st_size for f in files if f.is_file())
        return len(files), total_size
    
    def delete_archive(self, filepath: str) -> bool:
        """Delete an archived page"""
        try:
            Path(filepath).unlink()
            return True
        except Exception:
            return False


# =============================================================================
# AI Summary Generation
# =============================================================================
class AISummarizer:
    """Generate AI summaries for bookmark pages"""
    
    def __init__(self, ai_config: AIConfigManager):
        self.ai_config = ai_config
        self._cache: Dict[str, str] = {}
    
    def summarize_page(self, bookmark: Bookmark, 
                       max_length: int = 150) -> Optional[str]:
        """
        Fetch page content and generate a summary.
        Returns summary text or None on failure.
        """
        cache_key = bookmark.url
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            # Fetch page content
            response = requests.get(
                bookmark.url,
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=15
            )
            
            if response.status_code != 200:
                return None
            
            # Extract text content
            text = self._extract_text(response.text)
            if len(text) < 100:
                return None
            
            # Truncate for API
            text = text[:4000]
            
            # Generate summary with AI
            client = create_ai_client(self.ai_config)
            
            prompt = f"""Summarize this webpage in 1-2 sentences (max {max_length} characters).
Be concise and capture the main topic/purpose.

Title: {bookmark.title}
URL: {bookmark.url}

Content:
{text}

Summary:"""
            
            # Use categorize endpoint but extract summary
            result = client.categorize_bookmark(bookmark.url, bookmark.title, [])
            
            if result and 'summary' in result:
                summary = result['summary']
            else:
                # Fallback: extract first meaningful paragraph
                summary = self._extract_first_paragraph(text)
            
            if summary:
                self._cache[cache_key] = summary
                return summary
            
        except Exception as e:
            pass
        
        return None
    
    def _extract_text(self, html: str) -> str:
        """Extract readable text from HTML"""
        # Remove scripts and styles
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', html)
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Decode HTML entities
        text = html_module.unescape(text) if 'html_module' in dir() else text
        
        return text
    
    def _extract_first_paragraph(self, text: str) -> str:
        """Extract first meaningful paragraph as fallback summary"""
        sentences = re.split(r'[.!?]+', text)
        
        meaningful = []
        for sent in sentences:
            sent = sent.strip()
            if len(sent) > 30 and len(sent) < 200:
                meaningful.append(sent)
                if len(' '.join(meaningful)) > 100:
                    break
        
        if meaningful:
            return '. '.join(meaningful[:2]) + '.'
        
        return text[:150] + '...' if len(text) > 150 else text
    
    def batch_summarize(self, bookmarks: List[Bookmark],
                        progress_callback: Callable = None) -> Dict[int, str]:
        """Generate summaries for multiple bookmarks"""
        results = {}
        total = len(bookmarks)
        
        for i, bm in enumerate(bookmarks):
            summary = self.summarize_page(bm)
            if summary:
                results[bm.id] = summary
                bm.ai_summary = summary
            
            if progress_callback:
                progress_callback(i + 1, total, bm)
            
            # Rate limiting
            time.sleep(0.5)
        
        return results


# =============================================================================
# AI Semantic Duplicate Detection
# =============================================================================
class SemanticDuplicateDetector:
    """Detect semantically similar bookmarks using AI"""
    
    def __init__(self, ai_config: AIConfigManager):
        self.ai_config = ai_config
    
    def find_similar(self, bookmarks: List[Bookmark], 
                     threshold: float = 0.7) -> List[List[Bookmark]]:
        """
        Find groups of semantically similar bookmarks.
        Returns list of groups (each group is a list of similar bookmarks).
        """
        if len(bookmarks) < 2:
            return []
        
        # Group by domain first (optimization)
        by_domain: Dict[str, List[Bookmark]] = {}
        for bm in bookmarks:
            domain = bm.domain
            if domain not in by_domain:
                by_domain[domain] = []
            by_domain[domain].append(bm)
        
        similar_groups = []
        
        # Check within same domain
        for domain, domain_bms in by_domain.items():
            if len(domain_bms) < 2:
                continue
            
            groups = self._find_similar_in_group(domain_bms, threshold)
            similar_groups.extend(groups)
        
        # Check across different domains with similar titles
        cross_domain = self._find_cross_domain_similar(bookmarks, threshold)
        similar_groups.extend(cross_domain)
        
        return similar_groups
    
    def _find_similar_in_group(self, bookmarks: List[Bookmark], 
                                threshold: float) -> List[List[Bookmark]]:
        """Find similar bookmarks within a group"""
        groups = []
        used = set()
        
        for i, bm1 in enumerate(bookmarks):
            if bm1.id in used:
                continue
            
            group = [bm1]
            
            for bm2 in bookmarks[i+1:]:
                if bm2.id in used:
                    continue
                
                similarity = self._calculate_similarity(bm1, bm2)
                if similarity >= threshold:
                    group.append(bm2)
                    used.add(bm2.id)
            
            if len(group) > 1:
                groups.append(group)
                used.add(bm1.id)
        
        return groups
    
    def _find_cross_domain_similar(self, bookmarks: List[Bookmark],
                                    threshold: float) -> List[List[Bookmark]]:
        """Find similar bookmarks across domains"""
        groups = []
        
        # Use title similarity for cross-domain
        for i, bm1 in enumerate(bookmarks):
            similar = []
            
            for bm2 in bookmarks[i+1:]:
                if bm1.domain == bm2.domain:
                    continue
                
                # Title similarity
                title_sim = self._title_similarity(bm1.title, bm2.title)
                if title_sim >= threshold:
                    similar.append(bm2)
            
            if similar:
                groups.append([bm1] + similar)
        
        return groups
    
    def _calculate_similarity(self, bm1: Bookmark, bm2: Bookmark) -> float:
        """Calculate similarity score between two bookmarks"""
        scores = []
        
        # URL path similarity
        path1 = urllib.parse.urlparse(bm1.url).path
        path2 = urllib.parse.urlparse(bm2.url).path
        
        if path1 and path2:
            path_sim = 1 - (levenshtein_distance(path1, path2) / max(len(path1), len(path2)))
            scores.append(path_sim * 0.3)
        
        # Title similarity
        title_sim = self._title_similarity(bm1.title, bm2.title)
        scores.append(title_sim * 0.5)
        
        # Tag overlap
        if bm1.tags and bm2.tags:
            common = set(bm1.tags) & set(bm2.tags)
            total = set(bm1.tags) | set(bm2.tags)
            tag_sim = len(common) / len(total) if total else 0
            scores.append(tag_sim * 0.2)
        
        return sum(scores)
    
    def _title_similarity(self, title1: str, title2: str) -> float:
        """Calculate title similarity using word overlap and edit distance"""
        t1 = title1.lower()
        t2 = title2.lower()
        
        # Word overlap (Jaccard)
        words1 = set(re.findall(r'\w+', t1))
        words2 = set(re.findall(r'\w+', t2))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        jaccard = len(intersection) / len(union)
        
        # Edit distance normalized
        max_len = max(len(t1), len(t2))
        edit_sim = 1 - (levenshtein_distance(t1, t2) / max_len) if max_len > 0 else 0
        
        return (jaccard * 0.6 + edit_sim * 0.4)


# =============================================================================
# AI Cost Tracker
# =============================================================================
class AICostTracker:
    """Track AI API usage and estimated costs"""
    
    COST_FILE = DATA_DIR / "ai_costs.json"
    
    # Approximate costs per 1K tokens (as of 2024)
    COSTS = {
        "openai": {
            "gpt-4": {"input": 0.03, "output": 0.06},
            "gpt-4-turbo": {"input": 0.01, "output": 0.03},
            "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
        },
        "anthropic": {
            "claude-3-opus": {"input": 0.015, "output": 0.075},
            "claude-3-sonnet": {"input": 0.003, "output": 0.015},
            "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
        },
        "google": {
            "gemini-pro": {"input": 0.00025, "output": 0.0005},
        },
        "groq": {
            "llama2-70b": {"input": 0.0007, "output": 0.0008},
            "mixtral-8x7b": {"input": 0.00027, "output": 0.00027},
        },
        "ollama": {
            "default": {"input": 0, "output": 0},  # Local, no cost
        }
    }
    
    def __init__(self):
        self.usage: Dict[str, Dict] = {}
        self._load_usage()
    
    def _load_usage(self):
        """Load usage data from file"""
        if self.COST_FILE.exists():
            try:
                with open(self.COST_FILE, 'r') as f:
                    self.usage = json.load(f)
            except Exception:
                self.usage = {}
    
    def _save_usage(self):
        """Save usage data to file"""
        DATA_DIR.mkdir(exist_ok=True)
        with open(self.COST_FILE, 'w') as f:
            json.dump(self.usage, f, indent=2)
    
    def record_usage(self, provider: str, model: str, 
                     input_tokens: int, output_tokens: int):
        """Record API usage"""
        month_key = datetime.now().strftime("%Y-%m")
        
        if month_key not in self.usage:
            self.usage[month_key] = {}
        
        provider_key = f"{provider}/{model}"
        if provider_key not in self.usage[month_key]:
            self.usage[month_key][provider_key] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "calls": 0,
                "cost": 0.0
            }
        
        entry = self.usage[month_key][provider_key]
        entry["input_tokens"] += input_tokens
        entry["output_tokens"] += output_tokens
        entry["calls"] += 1
        
        # Calculate cost
        cost = self._calculate_cost(provider, model, input_tokens, output_tokens)
        entry["cost"] += cost
        
        self._save_usage()
    
    def _calculate_cost(self, provider: str, model: str,
                        input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for usage"""
        provider_costs = self.COSTS.get(provider, {})
        model_costs = provider_costs.get(model, provider_costs.get("default", {"input": 0, "output": 0}))
        
        input_cost = (input_tokens / 1000) * model_costs["input"]
        output_cost = (output_tokens / 1000) * model_costs["output"]
        
        return input_cost + output_cost
    
    def get_monthly_summary(self, month: str = None) -> Dict:
        """Get usage summary for a month"""
        if month is None:
            month = datetime.now().strftime("%Y-%m")
        
        month_data = self.usage.get(month, {})
        
        total_input = sum(d["input_tokens"] for d in month_data.values())
        total_output = sum(d["output_tokens"] for d in month_data.values())
        total_calls = sum(d["calls"] for d in month_data.values())
        total_cost = sum(d["cost"] for d in month_data.values())
        
        return {
            "month": month,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_calls": total_calls,
            "total_cost": total_cost,
            "by_provider": month_data
        }
    
    def get_all_time_summary(self) -> Dict:
        """Get all-time usage summary"""
        total_input = 0
        total_output = 0
        total_calls = 0
        total_cost = 0.0
        
        for month_data in self.usage.values():
            for provider_data in month_data.values():
                total_input += provider_data["input_tokens"]
                total_output += provider_data["output_tokens"]
                total_calls += provider_data["calls"]
                total_cost += provider_data["cost"]
        
        return {
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_calls": total_calls,
            "total_cost": total_cost,
            "months": len(self.usage)
        }
    
    def get_cost_report(self) -> str:
        """Generate a cost report"""
        summary = self.get_all_time_summary()
        monthly = self.get_monthly_summary()
        
        report = f"""AI Usage Report
══════════════════════════════════════

This Month ({monthly['month']}):
  Calls: {monthly['total_calls']}
  Input Tokens: {monthly['total_input_tokens']:,}
  Output Tokens: {monthly['total_output_tokens']:,}
  Estimated Cost: ${monthly['total_cost']:.4f}

All Time:
  Total Calls: {summary['total_calls']}
  Total Input Tokens: {summary['total_input_tokens']:,}
  Total Output Tokens: {summary['total_output_tokens']:,}
  Total Cost: ${summary['total_cost']:.4f}
"""
        return report




# =============================================================================
# Pocket Import
# =============================================================================
class PocketImporter:
    """Import bookmarks from Pocket export"""
    
    @staticmethod
    def import_from_html(filepath: str) -> List[Bookmark]:
        """Import from Pocket HTML export file"""
        bookmarks = []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Pocket exports have <a> tags with href, time_added, tags attributes
            pattern = r'<a\s+href="([^"]+)"[^>]*time_added="(\d+)"[^>]*(?:tags="([^"]*)")?[^>]*>([^<]*)</a>'
            
            matches = re.findall(pattern, content, re.IGNORECASE)
            
            for match in matches:
                url, timestamp, tags, title = match
                
                bm = Bookmark(
                    id=None,
                    url=url,
                    title=title.strip() or url,
                    category="Imported from Pocket"
                )
                
                # Parse timestamp
                try:
                    bm.created_at = datetime.fromtimestamp(int(timestamp)).isoformat()
                except Exception:
                    pass
                
                # Parse tags
                if tags:
                    bm.tags = [t.strip() for t in tags.split(',') if t.strip()]
                
                bookmarks.append(bm)
            
            # Also try simpler pattern for basic exports
            if not bookmarks:
                simple_pattern = r'<a\s+href="([^"]+)"[^>]*>([^<]*)</a>'
                matches = re.findall(simple_pattern, content, re.IGNORECASE)
                
                for url, title in matches:
                    if url.startswith(('http://', 'https://')):
                        bm = Bookmark(
                            id=None,
                            url=url,
                            title=title.strip() or url,
                            category="Imported from Pocket"
                        )
                        bookmarks.append(bm)
        
        except Exception as e:
            print(f"Error importing Pocket: {e}")
        
        return bookmarks


# =============================================================================
# Raindrop.io Import
# =============================================================================
class RaindropImporter:
    """Import bookmarks from Raindrop.io export"""
    
    @staticmethod
    def import_from_csv(filepath: str) -> List[Bookmark]:
        """Import from Raindrop CSV export"""
        bookmarks = []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    bm = Bookmark(
                        id=None,
                        url=row.get('url', row.get('link', '')),
                        title=row.get('title', ''),
                        category=row.get('folder', row.get('collection', 'Imported from Raindrop'))
                    )
                    
                    # Notes/description
                    if row.get('note') or row.get('excerpt'):
                        bm.notes = row.get('note', '') or row.get('excerpt', '')
                    
                    # Tags
                    tags = row.get('tags', '')
                    if tags:
                        bm.tags = [t.strip() for t in tags.split(',') if t.strip()]
                    
                    # Created date
                    created = row.get('created', row.get('created_at', ''))
                    if created:
                        try:
                            bm.created_at = datetime.fromisoformat(created.replace('Z', '+00:00')).isoformat()
                        except Exception:
                            pass
                    
                    if bm.url:
                        bookmarks.append(bm)
        
        except Exception as e:
            print(f"Error importing Raindrop: {e}")
        
        return bookmarks
    
    @staticmethod
    def import_from_html(filepath: str) -> List[Bookmark]:
        """Import from Raindrop HTML export"""
        bookmarks = []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse folders
            folder_pattern = r'<h3[^>]*>([^<]+)</h3>\s*<dl>(.*?)</dl>'
            folder_matches = re.findall(folder_pattern, content, re.DOTALL | re.IGNORECASE)
            
            for folder_name, folder_content in folder_matches:
                # Parse bookmarks in folder
                bm_pattern = r'<a\s+href="([^"]+)"[^>]*>([^<]*)</a>'
                bm_matches = re.findall(bm_pattern, folder_content, re.IGNORECASE)
                
                for url, title in bm_matches:
                    bm = Bookmark(
                        id=None,
                        url=url,
                        title=title.strip() or url,
                        category=folder_name.strip()
                    )
                    bookmarks.append(bm)
        
        except Exception as e:
            print(f"Error importing Raindrop HTML: {e}")
        
        return bookmarks


# =============================================================================
# OPML Export (for RSS readers)
# =============================================================================
class OPMLExporter:
    """Export bookmarks in OPML format"""
    
    @staticmethod
    def export(bookmarks: List[Bookmark], filepath: str, 
               title: str = "Bookmark Export"):
        """Export bookmarks to OPML file"""
        # Group by category
        by_category: Dict[str, List[Bookmark]] = {}
        for bm in bookmarks:
            cat = bm.category or "Uncategorized"
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(bm)
        
        # Build OPML
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<opml version="2.0">',
            '  <head>',
            f'    <title>{title}</title>',
            f'    <dateCreated>{datetime.now().isoformat()}</dateCreated>',
            '  </head>',
            '  <body>',
        ]
        
        for category, cat_bookmarks in sorted(by_category.items()):
            # Escape XML
            cat_escaped = category.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
            
            lines.append(f'    <outline text="{cat_escaped}" title="{cat_escaped}">')
            
            for bm in cat_bookmarks:
                title_escaped = bm.title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
                url_escaped = bm.url.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
                
                lines.append(f'      <outline type="link" text="{title_escaped}" title="{title_escaped}" xmlUrl="{url_escaped}" htmlUrl="{url_escaped}"/>')
            
            lines.append('    </outline>')
        
        lines.extend([
            '  </body>',
            '</opml>'
        ])
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))


# =============================================================================
# Selective Export Dialog
# =============================================================================
class SelectiveExportDialog(tk.Toplevel, ThemedWidget):
    """Dialog for selecting what to export"""
    
    def __init__(self, parent, bookmark_manager: BookmarkManager,
                 on_export: Callable = None):
        super().__init__(parent)
        self.bookmark_manager = bookmark_manager
        self.on_export = on_export
        self.result = None
        
        theme = get_theme()
        
        self.title("Selective Export")
        self.geometry("550x600")
        self.configure(bg=theme.bg_primary)
        self.transient(parent)
        self.grab_set()
        
        set_dark_title_bar(self)
        
        # Header
        header = tk.Frame(self, bg=theme.bg_dark, height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(
            header, text="📤 Selective Export", bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.header()
        ).pack(side=tk.LEFT, padx=20, pady=15)
        
        # Content
        content = tk.Frame(self, bg=theme.bg_primary)
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        # Format selection
        tk.Label(
            content, text="Export Format:", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        ).pack(anchor="w")
        
        self.format_var = tk.StringVar(value="html")
        formats_frame = tk.Frame(content, bg=theme.bg_primary)
        formats_frame.pack(fill=tk.X, pady=(5, 15))
        
        for fmt, label in [("html", "HTML"), ("json", "JSON"), 
                           ("csv", "CSV"), ("md", "Markdown"), ("opml", "OPML")]:
            ttk.Radiobutton(
                formats_frame, text=label, variable=self.format_var, value=fmt
            ).pack(side=tk.LEFT, padx=(0, 15))
        
        # Category selection
        tk.Label(
            content, text="Select Categories:", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        ).pack(anchor="w", pady=(10, 5))
        
        # Category checkboxes with scroll
        cat_frame = tk.Frame(content, bg=theme.bg_secondary)
        cat_frame.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(cat_frame, bg=theme.bg_secondary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(cat_frame, orient="vertical", command=canvas.yview)
        cat_inner = tk.Frame(canvas, bg=theme.bg_secondary)
        
        cat_inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=cat_inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Select all / none buttons
        select_frame = tk.Frame(cat_inner, bg=theme.bg_secondary)
        select_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(
            select_frame, text="Select All", bg=theme.bg_secondary,
            fg=theme.accent_primary, font=FONTS.small(),
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=(0, 15))
        
        tk.Label(
            select_frame, text="Select None", bg=theme.bg_secondary,
            fg=theme.accent_primary, font=FONTS.small(),
            cursor="hand2"
        ).pack(side=tk.LEFT)
        
        select_frame.winfo_children()[0].bind("<Button-1>", lambda e: self._select_all(True))
        select_frame.winfo_children()[1].bind("<Button-1>", lambda e: self._select_all(False))
        
        # Category checkboxes
        self.cat_vars: Dict[str, tk.BooleanVar] = {}
        categories = bookmark_manager.category_manager.get_sorted_categories()
        counts = bookmark_manager.get_category_counts()
        
        for cat in categories:
            count = counts.get(cat, 0)
            var = tk.BooleanVar(value=True)
            self.cat_vars[cat] = var
            
            cb = ttk.Checkbutton(
                cat_inner, text=f"{cat} ({count})", variable=var
            )
            cb.pack(anchor="w", padx=10, pady=2)
        
        # Options
        opts_frame = tk.Frame(content, bg=theme.bg_primary)
        opts_frame.pack(fill=tk.X, pady=(15, 0))
        
        self.include_tags_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opts_frame, text="Include tags", variable=self.include_tags_var
        ).pack(anchor="w")
        
        self.include_notes_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opts_frame, text="Include notes", variable=self.include_notes_var
        ).pack(anchor="w")
        
        self.include_metadata_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opts_frame, text="Include metadata (dates, visit count)", 
            variable=self.include_metadata_var
        ).pack(anchor="w")
        
        # Buttons
        btn_frame = tk.Frame(self, bg=theme.bg_primary)
        btn_frame.pack(fill=tk.X, padx=20, pady=15)
        
        ModernButton(
            btn_frame, text="Cancel", command=self.destroy
        ).pack(side=tk.RIGHT, padx=(10, 0))
        
        ModernButton(
            btn_frame, text="Export", command=self._export,
            style="primary", icon="📤"
        ).pack(side=tk.RIGHT)
        
        self.center_window()
    
    def _select_all(self, select: bool):
        """Select all or none"""
        for var in self.cat_vars.values():
            var.set(select)
    
    def _export(self):
        """Perform export"""
        selected_cats = [cat for cat, var in self.cat_vars.items() if var.get()]
        
        if not selected_cats:
            messagebox.showwarning("Warning", "Please select at least one category")
            return
        
        # Get bookmarks from selected categories
        bookmarks = []
        for cat in selected_cats:
            bookmarks.extend(self.bookmark_manager.get_bookmarks_by_category(cat))
        
        if not bookmarks:
            messagebox.showwarning("Warning", "No bookmarks to export")
            return
        
        # Ask for file location
        fmt = self.format_var.get()
        extensions = {
            "html": ("HTML files", "*.html"),
            "json": ("JSON files", "*.json"),
            "csv": ("CSV files", "*.csv"),
            "md": ("Markdown files", "*.md"),
            "opml": ("OPML files", "*.opml"),
        }
        
        filepath = filedialog.asksaveasfilename(
            title="Export Bookmarks",
            defaultextension=f".{fmt}",
            filetypes=[extensions[fmt], ("All files", "*.*")]
        )
        
        if not filepath:
            return
        
        # Export
        try:
            if fmt == "html":
                self.bookmark_manager.export_html(filepath)
            elif fmt == "json":
                self.bookmark_manager.export_json(filepath)
            elif fmt == "csv":
                self.bookmark_manager.export_csv(filepath)
            elif fmt == "md":
                self.bookmark_manager.export_markdown(filepath)
            elif fmt == "opml":
                OPMLExporter.export(bookmarks, filepath)
            
            self.result = {
                "filepath": filepath,
                "format": fmt,
                "count": len(bookmarks)
            }
            
            messagebox.showinfo("Success", f"Exported {len(bookmarks)} bookmarks to {Path(filepath).name}")
            self.destroy()
        
        except Exception as e:
            messagebox.showerror("Error", f"Export failed: {e}")
    
    def center_window(self):
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')


# =============================================================================
# Scheduled Backups
# =============================================================================
class BackupScheduler:
    """Schedule automatic backups"""
    
    BACKUP_DIR = DATA_DIR / "backups"
    CONFIG_FILE = DATA_DIR / "backup_config.json"
    
    def __init__(self, bookmark_manager: BookmarkManager):
        self.bookmark_manager = bookmark_manager
        self.config = self._load_config()
        self._timer: Optional[threading.Timer] = None
        self._running = False
        
        self.BACKUP_DIR.mkdir(exist_ok=True)
    
    def _load_config(self) -> Dict:
        """Load backup configuration"""
        default = {
            "enabled": False,
            "interval_hours": 24,
            "max_backups": 10,
            "last_backup": None,
            "backup_location": str(self.BACKUP_DIR)
        }
        
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE, 'r') as f:
                    loaded = json.load(f)
                    default.update(loaded)
            except Exception:
                pass
        
        return default
    
    def _save_config(self):
        """Save backup configuration"""
        DATA_DIR.mkdir(exist_ok=True)
        with open(self.CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def start(self):
        """Start the backup scheduler"""
        if not self.config["enabled"]:
            return
        
        self._running = True
        self._schedule_next()
    
    def stop(self):
        """Stop the backup scheduler"""
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
    
    def _schedule_next(self):
        """Schedule the next backup"""
        if not self._running:
            return
        
        interval_seconds = self.config["interval_hours"] * 3600
        self._timer = threading.Timer(interval_seconds, self._do_backup)
        self._timer.daemon = True
        self._timer.start()
    
    def _do_backup(self):
        """Perform a backup"""
        try:
            filepath = self.create_backup()
            self.config["last_backup"] = datetime.now().isoformat()
            self._save_config()
            self._cleanup_old_backups()
        except Exception as e:
            print(f"Backup failed: {e}")
        
        # Schedule next
        if self._running:
            self._schedule_next()
    
    def create_backup(self, location: str = None) -> str:
        """Create a backup now"""
        backup_dir = Path(location) if location else self.BACKUP_DIR
        backup_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"bookmark_backup_{timestamp}.json"
        filepath = backup_dir / filename
        
        # Export to JSON
        self.bookmark_manager.export_json(str(filepath))
        
        return str(filepath)
    
    def _cleanup_old_backups(self):
        """Remove old backups beyond max_backups limit"""
        backups = sorted(
            self.BACKUP_DIR.glob("bookmark_backup_*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )
        
        for old_backup in backups[self.config["max_backups"]:]:
            old_backup.unlink()
    
    def get_backups(self) -> List[Dict]:
        """Get list of available backups"""
        backups = []
        
        for backup_file in self.BACKUP_DIR.glob("bookmark_backup_*.json"):
            stat = backup_file.stat()
            backups.append({
                "filename": backup_file.name,
                "path": str(backup_file),
                "size": stat.st_size,
                "date": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
        
        return sorted(backups, key=lambda x: x['date'], reverse=True)
    
    def restore_backup(self, filepath: str) -> Tuple[int, int]:
        """Restore from a backup file"""
        return self.bookmark_manager.import_json_file(filepath)
    
    def set_enabled(self, enabled: bool):
        """Enable or disable scheduled backups"""
        self.config["enabled"] = enabled
        self._save_config()
        
        if enabled:
            self.start()
        else:
            self.stop()
    
    def set_interval(self, hours: int):
        """Set backup interval in hours"""
        self.config["interval_hours"] = hours
        self._save_config()
        
        # Restart scheduler with new interval
        if self._running:
            self.stop()
            self.start()


# =============================================================================
# Version History
# =============================================================================
class VersionHistory:
    """Track bookmark changes and allow restoration"""
    
    HISTORY_FILE = DATA_DIR / "version_history.json"
    MAX_VERSIONS = 50
    
    def __init__(self):
        self.versions: List[Dict] = []
        self._load_history()
    
    def _load_history(self):
        """Load version history"""
        if self.HISTORY_FILE.exists():
            try:
                with open(self.HISTORY_FILE, 'r') as f:
                    self.versions = json.load(f)
            except Exception:
                self.versions = []
    
    def _save_history(self):
        """Save version history"""
        DATA_DIR.mkdir(exist_ok=True)
        with open(self.HISTORY_FILE, 'w') as f:
            json.dump(self.versions[-self.MAX_VERSIONS:], f, indent=2)
    
    def record_change(self, action: str, bookmark_id: int, 
                      old_data: Dict = None, new_data: Dict = None):
        """Record a change to the history"""
        version = {
            "timestamp": datetime.now().isoformat(),
            "action": action,  # "add", "edit", "delete", "move", "bulk"
            "bookmark_id": bookmark_id,
            "old_data": old_data,
            "new_data": new_data
        }
        
        self.versions.append(version)
        self._save_history()
    
    def record_bulk_change(self, action: str, bookmark_ids: List[int],
                           description: str):
        """Record a bulk change"""
        version = {
            "timestamp": datetime.now().isoformat(),
            "action": f"bulk_{action}",
            "bookmark_ids": bookmark_ids,
            "description": description
        }
        
        self.versions.append(version)
        self._save_history()
    
    def get_history(self, limit: int = 20) -> List[Dict]:
        """Get recent history entries"""
        return list(reversed(self.versions[-limit:]))
    
    def get_bookmark_history(self, bookmark_id: int) -> List[Dict]:
        """Get history for a specific bookmark"""
        return [
            v for v in self.versions 
            if v.get("bookmark_id") == bookmark_id or 
               bookmark_id in v.get("bookmark_ids", [])
        ]
    
    def clear_history(self):
        """Clear all history"""
        self.versions = []
        self._save_history()




# =============================================================================
# Per-Category Colors
# =============================================================================
class CategoryColorManager:
    """
        Represents a bookmark category.
        
        Attributes:
            name: Category name (unique identifier)
            parent: Parent category name (for nesting)
            icon: Emoji icon for display
            color: Optional color override
            sort_order: Order within parent
            created_at: ISO timestamp of creation
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
        """
    
    COLORS_FILE = DATA_DIR / "category_colors.json"
    
    DEFAULT_COLORS = [
        "#58a6ff", "#3fb950", "#f0883e", "#a371f7", "#f778ba",
        "#79c0ff", "#7ee787", "#ffa657", "#d2a8ff", "#ff7b72",
        "#56d4dd", "#e3b341", "#8b949e", "#6e7681", "#238636"
    ]
    
    def __init__(self):
        self.colors: Dict[str, str] = {}
        self._load_colors()
    
    def _load_colors(self):
        """Load custom colors from file"""
        if self.COLORS_FILE.exists():
            try:
                with open(self.COLORS_FILE, 'r') as f:
                    self.colors = json.load(f)
            except Exception:
                pass
    
    def _save_colors(self):
        """Save colors to file"""
        DATA_DIR.mkdir(exist_ok=True)
        with open(self.COLORS_FILE, 'w') as f:
            json.dump(self.colors, f, indent=2)
    
    def get_color(self, category: str) -> str:
        """Get color for a category"""
        if category in self.colors:
            return self.colors[category]
        
        # Generate consistent color from category name
        hash_val = sum(ord(c) for c in category)
        return self.DEFAULT_COLORS[hash_val % len(self.DEFAULT_COLORS)]
    
    def set_color(self, category: str, color: str):
        """Set custom color for a category"""
        self.colors[category] = color
        self._save_colors()
    
    def reset_color(self, category: str):
        """Reset category to default color"""
        if category in self.colors:
            del self.colors[category]
            self._save_colors()
    
    def get_all_colors(self) -> Dict[str, str]:
        """Get all category colors"""
        return self.colors.copy()


# =============================================================================
# Window Transparency
# =============================================================================
class WindowTransparency:
    """Manage window transparency/opacity"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self._opacity = 1.0
    
    @property
    def opacity(self) -> float:
        return self._opacity
    
    @opacity.setter
    def opacity(self, value: float):
        """Set window opacity (0.0 to 1.0)"""
        self._opacity = max(0.3, min(1.0, value))  # Min 30% opacity
        self.root.attributes('-alpha', self._opacity)
    
    def increase(self, step: float = 0.1):
        """Increase opacity"""
        self.opacity = self._opacity + step
    
    def decrease(self, step: float = 0.1):
        """Decrease opacity"""
        self.opacity = self._opacity - step
    
    def reset(self):
        """Reset to full opacity"""
        self.opacity = 1.0


# =============================================================================
# Custom Fonts Manager
# =============================================================================
class FontManager:
    """Manage custom fonts for the application"""
    
    FONTS_FILE = DATA_DIR / "font_settings.json"
    
    # Common safe fonts
    AVAILABLE_FONTS = {
        "ui": [
            "Segoe UI", "SF Pro Display", "Helvetica Neue", "Arial",
            "Roboto", "Open Sans", "Lato", "Inter", "Noto Sans"
        ],
        "mono": [
            "Consolas", "SF Mono", "Monaco", "Menlo", "Fira Code",
            "JetBrains Mono", "Source Code Pro", "Cascadia Code",
            "Ubuntu Mono", "Courier New"
        ]
    }
    
    def __init__(self):
        self.settings = self._load_settings()
    
    def _load_settings(self) -> Dict:
        """Load font settings"""
        default = {
            "ui_font": "Segoe UI",
            "mono_font": "Consolas",
            "ui_size": 10,
            "mono_size": 10
        }
        
        if self.FONTS_FILE.exists():
            try:
                with open(self.FONTS_FILE, 'r') as f:
                    loaded = json.load(f)
                    default.update(loaded)
            except Exception:
                pass
        
        return default
    
    def _save_settings(self):
        """Save font settings"""
        DATA_DIR.mkdir(exist_ok=True)
        with open(self.FONTS_FILE, 'w') as f:
            json.dump(self.settings, f, indent=2)
    
    def get_ui_font(self) -> Tuple[str, int]:
        """Get UI font tuple"""
        return (self.settings["ui_font"], self.settings["ui_size"])
    
    def get_mono_font(self) -> Tuple[str, int]:
        """Get monospace font tuple"""
        return (self.settings["mono_font"], self.settings["mono_size"])
    
    def set_ui_font(self, family: str, size: int = None):
        """Set UI font"""
        self.settings["ui_font"] = family
        if size:
            self.settings["ui_size"] = size
        self._save_settings()
    
    def set_mono_font(self, family: str, size: int = None):
        """Set monospace font"""
        self.settings["mono_font"] = family
        if size:
            self.settings["mono_size"] = size
        self._save_settings()
    
    def get_available_fonts(self) -> List[str]:
        """Get list of available system fonts"""
        try:
            import tkinter.font as tkfont
            return list(tkfont.families())
        except Exception:
            return self.AVAILABLE_FONTS["ui"] + self.AVAILABLE_FONTS["mono"]


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
        
        set_dark_title_bar(self)
        
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
                fg=theme.text_secondary, font=("Segoe UI", 9, "bold"),
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


# =============================================================================
# Icon Library
# =============================================================================
class IconLibrary:
    """Built-in icon library with common icons"""
    
    # Organized icon collection (using emoji as icons)
    ICONS = {
        "Files & Folders": {
            "folder": "📁", "folder_open": "📂", "file": "📄", "document": "📃",
            "clipboard": "📋", "archive": "🗃️", "cabinet": "🗄️", "briefcase": "💼"
        },
        "Communication": {
            "email": "📧", "envelope": "✉️", "chat": "💬", "phone": "📱",
            "megaphone": "📢", "bell": "🔔", "comment": "💭", "mail": "📨"
        },
        "Technology": {
            "laptop": "💻", "desktop": "🖥️", "keyboard": "⌨️", "mouse": "🖱️",
            "globe": "🌐", "link": "🔗", "database": "🗄️", "server": "🖲️",
            "code": "💻", "terminal": "⬛", "bug": "🐛", "robot": "🤖"
        },
        "Media": {
            "photo": "📷", "video": "📹", "music": "🎵", "film": "🎬",
            "headphones": "🎧", "mic": "🎤", "tv": "📺", "radio": "📻"
        },
        "Business": {
            "chart_up": "📈", "chart_down": "📉", "chart": "📊", "money": "💰",
            "card": "💳", "bank": "🏦", "shopping": "🛒", "gift": "🎁"
        },
        "Tools": {
            "wrench": "🔧", "hammer": "🔨", "gear": "⚙️", "tools": "🛠️",
            "lightbulb": "💡", "magnifier": "🔍", "lock": "🔒", "key": "🔑"
        },
        "Status": {
            "check": "✅", "cross": "❌", "warning": "⚠️", "info": "ℹ️",
            "question": "❓", "star": "⭐", "heart": "❤️", "fire": "🔥"
        },
        "Navigation": {
            "home": "🏠", "building": "🏢", "pin": "📍", "map": "🗺️",
            "compass": "🧭", "flag": "🚩", "bookmark": "🔖", "tag": "🏷️"
        },
        "Education": {
            "book": "📚", "notebook": "📓", "pencil": "✏️", "pen": "🖊️",
            "graduation": "🎓", "science": "🔬", "calculator": "🧮", "abc": "🔤"
        },
        "Nature": {
            "sun": "☀️", "moon": "🌙", "cloud": "☁️", "tree": "🌳",
            "flower": "🌸", "earth": "🌍", "mountain": "⛰️", "water": "💧"
        },
        "People": {
            "user": "👤", "users": "👥", "person": "🧑", "team": "👨‍👩‍👧‍👦",
            "handshake": "🤝", "thumbs_up": "👍", "clap": "👏", "wave": "👋"
        },
        "Time": {
            "clock": "🕐", "calendar": "📅", "hourglass": "⏳", "alarm": "⏰",
            "stopwatch": "⏱️", "timer": "⏲️", "history": "🕰️", "schedule": "📆"
        }
    }
    
    @classmethod
    def get_all_icons(cls) -> Dict[str, Dict[str, str]]:
        """Get all icons organized by category"""
        return cls.ICONS
    
    @classmethod
    def get_flat_icons(cls) -> Dict[str, str]:
        """Get all icons as flat dict"""
        flat = {}
        for category_icons in cls.ICONS.values():
            flat.update(category_icons)
        return flat
    
    @classmethod
    def search_icons(cls, query: str) -> Dict[str, str]:
        """Search icons by name"""
        query = query.lower()
        results = {}
        
        for category_icons in cls.ICONS.values():
            for name, icon in category_icons.items():
                if query in name.lower():
                    results[name] = icon
        
        return results
    
    @classmethod
    def suggest_icon(cls, text: str) -> str:
        """Suggest an icon based on text"""
        text_lower = text.lower()
        
        # Keywords to icon mapping
        keyword_map = {
            "code": "💻", "dev": "💻", "program": "💻", "software": "💻",
            "doc": "📄", "document": "📄", "file": "📄", "paper": "📄",
            "video": "📹", "movie": "🎬", "film": "🎬", "youtube": "📺",
            "music": "🎵", "audio": "🎵", "sound": "🎵", "spotify": "🎵",
            "photo": "📷", "image": "📷", "picture": "📷", "instagram": "📷",
            "mail": "📧", "email": "📧", "gmail": "📧", "outlook": "📧",
            "shop": "🛒", "store": "🛒", "buy": "🛒", "amazon": "🛒",
            "news": "📰", "article": "📰", "blog": "📝", "read": "📖",
            "game": "🎮", "play": "🎮", "gaming": "🎮", "steam": "🎮",
            "social": "👥", "facebook": "👥", "twitter": "🐦", "linkedin": "💼",
            "github": "🐙", "git": "🐙", "repo": "📦", "code": "💻",
            "ai": "🤖", "ml": "🤖", "machine": "🤖", "learning": "🎓",
            "finance": "💰", "money": "💰", "bank": "🏦", "invest": "📈",
            "travel": "✈️", "trip": "✈️", "vacation": "🏖️", "hotel": "🏨",
            "food": "🍕", "recipe": "🍳", "restaurant": "🍽️", "cook": "👨‍🍳",
            "health": "💊", "medical": "🏥", "doctor": "👨‍⚕️", "fitness": "💪",
            "education": "🎓", "learn": "📚", "course": "📖", "school": "🏫",
            "work": "💼", "job": "💼", "career": "👔", "office": "🏢",
        }
        
        for keyword, icon in keyword_map.items():
            if keyword in text_lower:
                return icon
        
        return "📁"  # Default folder icon


# =============================================================================
# Screenshot Capture (for bookmarks)
# =============================================================================
class ScreenshotCapture:
    """Capture screenshots of web pages"""
    
    SCREENSHOT_DIR = DATA_DIR / "screenshots"
    
    def __init__(self):
        self.SCREENSHOT_DIR.mkdir(exist_ok=True)
    
    def capture(self, url: str, bookmark_id: int) -> Optional[str]:
        """
        Capture screenshot of a URL.
        Returns filepath or None on failure.
        
        Note: This uses a simple approach. For production, 
        consider using playwright, selenium, or a screenshot API.
        """
        try:
            # Try using a screenshot API service
            api_url = f"https://image.thum.io/get/width/1280/crop/800/{url}"
            
            response = requests.get(api_url, timeout=30)
            
            if response.status_code == 200:
                filename = f"screenshot_{bookmark_id}.png"
                filepath = self.SCREENSHOT_DIR / filename
                
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                return str(filepath)
        except Exception:
            pass
        
        return None
    
    def get_screenshot_path(self, bookmark_id: int) -> Optional[str]:
        """Get path to existing screenshot"""
        filepath = self.SCREENSHOT_DIR / f"screenshot_{bookmark_id}.png"
        if filepath.exists():
            return str(filepath)
        return None
    
    def delete_screenshot(self, bookmark_id: int):
        """Delete a screenshot"""
        filepath = self.SCREENSHOT_DIR / f"screenshot_{bookmark_id}.png"
        if filepath.exists():
            filepath.unlink()
    
    def get_cache_size(self) -> Tuple[int, int]:
        """Get screenshot cache size (count, bytes)"""
        files = list(self.SCREENSHOT_DIR.glob("*.png"))
        total_size = sum(f.stat().st_size for f in files)
        return len(files), total_size
    
    def clear_cache(self):
        """Clear all screenshots"""
        for f in self.SCREENSHOT_DIR.glob("*.png"):
            f.unlink()


# =============================================================================
# PDF Export (Save page as PDF)
# =============================================================================
class PDFExporter:
    """Export pages or bookmarks as PDF"""
    
    PDF_DIR = DATA_DIR / "pdfs"
    
    def __init__(self):
        self.PDF_DIR.mkdir(exist_ok=True)
    
    def save_page_as_pdf(self, url: str, title: str) -> Optional[str]:
        """
        Save a web page as PDF.
        Note: Full implementation would require a headless browser.
        This is a simplified version using weasyprint if available.
        """
        try:
            # Try to use weasyprint if available
            from weasyprint import HTML
            
            response = requests.get(url, timeout=30)
            if response.status_code != 200:
                return None
            
            safe_title = re.sub(r'[^\w\s-]', '', title)[:50]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{safe_title}_{timestamp}.pdf"
            filepath = self.PDF_DIR / filename
            
            HTML(string=response.text, base_url=url).write_pdf(str(filepath))
            
            return str(filepath)
        except ImportError:
            # weasyprint not available
            return None
        except Exception as e:
            print(f"PDF export failed: {e}")
            return None
    
    def export_bookmarks_pdf(self, bookmarks: List[Bookmark], filepath: str):
        """Export bookmark list as PDF document"""
        try:
            from weasyprint import HTML
            
            theme = get_theme()
            
            # Generate HTML for the bookmarks
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        h1 {{ color: #333; border-bottom: 2px solid #58a6ff; padding-bottom: 10px; }}
        .category {{ margin-top: 30px; }}
        .category h2 {{ color: #555; font-size: 16px; }}
        .bookmark {{ margin: 10px 0; padding: 10px; background: #f5f5f5; border-radius: 4px; }}
        .bookmark a {{ color: #0366d6; text-decoration: none; }}
        .bookmark .domain {{ color: #888; font-size: 12px; }}
        .bookmark .tags {{ color: #6e40c9; font-size: 11px; }}
    </style>
</head>
<body>
    <h1>📚 Bookmark Collection</h1>
    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    <p>Total: {len(bookmarks)} bookmarks</p>
"""
            
            # Group by category
            by_category: Dict[str, List[Bookmark]] = {}
            for bm in bookmarks:
                cat = bm.category or "Uncategorized"
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(bm)
            
            for category, cat_bookmarks in sorted(by_category.items()):
                html_content += f'<div class="category"><h2>{category} ({len(cat_bookmarks)})</h2>'
                
                for bm in cat_bookmarks:
                    tags_html = f'<div class="tags">{" ".join("#"+t for t in bm.tags)}</div>' if bm.tags else ''
                    html_content += f'''
                    <div class="bookmark">
                        <a href="{bm.url}">{bm.title}</a>
                        <div class="domain">{bm.domain}</div>
                        {tags_html}
                    </div>'''
                
                html_content += '</div>'
            
            html_content += '</body></html>'
            
            HTML(string=html_content).write_pdf(filepath)
            return True
        
        except ImportError:
            return False
        except Exception as e:
            print(f"PDF export failed: {e}")
            return False




# =============================================================================
# CLI Tool
# =============================================================================
class BookmarkCLI:
    """
        Represents a single bookmark with all metadata.
        
        Attributes:
            id: Unique integer identifier
            url: Bookmark URL
            title: Display title
            category: Category name
            tags: List of tag names
            ai_tags: List of AI-suggested tags
            description: Optional description
            favicon_url: URL to favicon image
            created_at: ISO timestamp of creation
            updated_at: ISO timestamp of last update
            visited_at: ISO timestamp of last visit
            visit_count: Number of times visited
            is_valid: Whether URL validation passed
            is_pinned: Whether bookmark is pinned
            ai_category: AI-suggested category
            ai_summary: AI-generated summary
            notes: User notes
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
            matches_search(query): Check if bookmark matches search
        """
    
    def __init__(self):
        self.category_manager = CategoryManager()
        self.tag_manager = TagManager()
        self.bookmark_manager = BookmarkManager(self.category_manager, self.tag_manager)
    
    def run(self, args: List[str]):
        """Run CLI command"""
        if not args:
            self._print_help()
            return
        
        command = args[0].lower()
        cmd_args = args[1:]
        
        commands = {
            "list": self._cmd_list,
            "add": self._cmd_add,
            "delete": self._cmd_delete,
            "search": self._cmd_search,
            "import": self._cmd_import,
            "export": self._cmd_export,
            "categories": self._cmd_categories,
            "tags": self._cmd_tags,
            "stats": self._cmd_stats,
            "check": self._cmd_check,
            "help": self._print_help,
        }
        
        if command in commands:
            commands[command](cmd_args)
        else:
            print(f"Unknown command: {command}")
            self._print_help()
    
    def _print_help(self, args=None):
        """Print help message"""
        print(f"""
{APP_NAME} CLI v{APP_VERSION}

Usage: python bookmark_organizer.py [command] [options]

Commands:
  list [category]        List bookmarks (optionally filter by category)
  add <url> [title]      Add a new bookmark
  delete <id>            Delete a bookmark by ID
  search <query>         Search bookmarks
  import <file>          Import bookmarks from file (HTML/JSON)
  export <file>          Export bookmarks to file
  categories             List all categories
  tags                   List all tags
  stats                  Show statistics
  check                  Check for broken links
  help                   Show this help message

Examples:
  python bookmark_organizer.py list
  python bookmark_organizer.py add https://example.com "Example Site"
  python bookmark_organizer.py search python
  python bookmark_organizer.py export bookmarks.html
""")
    
    def _cmd_list(self, args):
        """List bookmarks"""
        if args:
            category = ' '.join(args)
            bookmarks = self.bookmark_manager.get_bookmarks_by_category(category)
            print(f"\nBookmarks in '{category}':")
        else:
            bookmarks = self.bookmark_manager.get_all_bookmarks()
            print(f"\nAll Bookmarks ({len(bookmarks)}):")
        
        for bm in bookmarks[:50]:
            pin = "📌 " if bm.is_pinned else ""
            print(f"  [{bm.id}] {pin}{bm.title[:50]}")
            print(f"       {bm.url[:60]}")
            if bm.tags:
                print(f"       Tags: {', '.join(bm.tags)}")
            print()
    
    def _cmd_add(self, args):
        """Add a bookmark"""
        if not args:
            log.error("Error: URL required")
            return
        
        url = args[0]
        title = ' '.join(args[1:]) if len(args) > 1 else url
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        bookmark = Bookmark(
            id=None,
            url=url,
            title=title,
            category="Uncategorized / Needs Review"
        )
        
        self.bookmark_manager.add_bookmark(bookmark)
        print(f"✓ Added: {title}")
        print(f"  URL: {url}")
        print(f"  ID: {bookmark.id}")
    
    def _cmd_delete(self, args):
        """Delete a bookmark"""
        if not args:
            log.error("Error: Bookmark ID required")
            return
        
        try:
            bm_id = int(args[0])
            bookmark = self.bookmark_manager.get_bookmark(bm_id)
            
            if bookmark:
                self.bookmark_manager.delete_bookmark(bm_id)
                print(f"✓ Deleted: {bookmark.title}")
            else:
                log.error(f"Error: Bookmark with ID {bm_id} not found")
        except ValueError:
            log.error("Error: Invalid bookmark ID")
    
    def _cmd_search(self, args):
        """Search bookmarks"""
        if not args:
            log.error("Error: Search query required")
            return
        
        query = ' '.join(args)
        results = self.bookmark_manager.search_bookmarks(query)
        
        print(f"\nSearch results for '{query}' ({len(results)} found):")
        for bm in results[:20]:
            print(f"  [{bm.id}] {bm.title[:50]}")
            print(f"       {bm.domain} | {bm.category}")
    
    def _cmd_import(self, args):
        """Import bookmarks"""
        if not args:
            log.error("Error: File path required")
            return
        
        filepath = args[0]
        
        if not Path(filepath).exists():
            log.error(f"Error: File not found: {filepath}")
            return
        
        if filepath.endswith('.html') or filepath.endswith('.htm'):
            added, dupes = self.bookmark_manager.import_html_file(filepath)
        elif filepath.endswith('.json'):
            added, dupes = self.bookmark_manager.import_json_file(filepath)
        else:
            log.error("Error: Unsupported file format (use .html or .json)")
            return
        
        print(f"✓ Imported {added} bookmarks ({dupes} duplicates skipped)")
    
    def _cmd_export(self, args):
        """Export bookmarks"""
        if not args:
            log.error("Error: File path required")
            return
        
        filepath = args[0]
        
        if filepath.endswith('.html'):
            self.bookmark_manager.export_html(filepath)
        elif filepath.endswith('.json'):
            self.bookmark_manager.export_json(filepath)
        elif filepath.endswith('.csv'):
            self.bookmark_manager.export_csv(filepath)
        elif filepath.endswith('.md'):
            self.bookmark_manager.export_markdown(filepath)
        else:
            # Default to HTML
            filepath += '.html'
            self.bookmark_manager.export_html(filepath)
        
        count = len(self.bookmark_manager.bookmarks)
        print(f"✓ Exported {count} bookmarks to {filepath}")
    
    def _cmd_categories(self, args):
        """List categories"""
        counts = self.bookmark_manager.get_category_counts()
        
        print(f"\nCategories ({len(counts)}):")
        for cat, count in sorted(counts.items(), key=lambda x: -x[1]):
            icon = get_category_icon(cat)
            print(f"  {icon} {cat}: {count}")
    
    def _cmd_tags(self, args):
        """List tags"""
        counts = self.bookmark_manager.get_tag_counts()
        
        print(f"\nTags ({len(counts)}):")
        for tag, count in sorted(counts.items(), key=lambda x: -x[1])[:30]:
            print(f"  #{tag}: {count}")
    
    def _cmd_stats(self, args):
        """Show statistics"""
        stats = self.bookmark_manager.get_statistics()
        
        print(f"""
Bookmark Statistics
═══════════════════
Total Bookmarks:  {stats['total_bookmarks']}
Categories:       {stats['total_categories']}
Tags:             {stats['total_tags']}
Duplicates:       {stats['duplicate_bookmarks']}
Broken Links:     {stats['broken']}
Uncategorized:    {stats['uncategorized']}
With Tags:        {stats['with_tags']}
With Notes:       {stats['with_notes']}
Pinned:           {stats['pinned']}
Archived:         {stats['archived']}

Top Domains:
""")
        for domain, count in stats['top_domains'][:10]:
            print(f"  {domain}: {count}")
    
    def _cmd_check(self, args):
        """Check for broken links"""
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        print(f"Checking {len(bookmarks)} bookmarks for broken links...")
        print("(This may take a while)\n")
        
        broken = []
        for i, bm in enumerate(bookmarks):
            try:
                response = requests.head(bm.url, timeout=5, allow_redirects=True)
                if response.status_code >= 400:
                    broken.append((bm, response.status_code))
                    bm.is_valid = False
                else:
                    bm.is_valid = True
                bm.http_status = response.status_code
            except Exception:
                broken.append((bm, 0))
                bm.is_valid = False
                bm.http_status = 0
            
            # Progress
            if (i + 1) % 10 == 0:
                print(f"  Checked {i + 1}/{len(bookmarks)}...")
        
        self.bookmark_manager.save_bookmarks()
        
        print(f"\n✓ Check complete. Found {len(broken)} broken links:\n")
        for bm, status in broken[:20]:
            print(f"  [{bm.id}] {bm.title[:40]}")
            print(f"       {bm.url[:50]} (status: {status})")


# =============================================================================
# REST API (Simple Flask-like API using built-in http.server)
# =============================================================================
class BookmarkAPI:
    """
        Represents a single bookmark with all metadata.
        
        Attributes:
            id: Unique integer identifier
            url: Bookmark URL
            title: Display title
            category: Category name
            tags: List of tag names
            ai_tags: List of AI-suggested tags
            description: Optional description
            favicon_url: URL to favicon image
            created_at: ISO timestamp of creation
            updated_at: ISO timestamp of last update
            visited_at: ISO timestamp of last visit
            visit_count: Number of times visited
            is_valid: Whether URL validation passed
            is_pinned: Whether bookmark is pinned
            ai_category: AI-suggested category
            ai_summary: AI-generated summary
            notes: User notes
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
            matches_search(query): Check if bookmark matches search
        """
    
    def __init__(self, bookmark_manager: BookmarkManager, port: int = 8765):
        self.bookmark_manager = bookmark_manager
        self.port = port
        self._server = None
        self._thread = None
    
    def start(self):
        """Start the API server"""
        from http.server import HTTPServer, BaseHTTPRequestHandler
        
        bookmark_manager = self.bookmark_manager
        
        class APIHandler(BaseHTTPRequestHandler):
            def _send_json(self, data, status=200):
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())
            
            def _parse_path(self):
                """Parse URL path and query params"""
                parsed = urllib.parse.urlparse(self.path)
                path_parts = parsed.path.strip('/').split('/')
                query_params = urllib.parse.parse_qs(parsed.query)
                return path_parts, query_params
            
            def do_GET(self):
                path_parts, params = self._parse_path()
                
                if not path_parts or path_parts[0] == '':
                    # API info
                    self._send_json({
                        "name": APP_NAME,
                        "version": APP_VERSION,
                        "endpoints": [
                            "GET /bookmarks",
                            "GET /bookmarks/:id",
                            "POST /bookmarks",
                            "DELETE /bookmarks/:id",
                            "GET /categories",
                            "GET /tags",
                            "GET /stats",
                            "GET /search?q=query"
                        ]
                    })
                
                elif path_parts[0] == 'bookmarks':
                    if len(path_parts) > 1:
                        # Get single bookmark
                        try:
                            bm_id = int(path_parts[1])
                            bm = bookmark_manager.get_bookmark(bm_id)
                            if bm:
                                self._send_json(asdict(bm))
                            else:
                                self._send_json({"error": "Not found"}, 404)
                        except Exception:
                            self._send_json({"error": "Invalid ID"}, 400)
                    else:
                        # List bookmarks
                        category = params.get('category', [None])[0]
                        limit = int(params.get('limit', [100])[0])
                        
                        if category:
                            bookmarks = bookmark_manager.get_bookmarks_by_category(category)
                        else:
                            bookmarks = bookmark_manager.get_all_bookmarks()
                        
                        self._send_json({
                            "count": len(bookmarks),
                            "bookmarks": [asdict(bm) for bm in bookmarks[:limit]]
                        })
                
                elif path_parts[0] == 'categories':
                    counts = bookmark_manager.get_category_counts()
                    self._send_json({
                        "count": len(counts),
                        "categories": [
                            {"name": name, "count": count}
                            for name, count in sorted(counts.items())
                        ]
                    })
                
                elif path_parts[0] == 'tags':
                    counts = bookmark_manager.get_tag_counts()
                    self._send_json({
                        "count": len(counts),
                        "tags": [
                            {"name": name, "count": count}
                            for name, count in sorted(counts.items(), key=lambda x: -x[1])
                        ]
                    })
                
                elif path_parts[0] == 'stats':
                    stats = bookmark_manager.get_statistics()
                    self._send_json(stats)
                
                elif path_parts[0] == 'search':
                    query = params.get('q', [''])[0]
                    if query:
                        results = bookmark_manager.search_bookmarks(query)
                        self._send_json({
                            "query": query,
                            "count": len(results),
                            "results": [asdict(bm) for bm in results[:50]]
                        })
                    else:
                        self._send_json({"error": "Query parameter 'q' required"}, 400)
                
                else:
                    self._send_json({"error": "Not found"}, 404)
            
            def do_POST(self):
                path_parts, _ = self._parse_path()
                
                if path_parts[0] == 'bookmarks':
                    content_length = int(self.headers.get('Content-Length', 0))
                    body = self.rfile.read(content_length)
                    
                    try:
                        data = json.loads(body)
                        
                        if 'url' not in data:
                            self._send_json({"error": "URL required"}, 400)
                            return
                        
                        bookmark = Bookmark(
                            id=None,
                            url=data['url'],
                            title=data.get('title', data['url']),
                            category=data.get('category', 'Uncategorized'),
                            tags=data.get('tags', []),
                            notes=data.get('notes', '')
                        )
                        
                        bookmark_manager.add_bookmark(bookmark)
                        self._send_json(asdict(bookmark), 201)
                    
                    except json.JSONDecodeError:
                        self._send_json({"error": "Invalid JSON"}, 400)
                else:
                    self._send_json({"error": "Not found"}, 404)
            
            def do_DELETE(self):
                path_parts, _ = self._parse_path()
                
                if path_parts[0] == 'bookmarks' and len(path_parts) > 1:
                    try:
                        bm_id = int(path_parts[1])
                        if bookmark_manager.delete_bookmark(bm_id):
                            self._send_json({"success": True, "deleted": bm_id})
                        else:
                            self._send_json({"error": "Not found"}, 404)
                    except Exception:
                        self._send_json({"error": "Invalid ID"}, 400)
                else:
                    self._send_json({"error": "Not found"}, 404)
            
            def do_OPTIONS(self):
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type')
                self.end_headers()
            
            def log_message(self, format, *args):
                pass  # Suppress logging
        
        self._server = HTTPServer(('localhost', self.port), APIHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        
        print(f"API server started at http://localhost:{self.port}")
    
    def stop(self):
        """Stop the API server"""
        if self._server:
            self._server.shutdown()
            self._server = None


# =============================================================================
# Hover Preview (Tooltip with page info)
# =============================================================================
class HoverPreview:
    """Show preview tooltip on bookmark hover"""
    
    def __init__(self, parent: tk.Widget):
        self.parent = parent
        self.tooltip: Optional[tk.Toplevel] = None
        self._after_id = None
        self._delay = 500  # ms before showing tooltip
    
    def show(self, event, bookmark: Bookmark):
        """Schedule showing the preview"""
        self.hide()
        self._after_id = self.parent.after(
            self._delay, 
            lambda: self._create_tooltip(event, bookmark)
        )
    
    def _create_tooltip(self, event, bookmark: Bookmark):
        """Create and show the tooltip"""
        theme = get_theme()
        
        self.tooltip = tk.Toplevel(self.parent)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.configure(bg=theme.bg_dark)
        
        # Position near mouse
        x = event.x_root + 15
        y = event.y_root + 10
        
        # Main frame
        frame = tk.Frame(self.tooltip, bg=theme.bg_dark, padx=12, pady=10)
        frame.pack()
        
        # Title
        title = bookmark.title[:60] + "..." if len(bookmark.title) > 63 else bookmark.title
        tk.Label(
            frame, text=title, bg=theme.bg_dark,
            fg=theme.text_primary, font=("Segoe UI", 10, "bold"),
            wraplength=300, justify=tk.LEFT
        ).pack(anchor="w")
        
        # URL
        tk.Label(
            frame, text=bookmark.url[:50] + "..." if len(bookmark.url) > 53 else bookmark.url,
            bg=theme.bg_dark, fg=theme.text_link, font=FONTS.small()
        ).pack(anchor="w", pady=(5, 0))
        
        # Category and tags
        meta = f"📂 {bookmark.category}"
        if bookmark.tags:
            meta += f"  🏷️ {', '.join(bookmark.tags[:3])}"
        
        tk.Label(
            frame, text=meta, bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.small()
        ).pack(anchor="w", pady=(5, 0))
        
        # Notes preview if available
        if bookmark.notes:
            notes_preview = bookmark.notes[:100] + "..." if len(bookmark.notes) > 100 else bookmark.notes
            tk.Label(
                frame, text=notes_preview, bg=theme.bg_dark,
                fg=theme.text_secondary, font=FONTS.small(),
                wraplength=280, justify=tk.LEFT
            ).pack(anchor="w", pady=(8, 0))
        
        # Stats
        stats_parts = []
        if bookmark.visit_count > 0:
            stats_parts.append(f"👁️ {bookmark.visit_count} visits")
        if bookmark.created_at:
            try:
                created = datetime.fromisoformat(bookmark.created_at.replace('Z', '+00:00'))
                stats_parts.append(f"📅 Added {created.strftime('%Y-%m-%d')}")
            except Exception:
                pass
        
        if stats_parts:
            tk.Label(
                frame, text="  •  ".join(stats_parts), bg=theme.bg_dark,
                fg=theme.text_muted, font=FONTS.tiny()
            ).pack(anchor="w", pady=(5, 0))
        
        # Position tooltip
        self.tooltip.geometry(f"+{x}+{y}")
    
    def hide(self):
        """Hide the tooltip"""
        if self._after_id:
            self.parent.after_cancel(self._after_id)
            self._after_id = None
        
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None


# =============================================================================
# Auto-Icon Suggestion (AI-powered)
# =============================================================================
class AIIconSuggester:
    """Suggest icons for categories using AI or keyword matching"""
    
    KEYWORD_ICONS = {
        # Technology
        "code": "💻", "programming": "💻", "developer": "💻", "software": "💻",
        "github": "🐙", "git": "🐙", "repository": "📦",
        "api": "🔌", "database": "🗄️", "server": "🖥️", "cloud": "☁️",
        "security": "🔒", "network": "🌐", "web": "🌐", "internet": "🌐",
        
        # AI/ML
        "ai": "🤖", "artificial": "🤖", "machine learning": "🧠", "ml": "🧠",
        "neural": "🧠", "deep learning": "🧠", "data science": "📊",
        
        # Design
        "design": "🎨", "ui": "🎨", "ux": "🎨", "graphic": "🎨",
        "photo": "📷", "image": "🖼️", "video": "🎬", "audio": "🎵",
        
        # Business
        "business": "💼", "work": "💼", "career": "👔", "job": "💼",
        "finance": "💰", "money": "💵", "invest": "📈", "stock": "📈",
        "marketing": "📢", "sales": "🤝", "customer": "👥",
        
        # Education
        "education": "🎓", "learn": "📚", "course": "📖", "tutorial": "📝",
        "school": "🏫", "university": "🎓", "research": "🔬",
        
        # Entertainment
        "game": "🎮", "gaming": "🎮", "movie": "🎬", "music": "🎵",
        "book": "📚", "reading": "📖", "news": "📰", "blog": "📝",
        
        # Social
        "social": "👥", "community": "👥", "forum": "💬", "chat": "💬",
        "twitter": "🐦", "facebook": "👤", "linkedin": "💼",
        
        # Shopping
        "shop": "🛒", "store": "🏪", "buy": "🛍️", "amazon": "📦",
        "deal": "🏷️", "coupon": "🎟️",
        
        # Travel
        "travel": "✈️", "trip": "🧳", "hotel": "🏨", "flight": "✈️",
        "vacation": "🏖️", "map": "🗺️",
        
        # Health
        "health": "💊", "medical": "🏥", "fitness": "💪", "exercise": "🏃",
        "diet": "🥗", "nutrition": "🍎",
        
        # Food
        "food": "🍕", "recipe": "🍳", "restaurant": "🍽️", "cooking": "👨‍🍳",
        "coffee": "☕", "drink": "🥤",
    }
    
    @classmethod
    def suggest_icon(cls, category_name: str) -> str:
        """Suggest an icon based on category name"""
        name_lower = category_name.lower()
        
        # Check keyword matches
        for keyword, icon in cls.KEYWORD_ICONS.items():
            if keyword in name_lower:
                return icon
        
        # Check partial matches
        for keyword, icon in cls.KEYWORD_ICONS.items():
            if any(word in name_lower for word in keyword.split()):
                return icon
        
        # Use IconLibrary for broader matching
        flat_icons = IconLibrary.get_flat_icons()
        for icon_name, icon in flat_icons.items():
            if icon_name.replace('_', ' ') in name_lower or name_lower in icon_name:
                return icon
        
        # Default folder icon
        return "📁"
    
    @classmethod
    def suggest_multiple(cls, category_name: str, count: int = 5) -> List[str]:
        """Suggest multiple icon options"""
        suggestions = []
        name_lower = category_name.lower()
        
        # Collect all matching icons
        for keyword, icon in cls.KEYWORD_ICONS.items():
            if keyword in name_lower or any(w in name_lower for w in keyword.split()):
                if icon not in suggestions:
                    suggestions.append(icon)
        
        # Add defaults if needed
        defaults = ["📁", "📂", "🗂️", "📋", "🔖"]
        for icon in defaults:
            if icon not in suggestions:
                suggestions.append(icon)
        
        return suggestions[:count]


# =============================================================================
# Main entry point update for CLI support
# =============================================================================


# =============================================================================
# OPTIMIZED FAVICON MANAGER (Non-blocking, CPU-friendly)
# =============================================================================
class OptimizedFaviconManager:
    """
    Optimized favicon manager with:
    - Background downloading with rate limiting
    - Queue-based processing
    - CPU-friendly with sleep intervals
    - Progress callbacks
    - Lazy loading support
    """
    
    CACHE_DIR = DATA_DIR / "favicons"
    
    # Sources for favicon fetching
    FAVICON_SOURCES = [
        "https://www.google.com/s2/favicons?domain={domain}&sz=32",
        "https://icons.duckduckgo.com/ip3/{domain}.ico",
        "https://api.faviconkit.com/{domain}/32",
        "https://{domain}/favicon.ico",
    ]
    
    def __init__(self):
        self.CACHE_DIR.mkdir(exist_ok=True)
        self._cache: Dict[str, Optional[str]] = {}
        self._queue: queue.Queue = queue.Queue()
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
        self._progress_callback: Optional[Callable] = None
        self._on_favicon_ready: Optional[Callable] = None
        self._total_queued = 0
        self._completed = 0
        self._failed = 0
        
        # Rate limiting
        self._requests_per_second = 2  # Max 2 requests per second
        self._last_request_time = 0
        
        # Load existing cache
        self._load_cache_index()
    
    def _load_cache_index(self):
        """Load index of cached favicons"""
        for filepath in self.CACHE_DIR.glob("*.png"):
            domain = filepath.stem
            self._cache[domain] = str(filepath)
        
        for filepath in self.CACHE_DIR.glob("*.ico"):
            domain = filepath.stem
            if domain not in self._cache:
                self._cache[domain] = str(filepath)
    
    def start_background_worker(self):
        """Start the background favicon download worker"""
        if self._running:
            return
        
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
    
    def stop_background_worker(self):
        """Stop the background worker"""
        self._running = False
        if self._worker_thread:
            self._queue.put(None)  # Signal to stop
    
    def _worker_loop(self):
        """Background worker loop - processes favicon queue"""
        while self._running:
            try:
                # Get next item with timeout (allows checking _running flag)
                item = self._queue.get(timeout=0.5)
                
                if item is None:  # Stop signal
                    break
                
                domain, bookmark_id = item
                
                # Rate limiting - sleep if needed
                elapsed = time.time() - self._last_request_time
                min_interval = 1.0 / self._requests_per_second
                if elapsed < min_interval:
                    time.sleep(min_interval - elapsed)
                
                # Download favicon
                filepath = self._download_favicon(domain)
                self._last_request_time = time.time()
                
                self._completed += 1
                
                if filepath:
                    self._cache[domain] = filepath
                    # Notify that favicon is ready
                    if self._on_favicon_ready:
                        try:
                            self._on_favicon_ready(domain, filepath, bookmark_id)
                        except Exception:
                            pass
                else:
                    self._failed += 1
                
                # Update progress
                if self._progress_callback:
                    try:
                        self._progress_callback(self._completed, self._total_queued, domain)
                    except Exception:
                        pass
                
                # Small sleep to prevent CPU hogging
                time.sleep(0.05)
                
            except queue.Empty:
                continue
            except Exception as e:
                self._failed += 1
                time.sleep(0.1)
    
    def _download_favicon(self, domain: str) -> Optional[str]:
        """Download favicon from multiple sources"""
        for source_template in self.FAVICON_SOURCES:
            try:
                url = source_template.format(domain=domain)
                
                response = requests.get(
                    url, 
                    timeout=5,
                    headers={'User-Agent': 'Mozilla/5.0'},
                    stream=True  # Stream to avoid memory issues
                )
                
                if response.status_code == 200:
                    content_type = response.headers.get('content-type', '')
                    
                    # Determine extension
                    if 'png' in content_type:
                        ext = 'png'
                    elif 'ico' in content_type or 'icon' in content_type:
                        ext = 'ico'
                    else:
                        ext = 'png'
                    
                    filepath = self.CACHE_DIR / f"{domain}.{ext}"
                    
                    # Write in chunks to avoid memory issues
                    with open(filepath, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=1024):
                            f.write(chunk)
                    
                    return str(filepath)
            except Exception:
                continue
        
        return None
    
    def queue_favicon(self, domain: str, bookmark_id: int = 0, priority: bool = False):
        """Add a favicon to the download queue"""
        # Skip if already cached
        if domain in self._cache:
            if self._on_favicon_ready:
                self._on_favicon_ready(domain, self._cache[domain], bookmark_id)
            return
        
        self._total_queued += 1
        
        if priority:
            # For priority, we'd need a priority queue - simplified here
            self._queue.put((domain, bookmark_id))
        else:
            self._queue.put((domain, bookmark_id))
    
    def queue_bookmarks(self, bookmarks: List[Bookmark]):
        """Queue all bookmarks for favicon download"""
        # Get unique domains
        domains_seen = set()
        for bm in bookmarks:
            if bm.domain not in domains_seen and bm.domain not in self._cache:
                domains_seen.add(bm.domain)
                self._queue.put((bm.domain, bm.id))
                self._total_queued += 1
    
    def get_favicon_path(self, domain: str) -> Optional[str]:
        """Get cached favicon path (non-blocking)"""
        return self._cache.get(domain)
    
    def get_or_placeholder(self, domain: str) -> Tuple[str, bool]:
        """
        Get favicon path or generate placeholder.
        Returns (path_or_placeholder_data, is_real_favicon)
        """
        if domain in self._cache:
            return self._cache[domain], True
        return self._generate_placeholder(domain), False
    
    def _generate_placeholder(self, domain: str) -> str:
        """Generate a text-based placeholder (returns the letter and color)"""
        letter = domain[0].upper() if domain else "?"
        # Generate consistent color from domain
        colors = ["#58a6ff", "#3fb950", "#f0883e", "#a371f7", "#f778ba", "#79c0ff"]
        color = colors[hash(domain) % len(colors)]
        return f"placeholder:{letter}:{color}"
    
    def set_progress_callback(self, callback: Callable):
        """Set callback for progress updates: callback(completed, total, current_domain)"""
        self._progress_callback = callback
    
    def set_favicon_ready_callback(self, callback: Callable):
        """Set callback when favicon is ready: callback(domain, filepath, bookmark_id)"""
        self._on_favicon_ready = callback
    
    @property
    def progress(self) -> Tuple[int, int, int]:
        """Get progress: (completed, total, failed)"""
        return self._completed, self._total_queued, self._failed
    
    @property
    def is_downloading(self) -> bool:
        """Check if downloads are in progress"""
        return not self._queue.empty()
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        files = list(self.CACHE_DIR.glob("*"))
        total_size = sum(f.stat().st_size for f in files if f.is_file())
        
        return {
            "cached_count": len(self._cache),
            "file_count": len(files),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2)
        }
    
    def clear_cache(self):
        """Clear all cached favicons"""
        for f in self.CACHE_DIR.glob("*"):
            f.unlink()
        self._cache.clear()


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
        
        self._progress = min(value, self._max)
        
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
        super().__init__(parent, bg=theme.bg_secondary, padx=20, pady=15)
        
        self.on_files_dropped = on_files_dropped
        self._drag_active = False
        
        self.configure(highlightbackground=theme.border, highlightthickness=2)
        
        # Icon
        self.icon_label = tk.Label(
            self, text="📥", bg=theme.bg_secondary,
            font=("Segoe UI Emoji", 32)
        )
        self.icon_label.pack(pady=(10, 5))
        
        # Main text
        self.main_label = tk.Label(
            self, text="Drop Bookmark Files Here", bg=theme.bg_secondary,
            fg=theme.text_primary, font=("Segoe UI", 11, "bold")
        )
        self.main_label.pack()
        
        # Supported formats
        formats_text = "Supports: " + ", ".join(self.SUPPORTED_FORMATS.values())
        self.formats_label = tk.Label(
            self, text=formats_text, bg=theme.bg_secondary,
            fg=theme.text_muted, font=FONTS.small()
        )
        self.formats_label.pack(pady=(5, 0))
        
        # Browse button
        self.browse_btn = ModernButton(
            self, text="Browse Files", icon="📁",
            command=self._browse_files
        )
        self.browse_btn.pack(pady=(15, 10))
        
        # Bind events (note: true drag-drop requires tkinterdnd2 or similar)
        # For now, we'll use click-to-browse and simulated drop
        self.bind("<Button-1>", lambda e: self._browse_files())
        for child in self.winfo_children():
            child.bind("<Button-1>", lambda e: self._browse_files())
        
        # Visual feedback on hover
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
    
    def _on_enter(self, e):
        """Mouse enter - highlight"""
        theme = get_theme()
        self.configure(highlightbackground=theme.accent_primary)
    
    def _on_leave(self, e):
        """Mouse leave - reset"""
        theme = get_theme()
        self.configure(highlightbackground=theme.border)
    
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
                "No Valid Files",
                "No supported bookmark files found.\n\n" +
                "Supported formats: " + ", ".join(self.SUPPORTED_FORMATS.keys())
            )
    
    def set_importing(self, is_importing: bool):
        """Visual feedback during import"""
        theme = get_theme()
        
        if is_importing:
            self.icon_label.configure(text="⏳")
            self.main_label.configure(text="Importing...")
            self.browse_btn.state = "disabled"
            self.browse_btn.label.configure(fg=theme.text_muted, cursor="arrow")
        else:
            self.icon_label.configure(text="📥")
            self.main_label.configure(text="Drop Bookmark Files Here")
            self.browse_btn.state = "normal"
            self.browse_btn.label.configure(fg=theme.text_primary, cursor="hand2")


# =============================================================================
# ADDITIONAL BOOKMARK FILE FORMAT IMPORTERS
# =============================================================================
class TextURLImporter:
    """Import URLs from plain text files (one URL per line)"""
    
    URL_PATTERN = re.compile(
        r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[^\s]*',
        re.IGNORECASE
    )
    
    @staticmethod
    def import_from_text(filepath: str) -> List[Bookmark]:
        """Import URLs from text file"""
        bookmarks = []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Find all URLs
            urls = TextURLImporter.URL_PATTERN.findall(content)
            
            for url in urls:
                # Clean URL
                url = url.strip().rstrip('.,;:!?')
                
                if url:
                    bm = Bookmark(
                        id=None,
                        url=url,
                        title=url,  # Will be fetched later
                        category="Imported from Text"
                    )
                    bookmarks.append(bm)
        
        except Exception as e:
            print(f"Error importing text file: {e}")
        
        return bookmarks


class OPMLImporter:
    """Import bookmarks from OPML files"""
    
    @staticmethod
    def import_from_opml(filepath: str) -> List[Bookmark]:
        """Import from OPML file"""
        bookmarks = []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse outline elements with xmlUrl or htmlUrl
            outline_pattern = r'<outline[^>]*(?:xmlUrl|htmlUrl)="([^"]*)"[^>]*(?:text|title)="([^"]*)"[^>]*/?\s*>'
            matches = re.findall(outline_pattern, content, re.IGNORECASE)
            
            for url, title in matches:
                if url:
                    bm = Bookmark(
                        id=None,
                        url=url,
                        title=title or url,
                        category="Imported from OPML"
                    )
                    bookmarks.append(bm)
            
            # Also try alternate format
            if not bookmarks:
                alt_pattern = r'<outline[^>]*text="([^"]*)"[^>]*(?:xmlUrl|htmlUrl)="([^"]*)"[^>]*/?\s*>'
                matches = re.findall(alt_pattern, content, re.IGNORECASE)
                
                for title, url in matches:
                    if url:
                        bm = Bookmark(
                            id=None,
                            url=url,
                            title=title or url,
                            category="Imported from OPML"
                        )
                        bookmarks.append(bm)
        
        except Exception as e:
            print(f"Error importing OPML: {e}")
        
        return bookmarks


class OneTabImporter:
    """Import from OneTab export format"""
    
    @staticmethod
    def import_from_onetab(filepath: str) -> List[Bookmark]:
        """Import from OneTab export (pipe-separated format)"""
        bookmarks = []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # OneTab format: URL | Title
                    if ' | ' in line:
                        parts = line.split(' | ', 1)
                        url = parts[0].strip()
                        title = parts[1].strip() if len(parts) > 1 else url
                    else:
                        url = line
                        title = line
                    
                    if url.startswith(('http://', 'https://')):
                        bm = Bookmark(
                            id=None,
                            url=url,
                            title=title,
                            category="Imported from OneTab"
                        )
                        bookmarks.append(bm)
        
        except Exception as e:
            print(f"Error importing OneTab: {e}")
        
        return bookmarks


class NetscapeBookmarkImporter:
    """Enhanced Netscape bookmark format parser (used by most browsers)"""
    
    @staticmethod
    def import_from_netscape(filepath: str) -> List[Bookmark]:
        """Import from Netscape/Mozilla bookmark format"""
        bookmarks = []
        current_folder = "Imported"
        folder_stack = []
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Process line by line
            lines = content.split('\n')
            
            for line in lines:
                line = line.strip()
                
                # Folder start
                folder_match = re.search(r'<H3[^>]*>([^<]+)</H3>', line, re.IGNORECASE)
                if folder_match:
                    folder_name = folder_match.group(1).strip()
                    folder_stack.append(current_folder)
                    current_folder = folder_name
                    continue
                
                # Folder end
                if '</DL>' in line.upper():
                    if folder_stack:
                        current_folder = folder_stack.pop()
                    continue
                
                # Bookmark
                bm_match = re.search(
                    r'<A[^>]*HREF="([^"]*)"[^>]*>([^<]*)</A>',
                    line, re.IGNORECASE
                )
                if bm_match:
                    url = bm_match.group(1)
                    title = bm_match.group(2).strip()
                    
                    if url and url.startswith(('http://', 'https://')):
                        # Try to get ADD_DATE
                        add_date_match = re.search(r'ADD_DATE="(\d+)"', line, re.IGNORECASE)
                        
                        bm = Bookmark(
                            id=None,
                            url=url,
                            title=title or url,
                            category=current_folder
                        )
                        
                        if add_date_match:
                            try:
                                timestamp = int(add_date_match.group(1))
                                bm.created_at = datetime.fromtimestamp(timestamp).isoformat()
                            except Exception:
                                pass
                        
                        # Try to get tags
                        tags_match = re.search(r'TAGS="([^"]*)"', line, re.IGNORECASE)
                        if tags_match:
                            tags = tags_match.group(1)
                            bm.tags = [t.strip() for t in tags.split(',') if t.strip()]
                        
                        bookmarks.append(bm)
        
        except Exception as e:
            print(f"Error importing Netscape bookmarks: {e}")
        
        return bookmarks




# =============================================================================
# SORTABLE TREEVIEW WITH FAVICONS
# =============================================================================
class SortableTreeview(ttk.Treeview):
    """
    Enhanced Treeview with:
    - Sortable columns (click header)
    - Favicon support
    - Better performance
    """
    
    def __init__(self, parent, columns, **kwargs):
        super().__init__(parent, columns=columns, **kwargs)
        
        self._sort_column = None
        self._sort_reverse = False
        self._favicon_images: Dict[str, tk.PhotoImage] = {}
        self._placeholder_images: Dict[str, tk.PhotoImage] = {}
        
        # Setup column headers for sorting
        for col in columns:
            self.heading(col, command=lambda c=col: self._sort_by_column(c))
        
        # Also make #0 (tree column) sortable if shown
        self.heading("#0", command=lambda: self._sort_by_column("#0"))
    
    def _sort_by_column(self, column: str):
        """Sort treeview by column"""
        # Get all items
        items = [(self.set(item, column) if column != "#0" else self.item(item, "text"), item) 
                 for item in self.get_children('')]
        
        # Toggle sort direction
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = False
        
        # Sort items
        try:
            # Try numeric sort first
            items.sort(key=lambda x: float(x[0]) if x[0] else 0, reverse=self._sort_reverse)
        except (ValueError, TypeError):
            # Fall back to string sort
            items.sort(key=lambda x: str(x[0]).lower(), reverse=self._sort_reverse)
        
        # Rearrange items
        for index, (_, item) in enumerate(items):
            self.move(item, '', index)
        
        # Update header to show sort direction
        for col in self["columns"]:
            current_text = str(self.heading(col, "text"))
            # Remove existing sort indicators
            current_text = current_text.replace(" ▲", "").replace(" ▼", "")
            
            if col == column:
                indicator = " ▼" if self._sort_reverse else " ▲"
                self.heading(col, text=current_text + indicator)
            else:
                self.heading(col, text=current_text)
    
    def set_favicon(self, item_id: str, image_path: str):
        """Set favicon for an item"""
        try:
            # Check if already loaded
            if image_path in self._favicon_images:
                self.item(item_id, image=self._favicon_images[image_path])
                return
            
            # Load image
            if image_path.endswith('.ico'):
                # For ICO files, try to load with PIL if available
                try:
                    from PIL import Image, ImageTk
                    img = Image.open(image_path)
                    img = img.resize((16, 16), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                except Exception:
                    # Fallback - try direct load
                    photo = tk.PhotoImage(file=image_path)
                    try:
                        photo = photo.subsample(photo.width() // 16, photo.height() // 16)
                    except Exception:
                        pass
            else:
                # PNG or other format
                try:
                    from PIL import Image, ImageTk
                    img = Image.open(image_path)
                    img = img.resize((16, 16), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                except Exception:
                    photo = tk.PhotoImage(file=image_path)
                    try:
                        photo = photo.subsample(max(1, photo.width() // 16), max(1, photo.height() // 16))
                    except Exception:
                        pass
            
            self._favicon_images[image_path] = photo
            self.item(item_id, image=photo)
        except Exception as e:
            pass  # Silently fail - favicon not critical
    
    def set_placeholder(self, item_id: str, letter: str, color: str):
        """Set placeholder image for an item"""
        key = f"{letter}_{color}"
        
        if key not in self._placeholder_images:
            # Create a simple colored square with letter
            # This is a minimal placeholder - real implementation would draw properly
            try:
                size = 16
                from PIL import Image, ImageDraw, ImageFont, ImageTk
                
                img = Image.new('RGB', (size, size), color)
                draw = ImageDraw.Draw(img)
                
                # Draw letter
                try:
                    font = ImageFont.truetype("arial.ttf", 10)
                except Exception:
                    font = ImageFont.load_default()
                
                # Center letter
                bbox = draw.textbbox((0, 0), letter, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                x = (size - text_width) // 2
                y = (size - text_height) // 2 - 2
                
                draw.text((x, y), letter, fill="white", font=font)
                
                photo = ImageTk.PhotoImage(img)
                self._placeholder_images[key] = photo
            except Exception:
                return  # Can't create placeholder
        
        if key in self._placeholder_images:
            self.item(item_id, image=self._placeholder_images[key])


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
            fg=theme.text_muted, font=("Segoe UI", 12),
            cursor="hand2", padx=10
        )
        self.refresh_btn.pack(side=tk.RIGHT)
        self.refresh_btn.bind("<Button-1>", lambda e: self.refresh())
        
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
            fg=theme.text_secondary, font=("Segoe UI", 9, "bold"),
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
            self, text="Favicons: Ready", bg=theme.bg_dark,
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
        
        self.status_label.configure(text=f"Favicons: {completed}/{total}")
        self.progress_fill.place(relwidth=pct/100)
        
        if completed >= total:
            self.status_label.configure(text=f"Favicons: {completed} ✓")
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
# ENHANCED BOOKMARK ORGANIZER APP (with all optimizations)
# =============================================================================
class EnhancedBookmarkOrganizerApp(ThemedWidget):
    """
    Enhanced main application with:
    - Optimized favicon loading
    - Analytics dashboard in sidebar
    - Drag-drop import
    - Sortable list view
    - Default list view with favicons
    - Clear progress displays
    """
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("1400x900")
        self.root.minsize(1000, 600)
        
        theme = get_theme()
        self.root.configure(bg=theme.bg_primary)
        
        # Dark title bar on Windows
        set_dark_title_bar(self.root)
        
        # Initialize managers
        self.category_manager = CategoryManager()
        self.tag_manager = TagManager()
        self.bookmark_manager = BookmarkManager(self.category_manager, self.tag_manager)
        self.favicon_manager = OptimizedFaviconManager()
        self.command_stack = CommandStack()
        
        # View state
        self.view_mode = ViewMode.LIST  # Default to list view
        self.current_category: Optional[str] = None
        self.search_query: str = ""
        self.selected_bookmarks: List[int] = []
        
        # Setup favicon callbacks
        self.favicon_manager.set_progress_callback(self._on_favicon_progress)
        self.favicon_manager.set_favicon_ready_callback(self._on_favicon_ready)
        
        # Build UI
        self._setup_styles()
        self._create_menu()
        self._create_main_layout()
        self._create_status_bar()
        
        # Load data and start favicon downloads
        self._load_and_display_data()
        
        # Start favicon background worker
        self.favicon_manager.start_background_worker()
        
        # Bind window events
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Control-f>", lambda e: self.search_entry.focus_set())
        self.root.bind("<Control-n>", lambda e: self._add_bookmark())
        self.root.bind("<Control-i>", lambda e: self._show_import_dialog())
        self.root.bind("<F5>", lambda e: self._refresh_all())
    
    def _setup_styles(self):
        """Configure ttk styles"""
        theme = get_theme()
        style = ttk.Style()
        
        try:
            style.theme_use('clam')
        except Exception:
            pass
        
        # Treeview styles
        style.configure(
            "Treeview",
            background=theme.bg_primary,
            foreground=theme.text_primary,
            fieldbackground=theme.bg_primary,
            borderwidth=0,
            rowheight=28  # Slightly taller for favicons
        )
        
        style.configure(
            "Treeview.Heading",
            background=theme.bg_secondary,
            foreground=theme.text_primary,
            borderwidth=0,
            font=("Segoe UI", 9, "bold")
        )
        
        style.map(
            "Treeview",
            background=[("selected", theme.selection)],
            foreground=[("selected", theme.text_primary)]
        )
    
    def _create_menu(self):
        """Create menu bar"""
        theme = get_theme()
        
        menubar = tk.Menu(self.root, bg=theme.bg_dark, fg=theme.text_primary,
                         activebackground=theme.selection, activeforeground=theme.text_primary,
                         borderwidth=0)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary)
        file_menu.add_command(label="New Bookmark", accelerator="Ctrl+N", command=self._add_bookmark)
        file_menu.add_separator()
        file_menu.add_command(label="Import...", accelerator="Ctrl+I", command=self._show_import_dialog)
        file_menu.add_command(label="Export...", command=self._show_export_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary)
        edit_menu.add_command(label="Undo", accelerator="Ctrl+Z", command=self._undo)
        edit_menu.add_command(label="Redo", accelerator="Ctrl+Y", command=self._redo)
        edit_menu.add_separator()
        edit_menu.add_command(label="Select All", accelerator="Ctrl+A", command=self._select_all)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary)
        view_menu.add_command(label="List View", command=lambda: self._set_view_mode(ViewMode.LIST))
        view_menu.add_command(label="Grid View", command=lambda: self._set_view_mode(ViewMode.GRID))
        view_menu.add_separator()
        view_menu.add_command(label="Refresh", accelerator="F5", command=self._refresh_all)
        menubar.add_cascade(label="View", menu=view_menu)
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary)
        tools_menu.add_command(label="Check Links", command=self._check_all_links)
        tools_menu.add_command(label="Find Duplicates", command=self._find_duplicates)
        tools_menu.add_command(label="Clean URLs", command=self._clean_urls)
        tools_menu.add_separator()
        tools_menu.add_command(label="Full Analytics", command=self._show_analytics)
        tools_menu.add_command(label="Theme Settings", command=self._show_theme_settings)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        
        self.root.config(menu=menubar)
    
    def _create_main_layout(self):
        """Create main application layout"""
        theme = get_theme()
        
        # Main container
        self.main_container = tk.Frame(self.root, bg=theme.bg_primary)
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        # ===== HEADER =====
        header = tk.Frame(self.main_container, bg=theme.bg_dark, height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        # Logo/Title
        tk.Label(
            header, text=f"📚 {APP_NAME}", bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.title(bold=False)
        ).pack(side=tk.LEFT, padx=20, pady=15)
        
        # Search bar
        search_frame = tk.Frame(header, bg=theme.bg_secondary)
        search_frame.pack(side=tk.LEFT, padx=20, fill=tk.X, expand=True, pady=12)
        
        tk.Label(
            search_frame, text="🔍", bg=theme.bg_secondary,
            fg=theme.text_muted, font=("Segoe UI", 12)
        ).pack(side=tk.LEFT, padx=(10, 5))
        
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', self._on_search_change)
        
        self.search_entry = tk.Entry(
            search_frame, textvariable=self.search_var,
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            font=FONTS.body(), width=40
        )
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=5)
        
        # View mode toggle
        view_frame = tk.Frame(header, bg=theme.bg_dark)
        view_frame.pack(side=tk.RIGHT, padx=20)
        
        self.list_btn = ModernButton(
            view_frame, text="☰", command=lambda: self._set_view_mode(ViewMode.LIST),
            style="primary" if self.view_mode == ViewMode.LIST else "default"
        )
        self.list_btn.pack(side=tk.LEFT, padx=2)
        
        self.grid_btn = ModernButton(
            view_frame, text="▦", command=lambda: self._set_view_mode(ViewMode.GRID),
            style="primary" if self.view_mode == ViewMode.GRID else "default"
        )
        self.grid_btn.pack(side=tk.LEFT, padx=2)
        
        # ===== CONTENT AREA =====
        content = tk.Frame(self.main_container, bg=theme.bg_primary)
        content.pack(fill=tk.BOTH, expand=True)
        
        # ----- LEFT SIDEBAR -----
        self.sidebar = tk.Frame(content, bg=theme.bg_secondary, width=280)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)
        
        # Drag-drop import area
        self.import_area = DragDropImportArea(
            self.sidebar, on_files_dropped=self._on_files_dropped
        )
        self.import_area.pack(fill=tk.X, padx=10, pady=10)
        
        # Quick filters
        filters_frame = tk.Frame(self.sidebar, bg=theme.bg_secondary)
        filters_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        tk.Label(
            filters_frame, text="Quick Filters", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", pady=(5, 5))
        
        self.filter_buttons = {}
        for filter_name, icon in [("All", "📚"), ("Pinned", "📌"), ("Recent", "🕐"), ("Broken", "⚠️")]:
            btn = tk.Label(
                filters_frame, text=f"{icon} {filter_name}",
                bg=theme.bg_secondary, fg=theme.text_primary,
                font=FONTS.body(), cursor="hand2",
                padx=10, pady=5
            )
            btn.pack(fill=tk.X, pady=1)
            btn.bind("<Button-1>", lambda e, f=filter_name: self._apply_filter(f))
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=theme.bg_hover))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=theme.bg_secondary))
            self.filter_buttons[filter_name] = btn
        
        # Categories
        cat_header = tk.Frame(self.sidebar, bg=theme.bg_secondary)
        cat_header.pack(fill=tk.X, padx=10, pady=(15, 5))
        
        tk.Label(
            cat_header, text="Categories", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=("Segoe UI", 9, "bold")
        ).pack(side=tk.LEFT)
        
        # Category list with scroll
        cat_container = tk.Frame(self.sidebar, bg=theme.bg_secondary)
        cat_container.pack(fill=tk.BOTH, expand=True, padx=10)
        
        cat_canvas = tk.Canvas(cat_container, bg=theme.bg_secondary, highlightthickness=0)
        cat_scrollbar = ttk.Scrollbar(cat_container, orient="vertical", command=cat_canvas.yview)
        self.categories_frame = tk.Frame(cat_canvas, bg=theme.bg_secondary)
        
        self.categories_frame.bind(
            "<Configure>",
            lambda e: cat_canvas.configure(scrollregion=cat_canvas.bbox("all"))
        )
        
        cat_canvas.create_window((0, 0), window=self.categories_frame, anchor="nw", width=250)
        cat_canvas.configure(yscrollcommand=cat_scrollbar.set)
        
        cat_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        cat_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Mini Analytics Dashboard
        self.mini_analytics = MiniAnalyticsDashboard(self.sidebar, self.bookmark_manager)
        self.mini_analytics.pack(fill=tk.X, padx=10, pady=10, side=tk.BOTTOM)
        
        # ----- MAIN CONTENT -----
        self.content_area = tk.Frame(content, bg=theme.bg_primary)
        self.content_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Toolbar
        toolbar = tk.Frame(self.content_area, bg=theme.bg_primary)
        toolbar.pack(fill=tk.X, padx=15, pady=10)
        
        ModernButton(
            toolbar, text="Add", icon="➕", style="primary",
            command=self._add_bookmark
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ModernButton(
            toolbar, text="Import", icon="📥",
            command=self._show_import_dialog
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ModernButton(
            toolbar, text="Export", icon="📤",
            command=self._show_export_dialog
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        # Bookmark count
        self.count_label = tk.Label(
            toolbar, text="0 bookmarks", bg=theme.bg_primary,
            fg=theme.text_muted, font=FONTS.body()
        )
        self.count_label.pack(side=tk.RIGHT)
        
        # ----- LIST VIEW -----
        self.list_frame = tk.Frame(self.content_area, bg=theme.bg_primary)
        
        # Create sortable treeview
        columns = ("title", "url", "category", "tags", "added")
        self.tree = SortableTreeview(
            self.list_frame, columns=columns, show="tree headings",
            selectmode="extended"
        )
        
        # Configure columns
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=30, stretch=False)  # For favicon
        
        self.tree.heading("title", text="Title")
        self.tree.column("title", width=300)
        
        self.tree.heading("url", text="URL")
        self.tree.column("url", width=250)
        
        self.tree.heading("category", text="Category")
        self.tree.column("category", width=150)
        
        self.tree.heading("tags", text="Tags")
        self.tree.column("tags", width=150)
        
        self.tree.heading("added", text="Added")
        self.tree.column("added", width=100)
        
        # Scrollbars
        tree_scroll_y = ttk.Scrollbar(self.list_frame, orient="vertical", command=self.tree.yview)
        tree_scroll_x = ttk.Scrollbar(self.list_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)
        
        # Pack tree
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Tree bindings
        self.tree.bind("<Double-1>", self._on_item_double_click)
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<<TreeviewSelect>>", self._on_selection_change)
        
        # ----- GRID VIEW -----
        self.grid_frame = tk.Frame(self.content_area, bg=theme.bg_primary)
        
        grid_canvas = tk.Canvas(self.grid_frame, bg=theme.bg_primary, highlightthickness=0)
        grid_scrollbar = ttk.Scrollbar(self.grid_frame, orient="vertical", command=grid_canvas.yview)
        self.grid_inner = tk.Frame(grid_canvas, bg=theme.bg_primary)
        
        self.grid_inner.bind(
            "<Configure>",
            lambda e: grid_canvas.configure(scrollregion=grid_canvas.bbox("all"))
        )
        
        grid_canvas.create_window((0, 0), window=self.grid_inner, anchor="nw")
        grid_canvas.configure(yscrollcommand=grid_scrollbar.set)
        
        grid_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        grid_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        grid_canvas.bind("<MouseWheel>",
            lambda e: grid_canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        
        # Show list view by default
        self.list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
    
    def _create_status_bar(self):
        """Create status bar"""
        theme = get_theme()
        
        self.status_bar = tk.Frame(self.root, bg=theme.bg_dark, height=30)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_bar.pack_propagate(False)
        
        # Status message
        self.status_label = tk.Label(
            self.status_bar, text="Ready", bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.small()
        )
        self.status_label.pack(side=tk.LEFT, padx=15)
        
        # Favicon status
        self.favicon_status = FaviconStatusDisplay(self.status_bar)
        
        # Progress bar (hidden by default)
        self.main_progress = EnhancedProgressBar(
            self.status_bar, height=30, show_label=True, show_percentage=True
        )
        
        # Version
        tk.Label(
            self.status_bar, text=f"v{APP_VERSION}", bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.small()
        ).pack(side=tk.RIGHT, padx=15)
    
    def _show_status_progress(self, show: bool = True):
        """Show or hide progress indicator in status bar"""
        if show:
            self.status_progress.pack(side=tk.LEFT, padx=(DesignTokens.SPACE_MD, 0))
            self.status_progress.start(10)
        else:
            self.status_progress.stop()
            self.status_progress.pack_forget()
    
    def _update_status_counts(self):
        """Update item counts in status bar"""
        if hasattr(self, 'status_total_label'):
            total = len(self.bookmark_manager.get_all_bookmarks())
            self.status_total_label.configure(text=f"{total} items")
        
        if hasattr(self, 'status_selected_label'):
            selected = len(self.selected_bookmarks) if hasattr(self, 'selected_bookmarks') else 0
            if selected > 0:
                self.status_selected_label.configure(text=f"{selected} selected")
            else:
                self.status_selected_label.configure(text="")

    def _load_and_display_data(self):
        """Load bookmarks and display"""
        # Refresh category list
        self._refresh_category_list()
        
        # Load bookmarks into view
        self._refresh_bookmark_list()
        
        # Queue all favicons for background download
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        self.favicon_manager.queue_bookmarks(bookmarks)
        
        # Update status
        self._set_status(f"Loaded {len(bookmarks)} bookmarks")
    
    def _refresh_category_list(self):
        """Refresh sidebar category list"""
        theme = get_theme()
        
        # Clear existing
        for widget in self.categories_frame.winfo_children():
            widget.destroy()
        
        categories = self.category_manager.get_sorted_categories()
        counts = self.bookmark_manager.get_category_counts()
        
        for cat in categories:
            count = counts.get(cat, 0)
            icon = get_category_icon(cat)
            
            cat_btn = tk.Label(
                self.categories_frame,
                text=f"{icon} {cat} ({count})",
                bg=theme.bg_secondary if cat != self.current_category else theme.selection,
                fg=theme.text_primary,
                font=FONTS.body(),
                cursor="hand2", anchor="w",
                padx=10, pady=6
            )
            cat_btn.pack(fill=tk.X, pady=1)
            
            cat_btn.bind("<Button-1>", lambda e, c=cat: self._select_category(c))
            cat_btn.bind("<Enter>", lambda e, b=cat_btn, c=cat: 
                        b.configure(bg=theme.bg_hover) if c != self.current_category else None)
            cat_btn.bind("<Leave>", lambda e, b=cat_btn, c=cat: 
                        b.configure(bg=theme.bg_secondary) if c != self.current_category else None)
    
    def _refresh_bookmark_list(self):
        """Refresh the bookmark list display"""
        # Get filtered bookmarks
        if self.current_category:
            bookmarks = self.bookmark_manager.get_bookmarks_by_category(self.current_category)
        else:
            bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        # Apply search filter
        if self.search_query:
            bookmarks = [bm for bm in bookmarks 
                        if self.search_query.lower() in bm.title.lower() or
                           self.search_query.lower() in bm.url.lower() or
                           self.search_query.lower() in ' '.join(bm.tags).lower()]
        
        # Sort pinned first
        bookmarks.sort(key=lambda b: (not b.is_pinned, b.title.lower()))
        
        # Update count
        self.count_label.configure(text=f"{len(bookmarks)} bookmarks")
        
        # Update view
        if self.view_mode == ViewMode.LIST:
            self._populate_list_view(bookmarks)
        else:
            self._populate_grid_view(bookmarks)
    
    def _populate_list_view(self, bookmarks: List[Bookmark]):
        """Populate the treeview with bookmarks"""
        # Clear existing
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Track item IDs for favicon updates
        self._tree_items: Dict[int, str] = {}  # bookmark_id -> tree_item_id
        self._tree_domains: Dict[str, List[str]] = {}  # domain -> [tree_item_ids]
        
        for bm in bookmarks:
            # Format added date
            try:
                added = datetime.fromisoformat(bm.created_at.replace('Z', '+00:00'))
                added_str = added.strftime("%Y-%m-%d")
            except Exception:
                added_str = ""
            
            # Format title with pin indicator
            title = f"📌 {bm.title}" if bm.is_pinned else bm.title
            
            # Tags
            tags_str = ", ".join(bm.tags[:3])
            if len(bm.tags) > 3:
                tags_str += f" +{len(bm.tags)-3}"
            
            # Insert item
            item_id = self.tree.insert(
                "", "end",
                iid=str(bm.id),
                text="",  # Will show favicon here
                values=(title, bm.url[:50], bm.category, tags_str, added_str)
            )
            
            self._tree_items[bm.id] = item_id
            
            # Track domain for favicon updates
            if bm.domain not in self._tree_domains:
                self._tree_domains[bm.domain] = []
            self._tree_domains[bm.domain].append(item_id)
            
            # Try to set favicon immediately if cached
            favicon_path = self.favicon_manager.get_favicon_path(bm.domain)
            if favicon_path:
                self.tree.set_favicon(item_id, favicon_path)
            else:
                # Set placeholder
                letter = bm.domain[0].upper() if bm.domain else "?"
                colors = ["#58a6ff", "#3fb950", "#f0883e", "#a371f7", "#f778ba"]
                color = colors[hash(bm.domain) % len(colors)]
                self.tree.set_placeholder(item_id, letter, color)
    
    def _populate_grid_view(self, bookmarks: List[Bookmark]):
        """Populate the grid view with bookmark cards"""
        # Clear existing
        for widget in self.grid_inner.winfo_children():
            widget.destroy()
        
        # Calculate columns based on width
        cols = 4
        
        for i, bm in enumerate(bookmarks):
            row = i // cols
            col = i % cols
            
            card = BookmarkCard(
                self.grid_inner, bm,
                on_click=lambda b=bm: self._on_bookmark_click(b),
                on_double_click=lambda b=bm: self._open_bookmark(b)
            )
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
    
    def _set_view_mode(self, mode: ViewMode):
        """Switch view mode"""
        theme = get_theme()
        
        self.view_mode = mode
        
        # Update button styles
        if mode == ViewMode.LIST:
            self.list_btn.configure(bg=theme.accent_primary)
            self.grid_btn.configure(bg=theme.bg_secondary)
            self.grid_frame.pack_forget()
            self.list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        else:
            self.grid_btn.configure(bg=theme.accent_primary)
            self.list_btn.configure(bg=theme.bg_secondary)
            self.list_frame.pack_forget()
            self.grid_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        # Refresh display
        self._refresh_bookmark_list()
    
    def _on_favicon_progress(self, completed: int, total: int, current: str):
        """Callback for favicon download progress"""
        self.favicon_status.update_status(completed, total, current)
    
    def _on_favicon_ready(self, domain: str, filepath: str, bookmark_id: int):
        """Callback when a favicon finishes downloading"""
        # Update all tree items with this domain
        if hasattr(self, '_tree_domains') and domain in self._tree_domains:
            for item_id in self._tree_domains[domain]:
                try:
                    self.tree.set_favicon(item_id, filepath)
                except Exception:
                    pass
    
    def _on_search_change(self, *args):
        """Handle search input change"""
        self.search_query = self.search_var.get()
        
        # Debounce - refresh after short delay
        if hasattr(self, '_search_after'):
            self.root.after_cancel(self._search_after)
        
        self._search_after = self.root.after(300, self._refresh_bookmark_list)
    
    def _select_category(self, category: str):
        """Select a category"""
        self.current_category = category if category != self.current_category else None
        self._refresh_category_list()
        self._refresh_bookmark_list()
    
    def _apply_filter(self, filter_name: str):
        """Apply a quick filter"""
        theme = get_theme()
        
        # Reset all buttons
        for name, btn in self.filter_buttons.items():
            btn.configure(bg=theme.bg_secondary)
        
        # Highlight selected
        if filter_name in self.filter_buttons:
            self.filter_buttons[filter_name].configure(bg=theme.selection)
        
        # Apply filter
        if filter_name == "All":
            self.current_category = None
            self.search_query = ""
            self.search_var.set("")
        elif filter_name == "Pinned":
            self.search_var.set("is:pinned")
        elif filter_name == "Recent":
            self.search_var.set("is:recent")
        elif filter_name == "Broken":
            self.search_var.set("is:broken")
        
        self._refresh_bookmark_list()
    
    def _on_selection_change(self, event):
        """Handle selection change in tree"""
        selection = self.tree.selection()
        self.selected_bookmarks = [int(item) for item in selection]
    
    def _on_item_double_click(self, event):
        """Handle double-click on item"""
        item = self.tree.identify_row(event.y)
        if item:
            bookmark = self.bookmark_manager.get_bookmark(int(item))
            if bookmark:
                self._open_bookmark(bookmark)
    
    def _on_bookmark_click(self, bookmark: Bookmark):
        """Handle single click on bookmark"""
        pass  # Select item
    
    def _open_bookmark(self, bookmark: Bookmark):
        """Open bookmark in browser"""
        webbrowser.open(bookmark.url)
        
        # Update visit count
        bookmark.visit_count += 1
        bookmark.last_visited = datetime.now().isoformat()
        self.bookmark_manager.update_bookmark(bookmark)
    
    def _show_context_menu(self, event):
        """Show right-click context menu"""
        theme = get_theme()
        
        item = self.tree.identify_row(event.y)
        if not item:
            return
        
        # Select item if not selected
        if item not in self.tree.selection():
            self.tree.selection_set(item)
        
        menu = tk.Menu(self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary)
        
        menu.add_command(label="🔗 Open in Browser", command=lambda: self._open_selected())
        menu.add_command(label="✏️ Edit", command=lambda: self._edit_selected())
        menu.add_separator()
        menu.add_command(label="📋 Copy URL", command=lambda: self._copy_url())
        menu.add_command(label="📌 Toggle Pin", command=lambda: self._toggle_pin())
        menu.add_separator()
        menu.add_command(label="🗑️ Delete", command=lambda: self._delete_selected())
        
        menu.tk_popup(event.x_root, event.y_root)
    
    def _open_selected(self):
        """Open selected bookmarks"""
        for bm_id in self.selected_bookmarks:
            bookmark = self.bookmark_manager.get_bookmark(bm_id)
            if bookmark:
                self._open_bookmark(bookmark)
    
    def _edit_selected(self):
        """Edit first selected bookmark"""
        if self.selected_bookmarks:
            bookmark = self.bookmark_manager.get_bookmark(self.selected_bookmarks[0])
            if bookmark:
                self._show_edit_dialog(bookmark)
    
    def _copy_url(self):
        """Copy selected bookmark URLs to clipboard"""
        urls = []
        for bm_id in self.selected_bookmarks:
            bookmark = self.bookmark_manager.get_bookmark(bm_id)
            if bookmark:
                urls.append(bookmark.url)
        
        if urls:
            self.root.clipboard_clear()
            self.root.clipboard_append('\n'.join(urls))
            self._set_status(f"Copied {len(urls)} URL(s) to clipboard")
    
    def _toggle_pin(self):
        """Toggle pin status for selected bookmarks"""
        for bm_id in self.selected_bookmarks:
            bookmark = self.bookmark_manager.get_bookmark(bm_id)
            if bookmark:
                bookmark.is_pinned = not bookmark.is_pinned
                self.bookmark_manager.update_bookmark(bookmark)
        
        self._refresh_bookmark_list()
    
    def _delete_selected(self):
        """Delete selected bookmarks"""
        if not self.selected_bookmarks:
            return
        
        count = len(self.selected_bookmarks)
        if not messagebox.askyesno("Confirm Delete", f"Delete {count} bookmark(s)?"):
            return
        
        for bm_id in self.selected_bookmarks:
            self.bookmark_manager.delete_bookmark(bm_id)
        
        self.selected_bookmarks.clear()
        self._refresh_all()
        self._set_status(f"Deleted {count} bookmark(s)")
    
    def _add_bookmark(self):
        """Add new bookmark"""
        categories = self.category_manager.get_sorted_categories()
        
        dialog = QuickAddDialog(
            self.root, categories,
            on_add=self._on_bookmark_added
        )
    
    def _on_bookmark_added(self, data: Dict):
        """Handle bookmark added from dialog"""
        bookmark = Bookmark(
            id=None,
            url=data["url"],
            title=data["title"],
            category=data["category"]
        )
        
        self.bookmark_manager.add_bookmark(bookmark)
        
        # Queue favicon download
        self.favicon_manager.queue_favicon(bookmark.domain, bookmark.id, priority=True)
        
        self._refresh_all()
        self._set_status(f"Added: {bookmark.title}")
    
    def _show_edit_dialog(self, bookmark: Bookmark):
        """Show edit dialog for bookmark"""
        dialog = BookmarkEditorDialog(
            self.root, bookmark,
            categories=self.category_manager.get_sorted_categories(),
            available_tags=self.tag_manager.get_all_tags(),
            on_save=lambda bm: self._on_bookmark_edited(bm)
        )
    
    def _on_bookmark_edited(self, bookmark: Bookmark):
        """Handle bookmark edited"""
        self.bookmark_manager.update_bookmark(bookmark)
        self._refresh_all()
        self._set_status(f"Updated: {bookmark.title}")
    
    def _on_files_dropped(self, filepaths: List[str]):
        """Handle files dropped for import"""
        self.import_area.set_importing(True)
        self._set_status("Importing bookmarks...")
        
        # Process in background
        def import_files():
            total_added = 0
            total_dupes = 0
            
            for filepath in filepaths:
                ext = Path(filepath).suffix.lower()
                
                try:
                    if ext in ('.html', '.htm'):
                        bookmarks = NetscapeBookmarkImporter.import_from_netscape(filepath)
                    elif ext == '.json':
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        # Parse JSON bookmarks
                        bookmarks = []
                        for item in data if isinstance(data, list) else data.get('bookmarks', []):
                            bm = Bookmark(
                                id=None,
                                url=item.get('url', ''),
                                title=item.get('title', ''),
                                category=item.get('category', 'Imported')
                            )
                            bookmarks.append(bm)
                    elif ext == '.csv':
                        bookmarks = RaindropImporter.import_from_csv(filepath)
                    elif ext == '.opml':
                        bookmarks = OPMLImporter.import_from_opml(filepath)
                    elif ext == '.txt':
                        bookmarks = TextURLImporter.import_from_text(filepath)
                    else:
                        continue
                    
                    # Add bookmarks
                    for bm in bookmarks:
                        if bm.url:
                            existing = self.bookmark_manager.find_by_url(bm.url)
                            if not existing:
                                self.bookmark_manager.add_bookmark(bm)
                                total_added += 1
                            else:
                                total_dupes += 1
                
                except Exception as e:
                    print(f"Error importing {filepath}: {e}")
            
            # Update UI on main thread
            self.root.after(0, lambda: self._on_import_complete(total_added, total_dupes))
        
        threading.Thread(target=import_files, daemon=True).start()
    
    def _on_import_complete(self, added: int, dupes: int):
        """Handle import completion"""
        self.import_area.set_importing(False)
        self._refresh_all()
        
        # Queue favicons for new bookmarks
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        self.favicon_manager.queue_bookmarks(bookmarks)
        
        self._set_status(f"Imported {added} bookmarks ({dupes} duplicates skipped)")
        messagebox.showinfo("Import Complete", f"Imported {added} bookmarks\n{dupes} duplicates skipped")
    
    def _show_import_dialog(self):
        """Show import dialog"""
        self.import_area._browse_files()
    
    def _show_export_dialog(self):
        """Show export dialog"""
        dialog = SelectiveExportDialog(
            self.root, self.bookmark_manager,
            on_export=lambda r: self._set_status(f"Exported {r['count']} bookmarks")
        )
    
    def _check_all_links(self):
        """Check all bookmark links"""
        self._set_status("Checking links...")
        self.main_progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=20)
        
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        total = len(bookmarks)
        
        def check_links():
            broken = 0
            for i, bm in enumerate(bookmarks):
                try:
                    response = requests.head(bm.url, timeout=5, allow_redirects=True)
                    bm.http_status = response.status_code
                    bm.is_valid = response.status_code < 400
                except Exception:
                    bm.http_status = 0
                    bm.is_valid = False
                
                if not bm.is_valid:
                    broken += 1
                
                bm.last_checked = datetime.now().isoformat()
                
                # Update progress
                self.root.after(0, lambda i=i, bm=bm: 
                    self.main_progress.set_progress(i+1, total, f"Checking: {bm.domain}"))
                
                # Rate limiting
                time.sleep(0.2)
            
            self.bookmark_manager.save_bookmarks()
            self.root.after(0, lambda: self._on_link_check_complete(broken, total))
        
        threading.Thread(target=check_links, daemon=True).start()
    
    def _on_link_check_complete(self, broken: int, total: int):
        """Handle link check completion"""
        self.main_progress.complete(f"Found {broken} broken links")
        self.root.after(2000, lambda: self.main_progress.pack_forget())
        self._refresh_all()
        messagebox.showinfo("Link Check Complete", f"Checked {total} links\nFound {broken} broken")
    
    def _find_duplicates(self):
        """Find and show duplicate bookmarks"""
        dupes = self.bookmark_manager.find_duplicates()
        
        if not dupes:
            messagebox.showinfo("No Duplicates", "No duplicate bookmarks found!")
            return
        
        total = sum(len(group) - 1 for group in dupes)
        
        if messagebox.askyesno("Duplicates Found", 
            f"Found {total} duplicate bookmarks in {len(dupes)} groups.\n\nRemove duplicates (keep oldest)?"):
            
            removed = 0
            for group in dupes:
                # Keep first (oldest), delete rest
                for bm in group[1:]:
                    self.bookmark_manager.delete_bookmark(bm.id)
                    removed += 1
            
            self._refresh_all()
            self._set_status(f"Removed {removed} duplicates")
    
    def _clean_urls(self):
        """Clean tracking parameters from URLs"""
        count = self.bookmark_manager.clean_tracking_params()
        self._refresh_all()
        self._set_status(f"Cleaned {count} URLs")
        messagebox.showinfo("URLs Cleaned", f"Removed tracking parameters from {count} bookmarks")
    
    def _show_analytics(self):
        """Show full analytics dashboard"""
        dialog = AnalyticsDashboard(self.root, self.bookmark_manager)
    
    def _show_theme_settings(self):
        """Show theme settings dialog"""
        dialog = ThemeSelectorDialog(self.root, _theme_manager)
    
    def _undo(self):
        """Undo last action"""
        if self.command_stack.undo():
            self._refresh_all()
            self._set_status("Undo")
    
    def _redo(self):
        """Redo last undone action"""
        if self.command_stack.redo():
            self._refresh_all()
            self._set_status("Redo")
    
    def _select_all(self):
        """Select all items"""
        self.tree.selection_set(self.tree.get_children())
    
    def _refresh_all(self):
        """Refresh all displays"""
        self._refresh_category_list()
        self._refresh_bookmark_list()
        self.mini_analytics.refresh()
    
    def _set_status(self, message: str):
        """Set status bar message"""
        self.status_label.configure(text=message)
    
    def _on_close(self):
        """Handle window close"""
        self.favicon_manager.stop_background_worker()
        self.root.destroy()


# =============================================================================
# UPDATE MAIN ENTRY POINT
# =============================================================================


# =============================================================================
# UPDATED DATA DIRECTORY - Use local profile

(DATA_DIR / 'archives').mkdir(exist_ok=True)


# =============================================================================
# HIGH-SPEED FAVICON DOWNLOADER (Concurrent, Non-blocking)
# =============================================================================
class HighSpeedFaviconManager:
    """
    Ultra-fast favicon manager with:
    - Concurrent downloads (multiple at once)
    - Completely non-blocking
    - Memory efficient
    - Lazy loading from web until cached
    - Persistent failed domain tracking
    """
    
    CACHE_DIR = DATA_DIR / "favicons"
    FAILED_FILE = DATA_DIR / "failed_favicons.json"
    
    # Fast favicon sources (ordered by speed/reliability)
    FAVICON_SOURCES = [
        "https://www.google.com/s2/favicons?domain={domain}&sz=32",
        "https://icons.duckduckgo.com/ip3/{domain}.ico",
        "https://api.faviconkit.com/{domain}/64",
        "https://favicone.com/{domain}?s=64",
        "https://icon.horse/icon/{domain}",
        "https://{domain}/favicon.ico",
        "https://{domain}/favicon.png",
    ]
    
    def __init__(self, max_workers: int = 10):
        self.CACHE_DIR.mkdir(exist_ok=True)
        self._cache: Dict[str, Optional[str]] = {}
        self._pending: Set[str] = set()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._futures: Dict[str, Any] = {}
        self._progress_callback: Optional[Callable] = None
        self._on_favicon_ready: Optional[Callable] = None
        self._total_queued = 0
        self._completed = 0
        self._lock = threading.Lock()
        self._failed_domains: Set[str] = set()
        
        # Load existing cache and failed domains
        self._load_cache_index()
        self._load_failed_domains()
    
    def _load_cache_index(self):
        """Load index of cached favicons"""
        for filepath in self.CACHE_DIR.glob("*.*"):
            if filepath.suffix in ['.png', '.ico', '.jpg']:
                domain = filepath.stem
                self._cache[domain] = str(filepath)
    
    def _load_failed_domains(self):
        """Load failed domains from file"""
        try:
            if self.FAILED_FILE.exists():
                with open(self.FAILED_FILE, 'r') as f:
                    data = json.load(f)
                    self._failed_domains = set(data.get('failed_domains', []))
                    print(f"Loaded {len(self._failed_domains)} failed favicon domains")
        except Exception as e:
            print(f"Error loading failed domains: {e}")
    
    def _save_failed_domains(self):
        """Save failed domains to file"""
        try:
            with open(self.FAILED_FILE, 'w') as f:
                json.dump({'failed_domains': list(self._failed_domains)}, f)
        except Exception as e:
            print(f"Error saving failed domains: {e}")
    
    def get_failed_domains(self) -> Set[str]:
        """Get set of failed domains"""
        return self._failed_domains.copy()
    
    def clear_failed_domains(self):
        """Clear failed domains to allow retry"""
        self._failed_domains.clear()
        self._save_failed_domains()
    
    def get_cached_path(self, url: str) -> Optional[str]:
        """Get cached favicon path for a URL"""
        try:
            domain = urlparse(url).netloc
            return self.get_cached(domain)
        except Exception:
            return None
    
    def get_cached(self, domain: str) -> Optional[str]:
        """Get cached favicon path (instant, non-blocking). Returns None for failed domains."""
        cached = self._cache.get(domain)
        if cached == "FAILED":
            return None  # Don't return the placeholder marker
        return cached
    
    def is_cached(self, domain: str) -> bool:
        """Check if favicon is cached"""
        return domain in self._cache
    
    def download_async(self, domain: str, bookmark_id: int = 0):
        """
        Download favicon asynchronously.
        Returns immediately, calls callback when ready.
        """
        # Skip if already cached or pending
        if domain in self._cache or domain in self._pending:
            if domain in self._cache and self._on_favicon_ready:
                # Already cached - notify immediately
                self._on_favicon_ready(domain, self._cache[domain], bookmark_id)
            return
        
        with self._lock:
            self._pending.add(domain)
            self._total_queued += 1
        
        # Submit to thread pool
        future = self._executor.submit(self._download_favicon, domain, bookmark_id)
        self._futures[domain] = future
    
    def _download_favicon(self, domain: str, bookmark_id: int) -> Optional[str]:
        """Download favicon (runs in thread pool) with multiple fallback sources"""
        filepath = None
        
        for source_template in self.FAVICON_SOURCES:
            try:
                url = source_template.format(domain=domain)
                
                response = requests.get(
                    url,
                    timeout=5,  # Slightly longer timeout for reliability
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
                    stream=True
                )
                
                if response.status_code == 200 and len(response.content) > 100:
                    # Try to open as image to validate
                    try:
                        img_data = BytesIO(response.content)
                        img = Image.open(img_data)
                        
                        # Convert and save as PNG
                        if img.mode != 'RGBA':
                            img = img.convert('RGBA')
                        
                        # Resize if needed
                        if img.size[0] != 32 or img.size[1] != 32:
                            img = img.resize((32, 32), Image.Resampling.LANCZOS)
                        
                        filepath = self.CACHE_DIR / f"{domain}.png"
                        img.save(filepath, "PNG")
                        filepath = str(filepath)
                        break
                    except Exception as img_error:
                        # If can't open as image, save raw content
                        content_type = response.headers.get('content-type', '')
                        ext = 'png' if 'png' in content_type else 'ico'
                        
                        filepath = self.CACHE_DIR / f"{domain}.{ext}"
                        with open(filepath, 'wb') as f:
                            f.write(response.content)
                        filepath = str(filepath)
                        break
            except Exception as e:
                continue
        
        # Update state
        with self._lock:
            self._pending.discard(domain)
            self._completed += 1
            
            if filepath:
                self._cache[domain] = filepath
                # Remove from failed if it was there
                self._failed_domains.discard(domain)
            else:
                # Mark as failed and persist
                self._cache[domain] = "FAILED"
                self._failed_domains.add(domain)
                self._save_failed_domains()
        
        # Notify callbacks (on main thread via after())
        if filepath and self._on_favicon_ready:
            try:
                self._on_favicon_ready(domain, filepath, bookmark_id)
            except Exception:
                pass
        
        if self._progress_callback:
            try:
                self._progress_callback(self._completed, self._total_queued, domain)
            except Exception:
                pass
        
        return filepath
    
    def queue_bookmarks(self, bookmarks: List[Bookmark]):
        """Queue all bookmarks for favicon download - skips failed domains"""
        domains_seen = set()
        
        for bm in bookmarks:
            # Skip if already cached, pending, or previously failed
            if bm.domain not in domains_seen and bm.domain not in self._cache:
                # Skip failed domains on startup
                if bm.domain in self._failed_domains:
                    continue
                domains_seen.add(bm.domain)
                self.download_async(bm.domain, bm.id)
    
    def redownload_all_favicons(self, bookmarks: List, callback: Callable = None,
                                progress_callback: Callable = None):
        """Redownload all favicons - clears cache first"""
        # Clear cache
        for f in self.CACHE_DIR.glob("*.*"):
            try:
                f.unlink()
            except Exception:
                pass
        self._cache.clear()
        self._failed_domains.clear()
        self._save_failed_domains()
        self._total_queued = 0
        self._completed = 0
        
        # Queue all
        domains_seen = set()
        for bm in bookmarks:
            domain = bm.domain if hasattr(bm, 'domain') else urlparse(bm.get('url', '')).netloc
            if domain and domain not in domains_seen:
                domains_seen.add(domain)
                bm_id = bm.id if hasattr(bm, 'id') else 0
                self.download_async(domain, bm_id)
    
    def redownload_missing_favicons(self, bookmarks: List, callback: Callable = None,
                                    progress_callback: Callable = None):
        """Redownload only missing favicons - clears failed list first"""
        # Clear failed domains to retry
        self._failed_domains.clear()
        self._save_failed_domains()
        
        # Remove FAILED markers from cache
        self._cache = {k: v for k, v in self._cache.items() if v != "FAILED"}
        
        self._total_queued = 0
        self._completed = 0
        
        # Queue missing
        domains_seen = set()
        for bm in bookmarks:
            domain = bm.domain if hasattr(bm, 'domain') else urlparse(bm.get('url', '')).netloc
            if domain and domain not in domains_seen and domain not in self._cache:
                domains_seen.add(domain)
                bm_id = bm.id if hasattr(bm, 'id') else 0
                self.download_async(domain, bm_id)
    
    def set_progress_callback(self, callback: Callable):
        """Set progress callback: callback(completed, total, current_domain)"""
        self._progress_callback = callback
    
    def set_favicon_ready_callback(self, callback: Callable):
        """Set callback when favicon ready: callback(domain, filepath, bookmark_id)"""
        self._on_favicon_ready = callback
    
    @property
    def progress(self) -> Tuple[int, int]:
        """Get progress: (completed, total)"""
        return self._completed, self._total_queued
    
    @property
    def is_downloading(self) -> bool:
        """Check if downloads are in progress"""
        return len(self._pending) > 0
    
    def shutdown(self):
        """Shutdown the executor"""
        self._executor.shutdown(wait=False)
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        files = list(self.CACHE_DIR.glob("*.*"))
        total_size = sum(f.stat().st_size for f in files if f.is_file())
        
        return {
            "cached_count": len(self._cache),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2)
        }
    
    def clear_cache(self):
        """Clear all cached favicons"""
        for f in self.CACHE_DIR.glob("*.*"):
            try:
                f.unlink()
            except Exception:
                pass
        self._cache.clear()


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
        super().__init__(parent, bg=theme.bg_primary)
        
        self.theme_manager = theme_manager
        self.on_change = on_change
        
        # Current theme display
        self.current_var = tk.StringVar(value=theme_manager.current_theme.name)
        
        # Create dropdown button
        self.btn = tk.Label(
            self, text=f"🎨 {theme_manager.current_theme.name[:15]}",
            bg=theme.bg_secondary, fg=theme.text_primary,
            font=FONTS.small(), padx=10, pady=6,
            cursor="hand2"
        )
        self.btn.pack(fill=tk.X)
        
        self.btn.bind("<Button-1>", self._show_menu)
        self.btn.bind("<Enter>", lambda e: self.btn.configure(bg=theme.bg_hover))
        self.btn.bind("<Leave>", lambda e: self.btn.configure(bg=theme.bg_secondary))
    
    def _show_menu(self, event):
        """Show theme selection menu"""
        theme = get_theme()
        
        menu = tk.Menu(self, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                      font=FONTS.body())
        
        for theme_name in self.theme_manager.get_all_themes():
            menu.add_command(
                label=f"  {theme_name}",
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
        self.btn.configure(text=f"🎨 {theme_name[:15]}")
        
        if self.on_change:
            self.on_change(theme_name)


# =============================================================================
# NON-BLOCKING TASK RUNNER
# =============================================================================
class NonBlockingTaskRunner:
    """
    Runs tasks in background threads with proper UI updates.
    Ensures GUI never locks up.
    """
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._tasks: Dict[str, Any] = {}
    
    def run_task(self, task_id: str, func: Callable, 
                 on_progress: Callable = None,
                 on_complete: Callable = None,
                 on_error: Callable = None,
                 *args, **kwargs):
        """
        Run a task in background thread.
        
        Args:
            task_id: Unique identifier for the task
            func: Function to run
            on_progress: Progress callback (called via after())
            on_complete: Completion callback (called via after())
            on_error: Error callback (called via after())
        """
        def wrapper():
            try:
                result = func(*args, **kwargs)
                if on_complete:
                    self.root.after(0, lambda: on_complete(result))
            except Exception as e:
                if on_error:
                    self.root.after(0, lambda: on_error(e))
        
        future = self._executor.submit(wrapper)
        self._tasks[task_id] = future
        return future
    
    def run_with_progress(self, task_id: str, items: List,
                          process_func: Callable,
                          on_progress: Callable = None,
                          on_complete: Callable = None):
        """
        Run a task over multiple items with progress updates.
        """
        def wrapper():
            results = []
            total = len(items)
            
            for i, item in enumerate(items):
                try:
                    result = process_func(item)
                    results.append(result)
                except Exception as e:
                    results.append(None)
                
                if on_progress:
                    self.root.after(0, lambda i=i, item=item: on_progress(i + 1, total, item))
                
                # Small yield to prevent blocking
                time.sleep(0.01)
            
            if on_complete:
                self.root.after(0, lambda: on_complete(results))
        
        future = self._executor.submit(wrapper)
        self._tasks[task_id] = future
        return future
    
    def cancel(self, task_id: str):
        """Cancel a running task"""
        if task_id in self._tasks:
            self._tasks[task_id].cancel()
            del self._tasks[task_id]
    
    def shutdown(self):
        """Shutdown the executor"""
        self._executor.shutdown(wait=False)




# =============================================================================
# FINAL ENHANCED BOOKMARK ORGANIZER APP
# =============================================================================
# =============================================================================
# CATEGORY MANAGEMENT DIALOG
# =============================================================================
class CategoryManagementDialog(tk.Toplevel):
    """
        Represents a bookmark category.
        
        Attributes:
            name: Category name (unique identifier)
            parent: Parent category name (for nesting)
            icon: Emoji icon for display
            color: Optional color override
            sort_order: Order within parent
            created_at: ISO timestamp of creation
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
        """
    
    def __init__(self, parent, category_manager, bookmark_manager, on_change: Callable = None):
        super().__init__(parent)
        
        theme = get_theme()
        self.category_manager = category_manager
        self.bookmark_manager = bookmark_manager
        self.on_change = on_change
        
        self.title("Manage Categories")
        self.configure(bg=theme.bg_primary)
        self.geometry("500x600")
        self.transient(parent)
        self.grab_set()
        
        # Header
        header = tk.Frame(self, bg=theme.bg_secondary)
        header.pack(fill=tk.X, padx=20, pady=20)
        
        tk.Label(
            header, text="📁 Category Management", bg=theme.bg_secondary,
            fg=theme.text_primary, font=FONTS.title(bold=False)
        ).pack(anchor="w")
        
        tk.Label(
            header, text="Add, edit, or delete categories", bg=theme.bg_secondary,
            fg=theme.text_muted, font=FONTS.body()
        ).pack(anchor="w", pady=(4, 0))
        
        # Add category section
        add_frame = tk.LabelFrame(
            self, text=" Add New Category ", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        )
        add_frame.pack(fill=tk.X, padx=20, pady=(0, 15))
        
        add_inner = tk.Frame(add_frame, bg=theme.bg_primary)
        add_inner.pack(fill=tk.X, padx=10, pady=10)
        
        self.new_cat_entry = tk.Entry(
            add_inner, bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, font=FONTS.body(),
            relief=tk.FLAT
        )
        self.new_cat_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10), ipady=5)
        self.new_cat_entry.insert(0, "New category name...")
        self.new_cat_entry.bind("<FocusIn>", lambda e: self._clear_placeholder())
        
        add_btn = tk.Button(
            add_inner, text="➕ Add", bg=theme.accent_success, fg="white",
            font=FONTS.body(), relief=tk.FLAT, cursor="hand2",
            command=self._add_category
        )
        add_btn.pack(side=tk.RIGHT)
        
        # Category list
        list_frame = tk.LabelFrame(
            self, text=" Existing Categories ", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        )
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 15))
        
        # Scrollable list
        canvas = tk.Canvas(list_frame, bg=theme.bg_primary, highlightthickness=0)
        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)
        self.cat_list_frame = tk.Frame(canvas, bg=theme.bg_primary)
        
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        canvas.create_window((0, 0), window=self.cat_list_frame, anchor="nw")
        self.cat_list_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        self._populate_categories()
        
        # Close button
        tk.Button(
            self, text="Close", bg=theme.bg_secondary, fg=theme.text_primary,
            font=FONTS.body(), relief=tk.FLAT, cursor="hand2",
            command=self.destroy, padx=20, pady=8
        ).pack(pady=15)
    
    def _clear_placeholder(self):
        if self.new_cat_entry.get() == "New category name...":
            self.new_cat_entry.delete(0, tk.END)
    
    def _populate_categories(self):
        """Populate the category list"""
        theme = get_theme()
        
        # Clear existing
        for widget in self.cat_list_frame.winfo_children():
            widget.destroy()
        
        categories = self.category_manager.get_sorted_categories()
        
        for cat_name in categories:
            cat = self.category_manager.categories.get(cat_name)
            if not cat:
                continue
            
            # Count bookmarks in this category
            count = len(self.bookmark_manager.get_bookmarks_by_category(cat_name))
            
            row = tk.Frame(self.cat_list_frame, bg=theme.bg_secondary)
            row.pack(fill=tk.X, pady=2, padx=5)
            
            # Icon and name
            tk.Label(
                row, text=f"{cat.icon} {cat_name}", bg=theme.bg_secondary,
                fg=theme.text_primary, font=FONTS.body(), anchor="w"
            ).pack(side=tk.LEFT, padx=10, pady=8)
            
            # Count badge
            tk.Label(
                row, text=f"({count})", bg=theme.bg_secondary,
                fg=theme.text_muted, font=FONTS.small()
            ).pack(side=tk.LEFT)
            
            # Buttons
            btn_frame = tk.Frame(row, bg=theme.bg_secondary)
            btn_frame.pack(side=tk.RIGHT, padx=5)
            
            # Edit button
            edit_btn = tk.Label(
                btn_frame, text="✏️", bg=theme.bg_secondary,
                fg=theme.text_secondary, font=("Segoe UI", 12), cursor="hand2"
            )
            edit_btn.pack(side=tk.LEFT, padx=5, pady=5)
            edit_btn.bind("<Button-1>", lambda e, n=cat_name: self._edit_category(n))
            
            # Delete button
            del_btn = tk.Label(
                btn_frame, text="🗑️", bg=theme.bg_secondary,
                fg=theme.accent_error, font=("Segoe UI", 12), cursor="hand2"
            )
            del_btn.pack(side=tk.LEFT, padx=5, pady=5)
            del_btn.bind("<Button-1>", lambda e, n=cat_name: self._delete_category(n))
    
    def _add_category(self):
        """Add new category"""
        name = self.new_cat_entry.get().strip()
        if name and name != "New category name...":
            if self.category_manager.add_category(name):
                self.new_cat_entry.delete(0, tk.END)
                self._populate_categories()
                if self.on_change:
                    self.on_change()
            else:
                messagebox.showerror("Error", "Category already exists or invalid name")
    
    def _edit_category(self, old_name: str):
        """Edit category name"""
        theme = get_theme()
        
        dialog = tk.Toplevel(self)
        dialog.title("Edit Category")
        dialog.configure(bg=theme.bg_primary)
        dialog.geometry("350x150")
        dialog.transient(self)
        dialog.grab_set()
        
        tk.Label(
            dialog, text="New name:", bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.body()
        ).pack(pady=(20, 5))
        
        entry = tk.Entry(
            dialog, bg=theme.bg_secondary, fg=theme.text_primary,
            font=FONTS.body(), relief=tk.FLAT, width=30
        )
        entry.pack(pady=5, ipady=5)
        entry.insert(0, old_name)
        entry.select_range(0, tk.END)
        entry.focus_set()
        
        def save():
            new_name = entry.get().strip()
            if new_name and new_name != old_name:
                # Update bookmarks with this category
                for bm in self.bookmark_manager.get_bookmarks_by_category(old_name):
                    bm.category = new_name
                    self.bookmark_manager.update_bookmark(bm)
                
                self.category_manager.rename_category(old_name, new_name)
                dialog.destroy()
                self._populate_categories()
                if self.on_change:
                    self.on_change()
            else:
                dialog.destroy()
        
        tk.Button(
            dialog, text="Save", bg=theme.accent_primary, fg="white",
            font=FONTS.body(), relief=tk.FLAT, command=save, padx=20
        ).pack(pady=15)
    
    def _delete_category(self, name: str):
        """Delete category and move bookmarks to Uncategorized"""
        count = len(self.bookmark_manager.get_bookmarks_by_category(name))
        
        msg = f"Delete category '{name}'?"
        if count > 0:
            msg += f"\n\n{count} bookmark(s) will be moved to 'Uncategorized / Needs Review'."
        
        if messagebox.askyesno("Delete Category", msg):
            # Move bookmarks to Uncategorized
            for bm in self.bookmark_manager.get_bookmarks_by_category(name):
                bm.category = "Uncategorized / Needs Review"
                self.bookmark_manager.update_bookmark(bm)
            
            # Delete the category
            if name in self.category_manager.categories:
                del self.category_manager.categories[name]
                self.category_manager.save_categories()
            
            self._populate_categories()
            if self.on_change:
                self.on_change()


# =============================================================================
# CUSTOM FAVICON WRAPPER GENERATOR
# =============================================================================
class FaviconWrapperGenerator:
    """Generate HTML wrapper pages with custom favicons for bookmarks"""
    
    WRAPPER_DIR = APP_DIR / "favicon_wrappers"
    
    @classmethod
    def ensure_dir(cls):
        cls.WRAPPER_DIR.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def generate_wrapper(cls, bookmark: Bookmark, favicon_path: str) -> str:
        """
        Generate an HTML wrapper page with custom favicon.
        Returns the path to the wrapper file.
        """
        cls.ensure_dir()
        
        # Read and encode favicon
        favicon_data = ""
        try:
            with open(favicon_path, 'rb') as f:
                data = base64.b64encode(f.read()).decode('utf-8')
                # Detect image type
                if favicon_path.lower().endswith('.png'):
                    mime = "image/png"
                elif favicon_path.lower().endswith('.ico'):
                    mime = "image/x-icon"
                else:
                    mime = "image/png"
                favicon_data = f"data:{mime};base64,{data}"
        except Exception as e:
            print(f"Error reading favicon: {e}")
            return None
        
        # Sanitize title for filename
        safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in bookmark.title)[:50]
        filename = f"{safe_title}_{bookmark.id}.html"
        filepath = cls.WRAPPER_DIR / filename
        
        # Generate HTML
        html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{html_module.escape(bookmark.title)}</title>
    <link rel="icon" href="{favicon_data}">
    <meta http-equiv="refresh" content="0; url={html_module.escape(bookmark.url)}">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: #1a1a2e;
            color: #eee;
        }}
        .loader {{
            text-align: center;
        }}
        .spinner {{
            width: 40px;
            height: 40px;
            border: 3px solid #333;
            border-top-color: #3498db;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 15px;
        }}
        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
    </style>
</head>
<body>
    <div class="loader">
        <div class="spinner"></div>
        <p>Redirecting to {html_module.escape(bookmark.domain or bookmark.url)}...</p>
    </div>
</body>
</html>'''
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html)
            return str(filepath)
        except Exception as e:
            print(f"Error writing wrapper: {e}")
            return None
    
    @classmethod
    def update_bookmark_with_wrapper(cls, bookmark: Bookmark, favicon_path: str) -> bool:
        """
        Update a bookmark to use a wrapper page with custom favicon.
        Stores original URL and creates wrapper.
        """
        wrapper_path = cls.generate_wrapper(bookmark, favicon_path)
        if wrapper_path:
            # Store original URL
            if not bookmark.notes:
                bookmark.notes = ""
            if "Original URL:" not in bookmark.notes:
                bookmark.notes = f"Original URL: {bookmark.url}\n{bookmark.notes}"
            
            # Update to wrapper URL
            bookmark.url = f"file:///{wrapper_path.replace(chr(92), '/')}"
            bookmark.custom_favicon = favicon_path
            return True
        return False


# =============================================================================
# CUSTOM FAVICON DIALOG
# =============================================================================
class CustomFaviconDialog(tk.Toplevel):
    """Dialog to set a custom favicon for a bookmark"""
    
    def __init__(self, parent, bookmark: Bookmark, bookmark_manager, on_update: Callable = None):
        super().__init__(parent)
        
        theme = get_theme()
        self.bookmark = bookmark
        self.bookmark_manager = bookmark_manager
        self.on_update = on_update
        self.selected_favicon = None
        
        self.title("Custom Favicon")
        self.configure(bg=theme.bg_primary)
        self.geometry("450x350")
        self.transient(parent)
        self.grab_set()
        
        # Header
        tk.Label(
            self, text="🎨 Set Custom Favicon", bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.title(bold=False)
        ).pack(pady=(20, 5))
        
        tk.Label(
            self, text=f"For: {bookmark.title[:50]}", bg=theme.bg_primary,
            fg=theme.text_muted, font=FONTS.body()
        ).pack(pady=(0, 15))
        
        # Current favicon preview
        preview_frame = tk.Frame(self, bg=theme.bg_secondary)
        preview_frame.pack(pady=15, padx=20)
        
        tk.Label(
            preview_frame, text="Current:", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.body()
        ).pack(side=tk.LEFT, padx=10, pady=10)
        
        self.preview_label = tk.Label(
            preview_frame, text="🌐", bg=theme.bg_secondary,
            font=("Segoe UI Emoji", 24)
        )
        self.preview_label.pack(side=tk.LEFT, padx=10, pady=10)
        
        tk.Label(
            preview_frame, text="→", bg=theme.bg_secondary,
            fg=theme.text_muted, font=("Segoe UI", 16)
        ).pack(side=tk.LEFT, padx=10)
        
        tk.Label(
            preview_frame, text="New:", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.body()
        ).pack(side=tk.LEFT, padx=10, pady=10)
        
        self.new_preview = tk.Label(
            preview_frame, text="?", bg=theme.bg_secondary,
            font=("Segoe UI", 24), fg=theme.text_muted
        )
        self.new_preview.pack(side=tk.LEFT, padx=10, pady=10)
        
        # Select button
        tk.Button(
            self, text="📂 Select Favicon Image...", bg=theme.bg_secondary,
            fg=theme.text_primary, font=FONTS.body(), relief=tk.FLAT,
            command=self._select_favicon, padx=20, pady=8, cursor="hand2"
        ).pack(pady=15)
        
        # Info
        tk.Label(
            self, text="Note: This creates a wrapper page with your custom icon.\n"
                      "The wrapper redirects instantly to the original site.",
            bg=theme.bg_primary, fg=theme.text_muted, font=FONTS.small(),
            justify=tk.CENTER
        ).pack(pady=10)
        
        # Buttons
        btn_frame = tk.Frame(self, bg=theme.bg_primary)
        btn_frame.pack(pady=20)
        
        tk.Button(
            btn_frame, text="Apply", bg=theme.accent_primary, fg="white",
            font=FONTS.body(), relief=tk.FLAT, command=self._apply,
            padx=25, pady=8, cursor="hand2"
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            btn_frame, text="Cancel", bg=theme.bg_secondary, fg=theme.text_primary,
            font=FONTS.body(), relief=tk.FLAT, command=self.destroy,
            padx=25, pady=8, cursor="hand2"
        ).pack(side=tk.LEFT, padx=5)
    
    def _select_favicon(self):
        """Select favicon image"""
        filepath = filedialog.askopenfilename(
            title="Select Favicon Image",
            filetypes=[
                ("Image Files", "*.png *.ico *.jpg *.jpeg *.gif"),
                ("PNG", "*.png"),
                ("ICO", "*.ico"),
                ("All Files", "*.*")
            ]
        )
        
        if filepath:
            self.selected_favicon = filepath
            # Try to show preview
            try:
                from PIL import Image, ImageTk
                img = Image.open(filepath)
                img = img.resize((32, 32), Image.Resampling.LANCZOS)
                self._preview_img = ImageTk.PhotoImage(img)
                self.new_preview.configure(image=self._preview_img, text="")
            except Exception:
                self.new_preview.configure(text="✓", fg=get_theme().accent_success)
    
    def _apply(self):
        """Apply custom favicon"""
        if not self.selected_favicon:
            messagebox.showwarning("No Favicon", "Please select a favicon image first.")
            return
        
        if FaviconWrapperGenerator.update_bookmark_with_wrapper(
            self.bookmark, self.selected_favicon
        ):
            self.bookmark_manager.update_bookmark(self.bookmark)
            messagebox.showinfo("Success", "Custom favicon applied!\n\n"
                              "The bookmark now uses a wrapper page with your icon.")
            if self.on_update:
                self.on_update()
            self.destroy()
        else:
            messagebox.showerror("Error", "Failed to create favicon wrapper.")


# Need html module for escaping


class FinalBookmarkOrganizerApp(ThemedWidget):
    """
        Main application class with full feature set.
        
        The primary application window containing all UI components
        and coordinating all application functionality.
        
        Layout:
            - Header: Logo, search bar, toolbar buttons
            - Left Sidebar: Categories, quick filters
            - Main Content: Bookmark list/grid
            - Right Sidebar: Analytics dashboard
            - Status Bar: Status, counts, progress
        
        Attributes:
            root: Tk root window
            theme_manager: ThemeManager instance
            bookmark_manager: BookmarkManager instance
            category_manager: CategoryManager instance
            tag_manager: TagManager instance
            ai_config: AIConfigManager instance
            favicon_manager: FaviconManager instance
            command_stack: CommandStack for undo/redo
        
        Key Methods:
            _add_bookmark(): Add new bookmark
            _edit_bookmark(id): Edit existing bookmark
            _delete_selected(): Delete selected bookmarks
            _import_bookmarks(): Import from file
            _export_bookmarks(): Export to file
            _refresh_bookmark_list(): Refresh display
            _search(query): Perform search
            _show_settings(): Open settings dialog
        
        Keyboard Shortcuts:
            Ctrl+N: New bookmark
            Ctrl+F: Focus search
            Ctrl+I: Import
            Ctrl+S: Export
            Ctrl+Z: Undo
            Ctrl+Y: Redo
            Delete: Delete selected
            F5: Refresh
        """
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("1500x950")
        self.root.minsize(1100, 700)
        
        theme = get_theme()
        self.root.configure(bg=theme.bg_primary)
        
        set_dark_title_bar(self.root)
        
        # Initialize managers
        self.category_manager = CategoryManager()
        self.tag_manager = TagManager()
        self.bookmark_manager = BookmarkManager(self.category_manager, self.tag_manager)
        self.favicon_manager = HighSpeedFaviconManager(max_workers=15)  # Fast concurrent downloads
        self.task_runner = NonBlockingTaskRunner(root)
        self.command_stack = CommandStack()
        self.ai_config = AIConfigManager()  # AI settings
        
        # State
        self.view_mode = ViewMode.LIST
        self.current_category: Optional[str] = None
        self.search_query: str = ""
        self.selected_bookmarks: List[int] = []
        
        # Placeholder attributes (set before UI is built to prevent errors)
        self.status_label = None
        self.analytics_frame = None
        self.categories_frame = None
        self.tree = None
        self.grid_canvas = None
        self.grid_inner = None
        self.grid_frame = None
        self.main_container = None
        self.filter_buttons = {}
        self.count_label = None
        self.zoom_label = None
        self.search_var = None
        self.search_entry = None
        self._search_after = None
        self.active_filter = "All"
        self.quick_filter = None  # "pinned", "recent", "broken", "untagged" or None
        self._suppress_search_callback = False  # Flag to prevent search callback during programmatic changes
        
        # Setup favicon callbacks
        self.favicon_manager.set_progress_callback(self._on_favicon_progress)
        self.favicon_manager.set_favicon_ready_callback(self._on_favicon_ready_threadsafe)
        
        # Build UI
        self._setup_styles()
        self._create_menu()
        self._create_main_layout()
        self._create_status_bar()
        
        # Load data
        self._load_and_display_data()
        
        # Keyboard shortcuts - comprehensive set
        self.root.bind("<Control-f>", lambda e: self._focus_search())
        self.root.bind("<Control-l>", lambda e: self._focus_search())  # Also Ctrl+L
        self.root.bind("<Control-n>", lambda e: self._add_bookmark())
        self.root.bind("<Control-i>", lambda e: self._show_import_dialog())
        self.root.bind("<Control-o>", lambda e: self._show_import_dialog())  # Also Ctrl+O
        self.root.bind("<Control-a>", lambda e: self._select_all_bookmarks())
        self.root.bind("<Control-s>", lambda e: self._export_bookmarks())
        self.root.bind("<Control-e>", lambda e: self._edit_selected())
        self.root.bind("<Escape>", lambda e: self._clear_search())
        self.root.bind("<F5>", lambda e: self._refresh_all())
        self.root.bind("<Delete>", lambda e: self._delete_selected())
    
    def _focus_search(self, event=None):
        """Focus the search entry and select all text"""
        if hasattr(self, 'search_entry') and self.search_entry:
            self.search_entry.focus_set()
            self.search_entry.select_range(0, tk.END)
        return "break"
        self.root.bind("<Control-A>", lambda e: self._select_all_bookmarks())
        self.root.bind("<F5>", lambda e: self._refresh_all())
        self.root.bind("<Delete>", lambda e: self._delete_selected())
    
    def _focus_search(self, event=None):
        """Focus the search entry and select all text"""
        if hasattr(self, 'search_entry') and self.search_entry:
            self.search_entry.focus_set()
            self.search_entry.select_range(0, tk.END)
        return "break"
        
        # Window events
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Try to enable window-wide drag-drop
        self._try_enable_window_dnd()
        
        # Start analytics polling (update every 30 seconds)
        self._start_analytics_polling()
    
    def _setup_styles(self):
        """Configure ttk styles"""
        theme = get_theme()
        style = ttk.Style()
        
        try:
            style.theme_use('clam')
        except Exception:
            pass
        
        style.configure(
            "Treeview",
            background=theme.bg_primary,
            foreground=theme.text_primary,
            fieldbackground=theme.bg_primary,
            borderwidth=0,
            rowheight=32  # Taller rows for better favicon spacing
        )
        
        style.configure(
            "Treeview.Heading",
            background=theme.bg_secondary,
            foreground=theme.text_primary,
            borderwidth=0,
            font=("Segoe UI", 9, "bold")
        )
        
        style.map(
            "Treeview",
            background=[("selected", theme.selection)],
            foreground=[("selected", theme.text_primary)]
        )
    
    def _create_menu(self):
        """Create menu bar"""
        theme = get_theme()
        
        menubar = tk.Menu(self.root, bg=theme.bg_dark, fg=theme.text_primary,
                         activebackground=theme.selection, borderwidth=0)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary)
        file_menu.add_command(label="New Bookmark", accelerator="Ctrl+N", command=self._add_bookmark)
        file_menu.add_separator()
        file_menu.add_command(label="Import...", accelerator="Ctrl+I", command=self._show_import_dialog)
        file_menu.add_command(label="Export...", command=self._show_export_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary)
        edit_menu.add_command(label="Undo", accelerator="Ctrl+Z", command=self._undo)
        edit_menu.add_command(label="Redo", accelerator="Ctrl+Y", command=self._redo)
        edit_menu.add_separator()
        edit_menu.add_command(label="Select All", accelerator="Ctrl+A", command=self._select_all_bookmarks)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary)
        view_menu.add_command(label="List View", command=lambda: self._set_view_mode(ViewMode.LIST))
        view_menu.add_command(label="Grid View", command=lambda: self._set_view_mode(ViewMode.GRID))
        view_menu.add_separator()
        view_menu.add_command(label="Refresh", accelerator="F5", command=self._refresh_all)
        menubar.add_cascade(label="View", menu=view_menu)
        
        self.root.config(menu=menubar)
    
    def _create_main_layout(self):
        """Create main application layout"""
        theme = get_theme()
        
        # Main container
        self.main_container = tk.Frame(self.root, bg=theme.bg_primary)
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        # ===== HEADER / TOOLBAR =====
        header = tk.Frame(self.main_container, bg=theme.bg_dark, height=70)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        # Logo
        tk.Label(
            header, text=f"📚 {APP_NAME}", bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.title(bold=False)
        ).pack(side=tk.LEFT, padx=20, pady=15)
        
        # Search bar
        search_frame = tk.Frame(header, bg=theme.bg_secondary)
        search_frame.pack(side=tk.LEFT, padx=15, fill=tk.X, expand=True, pady=15)
        
        tk.Label(
            search_frame, text="🔍", bg=theme.bg_secondary,
            fg=theme.text_muted, font=("Segoe UI", 12)
        ).pack(side=tk.LEFT, padx=(10, 5))
        
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', self._on_search_change)
        
        self.search_entry = tk.Entry(
            search_frame, textvariable=self.search_var,
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            font=FONTS.body(), width=35
        )
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=5)
        Tooltip(self.search_entry, "Search bookmarks by title, URL, category, or tags.\nSpecial filters: is:pinned, is:broken, is:recent, is:untagged, domain:xyz")
        
        # Clear search button (X) - more visible styling
        self.clear_search_btn = tk.Label(
            search_frame, text="  ✕  ", bg=theme.bg_tertiary,
            fg=theme.text_secondary, font=("Segoe UI", 11, "bold"), cursor="hand2",
            relief=tk.FLAT, padx=4, pady=2
        )
        self.clear_search_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        def do_clear_search(event):
            # Clear search - handles everything
            self._clear_search()
            return "break"
        
        self.clear_search_btn.bind("<Button-1>", do_clear_search)
        self.clear_search_btn.bind("<Enter>", lambda e: self.clear_search_btn.configure(
            bg=theme.accent_error, fg="white"))
        self.clear_search_btn.bind("<Leave>", lambda e: self.clear_search_btn.configure(
            bg=theme.bg_tertiary, fg=theme.text_secondary))
        Tooltip(self.clear_search_btn, "Clear search and show all bookmarks (click to reset)")
        
        # ===== TOOLBAR BUTTONS =====
        toolbar = tk.Frame(header, bg=theme.bg_dark)
        toolbar.pack(side=tk.RIGHT, padx=15)
        
        # Add button
        add_btn = ModernButton(
            toolbar, text="Add", icon="➕", style="primary",
            command=self._add_bookmark,
            tooltip="Add a new bookmark manually"
        )
        add_btn.pack(side=tk.LEFT, padx=3)
        
        # Import button
        import_btn = ModernButton(
            toolbar, text="Import", icon="📥",
            command=self._show_import_dialog,
            tooltip="Import bookmarks from HTML, JSON, CSV, or OPML files"
        )
        import_btn.pack(side=tk.LEFT, padx=3)
        
        # Export button
        export_btn = ModernButton(
            toolbar, text="Export", icon="📤",
            command=self._show_export_dialog,
            tooltip="Export bookmarks to HTML, JSON, CSV, or Markdown"
        )
        export_btn.pack(side=tk.LEFT, padx=3)
        
        # Separator
        tk.Frame(toolbar, bg=theme.border, width=1, height=30).pack(side=tk.LEFT, padx=8)
        
        # AI button
        self.ai_btn = ModernButton(
            toolbar, text="AI", icon="🤖",
            command=self._show_ai_menu,
            tooltip="AI-powered tools: Auto-categorize, Generate tags,\nSummarize, Find semantic duplicates"
        )
        self.ai_btn.pack(side=tk.LEFT, padx=3)
        
        # Tools button
        self.tools_btn = ModernButton(
            toolbar, text="Tools", icon="🔧",
            command=self._show_tools_menu,
            tooltip="Tools: Check links, Find duplicates,\nClean URLs, Manage categories, Backup"
        )
        self.tools_btn.pack(side=tk.LEFT, padx=3)
        
        # Separator
        tk.Frame(toolbar, bg=theme.border, width=1, height=30).pack(side=tk.LEFT, padx=8)
        
        # Theme dropdown
        self.theme_dropdown = ThemeDropdown(
            toolbar, _theme_manager,
            on_change=lambda t: self._on_theme_change(t)
        )
        self.theme_dropdown.pack(side=tk.LEFT, padx=3)
        Tooltip(self.theme_dropdown, "Change application theme/color scheme")
        
        # Zoom controls
        tk.Frame(toolbar, bg=theme.border, width=1, height=30).pack(side=tk.LEFT, padx=8)
        
        zoom_frame = tk.Frame(toolbar, bg=theme.bg_primary)
        zoom_frame.pack(side=tk.LEFT, padx=3)
        
        self.zoom_level = 100  # 100% default
        self.zoom_min = 75
        self.zoom_max = 200
        
        zoom_out_btn = ModernButton(
            zoom_frame, text="−", command=self._zoom_out,
            tooltip="Zoom Out (Ctrl+Scroll Down)"
        )
        zoom_out_btn.pack(side=tk.LEFT, padx=1)
        
        self.zoom_label = tk.Label(
            zoom_frame, text="100%", bg=theme.bg_secondary,
            fg=theme.text_primary, font=FONTS.small(), width=5, padx=5, pady=4
        )
        self.zoom_label.pack(side=tk.LEFT, padx=2)
        Tooltip(self.zoom_label, "Current zoom level - Use Ctrl+Scroll to zoom")
        
        zoom_in_btn = ModernButton(
            zoom_frame, text="+", command=self._zoom_in,
            tooltip="Zoom In (Ctrl+Scroll Up)"
        )
        zoom_in_btn.pack(side=tk.LEFT, padx=1)
        
        # ===== CONTENT AREA =====
        content = tk.Frame(self.main_container, bg=theme.bg_primary)
        content.pack(fill=tk.BOTH, expand=True)
        
        # ----- LEFT SIDEBAR (Scrollable) -----
        left_sidebar = tk.Frame(content, bg=theme.bg_secondary, width=280)
        left_sidebar.pack(side=tk.LEFT, fill=tk.Y)
        left_sidebar.pack_propagate(False)
        
        # Scrollable container for left sidebar
        self.left_scroll = ScrollableFrame(left_sidebar, bg=theme.bg_secondary)
        self.left_scroll.pack(fill=tk.BOTH, expand=True)
        
        # Enhanced drag-drop import area
        self.import_area = DragDropImportArea(
            self.left_scroll.inner, on_files_dropped=self._on_files_dropped
        )
        self.import_area.pack(fill=tk.X, padx=10, pady=10)
        
        # Quick filters
        filters_frame = tk.Frame(self.left_scroll.inner, bg=theme.bg_secondary)
        filters_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        tk.Label(
            filters_frame, text="Quick Filters", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", pady=(5, 5))
        
        self.filter_buttons = {}
        self.active_filter = "All"  # Track active filter
        
        # Filter tooltips
        filter_tooltips = {
            "All": "Show all bookmarks",
            "Pinned": "Show only pinned bookmarks",
            "Recent": "Show bookmarks added in the last 7 days",
            "Broken": "Show bookmarks with broken links",
            "Untagged": "Show bookmarks without any tags"
        }
        
        for filter_name, icon in [("All", "📚"), ("Pinned", "📌"), ("Recent", "🕐"), ("Broken", "⚠️"), ("Untagged", "🏷️")]:
            is_active = (filter_name == "All")  # All is active by default
            btn = tk.Label(
                filters_frame, text=f"{icon} {filter_name}",
                bg=theme.selection if is_active else theme.bg_secondary,
                fg=theme.text_primary,
                font=FONTS.body(), cursor="hand2",
                padx=10, pady=5
            )
            btn.pack(fill=tk.X, pady=1)
            btn.bind("<Button-1>", lambda e, f=filter_name: self._apply_filter(f))
            # Only change bg on hover if not active
            def on_enter(e, b=btn, f=filter_name):
                if self.active_filter != f:
                    b.configure(bg=get_theme().bg_hover)
            def on_leave(e, b=btn, f=filter_name):
                if self.active_filter != f:
                    b.configure(bg=get_theme().bg_secondary)
            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)
            self.filter_buttons[filter_name] = btn
            
            # Add tooltip
            Tooltip(btn, filter_tooltips.get(filter_name, ""))
        
        # Categories header
        cat_header = tk.Frame(self.left_scroll.inner, bg=theme.bg_secondary)
        cat_header.pack(fill=tk.X, padx=10, pady=(15, 5))
        
        tk.Label(
            cat_header, text="Categories", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=("Segoe UI", 9, "bold")
        ).pack(side=tk.LEFT)
        
        # Categories list
        self.categories_frame = tk.Frame(self.left_scroll.inner, bg=theme.bg_secondary)
        self.categories_frame.pack(fill=tk.X, padx=10, pady=(0, 20))
        
        # ----- MAIN CONTENT -----
        self.content_area = tk.Frame(content, bg=theme.bg_primary)
        self.content_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Content header
        content_header = tk.Frame(self.content_area, bg=theme.bg_primary)
        content_header.pack(fill=tk.X, padx=15, pady=10)
        
        self.count_label = tk.Label(
            content_header, text="0 bookmarks", bg=theme.bg_primary,
            fg=theme.text_muted, font=FONTS.body()
        )
        self.count_label.pack(side=tk.LEFT)
        
        # List view frame
        self.list_frame = tk.Frame(self.content_area, bg=theme.bg_primary)
        
        # Create sortable treeview - REMOVED "Added" column, added more padding
        columns = ("title", "url", "category", "tags")
        self.tree = SortableTreeview(
            self.list_frame, columns=columns, show="tree headings",
            selectmode="extended"
        )
        
        # Configure columns with MORE padding for favicon
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=45, stretch=False, minwidth=45)  # Extra width for favicon padding
        
        self.tree.heading("title", text="Title")
        self.tree.column("title", width=350)
        
        self.tree.heading("url", text="URL")
        self.tree.column("url", width=280)
        
        self.tree.heading("category", text="Category")
        self.tree.column("category", width=160)
        
        self.tree.heading("tags", text="Tags")
        self.tree.column("tags", width=180)
        
        # Scrollbars
        tree_scroll_y = ttk.Scrollbar(self.list_frame, orient="vertical", command=self.tree.yview)
        tree_scroll_x = ttk.Scrollbar(self.list_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Tree bindings
        self.tree.bind("<Double-1>", self._on_item_double_click)
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<<TreeviewSelect>>", self._on_selection_change)
        
        # Ctrl+Scroll zoom binding
        self.tree.bind("<Control-MouseWheel>", self._on_mousewheel_zoom)
        self.list_frame.bind("<Control-MouseWheel>", self._on_mousewheel_zoom)
        
        # Show list view by default
        self.list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        # ----- RIGHT SIDEBAR (Scrollable) - ANALYTICS -----
        right_sidebar = tk.Frame(content, bg=theme.bg_secondary, width=300)
        right_sidebar.pack(side=tk.RIGHT, fill=tk.Y)
        right_sidebar.pack_propagate(False)
        
        # Scrollable container for right sidebar
        self.right_scroll = ScrollableFrame(right_sidebar, bg=theme.bg_secondary)
        self.right_scroll.pack(fill=tk.BOTH, expand=True)
        
        # Analytics Dashboard
        self._create_analytics_panel()
    
    def _create_analytics_panel(self):
        """Create analytics panel in right sidebar"""
        theme = get_theme()
        
        # Header
        header = tk.Frame(self.right_scroll.inner, bg=theme.bg_tertiary)
        header.pack(fill=tk.X)
        
        tk.Label(
            header, text="📊 Analytics", bg=theme.bg_tertiary,
            fg=theme.text_primary, font=("Segoe UI", 11, "bold"),
            padx=15, pady=12
        ).pack(side=tk.LEFT)
        
        refresh_btn = tk.Label(
            header, text="↻", bg=theme.bg_tertiary,
            fg=theme.text_muted, font=("Segoe UI", 14),
            cursor="hand2", padx=15
        )
        refresh_btn.pack(side=tk.RIGHT)
        refresh_btn.bind("<Button-1>", lambda e: self._refresh_analytics())
        
        # Stats container
        self.analytics_frame = tk.Frame(self.right_scroll.inner, bg=theme.bg_secondary)
        self.analytics_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
    
    def _refresh_analytics(self):
        """Refresh analytics display - streamlined version"""
        theme = get_theme()
        
        # Clear existing
        for widget in self.analytics_frame.winfo_children():
            widget.destroy()
        
        stats = self.bookmark_manager.get_statistics()
        
        # Health Score
        health = self._calculate_health_score(stats)
        health_color = theme.accent_success if health >= 70 else (theme.accent_warning if health >= 40 else theme.accent_error)
        
        # Health card
        health_card = tk.Frame(self.analytics_frame, bg=theme.bg_tertiary, padx=15, pady=10)
        health_card.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(
            health_card, text="Health Score", bg=theme.bg_tertiary,
            fg=theme.text_secondary, font=FONTS.small()
        ).pack(anchor="w")
        
        tk.Label(
            health_card, text=f"{health}%", bg=theme.bg_tertiary,
            fg=health_color, font=("Segoe UI", 24, "bold")
        ).pack(anchor="w", pady=(3, 3))
        
        # Health bar
        bar_bg = tk.Frame(health_card, bg=theme.bg_primary, height=6)
        bar_bg.pack(fill=tk.X, pady=(0, 3))
        bar_fill = tk.Frame(bar_bg, bg=health_color, height=6)
        bar_fill.place(x=0, y=0, relheight=1.0, relwidth=health/100)
        
        # Quick stats grid - streamlined (removed With Notes, Pinned, With Tags)
        tk.Label(
            self.analytics_frame, text="Overview", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", pady=(8, 5))
        
        stats_data = [
            ("Total Bookmarks", stats['total_bookmarks'], theme.text_primary),
            ("Categories", stats['total_categories'], theme.accent_primary),
            ("Unique Tags", stats['total_tags'], theme.accent_purple),
            ("Broken Links", stats['broken'], theme.accent_error),
            ("Uncategorized", stats['uncategorized'], theme.accent_warning),
        ]
        
        for label, value, color in stats_data:
            row = tk.Frame(self.analytics_frame, bg=theme.bg_secondary)
            row.pack(fill=tk.X, pady=2)
            
            tk.Label(
                row, text=label, bg=theme.bg_secondary,
                fg=theme.text_muted, font=FONTS.tiny()
            ).pack(side=tk.LEFT)
            
            tk.Label(
                row, text=str(value), bg=theme.bg_secondary,
                fg=color, font=("Segoe UI", 9, "bold")
            ).pack(side=tk.RIGHT)
        
        # Top categories (compact) - clickable like domains
        tk.Label(
            self.analytics_frame, text="Top Categories", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", pady=(12, 5))
        
        sorted_cats = sorted(stats['category_counts'].items(), key=lambda x: -x[1])[:5]
        max_count = max(sorted_cats[0][1], 1) if sorted_cats else 1
        
        for cat, count in sorted_cats:
            cat_frame = tk.Frame(self.analytics_frame, bg=theme.bg_secondary, cursor="hand2")
            cat_frame.pack(fill=tk.X, pady=2)
            
            cat_lbl = tk.Label(
                cat_frame, text=cat[:16], bg=theme.bg_secondary,
                fg=theme.accent_primary, font=("Segoe UI", 8, "underline"),
                cursor="hand2", anchor="w"
            )
            cat_lbl.pack(side=tk.LEFT)
            
            tk.Label(
                cat_frame, text=str(count), bg=theme.bg_secondary,
                fg=theme.text_muted, font=FONTS.tiny()
            ).pack(side=tk.RIGHT)
            
            # Bind click to select category (like clicking in left panel)
            for widget in [cat_frame, cat_lbl]:
                widget.bind("<Button-1>", lambda e, c=cat: self._select_category(c))
                widget.bind("<Enter>", lambda e, lbl=cat_lbl: lbl.configure(fg=theme.accent_success))
                widget.bind("<Leave>", lambda e, lbl=cat_lbl: lbl.configure(fg=theme.accent_primary))
        
        # Top domains - show up to 20 (clickable for filtering)
        top_domains = stats.get('top_domains', [])
        num_domains = min(20, len(top_domains)) if len(top_domains) >= 20 else len(top_domains)
        
        tk.Label(
            self.analytics_frame, text=f"Top Domains ({num_domains})", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", pady=(12, 5))
        
        # Create scrollable frame for domains if many
        domains_frame = tk.Frame(self.analytics_frame, bg=theme.bg_secondary)
        domains_frame.pack(fill=tk.X)
        
        for domain, count in top_domains[:20]:
            row = tk.Frame(domains_frame, bg=theme.bg_secondary, cursor="hand2")
            row.pack(fill=tk.X, pady=1)
            
            domain_lbl = tk.Label(
                row, text=domain[:20], bg=theme.bg_secondary,
                fg=theme.accent_primary, font=("Segoe UI", 8, "underline"),
                cursor="hand2"
            )
            domain_lbl.pack(side=tk.LEFT)
            
            tk.Label(
                row, text=str(count), bg=theme.bg_secondary,
                fg=theme.text_muted, font=FONTS.tiny()
            ).pack(side=tk.RIGHT)
            
            # Bind click to filter by domain
            for widget in [row, domain_lbl]:
                widget.bind("<Button-1>", lambda e, d=domain: self._filter_by_domain(d))
                widget.bind("<Enter>", lambda e, lbl=domain_lbl: lbl.configure(fg=theme.accent_success))
                widget.bind("<Leave>", lambda e, lbl=domain_lbl: lbl.configure(fg=theme.accent_primary))
    
    def _calculate_health_score(self, stats: Dict) -> int:
        """Calculate collection health score"""
        score = 100
        total = stats['total_bookmarks'] or 1
        
        broken_pct = (stats['broken'] / total) * 100
        uncat_pct = (stats['uncategorized'] / total) * 100
        dupe_pct = (stats['duplicate_bookmarks'] / total) * 100
        
        score -= min(30, broken_pct * 3)
        score -= min(20, uncat_pct * 0.5)
        score -= min(15, dupe_pct * 2)
        
        tagged_pct = (stats['with_tags'] / total) * 100
        noted_pct = (stats['with_notes'] / total) * 100
        
        score += min(10, tagged_pct * 0.1)
        score += min(5, noted_pct * 0.1)
        
        return max(0, min(100, int(score)))
    
    def _create_status_bar(self):
        """Create enhanced status bar with counts and progress"""
        theme = get_theme()
        
        self.status_bar = tk.Frame(self.root, bg=theme.bg_dark, height=32)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_bar.pack_propagate(False)
        
        # Left section: status message
        left_frame = tk.Frame(self.status_bar, bg=theme.bg_dark)
        left_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        self.status_label = tk.Label(
            left_frame, text="Ready", bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.small()
        )
        self.status_label.pack(side=tk.LEFT, padx=DesignTokens.SPACE_MD, pady=DesignTokens.SPACE_SM)
        
        # Progress indicator (hidden by default)
        self.status_progress = ttk.Progressbar(
            left_frame, mode="indeterminate", length=80
        )
        
        # Favicon progress
        self.favicon_status = FaviconStatusDisplay(self.status_bar)
        
        # Progress bar for long operations
        self.main_progress = EnhancedProgressBar(
            self.status_bar, height=32, show_label=True, show_percentage=True
        )
        
        # Right section: counts and version
        right_frame = tk.Frame(self.status_bar, bg=theme.bg_dark)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Separator
        sep = tk.Frame(right_frame, bg=theme.border, width=1)
        sep.pack(side=tk.LEFT, fill=tk.Y, padx=DesignTokens.SPACE_SM, pady=DesignTokens.SPACE_SM)
        
        # Selected count
        self.status_selected_label = tk.Label(
            right_frame, text="", bg=theme.bg_dark,
            fg=theme.accent_primary, font=FONTS.small()
        )
        self.status_selected_label.pack(side=tk.LEFT, padx=DesignTokens.SPACE_SM)
        
        # Total count
        self.status_total_label = tk.Label(
            right_frame, text="0 items", bg=theme.bg_dark,
            fg=theme.text_secondary, font=FONTS.small()
        )
        self.status_total_label.pack(side=tk.LEFT, padx=DesignTokens.SPACE_SM)
        
        # Separator
        sep2 = tk.Frame(right_frame, bg=theme.border, width=1)
        sep2.pack(side=tk.LEFT, fill=tk.Y, padx=DesignTokens.SPACE_SM, pady=DesignTokens.SPACE_SM)
        
        # Version
        tk.Label(
            right_frame, text=f"v{APP_VERSION}", bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.tiny()
        ).pack(side=tk.LEFT, padx=DesignTokens.SPACE_MD)
    
    def _load_and_display_data(self):
        """Load bookmarks and display - non-blocking"""
        self._refresh_category_list()
        self._refresh_bookmark_list()
        self._refresh_analytics()
        
        # Queue favicon downloads
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        self.favicon_manager.queue_bookmarks(bookmarks)
        
        self._set_status(f"Loaded {len(bookmarks)} bookmarks from {DATA_DIR}")
    
    def _refresh_category_list(self):
        """Refresh category list in sidebar with right-click support"""
        if not hasattr(self, 'categories_frame') or not self.categories_frame:
            return
        
        theme = get_theme()
        
        for widget in self.categories_frame.winfo_children():
            widget.destroy()
        
        categories = self.category_manager.get_sorted_categories()
        counts = self.bookmark_manager.get_category_counts()
        
        for cat in categories:
            count = counts.get(cat, 0)
            icon = get_category_icon(cat)
            
            btn = tk.Label(
                self.categories_frame,
                text=f"{icon} {cat} ({count})",
                bg=theme.bg_secondary if cat != self.current_category else theme.selection,
                fg=theme.text_primary, font=FONTS.body(),
                cursor="hand2", anchor="w", padx=10, pady=6
            )
            btn.pack(fill=tk.X, pady=1)
            
            btn.bind("<Button-1>", lambda e, c=cat: self._select_category(c))
            btn.bind("<Button-3>", lambda e, c=cat: self._show_category_context_menu(e, c))
            btn.bind("<Enter>", lambda e, b=btn, c=cat:
                    b.configure(bg=theme.bg_hover) if c != self.current_category else None)
            btn.bind("<Leave>", lambda e, b=btn, c=cat:
                    b.configure(bg=theme.bg_secondary) if c != self.current_category else None)
        
        # Also bind right-click on empty space for "Add Category"
        self.categories_frame.bind("<Button-3>", self._show_add_category_menu)
    
    def _show_category_context_menu(self, event, category: str):
        """Show context menu for category"""
        theme = get_theme()
        
        menu = tk.Menu(self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                      activebackground=theme.bg_hover, activeforeground=theme.text_primary)
        menu.add_command(label="  ➕  Add New Category", command=self._add_new_category_dialog)
        menu.add_command(label="  ✏️  Rename Category", command=lambda: self._rename_category_dialog(category))
        menu.add_separator()
        menu.add_command(label="  🗑️  Delete Category", command=lambda: self._delete_category_confirm(category))
        
        menu.tk_popup(event.x_root, event.y_root)
    
    def _show_add_category_menu(self, event):
        """Show menu for adding new category"""
        theme = get_theme()
        
        menu = tk.Menu(self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                      activebackground=theme.bg_hover, activeforeground=theme.text_primary)
        menu.add_command(label="  ➕  Add New Category", command=self._add_new_category_dialog)
        
        menu.tk_popup(event.x_root, event.y_root)
    
    def _add_new_category_dialog(self):
        """Show dialog to add new category"""
        theme = get_theme()
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Category")
        dialog.configure(bg=theme.bg_primary)
        dialog.geometry("350x120")
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(
            dialog, text="Category Name:", bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.body()
        ).pack(pady=(20, 5))
        
        entry = tk.Entry(
            dialog, bg=theme.bg_secondary, fg=theme.text_primary,
            font=FONTS.body(), relief=tk.FLAT, width=30
        )
        entry.pack(pady=5, ipady=5)
        entry.focus_set()
        
        def add():
            name = entry.get().strip()
            if name:
                if self.category_manager.add_category(name):
                    dialog.destroy()
                    self._refresh_category_list()
                    self._set_status(f"Added category: {name}")
                else:
                    messagebox.showerror("Error", "Category already exists or invalid name")
            else:
                dialog.destroy()
        
        entry.bind("<Return>", lambda e: add())
        
        tk.Button(
            dialog, text="Add", bg=theme.accent_success, fg="white",
            font=FONTS.body(), relief=tk.FLAT, command=add, padx=20
        ).pack(pady=10)
    
    def _rename_category_dialog(self, old_name: str):
        """Show dialog to rename category"""
        theme = get_theme()
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Rename Category")
        dialog.configure(bg=theme.bg_primary)
        dialog.geometry("350x120")
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(
            dialog, text="New Name:", bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.body()
        ).pack(pady=(20, 5))
        
        entry = tk.Entry(
            dialog, bg=theme.bg_secondary, fg=theme.text_primary,
            font=FONTS.body(), relief=tk.FLAT, width=30
        )
        entry.pack(pady=5, ipady=5)
        entry.insert(0, old_name)
        entry.select_range(0, tk.END)
        entry.focus_set()
        
        def rename():
            new_name = entry.get().strip()
            if new_name and new_name != old_name:
                # Update bookmarks
                for bm in self.bookmark_manager.get_bookmarks_by_category(old_name):
                    bm.category = new_name
                    self.bookmark_manager.update_bookmark(bm)
                
                self.category_manager.rename_category(old_name, new_name)
                dialog.destroy()
                self._refresh_category_list()
                self._refresh_bookmark_list()
                self._set_status(f"Renamed category to: {new_name}")
            else:
                dialog.destroy()
        
        entry.bind("<Return>", lambda e: rename())
        
        tk.Button(
            dialog, text="Rename", bg=theme.accent_primary, fg="white",
            font=FONTS.body(), relief=tk.FLAT, command=rename, padx=20
        ).pack(pady=10)
    
    def _delete_category_confirm(self, category: str):
        """Confirm and delete category"""
        count = len(self.bookmark_manager.get_bookmarks_by_category(category))
        
        msg = f"Delete category '{category}'?"
        if count > 0:
            msg += f"\n\n{count} bookmark(s) will be moved to 'Uncategorized / Needs Review'."
        
        if messagebox.askyesno("Delete Category", msg):
            # Move bookmarks to Uncategorized
            for bm in self.bookmark_manager.get_bookmarks_by_category(category):
                bm.category = "Uncategorized / Needs Review"
                self.bookmark_manager.update_bookmark(bm)
            
            # Delete the category
            if category in self.category_manager.categories:
                del self.category_manager.categories[category]
                self.category_manager.save_categories()
            
            self._refresh_category_list()
            self._refresh_bookmark_list()
            self._refresh_analytics()
            self._set_status(f"Deleted category: {category}")
    
    def _refresh_bookmark_list(self):
        """Refresh bookmark display with advanced filtering"""
        if not hasattr(self, 'tree') or not self.tree:
            return
        
        # Get base bookmarks - always start from all bookmarks for quick filters
        if self.current_category:
            bookmarks = self.bookmark_manager.get_bookmarks_by_category(self.current_category)
        else:
            bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        # Apply quick filter (takes priority over search)
        quick_filter = getattr(self, 'quick_filter', None)
        if quick_filter:
            if quick_filter == "pinned":
                bookmarks = [bm for bm in bookmarks if bm.is_pinned]
            elif quick_filter == "broken":
                bookmarks = [bm for bm in bookmarks if not bm.is_valid]
            elif quick_filter == "recent":
                week_ago = (datetime.now() - timedelta(days=7)).isoformat()
                # Handle bookmarks with empty or invalid created_at
                bookmarks = [bm for bm in bookmarks if bm.created_at and bm.created_at >= week_ago]
            elif quick_filter == "untagged":
                bookmarks = [bm for bm in bookmarks if not bm.tags and not bm.ai_tags]
        else:
            # Apply search query only if no quick filter
            query = self.search_query.strip() if hasattr(self, 'search_query') and self.search_query else ""
            
            if query:
                if query.startswith("domain:"):
                    # Filter by domain
                    domain_filter = query[7:].lower()
                    bookmarks = [bm for bm in bookmarks if domain_filter in (bm.domain or "").lower()]
                else:
                    # Regular text search
                    query_lower = query.lower()
                    bookmarks = [bm for bm in bookmarks
                                if query_lower in bm.title.lower() or
                                   query_lower in bm.url.lower() or
                                   query_lower in (bm.category or "").lower() or
                                   query_lower in ' '.join(bm.tags).lower()]
        
        bookmarks.sort(key=lambda b: (not b.is_pinned, b.title.lower()))
        
        if self.count_label:
            self.count_label.configure(text=f"{len(bookmarks)} bookmarks")
        
        if self.view_mode == ViewMode.LIST:
            self._populate_list_view(bookmarks)
        else:
            self._populate_grid_view(bookmarks)
    
    def _populate_list_view(self, bookmarks: List[Bookmark]):
        """Populate treeview with bookmarks"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        self._tree_items: Dict[int, str] = {}
        self._tree_domains: Dict[str, List[str]] = {}
        
        for bm in bookmarks:
            # Build title with status indicators
            prefix = ""
            if bm.is_pinned:
                prefix += "📌 "
            if bm.ai_confidence > 0:
                prefix += "🤖 "  # AI-processed indicator
            if not bm.is_valid:
                prefix += "⚠️ "
            
            if not prefix:
                prefix = "    "  # Extra padding for favicon alignment
            
            title = f"{prefix}{bm.title}"
            
            # Show both user tags and AI tags
            all_tags = list(bm.tags[:2])  # User tags first
            if bm.ai_tags and len(all_tags) < 3:
                # Add AI tags with indicator
                for at in bm.ai_tags[:2]:
                    if at not in all_tags and len(all_tags) < 3:
                        all_tags.append(f"🤖{at}")
            
            tags_str = ", ".join(all_tags)
            remaining = len(bm.tags) + len(bm.ai_tags) - len(all_tags)
            if remaining > 0:
                tags_str += f" +{remaining}"
            
            item_id = self.tree.insert(
                "", "end",
                iid=str(bm.id),
                text="  ",  # Padding space
                values=(title, bm.url[:45], bm.category, tags_str)
            )
            
            self._tree_items[bm.id] = item_id
            
            if bm.domain not in self._tree_domains:
                self._tree_domains[bm.domain] = []
            self._tree_domains[bm.domain].append(item_id)
            
            # Set favicon if cached
            favicon_path = self.favicon_manager.get_cached(bm.domain)
            if favicon_path:
                self.tree.set_favicon(item_id, favicon_path)
    
    def _populate_grid_view(self, bookmarks: List[Bookmark]):
        """Grid view disabled - using list view only"""
        pass  # Grid view removed - list view with zoom is now used
    
    def _load_next_grid_batch(self):
        """Grid view disabled - this is a stub"""
        pass
    
    def _on_favicon_progress(self, completed: int, total: int, current: str):
        """Favicon progress callback - thread-safe"""
        self.root.after(0, lambda: self.favicon_status.update_status(completed, total, current))
    
    def _on_favicon_ready_threadsafe(self, domain: str, filepath: str, bookmark_id: int):
        """Favicon ready callback - schedules UI update on main thread"""
        self.root.after(0, lambda: self._update_favicon_in_tree(domain, filepath))
    
    def _update_favicon_in_tree(self, domain: str, filepath: str):
        """Update favicon in treeview (runs on main thread)"""
        if hasattr(self, '_tree_domains') and domain in self._tree_domains:
            for item_id in self._tree_domains[domain]:
                try:
                    self.tree.set_favicon(item_id, filepath)
                except Exception:
                    pass
    
    def _set_view_mode(self, mode: ViewMode):
        """View mode - now only list view is supported"""
        self.view_mode = ViewMode.LIST
        self._refresh_bookmark_list()
    
    def _zoom_in(self):
        """Increase zoom level"""
        if self.zoom_level < self.zoom_max:
            self.zoom_level = min(self.zoom_level + 15, self.zoom_max)
            self._apply_zoom()
    
    def _zoom_out(self):
        """Decrease zoom level"""
        if self.zoom_level > self.zoom_min:
            self.zoom_level = max(self.zoom_level - 15, self.zoom_min)
            self._apply_zoom()
    
    def _on_mousewheel_zoom(self, event):
        """Handle Ctrl+Scroll for zoom"""
        # Check if Ctrl is pressed
        if event.state & 0x4:  # Control key modifier
            if event.delta > 0:
                self._zoom_in()
            else:
                self._zoom_out()
            return "break"  # Prevent normal scrolling
    
    def _apply_zoom(self):
        """Apply current zoom level to tree view"""
        theme = get_theme()
        
        # Update zoom label
        if self.zoom_label:
            self.zoom_label.configure(text=f"{self.zoom_level}%")
        
        # Calculate row height based on zoom (base is 30 at 100%)
        base_row_height = 30
        row_height = int(base_row_height * (self.zoom_level / 100))
        row_height = max(20, min(80, row_height))  # Clamp between 20-80
        
        # Calculate font size based on zoom (base is 10 at 100%)
        base_font_size = 10
        font_size = int(base_font_size * (self.zoom_level / 100))
        font_size = max(8, min(18, font_size))  # Clamp between 8-18
        
        # Update treeview style - use "Treeview" which is the default style
        style = ttk.Style()
        style.configure(
            "Treeview",
            rowheight=row_height,
            font=("Segoe UI", font_size)
        )
        style.configure(
            "Treeview.Heading",
            font=("Segoe UI", font_size, "bold")
        )
        
        # Force tree to update
        if self.tree:
            self.tree.update_idletasks()
        
        self._set_status(f"Zoom: {self.zoom_level}%")
    
    def _select_all_bookmarks(self):
        """Select all bookmarks in view (Ctrl+A)"""
        all_items = self.tree.get_children()
        self.tree.selection_set(all_items)
        self.selected_bookmarks = [int(item) for item in all_items]
        self._set_status(f"Selected {len(all_items)} bookmarks")
        return "break"  # Prevent default behavior
    
    def _on_search_change(self, *args):
        """Handle search change with debounce"""
        # Skip if suppressed (programmatic change)
        if getattr(self, '_suppress_search_callback', False):
            return
        
        if not self.search_var:
            return
        
        self.search_query = self.search_var.get()
        
        # When user types in search, clear quick filter and reset filter buttons
        if self.search_query:
            self.quick_filter = None
            self.active_filter = None
            # Update button highlighting
            theme = get_theme()
            for name, btn in self.filter_buttons.items():
                btn.configure(bg=theme.bg_secondary)
        
        # Cancel any pending refresh
        self._cancel_search_debounce()
        
        # Schedule debounced refresh
        self._search_after = self.root.after(200, self._refresh_bookmark_list)
    
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
        
        # Reset filter button highlighting
        theme = get_theme()
        for name, btn in self.filter_buttons.items():
            if name == "All":
                btn.configure(bg=theme.selection)
            else:
                btn.configure(bg=theme.bg_secondary)
        
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
        theme = get_theme()
        for name, btn in self.filter_buttons.items():
            btn.configure(bg=theme.bg_secondary)
        
        # Set search query directly in entry
        if self.search_entry:
            self.search_entry.delete(0, tk.END)
            self.search_entry.insert(0, f"domain:{domain}")
        if self.search_var:
            self.search_var.set(f"domain:{domain}")
        self.search_query = f"domain:{domain}"
        
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
        
        # Clear quick filter button highlighting
        theme = get_theme()
        for name, btn in self.filter_buttons.items():
            btn.configure(bg=theme.bg_secondary)
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
        theme = get_theme()
        
        # Cancel any pending search refresh first
        self._cancel_search_debounce()
        
        # Set suppress flag
        self._suppress_search_callback = True
        
        # Update active filter tracking
        self.active_filter = filter_name
        
        # Update all button states immediately
        for name, btn in self.filter_buttons.items():
            if name == filter_name:
                btn.configure(bg=theme.selection)
            else:
                btn.configure(bg=theme.bg_secondary)
        
        # Clear the search bar directly
        if self.search_entry:
            self.search_entry.delete(0, tk.END)
        if self.search_var:
            self.search_var.set("")
        
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
        
        # Set StringVar - this will trigger trace but flag is set
        if self.search_var:
            self.search_var.set(text)
        
        # Keep flag set for a brief moment to catch any queued callbacks
        def reset_flag():
            self._suppress_search_callback = False
        self.root.after(50, reset_flag)
    
    def _on_selection_change(self, event):
        """Handle tree selection change"""
        self.selected_bookmarks = [int(item) for item in self.tree.selection()]
        self._update_status_counts()
    
    def _on_item_double_click(self, event):
        """Handle double-click"""
        item = self.tree.identify_row(event.y)
        if item:
            bookmark = self.bookmark_manager.get_bookmark(int(item))
            if bookmark:
                self._open_bookmark(bookmark)
    
    def _on_bookmark_click(self, bookmark: Bookmark):
        """Handle bookmark click"""
        pass
    
    def _open_bookmark(self, bookmark: Bookmark):
        """Open bookmark in browser"""
        webbrowser.open(bookmark.url)
        bookmark.visit_count += 1
        bookmark.last_visited = datetime.now().isoformat()
        self.bookmark_manager.update_bookmark(bookmark)
    
    def _show_context_menu(self, event):
        """Show context menu with Send To and Search Domain options"""
        theme = get_theme()
        item = self.tree.identify_row(event.y)
        if not item:
            return
        
        # Select item if not already selected
        if item not in self.tree.selection():
            self.tree.selection_set(item)
        
        # Update selected_bookmarks list
        self.selected_bookmarks = [int(i) for i in self.tree.selection()]
        
        # Get selected bookmark for domain search
        first_bookmark = None
        if self.selected_bookmarks:
            first_bookmark = self.bookmark_manager.get_bookmark(self.selected_bookmarks[0])
        
        menu = tk.Menu(self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                      activebackground=theme.bg_hover, activeforeground=theme.text_primary)
        menu.add_command(label="  🔗  Open in Browser", command=self._open_selected)
        menu.add_command(label="  ✏️  Edit", command=self._edit_selected)
        menu.add_separator()
        
        # Search Domain option
        if first_bookmark and first_bookmark.domain:
            menu.add_command(
                label=f"  🔍  Search Domain ({first_bookmark.domain})",
                command=lambda: self._filter_by_domain(first_bookmark.domain)
            )
        
        # Send To submenu with all categories
        send_to_menu = tk.Menu(menu, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                              activebackground=theme.bg_hover, activeforeground=theme.text_primary)
        
        categories = self.category_manager.get_sorted_categories()
        for cat in categories:
            icon = get_category_icon(cat)
            send_to_menu.add_command(
                label=f"{icon} {cat}",
                command=lambda c=cat: self._send_to_category(c)
            )
        
        menu.add_cascade(label="  📂  Send to", menu=send_to_menu)
        menu.add_separator()
        menu.add_command(label="  📋  Copy URL", command=self._copy_url)
        menu.add_command(label="  📌  Toggle Pin", command=self._toggle_pin)
        menu.add_command(label="  🎨  Custom Favicon...", command=self._show_custom_favicon_dialog)
        menu.add_separator()
        
        # AI Tools submenu
        ai_menu = tk.Menu(menu, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                         activebackground=theme.bg_hover, activeforeground=theme.text_primary)
        ai_menu.add_command(label="🤖  AI Categorize", command=self._ai_categorize)
        ai_menu.add_command(label="🏷️  AI Suggest Tags", command=self._ai_suggest_tags)
        ai_menu.add_command(label="📝  AI Summarize", command=self._ai_summarize)
        ai_menu.add_command(label="✏️  AI Improve Titles", command=self._ai_improve_titles)
        menu.add_cascade(label="  🤖  AI Tools", menu=ai_menu)
        
        menu.add_separator()
        menu.add_command(label="  ⚠️  Mark as Broken", command=self._mark_as_broken)
        menu.add_command(label="  🗑️  Delete", command=self._delete_selected)
        
        menu.tk_popup(event.x_root, event.y_root)
    
    def _send_to_category(self, category: str):
        """Send selected bookmarks to a category"""
        if not self.selected_bookmarks:
            return
        
        count = 0
        for bm_id in self.selected_bookmarks:
            bookmark = self.bookmark_manager.get_bookmark(bm_id)
            if bookmark:
                bookmark.category = category
                self.bookmark_manager.update_bookmark(bookmark)
                count += 1
        
        self._refresh_all()
        self._set_status(f"Moved {count} bookmark(s) to '{category}'")
    
    def _mark_as_broken(self):
        """Mark selected bookmarks as broken"""
        if not self.selected_bookmarks:
            return
        
        for bm_id in self.selected_bookmarks:
            bookmark = self.bookmark_manager.get_bookmark(bm_id)
            if bookmark:
                bookmark.is_valid = False
                bookmark.notes = (bookmark.notes or "") + "\n[Marked as potentially broken]"
                self.bookmark_manager.update_bookmark(bookmark)
        
        self._refresh_bookmark_list()
        self._set_status(f"Marked {len(self.selected_bookmarks)} bookmark(s) as broken")
    
    def _show_ai_menu(self):
        """Show AI tools menu"""
        theme = get_theme()
        
        menu = tk.Menu(self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                      font=FONTS.body(), activebackground=theme.bg_hover,
                      activeforeground=theme.text_primary, bd=0)
        
        menu.add_command(label="  🤖  AI Categorize Selected", command=self._ai_categorize)
        menu.add_command(label="  🏷️  AI Suggest Tags", command=self._ai_suggest_tags)
        menu.add_command(label="  📝  AI Summarize", command=self._ai_summarize)
        menu.add_command(label="  ✏️  AI Improve Titles", command=self._ai_improve_titles)
        menu.add_separator()
        menu.add_command(label="  🔀  Merge AI Tags to User Tags", command=self._merge_ai_tags)
        menu.add_separator()
        menu.add_command(label="  📤  Export AI Data (JSON)", command=self._export_ai_data)
        menu.add_command(label="  🧠  Export Learned Patterns", command=self._generate_category_patterns)
        menu.add_command(label="  📥  Import Learned Patterns", command=self._import_ai_learned_data)
        menu.add_separator()
        menu.add_command(label="  📊  View AI Statistics", command=self._show_ai_stats)
        menu.add_command(label="  ⚙️  AI Settings", command=self._show_ai_settings)
        
        # Position below button
        x = self.ai_btn.winfo_rootx()
        y = self.ai_btn.winfo_rooty() + self.ai_btn.winfo_height()
        menu.tk_popup(x, y)
    
    def _merge_ai_tags(self):
        """Merge AI-suggested tags into user tags"""
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        merged = 0
        tags_added = 0
        
        for bm in bookmarks:
            if bm.ai_tags:
                # Merge AI tags into user tags (avoid duplicates)
                existing = set(t.lower() for t in bm.tags)
                for tag in bm.ai_tags:
                    if tag.lower() not in existing:
                        bm.tags.append(tag)
                        tags_added += 1
                        existing.add(tag.lower())
                
                if bm.ai_tags:
                    merged += 1
                    bm.modified_at = datetime.now().isoformat()
        
        if merged > 0:
            self.bookmark_manager.save_bookmarks()
            self._refresh_bookmark_list()
            messagebox.showinfo("Tags Merged", 
                f"Merged AI tags into user tags.\n\n"
                f"Bookmarks updated: {merged}\n"
                f"Tags added: {tags_added}")
        else:
            messagebox.showinfo("No AI Tags", 
                "No AI tags found to merge.\n\n"
                "Use 'AI Suggest Tags' first to generate AI tags.")
        
        self._set_status(f"Merged {tags_added} AI tags")
    
    def _export_ai_data(self):
        """Export AI-enriched bookmark data to JSON"""
        filepath = filedialog.asksaveasfilename(
            title="Export AI Data",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            initialfilename="bookmarks_ai_data.json"
        )
        
        if not filepath:
            return
        
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        # Build export data
        export_data = {
            "export_date": datetime.now().isoformat(),
            "total_bookmarks": len(bookmarks),
            "categories": {},
            "bookmarks": []
        }
        
        # Export category data
        for cat_name, cat in self.category_manager.categories.items():
            export_data["categories"][cat_name] = {
                "icon": cat.icon,
                "patterns": cat.patterns,
                "description": cat.description
            }
        
        # Export bookmark data with AI fields
        for bm in bookmarks:
            bm_data = {
                "url": bm.url,
                "title": bm.title,
                "domain": bm.domain,
                "category": bm.category,
                "tags": bm.tags,
                "ai_tags": bm.ai_tags,
                "ai_confidence": bm.ai_confidence,
                "description": bm.description,
                "created_at": bm.created_at
            }
            export_data["bookmarks"].append(bm_data)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            messagebox.showinfo("Export Complete", 
                f"AI data exported successfully.\n\n"
                f"File: {filepath}\n"
                f"Bookmarks: {len(bookmarks)}\n"
                f"Categories: {len(export_data['categories'])}")
            self._set_status(f"Exported AI data to {Path(filepath).name}")
            
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export: {str(e)}")
    
    def _show_ai_stats(self):
        """Show AI processing statistics"""
        theme = get_theme()
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        # Calculate stats
        total = len(bookmarks)
        with_ai_cat = sum(1 for bm in bookmarks if bm.ai_confidence > 0)
        with_ai_tags = sum(1 for bm in bookmarks if bm.ai_tags)
        with_desc = sum(1 for bm in bookmarks if bm.description)
        
        avg_confidence = 0
        if with_ai_cat > 0:
            avg_confidence = sum(bm.ai_confidence for bm in bookmarks if bm.ai_confidence > 0) / with_ai_cat
        
        # Count unique AI tags
        all_ai_tags = set()
        for bm in bookmarks:
            all_ai_tags.update(bm.ai_tags)
        
        # Show dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("AI Statistics")
        dialog.configure(bg=theme.bg_primary)
        dialog.geometry("400x350")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 400) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 350) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # Header
        tk.Label(dialog, text="📊 AI Processing Statistics", bg=theme.bg_primary,
                fg=theme.text_primary, font=FONTS.title(bold=False)).pack(pady=20)
        
        # Stats
        stats_frame = tk.Frame(dialog, bg=theme.bg_primary)
        stats_frame.pack(fill=tk.X, padx=30)
        
        stats = [
            ("Total Bookmarks", str(total)),
            ("AI Categorized", f"{with_ai_cat} ({100*with_ai_cat//max(1,total)}%)"),
            ("With AI Tags", f"{with_ai_tags} ({100*with_ai_tags//max(1,total)}%)"),
            ("With Descriptions", f"{with_desc} ({100*with_desc//max(1,total)}%)"),
            ("Avg. Confidence", f"{avg_confidence:.1%}"),
            ("Unique AI Tags", str(len(all_ai_tags)))
        ]
        
        for label, value in stats:
            row = tk.Frame(stats_frame, bg=theme.bg_primary)
            row.pack(fill=tk.X, pady=5)
            
            tk.Label(row, text=label + ":", bg=theme.bg_primary,
                    fg=theme.text_secondary, font=FONTS.body(),
                    width=20, anchor="w").pack(side=tk.LEFT)
            tk.Label(row, text=value, bg=theme.bg_primary,
                    fg=theme.text_primary, font=("Segoe UI", 10, "bold"),
                    anchor="e").pack(side=tk.RIGHT)
        
        # Top AI tags
        if all_ai_tags:
            tk.Label(dialog, text="Top AI Tags:", bg=theme.bg_primary,
                    fg=theme.text_secondary, font=FONTS.body()).pack(pady=(20, 5))
            
            # Count tag frequency
            tag_counts = {}
            for bm in bookmarks:
                for tag in bm.ai_tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
            
            top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            tags_text = ", ".join(f"{t} ({c})" for t, c in top_tags)
            
            tk.Label(dialog, text=tags_text, bg=theme.bg_primary,
                    fg=theme.accent_primary, font=FONTS.small(),
                    wraplength=350).pack(padx=20)
        
        # Close button
        tk.Button(dialog, text="Close", command=dialog.destroy,
                 bg=theme.bg_secondary, fg=theme.text_primary,
                 font=FONTS.body(), padx=20, pady=5).pack(pady=20)
    
    def _generate_category_patterns(self):
        """Generate category patterns from AI-categorized bookmarks to enhance built-in rules"""
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        # Only use high-confidence AI categorizations
        ai_categorized = [bm for bm in bookmarks if bm.ai_confidence >= 0.7]
        
        if not ai_categorized:
            messagebox.showinfo("No AI Data", 
                "No high-confidence AI categorizations found.\n\n"
                "Run AI Categorize on your bookmarks first.")
            return
        
        # Group domains by category
        category_domains: Dict[str, List[str]] = {}
        for bm in ai_categorized:
            cat = bm.category
            domain = bm.domain
            if cat and domain:
                if cat not in category_domains:
                    category_domains[cat] = []
                if domain not in category_domains[cat]:
                    category_domains[cat].append(domain)
        
        # Generate patterns file
        filepath = filedialog.asksaveasfilename(
            title="Export Category Patterns",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            initialfilename="learned_category_patterns.json"
        )
        
        if not filepath:
            return
        
        # Build export with domains sorted by frequency
        export_data = {
            "_meta": {
                "generated": datetime.now().isoformat(),
                "source": "Bookmark Organizer Pro - AI Learning",
                "total_bookmarks_analyzed": len(ai_categorized),
                "min_confidence": 0.7,
                "instructions": "Import this file using Tools > Import Categories File to add these patterns"
            },
            "categories": {}
        }
        
        for cat, domains in sorted(category_domains.items()):
            # Count how many bookmarks per domain
            domain_counts = {}
            for bm in ai_categorized:
                if bm.category == cat:
                    d = bm.domain
                    domain_counts[d] = domain_counts.get(d, 0) + 1
            
            # Sort by frequency and take top patterns
            sorted_domains = sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)
            top_patterns = [d for d, c in sorted_domains[:20]]  # Top 20 domains per category
            
            export_data["categories"][cat] = top_patterns
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            total_patterns = sum(len(p) for p in export_data["categories"].values())
            messagebox.showinfo("Patterns Exported", 
                f"Category patterns exported successfully!\n\n"
                f"File: {Path(filepath).name}\n"
                f"Categories: {len(export_data['categories'])}\n"
                f"Total patterns: {total_patterns}\n\n"
                "Share this file to help improve categorization for others!")
            self._set_status(f"Exported {total_patterns} learned patterns")
            
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export: {str(e)}")
    
    def _import_ai_learned_data(self):
        """Import AI-learned data from another user's export"""
        filepath = filedialog.askopenfilename(
            title="Import AI Learned Data",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        
        if not filepath:
            return
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check if it's our format
            if "categories" not in data:
                messagebox.showerror("Invalid File", "This doesn't appear to be an AI learned data file.")
                return
            
            imported = 0
            updated = 0
            
            for cat_name, patterns in data.get("categories", {}).items():
                if not isinstance(patterns, list):
                    continue
                
                if cat_name not in self.category_manager.categories:
                    # Create new category
                    new_cat = Category(
                        name=cat_name,
                        patterns=patterns,
                        icon=get_category_icon(cat_name)
                    )
                    self.category_manager.categories[cat_name] = new_cat
                    imported += 1
                else:
                    # Merge patterns into existing
                    existing = self.category_manager.categories[cat_name]
                    existing_patterns = set(existing.patterns)
                    for pattern in patterns:
                        if pattern not in existing_patterns:
                            existing.patterns.append(pattern)
                            updated += 1
            
            self.category_manager.save_categories()
            self._refresh_category_list()
            
            messagebox.showinfo("Import Complete", 
                f"AI learned data imported!\n\n"
                f"New categories: {imported}\n"
                f"Patterns added: {updated}")
            self._set_status(f"Imported {imported} categories, {updated} patterns")
            
        except Exception as e:
            messagebox.showerror("Import Error", f"Failed to import: {str(e)}")
    
    def _show_tools_menu(self):
        """Show tools menu"""
        theme = get_theme()
        
        menu = tk.Menu(self.root, tearoff=0, bg=theme.bg_secondary, fg=theme.text_primary,
                      font=FONTS.body(), activebackground=theme.bg_hover,
                      activeforeground=theme.text_primary, bd=0)
        
        menu.add_command(label="  📁  Manage Categories", command=self._show_category_manager)
        menu.add_command(label="  🗂️  Categorize All Bookmarks", command=self._categorize_all_bookmarks)
        menu.add_command(label="  📥  Import Categories File", command=self._import_categories_file)
        menu.add_command(label="  🎨  Set Custom Favicon", command=self._show_custom_favicon_dialog)
        menu.add_separator()
        menu.add_command(label="  🔍  Check All Links", command=self._check_all_links)
        menu.add_command(label="  🔄  Find Duplicates", command=self._find_duplicates)
        menu.add_command(label="  🧹  Clean URLs", command=self._clean_urls)
        menu.add_separator()
        menu.add_command(label="  📊  Full Analytics", command=self._show_analytics)
        menu.add_command(label="  💾  Backup Now", command=self._backup_now)
        menu.add_separator()
        menu.add_command(label="  🔄  Redownload All Favicons", command=self._redownload_all_favicons)
        menu.add_command(label="  🔄  Redownload Missing Favicons", command=self._redownload_missing_favicons)
        menu.add_command(label="  🗑️  Clear Favicon Cache", command=self._clear_favicon_cache)
        
        # Position below button
        x = self.tools_btn.winfo_rootx()
        y = self.tools_btn.winfo_rooty() + self.tools_btn.winfo_height()
        menu.tk_popup(x, y)
    
    def _categorize_all_bookmarks(self):
        """Reprocess all bookmarks and categorize them based on category patterns - non-blocking"""
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        if not bookmarks:
            messagebox.showinfo("No Bookmarks", "No bookmarks to categorize.")
            return
        
        result = messagebox.askyesno(
            "Categorize All Bookmarks",
            f"This will re-categorize all {len(bookmarks)} bookmarks based on URL patterns.\n\n"
            "Bookmarks will be assigned to categories based on domain matching.\n\n"
            "Continue?"
        )
        
        if not result:
            return
        
        # Create progress display
        theme = get_theme()
        self._cat_cancelled = False
        
        progress_frame = tk.Frame(self.status_bar, bg=theme.bg_dark)
        progress_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        
        progress_label = tk.Label(
            progress_frame, text="Categorizing...", bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.small()
        )
        progress_label.pack(side=tk.LEFT, padx=5)
        
        progress_bar = tk.Frame(progress_frame, bg=theme.bg_tertiary, height=8, width=200)
        progress_bar.pack(side=tk.LEFT, padx=5)
        progress_bar.pack_propagate(False)
        
        progress_fill = tk.Frame(progress_bar, bg=theme.accent_primary, height=8)
        progress_fill.place(x=0, y=0, relheight=1.0, relwidth=0)
        
        cancel_btn = tk.Label(
            progress_frame, text="✕ Cancel", bg=theme.accent_error, fg="white",
            font=FONTS.small(), padx=8, pady=2, cursor="hand2"
        )
        cancel_btn.pack(side=tk.LEFT, padx=10)
        cancel_btn.bind("<Button-1>", lambda e: setattr(self, '_cat_cancelled', True))
        
        # Categorize in batches using after() for UI responsiveness
        self._cat_index = 0
        self._cat_changed = 0
        self._cat_unchanged = 0
        self._cat_bookmarks = bookmarks
        
        def process_batch():
            if self._cat_cancelled or self._cat_index >= len(self._cat_bookmarks):
                # Done or cancelled
                progress_frame.destroy()
                self.bookmark_manager.save_bookmarks()
                self._refresh_all()
                
                if self._cat_cancelled:
                    self._set_status(f"Cancelled. Changed {self._cat_changed} bookmarks.")
                else:
                    self._set_status(f"Categorized {self._cat_changed} bookmarks")
                    messagebox.showinfo(
                        "Categorization Complete",
                        f"Categorized: {self._cat_changed} bookmarks\n"
                        f"Unchanged: {self._cat_unchanged} bookmarks"
                    )
                return
            
            # Process batch of 20
            batch_end = min(self._cat_index + 20, len(self._cat_bookmarks))
            for i in range(self._cat_index, batch_end):
                bm = self._cat_bookmarks[i]
                old_cat = bm.category
                new_cat = self.category_manager.categorize_url(bm.url, bm.title)
                
                if new_cat != old_cat:
                    bm.category = new_cat
                    self._cat_changed += 1
                else:
                    self._cat_unchanged += 1
            
            self._cat_index = batch_end
            
            # Update progress
            progress = self._cat_index / len(self._cat_bookmarks)
            progress_fill.place(relwidth=progress)
            progress_label.configure(text=f"Categorizing: {self._cat_index}/{len(self._cat_bookmarks)} ({self._cat_changed} changed)")
            
            # Schedule next batch
            self.root.after(10, process_batch)
        
        # Start processing
        self.root.after(100, process_batch)
    
    def _import_categories_file(self):
        """Import categories from a JSON file"""
        filepath = filedialog.askopenfilename(
            title="Select Categories JSON File",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        
        if not filepath:
            return
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                categories_data = json.load(f)
            
            if not isinstance(categories_data, dict):
                messagebox.showerror("Error", "Invalid categories file format. Expected JSON object.")
                return
            
            # Merge with existing categories
            imported = 0
            updated = 0
            for cat_name, patterns in categories_data.items():
                patterns_list = patterns if isinstance(patterns, list) else []
                
                if cat_name not in self.category_manager.categories:
                    # Create new Category object
                    new_cat = Category(
                        name=cat_name,
                        patterns=patterns_list,
                        icon=get_category_icon(cat_name)
                    )
                    self.category_manager.categories[cat_name] = new_cat
                    imported += 1
                else:
                    # Merge patterns into existing category
                    existing_cat = self.category_manager.categories[cat_name]
                    if hasattr(existing_cat, 'patterns'):
                        for p in patterns_list:
                            if p not in existing_cat.patterns:
                                existing_cat.patterns.append(p)
                        updated += 1
            
            # Rebuild pattern engine and save
            self.category_manager._rebuild_patterns()
            self.category_manager.save_categories()
            self._refresh_category_list()
            self._refresh_analytics()
            
            messagebox.showinfo(
                "Import Complete",
                f"Imported {imported} new categories.\n"
                f"Updated {updated} existing categories.\n"
                f"Total categories: {len(self.category_manager.categories)}"
            )
            self._set_status(f"Imported {imported} categories, updated {updated}")
            
        except json.JSONDecodeError as e:
            messagebox.showerror("Error", f"Invalid JSON format: {e}")
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to import categories: {e}")
    
    def _on_theme_change(self, theme_name: str):
        """Handle theme change - apply live"""
        self._apply_theme_live()
        self._set_status(f"Theme changed to {theme_name}")
    
    def _apply_theme_live(self):
        """Apply current theme to all widgets recursively"""
        # Safety check - only proceed if fully initialized
        if not hasattr(self, 'main_container'):
            return
        
        theme = get_theme()
        
        def apply_to_widget(widget, bg_color=None):
            """Recursively apply theme to widget and children"""
            try:
                widget_class = widget.winfo_class()
                
                # Skip certain widget types
                if widget_class in ('Menu', 'Scrollbar'):
                    return
                
                # Determine background color
                if bg_color:
                    widget.configure(bg=bg_color)
                elif widget_class == 'Frame':
                    widget.configure(bg=theme.bg_primary)
                elif widget_class == 'Label':
                    widget.configure(bg=theme.bg_primary, fg=theme.text_primary)
                elif widget_class == 'Entry':
                    widget.configure(bg=theme.bg_secondary, fg=theme.text_primary)
                elif widget_class == 'Listbox':
                    widget.configure(bg=theme.bg_secondary, fg=theme.text_primary)
            except Exception:
                pass
            
            # Apply to children
            for child in widget.winfo_children():
                try:
                    apply_to_widget(child)
                except Exception:
                    pass
        
        # Apply to root
        try:
            self.root.configure(bg=theme.bg_primary)
            apply_to_widget(self.main_container)
        except Exception:
            pass
        
        # Update status bar explicitly
        try:
            self.status_bar.configure(bg=theme.bg_dark)
            self.status_label.configure(bg=theme.bg_dark, fg=theme.text_muted)
        except Exception:
            pass
        
        # Refresh all data displays (this recreates widgets with new theme)
        try:
            self._refresh_category_list()
            self._refresh_bookmark_list()
            self._refresh_analytics()
        except Exception as e:
            print(f"Theme refresh error: {e}")
    
    def _add_bookmark(self):
        """Add new bookmark"""
        dialog = QuickAddDialog(
            self.root, self.category_manager.get_sorted_categories(),
            on_add=self._on_bookmark_added
        )
    
    def _on_bookmark_added(self, data: Dict):
        """Handle new bookmark"""
        bookmark = Bookmark(
            id=None, url=data["url"],
            title=data["title"], category=data["category"]
        )
        
        self.bookmark_manager.add_bookmark(bookmark)
        self.favicon_manager.download_async(bookmark.domain, bookmark.id)
        
        self._refresh_all()
        self._set_status(f"Added: {bookmark.title}")
    
    def _edit_selected(self):
        """Edit selected bookmark"""
        if self.selected_bookmarks:
            bookmark = self.bookmark_manager.get_bookmark(self.selected_bookmarks[0])
            if bookmark:
                dialog = BookmarkEditorDialog(
                    self.root, bookmark,
                    categories=self.category_manager.get_sorted_categories(),
                    available_tags=self.tag_manager.get_all_tags(),
                    on_save=lambda bm: self._on_bookmark_edited(bm)
                )
    
    def _on_bookmark_edited(self, bookmark: Bookmark):
        """Handle edited bookmark"""
        self.bookmark_manager.update_bookmark(bookmark)
        self._refresh_all()
    
    def _open_selected(self):
        """Open selected bookmarks"""
        for bm_id in self.selected_bookmarks:
            bookmark = self.bookmark_manager.get_bookmark(bm_id)
            if bookmark:
                self._open_bookmark(bookmark)
    
    def _copy_url(self):
        """Copy URLs to clipboard"""
        urls = []
        for bm_id in self.selected_bookmarks:
            bookmark = self.bookmark_manager.get_bookmark(bm_id)
            if bookmark:
                urls.append(bookmark.url)
        
        if urls:
            self.root.clipboard_clear()
            self.root.clipboard_append('\n'.join(urls))
            self._set_status(f"Copied {len(urls)} URL(s)")
    
    def _toggle_pin(self):
        """Toggle pin status"""
        for bm_id in self.selected_bookmarks:
            bookmark = self.bookmark_manager.get_bookmark(bm_id)
            if bookmark:
                bookmark.is_pinned = not bookmark.is_pinned
                self.bookmark_manager.update_bookmark(bookmark)
        self._refresh_bookmark_list()
    
    def _delete_selected(self):
        """Delete selected bookmarks"""
        if not self.selected_bookmarks:
            return
        
        count = len(self.selected_bookmarks)
        if not messagebox.askyesno("Delete", f"Delete {count} bookmark(s)?"):
            return
        
        for bm_id in self.selected_bookmarks:
            self.bookmark_manager.delete_bookmark(bm_id)
        
        self.selected_bookmarks.clear()
        self._refresh_all()
        self._set_status(f"Deleted {count} bookmark(s)")
    
    def _on_files_dropped(self, filepaths: List[str]):
        """Handle dropped files for import with backup and auto-categorization"""
        self.import_area.set_importing(True)
        self._set_status(f"Importing {len(filepaths)} file(s)...")
        
        def do_import():
            total_added = 0
            total_dupes = 0
            imported_bookmarks = []
            
            try:
                for filepath in filepaths:
                    ext = Path(filepath).suffix.lower()
                    bookmarks = []
                    
                    try:
                        if ext in ('.html', '.htm'):
                            bookmarks = NetscapeBookmarkImporter.import_from_netscape(filepath)
                        elif ext == '.json':
                            with open(filepath, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                            items = data if isinstance(data, list) else data.get('bookmarks', [])
                            for item in items:
                                if isinstance(item, dict) and item.get('url'):
                                    bm = Bookmark(id=None, url=item.get('url', ''),
                                                title=item.get('title', ''), category=item.get('category', 'Imported'))
                                    bookmarks.append(bm)
                        elif ext == '.csv':
                            bookmarks = RaindropImporter.import_from_csv(filepath)
                        elif ext == '.opml':
                            bookmarks = OPMLImporter.import_from_opml(filepath)
                        elif ext == '.txt':
                            bookmarks = TextURLImporter.import_from_text(filepath)
                        else:
                            continue
                        
                        for bm in bookmarks:
                            if bm and bm.url:
                                existing = self.bookmark_manager.find_by_url(bm.url)
                                if not existing:
                                    # Auto-categorize before adding
                                    if not bm.category or bm.category in ("Imported", "Uncategorized", "Uncategorized / Needs Review"):
                                        bm.category = self.category_manager.categorize_url(bm.url, bm.title)
                                    
                                    self.bookmark_manager.add_bookmark(bm, save=False)
                                    imported_bookmarks.append(bm)
                                    total_added += 1
                                else:
                                    total_dupes += 1
                    except Exception as e:
                        print(f"Import error for {filepath}: {e}")
                        traceback.print_exc()
                
                # Save all bookmarks after batch import
                self.bookmark_manager.save_bookmarks()
                
                # Save to permanent import backup (grows forever)
                if imported_bookmarks:
                    self._save_import_backup(imported_bookmarks)
                    
            except Exception as e:
                print(f"Import thread error: {e}")
                traceback.print_exc()
            finally:
                # Always call completion handler
                self.root.after(0, lambda: self._on_import_done(total_added, total_dupes))
        
        # Start import thread
        import_thread = threading.Thread(target=do_import, daemon=True)
        import_thread.start()
    
    def _save_import_backup(self, bookmarks: List[Bookmark]):
        """Save imported bookmarks to permanent backup file (grows forever)"""
        backup_file = BACKUP_DIR / "import_history_backup.json"
        
        try:
            # Load existing backup
            existing = []
            if backup_file.exists():
                with open(backup_file, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            
            # Add new bookmarks with timestamp
            timestamp = datetime.now().isoformat()
            for bm in bookmarks:
                existing.append({
                    'url': bm.url,
                    'title': bm.title,
                    'category': bm.category,
                    'tags': bm.tags,
                    'notes': bm.notes,
                    'imported_at': timestamp
                })
            
            # Save back
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            
            print(f"Saved {len(bookmarks)} bookmarks to import backup. Total: {len(existing)}")
        except Exception as e:
            print(f"Error saving import backup: {e}")
    
    def _on_import_done(self, added: int, dupes: int):
        """Handle import completion"""
        self.import_area.set_importing(False)
        self._refresh_all()
        
        # Queue favicons for new bookmarks
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        self.favicon_manager.queue_bookmarks(bookmarks)
        
        self._set_status(f"Imported {added} bookmarks ({dupes} duplicates skipped)")
        
        if added > 0 or dupes > 0:
            messagebox.showinfo("Import Complete", f"Imported {added} bookmarks\n{dupes} duplicates skipped")
    
    def _show_import_dialog(self):
        """Show import dialog"""
        self.import_area._browse_files()
    
    def _show_export_dialog(self):
        """Show export dialog"""
        dialog = SelectiveExportDialog(self.root, self.bookmark_manager)
    
    def _check_all_links(self):
        """Check all links - non-blocking with cancel support"""
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        if not bookmarks:
            messagebox.showinfo("No Bookmarks", "No bookmarks to check.")
            return
        
        # Create progress frame with cancel button
        theme = get_theme()
        self._link_check_cancelled = False
        
        progress_frame = tk.Frame(self.status_bar, bg=theme.bg_dark)
        progress_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        
        progress_label = tk.Label(
            progress_frame, text="Checking links...", bg=theme.bg_dark,
            fg=theme.text_muted, font=FONTS.small()
        )
        progress_label.pack(side=tk.LEFT, padx=5)
        
        progress_bar = tk.Frame(progress_frame, bg=theme.bg_tertiary, height=8, width=200)
        progress_bar.pack(side=tk.LEFT, padx=5)
        progress_bar.pack_propagate(False)
        
        progress_fill = tk.Frame(progress_bar, bg=theme.accent_primary, height=8)
        progress_fill.place(x=0, y=0, relheight=1.0, relwidth=0)
        
        cancel_btn = tk.Label(
            progress_frame, text="✕ Cancel", bg=theme.accent_error, fg="white",
            font=FONTS.small(), padx=8, pady=2, cursor="hand2"
        )
        cancel_btn.pack(side=tk.LEFT, padx=10)
        
        def cancel_check():
            self._link_check_cancelled = True
            cancel_btn.configure(text="Cancelling...", bg=theme.text_muted)
        
        cancel_btn.bind("<Button-1>", lambda e: cancel_check())
        
        self._set_status("Checking links...")
        
        broken_count = [0]  # Use list to allow modification in closure
        checked_count = [0]
        
        def check_links_batch():
            batch_size = 5
            start_idx = checked_count[0]
            end_idx = min(start_idx + batch_size, len(bookmarks))
            
            for i in range(start_idx, end_idx):
                if self._link_check_cancelled:
                    break
                
                bm = bookmarks[i]
                try:
                    response = requests.head(bm.url, timeout=5, allow_redirects=True)
                    bm.http_status = response.status_code
                    bm.is_valid = response.status_code < 400
                except Exception:
                    bm.http_status = 0
                    bm.is_valid = False
                
                if not bm.is_valid:
                    broken_count[0] += 1
                
                bm.last_checked = datetime.now().isoformat()
                checked_count[0] += 1
            
            # Update progress
            progress = checked_count[0] / len(bookmarks)
            progress_fill.place(relwidth=progress)
            progress_label.configure(text=f"Checked {checked_count[0]}/{len(bookmarks)} - {broken_count[0]} broken")
            
            # Save periodically and refresh filter counts
            if checked_count[0] % 20 == 0:
                self.bookmark_manager.save_bookmarks()
                self._refresh_analytics()
            
            # Continue or finish
            if checked_count[0] < len(bookmarks) and not self._link_check_cancelled:
                self.root.after(10, check_links_batch)
            else:
                # Complete
                self.bookmark_manager.save_bookmarks()
                progress_frame.destroy()
                status = "Cancelled" if self._link_check_cancelled else "Complete"
                self._set_status(f"{status}: Found {broken_count[0]} broken links")
                self._refresh_all()
                if not self._link_check_cancelled:
                    messagebox.showinfo("Link Check Complete", f"Checked {checked_count[0]} links\nFound {broken_count[0]} broken")
        
        # Start checking
        self.root.after(100, check_links_batch)
    
    def _find_duplicates(self):
        """Find duplicates"""
        dupes = self.bookmark_manager.find_duplicates()
        
        if not dupes:
            messagebox.showinfo("No Duplicates", "No duplicates found!")
            return
        
        # dupes is Dict[str, List[Bookmark]] - use values()
        total = sum(len(g) - 1 for g in dupes.values())
        
        if messagebox.askyesno("Duplicates", f"Found {total} duplicates. Remove?"):
            for group in dupes.values():
                for bm in group[1:]:
                    self.bookmark_manager.delete_bookmark(bm.id)
            self._refresh_all()
            self._set_status(f"Removed {total} duplicates")
    
    def _clean_urls(self):
        """Clean tracking params"""
        count = self.bookmark_manager.clean_tracking_params()
        self._refresh_all()
        self._set_status(f"Cleaned {count} URLs")
    
    def _get_ai_client(self):
        """Get configured AI client"""
        if not self.ai_config.is_configured():
            return None
        
        try:
            return create_ai_client(self.ai_config)
        except Exception as e:
            print(f"Error creating AI client: {e}")
            return None
    
    def _ai_categorize(self):
        """AI categorize selected bookmarks"""
        # Check if AI is configured
        if not self.ai_config.is_configured():
            messagebox.showwarning("AI Not Configured", 
                "Please configure AI settings first.\n\n"
                "Go to AI menu → AI Settings to add an API key.")
            return
        
        # Get selected bookmarks
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Please select bookmarks to categorize.")
            return
        
        bookmarks = []
        for item_id in selected:
            bm = self.bookmark_manager.get_bookmark(int(item_id))
            if bm:
                bookmarks.append(bm)
        
        if not bookmarks:
            return
        
        # Confirm action
        if not messagebox.askyesno("AI Categorize", 
            f"Categorize {len(bookmarks)} bookmark(s) using AI?\n\n"
            f"Provider: {self.ai_config.get_provider()}\n"
            f"Model: {self.ai_config.get_model()}"):
            return
        
        # Run AI categorization
        self._run_ai_categorization(bookmarks)
    
    def _run_ai_categorization(self, bookmarks: List[Bookmark]):
        """Run AI categorization in background with progress"""
        theme = get_theme()
        
        # Create progress dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("AI Categorization")
        dialog.configure(bg=theme.bg_primary)
        dialog.geometry("450x250")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        
        # Center dialog
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 450) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 250) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # Content
        tk.Label(dialog, text="🤖 AI Categorization", bg=theme.bg_primary,
                fg=theme.text_primary, font=FONTS.title(bold=False)).pack(pady=20)
        
        status_label = tk.Label(dialog, text="Preparing...", bg=theme.bg_primary,
                               fg=theme.text_secondary, font=FONTS.body())
        status_label.pack(pady=10)
        
        # Progress bar frame
        progress_frame = tk.Frame(dialog, bg=theme.bg_tertiary, height=20, width=350)
        progress_frame.pack(pady=10)
        progress_frame.pack_propagate(False)
        
        progress_fill = tk.Frame(progress_frame, bg=theme.accent_primary, height=20)
        progress_fill.place(x=0, y=0, relheight=1.0, relwidth=0)
        
        results_label = tk.Label(dialog, text="", bg=theme.bg_primary,
                                fg=theme.text_muted, font=FONTS.small())
        results_label.pack(pady=10)
        
        # Cancel flag
        self._ai_cancelled = False
        
        def cancel():
            self._ai_cancelled = True
            dialog.destroy()
        
        cancel_btn = tk.Button(dialog, text="Cancel", command=cancel,
                              bg=theme.bg_secondary, fg=theme.text_primary)
        cancel_btn.pack(pady=10)
        
        # Process in batches
        batch_size = self.ai_config.get_batch_size()
        categories = self.category_manager.get_sorted_categories()
        allow_new = self.ai_config.get_auto_create_categories()
        suggest_tags = self.ai_config.get_suggest_tags()
        
        total_processed = 0
        total_changed = 0
        all_results = []
        
        def process_batch(start_idx):
            nonlocal total_processed, total_changed, all_results
            
            if self._ai_cancelled or start_idx >= len(bookmarks):
                # Done - apply results
                dialog.destroy()
                self._apply_ai_results(bookmarks, all_results, total_changed)
                return
            
            end_idx = min(start_idx + batch_size, len(bookmarks))
            batch = bookmarks[start_idx:end_idx]
            
            status_label.configure(text=f"Processing batch {start_idx//batch_size + 1}...")
            progress_fill.place(relwidth=start_idx / len(bookmarks))
            dialog.update()
            
            try:
                client = self._get_ai_client()
                if not client:
                    messagebox.showerror("Error", "Failed to create AI client")
                    dialog.destroy()
                    return
                
                # Prepare bookmark data for AI
                bm_data = [{"url": bm.url, "title": bm.title} for bm in batch]
                
                # Call AI
                results = client.categorize_bookmarks(bm_data, categories, allow_new, suggest_tags)
                all_results.extend(results)
                
                # Count changes
                for i, result in enumerate(results):
                    if start_idx + i < len(bookmarks):
                        bm = bookmarks[start_idx + i]
                        if result.get("category") != bm.category:
                            total_changed += 1
                
                total_processed = end_idx
                results_label.configure(text=f"Processed: {total_processed}/{len(bookmarks)} | Changed: {total_changed}")
                
                # Rate limiting delay
                delay = int(60000 / self.ai_config.get_rate_limit())
                dialog.after(delay, lambda: process_batch(end_idx))
                
            except Exception as e:
                messagebox.showerror("AI Error", f"Error during categorization:\n{str(e)[:200]}")
                dialog.destroy()
        
        # Start processing
        dialog.after(100, lambda: process_batch(0))
    
    def _apply_ai_results(self, bookmarks: List[Bookmark], results: List[Dict], changed_count: int):
        """Apply AI categorization results to bookmarks"""
        min_confidence = self.ai_config.get_min_confidence()
        
        # Create result mapping
        result_map = {r["url"]: r for r in results}
        
        applied = 0
        titles_changed = 0
        new_categories = set()
        
        for bm in bookmarks:
            result = result_map.get(bm.url)
            if not result:
                continue
            
            confidence = result.get("confidence", 0)
            if confidence < min_confidence:
                continue
            
            # Update category
            new_cat = result.get("category", bm.category)
            if new_cat and new_cat != bm.category:
                # Add new category if needed
                if result.get("new_category") and new_cat not in self.category_manager.categories:
                    self.category_manager.add_category(new_cat)
                    new_categories.add(new_cat)
                
                bm.category = new_cat
                bm.ai_confidence = confidence
                applied += 1
            
            # Update AI tags
            ai_tags = result.get("tags", [])
            if ai_tags:
                bm.ai_tags = [t.lower().strip() for t in ai_tags if t]
            
            # Update title if suggested
            suggested_title = result.get("suggested_title")
            if suggested_title and suggested_title != bm.title and suggested_title.lower() not in ["null", "none", ""]:
                bm.title = suggested_title
                titles_changed += 1
            
            # Store reasoning if available
            reasoning = result.get("reasoning", "")
            if reasoning and not bm.description:
                bm.description = reasoning
            
            bm.modified_at = datetime.now().isoformat()
        
        # Save changes
        self.bookmark_manager.save_bookmarks()
        self.category_manager.save_categories()
        self._refresh_all()
        
        # Show summary
        msg = f"AI Categorization Complete\n\n"
        msg += f"Bookmarks processed: {len(bookmarks)}\n"
        msg += f"Categories changed: {applied}\n"
        if titles_changed > 0:
            msg += f"Titles improved: {titles_changed}\n"
        if new_categories:
            msg += f"New categories created: {', '.join(new_categories)}\n"
        
        messagebox.showinfo("AI Complete", msg)
        self._set_status(f"AI categorized {applied} bookmarks, {titles_changed} titles improved")
    
    def _ai_suggest_tags(self):
        """AI suggest tags for selected bookmarks"""
        if not self.ai_config.is_configured():
            messagebox.showwarning("AI Not Configured", 
                "Please configure AI settings first.")
            return
        
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Please select bookmarks for tag suggestions.")
            return
        
        bookmarks = []
        for item_id in selected:
            bm = self.bookmark_manager.get_bookmark(int(item_id))
            if bm:
                bookmarks.append(bm)
        
        if not bookmarks:
            return
        
        # Show progress
        self._set_status("Generating AI tags...")
        self.root.update()
        
        try:
            client = self._get_ai_client()
            if not client:
                messagebox.showerror("Error", "Failed to create AI client")
                return
            
            # Prepare data
            bm_data = [{"url": bm.url, "title": bm.title} for bm in bookmarks]
            categories = self.category_manager.get_sorted_categories()
            
            # Get suggestions (always with tags)
            results = client.categorize_bookmarks(bm_data, categories, 
                                                  allow_new=False, suggest_tags=True)
            
            # Apply tags
            result_map = {r["url"]: r for r in results}
            tagged = 0
            
            for bm in bookmarks:
                result = result_map.get(bm.url)
                if result and result.get("tags"):
                    bm.ai_tags = [t.lower().strip() for t in result["tags"] if t]
                    bm.modified_at = datetime.now().isoformat()
                    tagged += 1
            
            self.bookmark_manager.save_bookmarks()
            self._refresh_bookmark_list()
            
            messagebox.showinfo("Tags Generated", 
                f"Generated AI tags for {tagged} bookmark(s).\n\n"
                "Tags are stored in the 'AI Tags' field and can be merged with user tags.")
            self._set_status(f"Generated tags for {tagged} bookmarks")
            
        except Exception as e:
            messagebox.showerror("AI Error", f"Error generating tags:\n{str(e)[:200]}")
            self._set_status("Tag generation failed")
    
    def _ai_summarize(self):
        """AI generate descriptions for selected bookmarks"""
        if not self.ai_config.is_configured():
            messagebox.showwarning("AI Not Configured", 
                "Please configure AI settings first.")
            return
        
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Please select bookmarks for summarization.")
            return
        
        bookmarks = []
        for item_id in selected:
            bm = self.bookmark_manager.get_bookmark(int(item_id))
            if bm:
                bookmarks.append(bm)
        
        if not bookmarks:
            return
        
        if len(bookmarks) > 10:
            if not messagebox.askyesno("Large Selection", 
                f"Summarizing {len(bookmarks)} bookmarks may take a while. Continue?"):
                return
        
        self._set_status("Generating AI summaries...")
        self.root.update()
        
        try:
            client = self._get_ai_client()
            if not client:
                messagebox.showerror("Error", "Failed to create AI client")
                return
            
            # Build summary prompt
            bm_list = "\n".join([f"- {bm.title} ({bm.url})" for bm in bookmarks[:20]])
            prompt = f"""Analyze these bookmarks and provide a brief description (1-2 sentences) for each explaining what the site/page is about:

{bm_list}

Respond with JSON: {{"summaries": [{{"url": "...", "description": "..."}}]}}"""
            
            # Use the client directly for custom prompt
            provider = self.ai_config.get_provider()
            
            if provider == "openai":
                response = client.client.chat.completions.create(
                    model=client.model,
                    messages=[
                        {"role": "system", "content": "You summarize web pages. Respond only with valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                text = response.choices[0].message.content
            elif provider == "anthropic":
                response = client.client.messages.create(
                    model=client.model,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}]
                )
                text = response.content[0].text
            elif provider == "google":
                response = client.client.generate_content(prompt)
                text = response.text
            elif provider == "groq":
                response = client.client.chat.completions.create(
                    model=client.model,
                    messages=[
                        {"role": "system", "content": "You summarize web pages. Respond only with valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                text = response.choices[0].message.content
            else:  # ollama
                response = requests.post(
                    f"{client.base_url}/api/generate",
                    json={"model": client.model, "prompt": prompt, "stream": False},
                    timeout=120
                )
                text = response.json()["response"]
            
            # Parse response
            if "```json" in text:
                match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
                if match:
                    text = match.group(1)
            elif "```" in text:
                match = re.search(r"```\s*([\s\S]*?)\s*```", text)
                if match:
                    text = match.group(1)
            
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                data = json.loads(text[start:end+1])
                summaries = data.get("summaries", [])
                
                # Apply summaries
                summary_map = {s["url"]: s["description"] for s in summaries}
                updated = 0
                
                for bm in bookmarks:
                    desc = summary_map.get(bm.url)
                    if desc:
                        bm.description = desc
                        bm.modified_at = datetime.now().isoformat()
                        updated += 1
                
                self.bookmark_manager.save_bookmarks()
                self._refresh_bookmark_list()
                
                messagebox.showinfo("Summaries Generated", 
                    f"Generated descriptions for {updated} bookmark(s).")
                self._set_status(f"Generated {updated} summaries")
            else:
                messagebox.showerror("Parse Error", "Could not parse AI response")
                
        except Exception as e:
            messagebox.showerror("AI Error", f"Error generating summaries:\n{str(e)[:200]}")
            self._set_status("Summary generation failed")
    
    def _ai_improve_titles(self):
        """AI improve bookmark titles to be more descriptive"""
        if not self.ai_config.is_configured():
            messagebox.showwarning("AI Not Configured", 
                "Please configure AI settings first.")
            return
        
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Please select bookmarks to improve titles.")
            return
        
        bookmarks = []
        for item_id in selected:
            bm = self.bookmark_manager.get_bookmark(int(item_id))
            if bm:
                bookmarks.append(bm)
        
        if not bookmarks:
            return
        
        if len(bookmarks) > 20:
            if not messagebox.askyesno("Large Selection", 
                f"Improving titles for {len(bookmarks)} bookmarks may take a while. Continue?"):
                return
        
        self._set_status("Improving bookmark titles with AI...")
        self.root.update()
        
        try:
            client = self._get_ai_client()
            if not client:
                messagebox.showerror("Error", "Failed to create AI client")
                return
            
            # Build prompt for title improvement
            bm_list = []
            for bm in bookmarks[:30]:  # Limit to 30
                bm_list.append({
                    "url": bm.url,
                    "current_title": bm.title,
                    "domain": bm.domain
                })
            
            prompt = f"""Analyze these bookmarks and suggest better, more descriptive titles. 
The new titles should be:
- Clear and descriptive (explain what the page is about)
- Concise (under 60 characters ideally)
- Remove unnecessary prefixes like "Home |" or "Welcome to"
- Remove trailing site names if redundant with domain
- Fix capitalization issues
- Keep technical terms accurate

Bookmarks:
{json.dumps(bm_list, indent=2)}

Respond with ONLY valid JSON in this exact format:
{{"titles": [{{"url": "https://example.com", "new_title": "Improved Title Here"}}]}}"""
            
            # Use the client directly for custom prompt
            provider = self.ai_config.get_provider()
            
            if provider == "openai":
                response = client.client.chat.completions.create(
                    model=client.model,
                    messages=[
                        {"role": "system", "content": "You improve bookmark titles to be more descriptive and useful. Respond only with valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                text = response.choices[0].message.content
            elif provider == "anthropic":
                response = client.client.messages.create(
                    model=client.model,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}]
                )
                text = response.content[0].text
            elif provider == "google":
                response = client.client.generate_content(prompt)
                text = response.text
            elif provider == "groq":
                response = client.client.chat.completions.create(
                    model=client.model,
                    messages=[
                        {"role": "system", "content": "You improve bookmark titles. Respond only with valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                text = response.choices[0].message.content
            else:  # ollama
                response = requests.post(
                    f"{client.base_url}/api/generate",
                    json={"model": client.model, "prompt": prompt, "stream": False},
                    timeout=120
                )
                text = response.json()["response"]
            
            # Parse response
            if "```json" in text:
                match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
                if match:
                    text = match.group(1)
            elif "```" in text:
                match = re.search(r"```\s*([\s\S]*?)\s*```", text)
                if match:
                    text = match.group(1)
            
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                data = json.loads(text[start:end+1])
                titles = data.get("titles", [])
                
                # Show preview dialog before applying
                self._show_title_preview(bookmarks, titles)
            else:
                messagebox.showerror("Parse Error", "Could not parse AI response")
                
        except Exception as e:
            messagebox.showerror("AI Error", f"Error improving titles:\n{str(e)[:200]}")
            self._set_status("Title improvement failed")
    
    def _show_title_preview(self, bookmarks: List[Bookmark], titles: List[Dict]):
        """Show preview of title changes before applying"""
        theme = get_theme()
        
        # Create title mapping
        title_map = {t["url"]: t["new_title"] for t in titles}
        
        # Find bookmarks with actual changes
        changes = []
        for bm in bookmarks:
            new_title = title_map.get(bm.url)
            if new_title and new_title != bm.title:
                changes.append((bm, new_title))
        
        if not changes:
            messagebox.showinfo("No Changes", "AI did not suggest any title improvements.")
            return
        
        # Create preview dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Preview Title Changes")
        dialog.configure(bg=theme.bg_primary)
        dialog.geometry("700x500")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 700) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 500) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # Header
        header = tk.Frame(dialog, bg=theme.bg_secondary, padx=20, pady=15)
        header.pack(fill=tk.X)
        
        tk.Label(header, text="✏️ Preview Title Changes", bg=theme.bg_secondary,
                fg=theme.text_primary, font=FONTS.title(bold=False)).pack(anchor="w")
        tk.Label(header, text=f"{len(changes)} titles will be updated", bg=theme.bg_secondary,
                fg=theme.text_secondary, font=FONTS.small()).pack(anchor="w")
        
        # Scrollable list of changes
        canvas = tk.Canvas(dialog, bg=theme.bg_primary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=theme.bg_primary)
        
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=20, pady=10)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Track which changes to apply
        check_vars = []
        
        for bm, new_title in changes:
            frame = tk.Frame(scroll_frame, bg=theme.bg_tertiary, padx=10, pady=8)
            frame.pack(fill=tk.X, pady=3, padx=5)
            
            var = tk.BooleanVar(value=True)
            check_vars.append((bm, new_title, var))
            
            cb = ttk.Checkbutton(frame, variable=var)
            cb.pack(side=tk.LEFT, padx=(0, 10))
            
            text_frame = tk.Frame(frame, bg=theme.bg_tertiary)
            text_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            # Domain
            tk.Label(text_frame, text=bm.domain, bg=theme.bg_tertiary,
                    fg=theme.text_muted, font=FONTS.tiny()).pack(anchor="w")
            
            # Old title (strikethrough effect with color)
            tk.Label(text_frame, text=f"Old: {bm.title[:60]}", bg=theme.bg_tertiary,
                    fg=theme.accent_error, font=FONTS.small()).pack(anchor="w")
            
            # New title
            tk.Label(text_frame, text=f"New: {new_title[:60]}", bg=theme.bg_tertiary,
                    fg=theme.accent_success, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        
        # Buttons
        btn_frame = tk.Frame(dialog, bg=theme.bg_secondary, pady=15)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        def apply_changes():
            applied = 0
            for bm, new_title, var in check_vars:
                if var.get():
                    bm.title = new_title
                    bm.modified_at = datetime.now().isoformat()
                    applied += 1
            
            self.bookmark_manager.save_bookmarks()
            self._refresh_bookmark_list()
            dialog.destroy()
            
            messagebox.showinfo("Titles Updated", f"Updated {applied} bookmark title(s).")
            self._set_status(f"Updated {applied} titles")
        
        def select_all():
            for _, _, var in check_vars:
                var.set(True)
        
        def select_none():
            for _, _, var in check_vars:
                var.set(False)
        
        tk.Label(btn_frame, text="Select All", bg=theme.bg_tertiary, fg=theme.text_primary,
                font=FONTS.small(), padx=10, pady=5, cursor="hand2").pack(side=tk.LEFT, padx=10)
        btn_frame.winfo_children()[-1].bind("<Button-1>", lambda e: select_all())
        
        tk.Label(btn_frame, text="Select None", bg=theme.bg_tertiary, fg=theme.text_primary,
                font=FONTS.small(), padx=10, pady=5, cursor="hand2").pack(side=tk.LEFT)
        btn_frame.winfo_children()[-1].bind("<Button-1>", lambda e: select_none())
        
        tk.Label(btn_frame, text="Apply Selected", bg=theme.accent_success, fg="white",
                font=("Segoe UI", 10, "bold"), padx=20, pady=8, cursor="hand2").pack(side=tk.RIGHT, padx=20)
        btn_frame.winfo_children()[-1].bind("<Button-1>", lambda e: apply_changes())
        
        tk.Label(btn_frame, text="Cancel", bg=theme.bg_tertiary, fg=theme.text_primary,
                font=FONTS.body(), padx=15, pady=8, cursor="hand2").pack(side=tk.RIGHT)
        btn_frame.winfo_children()[-1].bind("<Button-1>", lambda e: dialog.destroy())
    
    def _show_ai_settings(self):
        """Show AI settings dialog"""
        theme = get_theme()
        
        dialog = tk.Toplevel(self.root)
        dialog.title("AI Settings")
        dialog.configure(bg=theme.bg_primary)
        dialog.geometry("500x550")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center dialog
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 500) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 550) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # Header
        header = tk.Frame(dialog, bg=theme.bg_secondary, padx=20, pady=15)
        header.pack(fill=tk.X)
        
        tk.Label(
            header, text="🤖 AI Provider Settings", bg=theme.bg_secondary,
            fg=theme.text_primary, font=FONTS.title(bold=False)
        ).pack(anchor="w")
        
        tk.Label(
            header, text="Configure AI providers for categorization and tagging", 
            bg=theme.bg_secondary, fg=theme.text_secondary, font=FONTS.small()
        ).pack(anchor="w", pady=(5, 0))
        
        # Scrollable content
        content_frame = tk.Frame(dialog, bg=theme.bg_primary)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Provider selection
        tk.Label(
            content_frame, text="Provider:", bg=theme.bg_primary,
            fg=theme.text_primary, font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", pady=(10, 5))
        
        provider_var = tk.StringVar(value=self.ai_config.get_provider())
        provider_frame = tk.Frame(content_frame, bg=theme.bg_primary)
        provider_frame.pack(fill=tk.X, pady=5)
        
        for provider_name, info in AI_PROVIDERS.items():
            rb = tk.Radiobutton(
                provider_frame, text=f"{info.display_name}",
                variable=provider_var, value=provider_name,
                bg=theme.bg_primary, fg=theme.text_primary,
                activebackground=theme.bg_primary, activeforeground=theme.text_primary,
                selectcolor=theme.bg_secondary, font=FONTS.small()
            )
            rb.pack(anchor="w", pady=2)
            
            desc = tk.Label(
                provider_frame, text=f"   {info.description}",
                bg=theme.bg_primary, fg=theme.text_muted, font=FONTS.tiny()
            )
            desc.pack(anchor="w")
        
        # Model selection
        tk.Label(
            content_frame, text="Model:", bg=theme.bg_primary,
            fg=theme.text_primary, font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", pady=(15, 5))
        
        model_var = tk.StringVar(value=self.ai_config.get_model())
        model_combo = ttk.Combobox(content_frame, textvariable=model_var, state="readonly", width=35)
        model_combo.pack(anchor="w", pady=5)
        
        # API Key
        tk.Label(
            content_frame, text="API Key:", bg=theme.bg_primary,
            fg=theme.text_primary, font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", pady=(15, 5))
        
        api_key_var = tk.StringVar(value=self.ai_config.get_api_key())
        api_entry = tk.Entry(
            content_frame, textvariable=api_key_var, show="•",
            bg=theme.bg_secondary, fg=theme.text_primary,
            font=FONTS.body(), relief=tk.FLAT, width=45
        )
        api_entry.pack(anchor="w", ipady=5, pady=5)
        
        # Show/Hide key button
        def toggle_key():
            if api_entry.cget('show') == '•':
                api_entry.configure(show='')
                show_btn.configure(text="Hide")
            else:
                api_entry.configure(show='•')
                show_btn.configure(text="Show")
        
        show_btn = tk.Label(
            content_frame, text="Show", bg=theme.accent_primary, fg="white",
            font=FONTS.tiny(), padx=8, pady=2, cursor="hand2"
        )
        show_btn.pack(anchor="w", pady=2)
        show_btn.bind("<Button-1>", lambda e: toggle_key())
        
        # Update models when provider changes
        def on_provider_change(*args):
            provider = provider_var.get()
            info = AI_PROVIDERS.get(provider)
            if info:
                model_combo['values'] = info.models
                if model_var.get() not in info.models:
                    model_var.set(info.default_model)
                # Update API key field
                api_key_var.set(self.ai_config.get_api_key(provider))
        
        provider_var.trace_add('write', on_provider_change)
        on_provider_change()  # Initialize
        
        # Batch size and rate limit
        settings_frame = tk.Frame(content_frame, bg=theme.bg_primary)
        settings_frame.pack(fill=tk.X, pady=(15, 5))
        
        tk.Label(
            settings_frame, text="Batch Size:", bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.small()
        ).grid(row=0, column=0, sticky="w", pady=5)
        
        batch_var = tk.IntVar(value=self.ai_config.get_batch_size())
        batch_spin = ttk.Spinbox(settings_frame, from_=5, to=50, textvariable=batch_var, width=8)
        batch_spin.grid(row=0, column=1, padx=10, pady=5)
        
        tk.Label(
            settings_frame, text="Rate Limit (req/min):", bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.small()
        ).grid(row=1, column=0, sticky="w", pady=5)
        
        rate_var = tk.IntVar(value=self.ai_config.get_rate_limit())
        rate_spin = ttk.Spinbox(settings_frame, from_=1, to=120, textvariable=rate_var, width=8)
        rate_spin.grid(row=1, column=1, padx=10, pady=5)
        
        # Test connection button
        def test_connection():
            provider = provider_var.get()
            model = model_var.get()
            key = api_key_var.get()
            
            # Validate API key is provided (except for Ollama)
            if not key and provider != "ollama":
                messagebox.showwarning("Missing API Key", 
                    f"Please enter an API key for {provider}.\n\n"
                    "You can get an API key from:\n"
                    "• OpenAI: platform.openai.com/api-keys\n"
                    "• Anthropic: console.anthropic.com/settings/keys\n"
                    "• Google: aistudio.google.com/app/apikey\n"
                    "• Groq: console.groq.com/keys",
                    parent=dialog)
                return
            
            # Temporarily set provider, model, and key for test
            old_provider = self.ai_config.get_provider()
            old_model = self.ai_config.get_model()
            old_key = self.ai_config.get_api_key(provider)
            
            # Set all values temporarily (without saving to file)
            self.ai_config._config["provider"] = provider
            self.ai_config._config["model"] = model
            self.ai_config._config.setdefault("api_keys", {})[provider] = key
            
            try:
                client = create_ai_client(self.ai_config)
                success, message = client.test_connection()
                
                if success:
                    messagebox.showinfo("Connection Test", f"✅ Success!\n\n{message}", parent=dialog)
                else:
                    messagebox.showerror("Connection Test", f"❌ Failed\n\n{message}", parent=dialog)
            except Exception as e:
                error_msg = str(e)
                # Provide helpful hints based on error
                hint = ""
                if "API_KEY" in error_msg or "api_key" in error_msg.lower() or "authentication" in error_msg.lower():
                    hint = "\n\nHint: Check that your API key is correct and active."
                elif "model" in error_msg.lower():
                    hint = f"\n\nHint: The model '{model}' may not be available for your account."
                elif "quota" in error_msg.lower() or "rate" in error_msg.lower():
                    hint = "\n\nHint: You may have exceeded your API quota or rate limit."
                
                messagebox.showerror("Connection Test", f"❌ Error\n\n{error_msg[:300]}{hint}", parent=dialog)
            finally:
                # Restore original values
                self.ai_config._config["provider"] = old_provider
                self.ai_config._config["model"] = old_model
                if old_key:
                    self.ai_config._config.setdefault("api_keys", {})[provider] = old_key
                elif provider in self.ai_config._config.get("api_keys", {}):
                    del self.ai_config._config["api_keys"][provider]
        
        test_btn = tk.Label(
            content_frame, text="🔌 Test Connection", bg=theme.accent_primary, fg="white",
            font=FONTS.small(), padx=15, pady=5, cursor="hand2"
        )
        test_btn.pack(anchor="w", pady=(15, 5))
        test_btn.bind("<Button-1>", lambda e: test_connection())
        
        # Buttons
        btn_frame = tk.Frame(dialog, bg=theme.bg_secondary, pady=15)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        def save():
            self.ai_config.set_provider(provider_var.get())
            self.ai_config.set_model(model_var.get())
            self.ai_config.set_api_key(provider_var.get(), api_key_var.get())
            self.ai_config.set_batch_size(batch_var.get())
            self.ai_config.set_rate_limit(rate_var.get())
            self.ai_config.save_config()
            dialog.destroy()
            self._set_status("AI settings saved")
        
        save_btn = tk.Label(
            btn_frame, text="Save", bg=theme.accent_success, fg="white",
            font=("Segoe UI", 10, "bold"), padx=25, pady=8, cursor="hand2"
        )
        save_btn.pack(side=tk.RIGHT, padx=20)
        save_btn.bind("<Button-1>", lambda e: save())
        
        cancel_btn = tk.Label(
            btn_frame, text="Cancel", bg=theme.bg_tertiary, fg=theme.text_primary,
            font=FONTS.body(), padx=20, pady=8, cursor="hand2"
        )
        cancel_btn.pack(side=tk.RIGHT)
        cancel_btn.bind("<Button-1>", lambda e: dialog.destroy())
    
    def _show_analytics(self):
        """Show full analytics"""
        dialog = AnalyticsDashboard(self.root, self.bookmark_manager)
    
    def _backup_now(self):
        """Create backup"""
        backup_dir = DATA_DIR / "backups"
        backup_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = backup_dir / f"backup_{timestamp}.json"
        
        self.bookmark_manager.export_json(str(filepath))
        self._set_status(f"Backup saved to {filepath.name}")
    
    def _clear_favicon_cache(self):
        """Clear favicon cache"""
        if messagebox.askyesno("Clear Cache", "Clear all cached favicons?"):
            self.favicon_manager.clear_cache()
            self._refresh_all()
            self._set_status("Favicon cache cleared")
    
    def _redownload_all_favicons(self):
        """Redownload all favicons"""
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        if not bookmarks:
            messagebox.showinfo("No Bookmarks", "No bookmarks to fetch favicons for.")
            return
        
        result = messagebox.askyesno(
            "Redownload Favicons",
            f"This will redownload favicons for all {len(bookmarks)} bookmarks.\n\n"
            "This may take a while. Continue?"
        )
        if not result:
            return
        
        self._set_status("Redownloading all favicons...")
        self.favicon_manager.redownload_all_favicons(bookmarks)
    
    def _redownload_missing_favicons(self):
        """Redownload only missing favicons"""
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        if not bookmarks:
            messagebox.showinfo("No Bookmarks", "No bookmarks to fetch favicons for.")
            return
        
        # Count missing
        missing_count = sum(1 for bm in bookmarks if not self.favicon_manager.get_cached(bm.domain))
        failed_count = len(self.favicon_manager.get_failed_domains())
        
        result = messagebox.askyesno(
            "Redownload Missing Favicons",
            f"Found approximately {missing_count} bookmarks without cached favicons.\n"
            f"Previously failed domains: {failed_count}\n\n"
            "This will retry all missing favicons. Continue?"
        )
        if not result:
            return
        
        self._set_status("Redownloading missing favicons...")
        self.favicon_manager.redownload_missing_favicons(bookmarks)
    
    def _undo(self):
        """Undo"""
        if self.command_stack.undo():
            self._refresh_all()
    
    def _redo(self):
        """Redo"""
        if self.command_stack.redo():
            self._refresh_all()
    
    def _refresh_all(self):
        """Refresh all displays"""
        self._refresh_category_list()
        self._refresh_bookmark_list()
        self._refresh_analytics()
    
    def _set_status(self, message: str):
        """Set status message and update counts"""
        if self.status_label:
            try:
                self.status_label.configure(text=message)
            except Exception:
                pass
        # Update counts whenever status changes
        self._update_status_counts()
    
    def _show_status_progress(self, show: bool = True):
        """Show or hide progress indicator in status bar"""
        if hasattr(self, 'status_progress'):
            try:
                if show:
                    self.status_progress.pack(side=tk.LEFT, padx=(8, 0))
                    self.status_progress.start(10)
                else:
                    self.status_progress.stop()
                    self.status_progress.pack_forget()
            except Exception:
                pass
    
    def _update_status_counts(self):
        """Update item counts in status bar"""
        try:
            if hasattr(self, 'status_total_label') and self.status_total_label:
                total = len(self.bookmark_manager.get_all_bookmarks())
                self.status_total_label.configure(text=f"{total} items")
            
            if hasattr(self, 'status_selected_label') and self.status_selected_label:
                selected = len(self.selected_bookmarks) if hasattr(self, 'selected_bookmarks') else 0
                if selected > 0:
                    self.status_selected_label.configure(text=f"{selected} selected")
                else:
                    self.status_selected_label.configure(text="")
        except Exception:
            pass
    
    def _try_enable_window_dnd(self):
        """Drag-drop requires tkinterdnd2 which may not be installed"""
        # Native drag-drop requires tkinterdnd2
        # Users can still use the browse button or import menu
        pass
    
    def _start_analytics_polling(self):
        """Start periodic analytics refresh"""
        self._analytics_poll_id = None
        self._poll_analytics()
    
    def _poll_analytics(self):
        """Poll and refresh analytics periodically"""
        try:
            self._refresh_analytics()
        except Exception as e:
            print(f"Analytics poll error: {e}")
        
        # Schedule next poll (30 seconds)
        self._analytics_poll_id = self.root.after(30000, self._poll_analytics)
    
    def _show_category_manager(self):
        """Show category management dialog"""
        CategoryManagementDialog(
            self.root, self.category_manager, self.bookmark_manager,
            on_change=self._refresh_all
        )
    
    def _show_custom_favicon_dialog(self):
        """Show custom favicon dialog for selected bookmark"""
        if not self.selected_bookmarks:
            messagebox.showinfo("Select Bookmark", "Please select a bookmark first.")
            return
        
        bm_id = list(self.selected_bookmarks)[0]
        bookmark = self.bookmark_manager.get_bookmark(bm_id)
        if bookmark:
            CustomFaviconDialog(
                self.root, bookmark, self.bookmark_manager,
                on_update=self._refresh_all
            )
    
    def _on_close(self):
        """Handle close"""
        # Cancel polling
        if hasattr(self, '_analytics_poll_id') and self._analytics_poll_id:
            self.root.after_cancel(self._analytics_poll_id)
        if hasattr(self, '_grid_after_id') and self._grid_after_id:
            self.root.after_cancel(self._grid_after_id)
        
        self.favicon_manager.shutdown()
        self.task_runner.shutdown()
        self.root.destroy()


# =============================================================================
# FINAL MAIN ENTRY POINT
# =============================================================================
def main():
    """Main entry point with professional error handling"""
    
    if IS_WINDOWS:
        multiprocessing.freeze_support()
    
    # CLI mode
    if len(sys.argv) > 1:
        cli = BookmarkCLI()
        cli.run(sys.argv[1:])
        return
    
    # GUI mode with error handling
    try:
        root = tk.Tk()
        root.withdraw()  # Hide while checking dependencies
        
        # Initialize style manager
        style_manager.initialize(root)
        
        # Check and install dependencies
        dep_ok = check_and_install_dependencies(root)
        if not dep_ok:
            log.warning("User cancelled dependency installation")
            root.destroy()
            return
        
        # Import dependencies after check
        import_dependencies()
        
        # Configure DPI scaling for tk
        try:
            dpi = root.winfo_fpixels('1i')
            scale = dpi / 96.0
            if scale > 1.0:
                root.tk.call('tk', 'scaling', scale)
                log.debug(f"Set tk scaling to {scale} (DPI: {dpi})")
        except Exception as e:
            log.warning(f"Could not set tk scaling: {e}")
        
        root.deiconify()  # Show window
        
        app = FinalBookmarkOrganizerApp(root)
        root.mainloop()
        
    except Exception as e:
        log.exception("Fatal error in main")
        # Try to show error dialog
        try:
            messagebox.showerror(
                "Fatal Error",
                f"An unexpected error occurred:\n\n{str(e)[:500]}\n\n"
                f"Please check the log file at:\n{LOG_FILE}"
            )
        except Exception:
            print(f"FATAL ERROR: {e}")
        raise


if __name__ == "__main__":
    main()




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




# =============================================================================
# ENHANCED DRAG & DROP SUPPORT
# =============================================================================
class EnhancedDragDropArea(tk.Frame, ThemedWidget):
    """
    Enhanced drag & drop area with better visual feedback and 
    support for dropping multiple files.
    """
    
    SUPPORTED_EXTENSIONS = {'.html', '.htm', '.json', '.csv', '.opml', '.txt'}
    
    def __init__(self, parent, on_files_dropped: Callable = None, compact: bool = False):
        theme = get_theme()
        super().__init__(parent, bg=theme.bg_secondary)
        
        self.on_files_dropped = on_files_dropped
        self.compact = compact
        self._is_importing = False
        
        # Border styling
        self.configure(
            highlightbackground=theme.border,
            highlightthickness=2,
            highlightcolor=theme.accent_primary
        )
        
        # Content frame
        content = tk.Frame(self, bg=theme.bg_secondary)
        content.pack(fill=tk.BOTH, expand=True, padx=15, pady=12)
        
        if compact:
            # Compact mode - single line
            row = tk.Frame(content, bg=theme.bg_secondary)
            row.pack(fill=tk.X)
            
            tk.Label(
                row, text="📥", bg=theme.bg_secondary,
                font=("Segoe UI Emoji", 16)
            ).pack(side=tk.LEFT, padx=(0, 8))
            
            tk.Label(
                row, text="Drop bookmark files here or", 
                bg=theme.bg_secondary, fg=theme.text_secondary,
                font=FONTS.body()
            ).pack(side=tk.LEFT)
            
            self.browse_link = tk.Label(
                row, text="browse", bg=theme.bg_secondary,
                fg=theme.accent_primary, font=("Segoe UI", 10, "underline"),
                cursor="hand2"
            )
            self.browse_link.pack(side=tk.LEFT, padx=(5, 0))
            self.browse_link.bind("<Button-1>", lambda e: self._browse_files())
        else:
            # Full mode
            self.icon_label = tk.Label(
                content, text="📥", bg=theme.bg_secondary,
                font=("Segoe UI Emoji", 36)
            )
            self.icon_label.pack(pady=(5, 8))
            
            self.title_label = tk.Label(
                content, text="Drop Bookmark Files Here",
                bg=theme.bg_secondary, fg=theme.text_primary,
                font=FONTS.header()
            )
            self.title_label.pack()
            
            self.subtitle_label = tk.Label(
                content, text="or click to browse",
                bg=theme.bg_secondary, fg=theme.text_muted,
                font=FONTS.small()
            )
            self.subtitle_label.pack(pady=(2, 8))
            
            # Supported formats
            formats = "HTML • JSON • CSV • OPML • TXT"
            self.formats_label = tk.Label(
                content, text=formats,
                bg=theme.bg_secondary, fg=theme.text_muted,
                font=FONTS.tiny()
            )
            self.formats_label.pack()
            
            # Progress indicator (hidden by default)
            self.progress_frame = tk.Frame(content, bg=theme.bg_secondary)
            
            self.progress_label = tk.Label(
                self.progress_frame, text="Importing...",
                bg=theme.bg_secondary, fg=theme.text_secondary,
                font=FONTS.body()
            )
            self.progress_label.pack()
            
            self.progress_bar = tk.Frame(
                self.progress_frame, bg=theme.bg_tertiary, height=4
            )
            self.progress_bar.pack(fill=tk.X, pady=(5, 0))
            
            self.progress_fill = tk.Frame(self.progress_bar, bg=theme.accent_primary, height=4)
            self.progress_fill.place(x=0, y=0, relheight=1.0, relwidth=0)
        
        # Make entire area clickable
        self._bind_click_recursive(self)
        
        # Hover effects
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        
        # Try to enable native drag-drop if available
        self._try_enable_native_dnd()
    
    def _bind_click_recursive(self, widget):
        """Bind click to widget and all children"""
        widget.bind("<Button-1>", lambda e: self._browse_files() if not self._is_importing else None)
        for child in widget.winfo_children():
            self._bind_click_recursive(child)
    
    def _on_enter(self, e):
        """Mouse enter - highlight"""
        if not self._is_importing:
            theme = get_theme()
            self.configure(highlightbackground=theme.accent_primary)
    
    def _on_leave(self, e):
        """Mouse leave - reset"""
        if not self._is_importing:
            theme = get_theme()
            self.configure(highlightbackground=theme.border)
    
    def _try_enable_native_dnd(self):
        """Try to enable native drag-drop support"""
        try:
            # Try tkinterdnd2 if available
            from tkinterdnd2 import DND_FILES, TkinterDnD
            
            # Register as drop target
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self._on_native_drop)
            self.dnd_bind('<<DragEnter>>', self._on_drag_enter)
            self.dnd_bind('<<DragLeave>>', self._on_drag_leave)
            
            print("Native drag-drop enabled via tkinterdnd2")
        except ImportError:
            # tkinterdnd2 not available - use fallback
            pass
    
    def _on_native_drop(self, event):
        """Handle native file drop"""
        files = self._parse_drop_data(event.data)
        if files:
            self._process_files(files)
    
    def _on_drag_enter(self, event):
        """Handle drag enter"""
        theme = get_theme()
        self.configure(highlightbackground=theme.accent_success, highlightthickness=3)
        if hasattr(self, 'title_label'):
            self.title_label.configure(text="Drop to Import!")
    
    def _on_drag_leave(self, event):
        """Handle drag leave"""
        theme = get_theme()
        self.configure(highlightbackground=theme.border, highlightthickness=2)
        if hasattr(self, 'title_label'):
            self.title_label.configure(text="Drop Bookmark Files Here")
    
    def _parse_drop_data(self, data: str) -> List[str]:
        """Parse dropped file data"""
        files = []
        
        # Handle different formats
        if '{' in data:
            # Tcl list format: {path with spaces} {another path}
            files = re.findall(r'\{([^}]+)\}', data)
        else:
            # Space-separated paths
            files = data.split()
        
        # Filter to supported extensions
        valid_files = []
        for f in files:
            f = f.strip()
            ext = Path(f).suffix.lower()
            if ext in self.SUPPORTED_EXTENSIONS:
                valid_files.append(f)
        
        return valid_files
    
    def _browse_files(self):
        """Open file browser"""
        if self._is_importing:
            return
        
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
        """Process selected/dropped files"""
        valid_files = []
        
        for filepath in filepaths:
            ext = Path(filepath).suffix.lower()
            if ext in self.SUPPORTED_EXTENSIONS:
                valid_files.append(filepath)
        
        if valid_files and self.on_files_dropped:
            self.on_files_dropped(valid_files)
        elif not valid_files and filepaths:
            messagebox.showwarning(
                "Unsupported Files",
                f"None of the {len(filepaths)} files are supported formats.\n\n" +
                "Supported: HTML, JSON, CSV, OPML, TXT"
            )
    
    def set_importing(self, is_importing: bool, progress: float = 0):
        """Set importing state with progress"""
        theme = get_theme()
        self._is_importing = is_importing
        
        if not self.compact:
            if is_importing:
                self.icon_label.configure(text="⏳")
                self.title_label.configure(text="Importing...")
                self.subtitle_label.pack_forget()
                self.formats_label.pack_forget()
                self.progress_frame.pack(pady=(5, 0))
                self.progress_fill.place(relwidth=progress)
                self.configure(highlightbackground=theme.accent_warning)
            else:
                self.icon_label.configure(text="📥")
                self.title_label.configure(text="Drop Bookmark Files Here")
                self.progress_frame.pack_forget()
                self.subtitle_label.pack(pady=(2, 8))
                self.formats_label.pack()
                self.configure(highlightbackground=theme.border)
    
    def set_progress(self, progress: float, message: str = None):
        """Update import progress"""
        if not self.compact and self._is_importing:
            self.progress_fill.place(relwidth=min(1.0, progress))
            if message:
                self.progress_label.configure(text=message)
    
    def show_success(self, count: int):
        """Show success message briefly"""
        if not self.compact:
            theme = get_theme()
            self.icon_label.configure(text="✅")
            self.title_label.configure(text=f"Imported {count} bookmarks!")
            self.configure(highlightbackground=theme.accent_success)
            
            # Reset after delay
            self.after(2000, lambda: self.set_importing(False))







