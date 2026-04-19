"""Quick-add bookmark dialog."""

from __future__ import annotations

from io import BytesIO
import hashlib
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, List, Optional
from urllib.parse import urlparse

try:
    import requests
except ImportError:  # pragma: no cover - optional runtime dependency
    requests = None

try:
    from PIL import Image, ImageTk
    Image.MAX_IMAGE_PIXELS = 20_000_000
    HAS_PIL = True
except ImportError:  # pragma: no cover - optional runtime dependency
    Image = None
    ImageTk = None
    HAS_PIL = False

from bookmark_organizer_pro.constants import FAVICON_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.url_utils import URLUtilities
from bookmark_organizer_pro.utils.runtime import atomic_json_write

from .foundation import FONTS
from .quick_add import (
    FAVICON_PLACEHOLDER,
    TITLE_PLACEHOLDER,
    pick_default_category,
    prepare_quick_add_payload,
)
from .widget_controls import ModernButton, ThemedWidget, Tooltip
from .widget_runtime import apply_window_chrome, get_theme

# =============================================================================
# AI background services are implemented in bookmark_organizer_pro.services.
# =============================================================================





# =============================================================================
# Quick Add Dialog (Global Hotkey Support)
# =============================================================================
class QuickAddDialog(tk.Toplevel, ThemedWidget):
    """Dialog for adding a bookmark with optional custom favicon"""
    
    def __init__(self, parent, categories: List[str], 
                 initial_url: str = "",
                 on_add: Callable = None):
        super().__init__(parent)
        self.categories = categories or []
        self.on_add = on_add
        self.result = None
        self.custom_favicon_path = None
        self._title_placeholder_active = True
        self._favicon_placeholder_active = True
        
        theme = get_theme()
        
        self.title("Add Bookmark")
        self.geometry("560x420")
        self.configure(bg=theme.bg_primary)
        self.transient(parent)
        self.grab_set()
        
        # Make it appear centered and always on top
        self.attributes('-topmost', True)
        apply_window_chrome(self)

        header = tk.Frame(self, bg=theme.bg_dark)
        header.pack(fill=tk.X)

        tk.Label(
            header, text="➕ Add bookmark", bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.title(bold=True)
        ).pack(anchor="w", padx=24, pady=(18, 3))

        tk.Label(
            header, text="Paste a URL now. You can refine title, category, and icon before saving.",
            bg=theme.bg_dark, fg=theme.text_secondary, font=FONTS.small()
        ).pack(anchor="w", padx=24, pady=(0, 16))
        
        # URL field
        url_frame = tk.Frame(self, bg=theme.bg_primary)
        url_frame.pack(fill=tk.X, padx=24, pady=(18, 10))
        
        tk.Label(
            url_frame, text="🔗", bg=theme.bg_primary,
            fg=theme.accent_primary, font=("Segoe UI", 14)
        ).pack(side=tk.LEFT)
        
        self.url_var = tk.StringVar(value=initial_url)
        self.url_entry = tk.Entry(
            url_frame, textvariable=self.url_var,
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            highlightthickness=1, highlightbackground=theme.border_muted,
            highlightcolor=theme.border_active, font=FONTS.body()
        )
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, ipady=8)
        
        # Title field (optional)
        title_frame = tk.Frame(self, bg=theme.bg_primary)
        title_frame.pack(fill=tk.X, padx=24, pady=(0, 10))
        
        tk.Label(
            title_frame, text="📝", bg=theme.bg_primary,
            fg=theme.text_muted, font=("Segoe UI", 14)
        ).pack(side=tk.LEFT)
        
        self.title_var = tk.StringVar()
        self.title_entry = tk.Entry(
            title_frame, textvariable=self.title_var,
            bg=theme.bg_secondary, fg=theme.text_muted,
            insertbackground=theme.text_primary, bd=0,
            highlightthickness=1, highlightbackground=theme.border_muted,
            highlightcolor=theme.border_active, font=FONTS.body()
        )
        self.title_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, ipady=6)
        self.title_entry.insert(0, TITLE_PLACEHOLDER)
        self.title_entry.bind("<FocusIn>", self._clear_title_placeholder)
        self.title_entry.bind("<FocusOut>", self._restore_title_placeholder)
        
        # Category dropdown
        cat_frame = tk.Frame(self, bg=theme.bg_primary)
        cat_frame.pack(fill=tk.X, padx=24, pady=(0, 10))
        
        tk.Label(
            cat_frame, text="📂", bg=theme.bg_primary,
            fg=theme.text_muted, font=("Segoe UI", 14)
        ).pack(side=tk.LEFT)
        
        default_category = pick_default_category(categories)
        self.category_var = tk.StringVar(value=default_category)
        self.category_combo = ttk.Combobox(
            cat_frame, textvariable=self.category_var,
            values=categories or [DEFAULT_CATEGORY], state="readonly"
        )
        self.category_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        
        # Custom favicon field
        favicon_frame = tk.Frame(self, bg=theme.bg_primary)
        favicon_frame.pack(fill=tk.X, padx=24, pady=(0, 8))
        
        tk.Label(
            favicon_frame, text="🖼️", bg=theme.bg_primary,
            fg=theme.text_muted, font=("Segoe UI", 14)
        ).pack(side=tk.LEFT)
        
        tk.Label(
            favicon_frame, text="Custom favicon (optional)", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.small()
        ).pack(side=tk.LEFT, padx=(5, 10))
        
        # Favicon URL/Path entry
        favicon_input_frame = tk.Frame(self, bg=theme.bg_primary)
        favicon_input_frame.pack(fill=tk.X, padx=24, pady=(0, 10))
        
        self.favicon_var = tk.StringVar()
        self.favicon_entry = tk.Entry(
            favicon_input_frame, textvariable=self.favicon_var,
            bg=theme.bg_secondary, fg=theme.text_muted,
            insertbackground=theme.text_primary, bd=0,
            highlightthickness=1, highlightbackground=theme.border_muted,
            highlightcolor=theme.border_active, font=FONTS.small(), width=40
        )
        self.favicon_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, padx=(35, 5))
        self.favicon_entry.insert(0, FAVICON_PLACEHOLDER)
        self.favicon_entry.bind("<FocusIn>", self._clear_favicon_placeholder)
        self.favicon_entry.bind("<FocusOut>", self._restore_favicon_placeholder)
        
        # Browse button
        browse_btn = ModernButton(
            favicon_input_frame, text="Browse",
            command=self._browse_favicon, padx=10, pady=5
        )
        browse_btn.pack(side=tk.LEFT, padx=5)
        
        # Favicon preview
        self.favicon_preview = tk.Label(
            favicon_input_frame, text="", bg=theme.bg_primary, width=3, height=1
        )
        self.favicon_preview.pack(side=tk.LEFT, padx=5)
        
        # Buttons
        btn_frame = tk.Frame(self, bg=theme.bg_primary)
        btn_frame.pack(fill=tk.X, padx=24, pady=(12, 20))
        
        ModernButton(
            btn_frame, text="Cancel", command=self.destroy
        ).pack(side=tk.RIGHT, padx=(10, 0))
        
        ModernButton(
            btn_frame, text="Add bookmark", command=self._add,
            style="primary", icon="➕"
        ).pack(side=tk.RIGHT)
        
        # Keyboard shortcuts
        self.bind("<Return>", lambda e: self._add())
        self.bind("<Escape>", lambda e: self.destroy())
        
        # Focus URL entry
        self.url_entry.focus_set()
        self.url_entry.select_range(0, tk.END)
        
        self.center_window()

    def _clear_title_placeholder(self, event=None):
        """Clear title helper text only when it is the active placeholder."""
        if self._title_placeholder_active:
            self.title_entry.delete(0, tk.END)
            self.title_entry.configure(fg=get_theme().text_primary)
            self._title_placeholder_active = False

    def _restore_title_placeholder(self, event=None):
        """Restore title helper text when the optional title is blank."""
        if not self.title_entry.get().strip():
            self.title_entry.delete(0, tk.END)
            self.title_entry.insert(0, TITLE_PLACEHOLDER)
            self.title_entry.configure(fg=get_theme().text_muted)
            self._title_placeholder_active = True

    def _clear_favicon_placeholder(self, event=None):
        """Clear favicon helper text only when it is the active placeholder."""
        if self._favicon_placeholder_active:
            self.favicon_entry.delete(0, tk.END)
            self.favicon_entry.configure(fg=get_theme().text_primary)
            self._favicon_placeholder_active = False

    def _restore_favicon_placeholder(self, event=None):
        """Restore favicon helper text when the optional field is blank."""
        if not self.favicon_entry.get().strip():
            self.favicon_entry.delete(0, tk.END)
            self.favicon_entry.insert(0, FAVICON_PLACEHOLDER)
            self.favicon_entry.configure(fg=get_theme().text_muted)
            self._favicon_placeholder_active = True

    def _get_title_value(self) -> str:
        return "" if self._title_placeholder_active else self.title_var.get().strip()

    def _get_favicon_value(self) -> str:
        return "" if self._favicon_placeholder_active else self.favicon_var.get().strip()
    
    def _browse_favicon(self):
        """Browse for a local favicon image"""
        self._clear_favicon_placeholder()
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
                if not URLUtilities._is_safe_url(path_or_url):
                    return
                if requests is None:
                    return
                # Download from URL
                resp = requests.get(path_or_url, timeout=5, allow_redirects=False, stream=True)
                if resp.status_code >= 400:
                    resp.close()
                    return
                content = bytearray()
                try:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if not chunk:
                            continue
                        content.extend(chunk)
                        if len(content) > 1_000_000:
                            return
                finally:
                    resp.close()
                img = Image.open(BytesIO(bytes(content)))
            else:
                # Load from file
                img = Image.open(path_or_url)
            
            img = img.convert('RGBA')
            img = img.resize((24, 24), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.favicon_preview.configure(image=photo)
            self.favicon_preview.image = photo
        except Exception as e:
            log.debug(f"Preview error: {e}")
    
    def _process_custom_favicon(self, bookmark_url: str = "") -> Optional[str]:
        """Process custom favicon URL or path and save to cache"""
        favicon_input = self._get_favicon_value()
        if not favicon_input:
            return None
        
        try:
            url = (bookmark_url or self.url_var.get()).strip()
            if not url.lower().startswith(('http://', 'https://')):
                url = 'https://' + url
            domain = urlparse(url).netloc
            if not domain:
                return None
            
            # Load image from URL or file
            if favicon_input.startswith(('http://', 'https://')):
                if not URLUtilities._is_safe_url(favicon_input):
                    messagebox.showerror(
                        "Favicon Not Available",
                        "Private or unsupported favicon URLs cannot be downloaded.",
                        parent=self
                    )
                    return None
                if requests is None:
                    messagebox.showerror(
                        "Favicon Not Available",
                        "The requests package is required to download favicon URLs.",
                        parent=self
                    )
                    return None
                resp = requests.get(favicon_input, timeout=10, allow_redirects=False, stream=True)
                if resp.status_code >= 400:
                    resp.close()
                    messagebox.showerror(
                        "Favicon Not Available",
                        f"The favicon URL returned HTTP {resp.status_code}.",
                        parent=self
                    )
                    return None
                content = bytearray()
                try:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if not chunk:
                            continue
                        content.extend(chunk)
                        if len(content) > 1_000_000:
                            messagebox.showerror(
                                "Favicon Too Large",
                                "Choose an image smaller than 1 MB.",
                                parent=self
                            )
                            return None
                finally:
                    resp.close()
                img = Image.open(BytesIO(bytes(content)))
            else:
                img = Image.open(favicon_input)
            
            # Convert and resize
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # Save to cache
            FAVICON_DIR.mkdir(parents=True, exist_ok=True)
            hash_name = hashlib.md5(domain.encode()).hexdigest() + ".png"
            save_path = FAVICON_DIR / hash_name
            
            # Save multiple sizes
            for size in [16, 32, 64]:
                resized = img.resize((size, size), Image.Resampling.LANCZOS)
                suffix = f"_{size}" if size != 16 else ""
                size_path = FAVICON_DIR / (hashlib.md5(domain.encode()).hexdigest() + suffix + ".png")
                resized.save(size_path, "PNG")
            
            return str(save_path)
        except Exception:
            log.warning("Error processing custom favicon", exc_info=True)
            return None
    
    def _add(self):
        """Add the bookmark"""
        payload, error = prepare_quick_add_payload(
            url=self.url_var.get(),
            title=self.title_var.get(),
            category=self.category_var.get(),
            categories=self.categories,
            favicon_input=self.favicon_var.get(),
            title_placeholder_active=self._title_placeholder_active,
            favicon_placeholder_active=self._favicon_placeholder_active,
        )
        if not payload:
            messagebox.showwarning("Bookmark URL Needed", error, parent=self)
            self.url_entry.focus_set()
            self.url_entry.select_range(0, tk.END)
            return
        
        # Process custom favicon if provided
        custom_favicon = self._process_custom_favicon(payload.url)
        self.result = payload.to_dict(custom_favicon=custom_favicon or "")
        
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
