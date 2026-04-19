"""System tray compatibility manager for the desktop shell."""

from __future__ import annotations

import threading
from typing import List

try:
    from PIL import Image, ImageDraw
    Image.MAX_IMAGE_PIXELS = 20_000_000
    HAS_PIL = True
except ImportError:  # pragma: no cover - optional runtime dependency
    Image = None
    ImageDraw = None
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
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark

from .widget_runtime import _open_external_url, get_theme

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
        except Exception:
            log.warning("Error starting system tray", exc_info=True)
            return False
    
    def stop(self):
        """Stop system tray icon"""
        self._running = False
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
    
    def _create_icon(self) -> "Image.Image":
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
        if _open_external_url(bookmark.url):
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
