"""Treeview widgets used by the desktop bookmark list."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict


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
        except Exception:
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
                text_width = (bbox[2] - bbox[0]) if bbox else 0
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
