"""Desktop bootstrap helpers for DPI, optional dependencies, icons, and window chrome."""

from __future__ import annotations

import base64
import ctypes
import sys
import tkinter as tk
from pathlib import Path
from typing import Optional

from bookmark_organizer_pro.constants import APP_DIR, IS_WINDOWS
from bookmark_organizer_pro.logging_config import log

SOURCE_ROOT = Path(__file__).resolve().parent.parent
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT))
ASSETS_DIR = BUNDLE_ROOT / "assets"


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

# =============================================================================
# DEPENDENCY MANAGEMENT - Professional first-run experience
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
        Image.MAX_IMAGE_PIXELS = 20_000_000
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

# =============================================================================
# DISTRIBUTION - Application Icon and About Dialog
# =============================================================================

# Base64 encoded application icon (64x64 PNG)
APP_ICON_BASE64 = """iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAABz0lEQVR4nO2bSXICMQxFnVTOAAtYwak4IadKVmGRXIKsXNWleJA1urHtsHW//4W9JRSEAQr82Y52eF0eWI/+/v4MqlNdZIRwT20DFEZVFI4RNoI0cE0hUOkjBAZxFI4hGvEO7cAT/ES87MM8Baf4dRBis8swkuMbolhA1rif74/R4cjcTxfm8dHTBjaAjOv/JaROtlNcO+gDdjL6mew9aIM2Jv4DKbuD4lBStzulG/Vud9o3zucLs9WU4we0Dq41+hDWjoiAbUDr7L6mZqe5RNQ7I7U1Z/lr3AL+IuwfALCAO8CvPlnwKt1fwjUFwnwnFz6fIFCJMC7AG/cDMjx994Gyyege0FEitZKw2PUix8UzAyAoraiLQVDlt8CbgbkVfdc/ZQKBlg9meFFnA4DXA3wjn9KkYCyAVZ9gHNpi0JJl1sCsvjj+WpuxJaqAVopqAnWNqGmxzQBPZEeSWgaIJkCrDiNLeF+c5QiyCoNXQO4KeAIkTChVz8qARQTpKIseReoBHoLjJggHV+Kmdh6xXuA5t7VGFv0OcFZUHtOcHRwD9SfFN0yUxqoC8PqAbOkgVMHuwl6m8CdP94YkRgEsuw7Q5Bl3xqrMeN7g0GwOH9PBaSF+GcDqAAAAABJRU5ErkJggg=="""

def get_embedded_icon() -> Optional[bytes]:
    """
    Get the embedded application icon as PNG bytes.
    
    Returns:
        Optional[bytes]: PNG icon data or None if unavailable
    """
    try:
        return base64.b64decode(APP_ICON_BASE64.strip())
    except Exception:
        return None


def set_window_icon(window: tk.Tk) -> bool:
    """
    Set the application icon on a Tk window.
    
    Tries multiple methods in order:
    1. Embedded base64 icon (cross-platform)
    2. External .ico file (Windows)
    3. External .png file (all platforms)
    
    Args:
        window: Tk or Toplevel window
        
    Returns:
        bool: True if icon was set successfully
    """
    # Method 1: Try embedded icon with PIL
    if HAS_PIL:
        try:
            icon_data = get_embedded_icon()
            if icon_data:
                from PIL import Image, ImageTk
                from io import BytesIO
                
                img = Image.open(BytesIO(icon_data))
                photo = ImageTk.PhotoImage(img)
                window.iconphoto(True, photo)
                window._app_icon_ref = photo  # Prevent garbage collection
                log.debug("Set window icon from embedded data")
                return True
        except Exception as e:
            log.debug(f"Could not set embedded icon: {e}")
    
    # Method 2: Try external .ico file (Windows)
    if IS_WINDOWS:
        ico_paths = [
            ASSETS_DIR / "bookmark_organizer.ico",
            Path(sys.executable).parent / "bookmark_organizer.ico",
            Path(sys.executable).parent / "assets" / "bookmark_organizer.ico",
            APP_DIR / "bookmark_organizer.ico",
        ]
        for ico_path in ico_paths:
            if ico_path.exists():
                try:
                    window.iconbitmap(str(ico_path))
                    log.debug(f"Set window icon from {ico_path}")
                    return True
                except Exception as e:
                    log.debug(f"Could not load ico from {ico_path}: {e}")
    
    # Method 3: Try external .png file
    if HAS_PIL:
        png_paths = [
            ASSETS_DIR / "bookmark_organizer.png",
            Path(sys.executable).parent / "bookmark_organizer.png",
            Path(sys.executable).parent / "assets" / "bookmark_organizer.png",
            APP_DIR / "bookmark_organizer.png",
        ]
        for png_path in png_paths:
            if png_path.exists():
                try:
                    from PIL import Image, ImageTk
                    img = Image.open(png_path)
                    photo = ImageTk.PhotoImage(img)
                    window.iconphoto(True, photo)
                    window._app_icon_ref = photo
                    log.debug(f"Set window icon from {png_path}")
                    return True
                except Exception as e:
                    log.debug(f"Could not load png from {png_path}: {e}")
    
    log.debug("Could not set window icon")
    return False


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

