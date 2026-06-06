"""Table widgets used by the desktop bookmark list."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict, Iterable, List, Sequence

from bookmark_organizer_pro.ui.foundation import FONTS

try:  # pragma: no cover - exercised when the optional GUI dependency exists
    from tksheet import Sheet
except Exception:  # pragma: no cover - fallback keeps the app usable
    Sheet = None


TKSHEET_AVAILABLE = Sheet is not None


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


class VirtualBookmarkSheet(tk.Frame):
    """Treeview-compatible bookmark table backed by tksheet virtual drawing."""

    uses_internal_scrollbars = True

    def __init__(self, parent, columns: Sequence[str], **kwargs):
        if Sheet is None:
            raise RuntimeError("tksheet is not available")

        bg = str(kwargs.pop("background", "#111111"))
        super().__init__(parent, bg=bg)
        self._columns = ("#0", *tuple(columns))
        self._headers: Dict[str, str] = {column: "" for column in self._columns}
        self._column_widths: Dict[str, int] = {}
        self._tag_styles: Dict[str, Dict[str, str]] = {}
        self._row_to_id: List[str] = []
        self._id_to_row: Dict[str, int] = {}
        self._item_values: Dict[str, tuple] = {}
        self._item_text: Dict[str, str] = {}
        self._item_tags: Dict[str, tuple] = {}
        self._selected_ids: List[str] = []
        self._sort_column: str | None = None
        self._sort_reverse = False

        self._sheet = Sheet(
            self,
            headers=[""] * len(self._columns),
            data=[],
            show_row_index=False,
            show_x_scrollbar=True,
            show_y_scrollbar=True,
            default_row_height=30,
            default_header_height=28,
            font=FONTS.body(),
            header_font=FONTS.small(bold=True),
            table_wrap="",
            header_wrap="",
            column_drag_and_drop_perform=False,
            row_drag_and_drop_perform=False,
            show_selected_cells_border=False,
        )
        self._sheet.pack(fill=tk.BOTH, expand=True)
        self._sheet.enable_bindings(
            "single_select",
            "row_select",
            "drag_select",
            "ctrl_row_select",
            "shift_row_select",
            "copy",
            "arrowkeys",
        )
        self._sheet.extra_bindings("select", lambda _event: self._sync_selection_from_sheet())
        self._sheet.bind("<ButtonRelease-1>", self._on_button_release, add="+")

    def heading(self, column: str, text: str | None = None, command=None):
        """Set or get a column heading."""
        if text is not None:
            self._headers[column] = text
            self._apply_headers()
        if command is not None:
            self._headers[f"{column}:command"] = command
        return self._headers.get(column, "")

    def column(self, column: str, width: int | None = None, **_kwargs):
        """Set or get a column width."""
        if width is not None:
            self._column_widths[column] = int(width)
            col_index = self._column_index(column)
            if col_index is not None:
                self._sheet.column_width(col_index, width=int(width), redraw=True)
        return {"width": self._column_widths.get(column)}

    def tag_configure(self, tag: str, **kwargs):
        """Store row style tokens and apply them to existing rows."""
        current = self._tag_styles.setdefault(tag, {})
        for key in ("background", "foreground"):
            if key in kwargs:
                current[key] = kwargs[key]
        self._apply_row_highlights()

    def set_bookmark_rows(self, rows: Sequence[dict]):
        """Replace all visible rows in one tksheet data update."""
        previous_selection = set(self._selected_ids)
        self._row_to_id = [str(row["iid"]) for row in rows]
        self._id_to_row = {item_id: index for index, item_id in enumerate(self._row_to_id)}
        self._item_values = {str(row["iid"]): tuple(row.get("values", ())) for row in rows}
        self._item_text = {str(row["iid"]): str(row.get("text", "")) for row in rows}
        self._item_tags = {str(row["iid"]): tuple(row.get("tags", ())) for row in rows}

        data = [
            [self._item_text[item_id], *self._item_values[item_id]]
            for item_id in self._row_to_id
        ]
        self._sheet.set_sheet_data(
            data,
            reset_col_positions=False,
            reset_row_positions=True,
            reset_highlights=True,
            redraw=False,
        )
        self._apply_headers()
        self._apply_column_widths()
        self._apply_row_highlights(redraw=False)

        restored = [item_id for item_id in self._row_to_id if item_id in previous_selection]
        if restored:
            self.selection_set(restored, emit=False)
        else:
            self._selected_ids = []
            self._sheet.deselect("all", redraw=False)
        self._sheet.redraw()

    def insert(self, _parent, index, iid=None, text="", values=(), tags=()):
        """Append one row. Kept for compatibility with Treeview callers."""
        item_id = str(iid if iid is not None else len(self._row_to_id))
        row = {"iid": item_id, "text": text, "values": tuple(values), "tags": tuple(tags)}
        current = [
            {
                "iid": existing,
                "text": self._item_text.get(existing, ""),
                "values": self._item_values.get(existing, ()),
                "tags": self._item_tags.get(existing, ()),
            }
            for existing in self._row_to_id
        ]
        if index == "end":
            current.append(row)
        else:
            current.insert(int(index), row)
        self.set_bookmark_rows(current)
        return item_id

    def delete(self, item: str):
        item_id = str(item)
        rows = [
            {
                "iid": existing,
                "text": self._item_text.get(existing, ""),
                "values": self._item_values.get(existing, ()),
                "tags": self._item_tags.get(existing, ()),
            }
            for existing in self._row_to_id
            if existing != item_id
        ]
        self.set_bookmark_rows(rows)

    def get_children(self, _parent: str = ""):
        return tuple(self._row_to_id)

    def selection(self):
        return tuple(self._selected_ids)

    def selection_set(self, items, emit: bool = True):
        if isinstance(items, (str, int)):
            item_ids = [str(items)]
        else:
            item_ids = [str(item) for item in items]
        item_ids = [item_id for item_id in item_ids if item_id in self._id_to_row]

        self._sheet.deselect("all", redraw=False)
        for item_id in item_ids:
            self._sheet.select_row(
                self._id_to_row[item_id],
                redraw=False,
                run_binding_func=False,
            )
        self._selected_ids = item_ids
        self._sheet.redraw()
        if emit:
            self.event_generate("<<TreeviewSelect>>")

    def selection_clear(self):
        self._selected_ids = []
        self._sheet.deselect("all", redraw=True)
        self.event_generate("<<TreeviewSelect>>")

    def item(self, item: str, option: str | None = None, **kwargs):
        item_id = str(item)
        if kwargs:
            if "values" in kwargs:
                self._item_values[item_id] = tuple(kwargs["values"])
            if "text" in kwargs:
                self._item_text[item_id] = str(kwargs["text"])
            if "tags" in kwargs:
                self._item_tags[item_id] = tuple(kwargs["tags"])
            self._redraw_from_cache()
        data = {
            "text": self._item_text.get(item_id, ""),
            "values": self._item_values.get(item_id, ()),
            "tags": self._item_tags.get(item_id, ()),
        }
        return data.get(option) if option else data

    def set(self, item: str, column: str, value=None):
        item_id = str(item)
        values = list(self._item_values.get(item_id, ()))
        value_index = self._value_index(column)
        if value_index is None:
            return ""
        while len(values) <= value_index:
            values.append("")
        if value is None:
            return values[value_index]
        values[value_index] = value
        self._item_values[item_id] = tuple(values)
        self._redraw_from_cache()
        return value

    def identify_row(self, event):
        try:
            row = self._sheet.identify_row(event, allow_end=False)
        except Exception:
            row = None
        if row is None or row < 0 or row >= len(self._row_to_id):
            return ""
        return self._row_to_id[row]

    def focus(self, item: str | None = None):
        if item is not None and str(item) in self._id_to_row:
            self.see(str(item))
        return self._selected_ids[0] if self._selected_ids else ""

    def focus_set(self):
        self._sheet.focus_set()

    def see(self, item: str):
        item_id = str(item)
        row = self._id_to_row.get(item_id)
        if row is not None:
            self._sheet.see(row, 0)

    def set_favicon(self, _item_id: str, _image_path: str):
        """tksheet does not expose per-row images; retain API compatibility."""
        return None

    def set_placeholder(self, _item_id: str, _letter: str, _color: str):
        return None

    def yview(self, *args):
        return self._sheet.yview(*args)

    def xview(self, *args):
        return self._sheet.xview(*args)

    def configure(self, cnf=None, **kwargs):
        if any(key in kwargs for key in ("yscrollcommand", "xscrollcommand")):
            kwargs.pop("yscrollcommand", None)
            kwargs.pop("xscrollcommand", None)
        if kwargs or cnf:
            return super().configure(cnf, **kwargs)
        return super().configure()

    config = configure

    def bind(self, sequence=None, func=None, add=None):
        if sequence == "<<TreeviewSelect>>":
            return super().bind(sequence, func, add)
        if sequence:
            return self._sheet.bind(sequence, func, add=add)
        return super().bind(sequence, func, add)

    def unbind(self, sequence, funcid=None):
        if sequence == "<<TreeviewSelect>>":
            return super().unbind(sequence, funcid)
        return self._sheet.unbind(sequence, funcid)

    def event_generate(self, sequence, **kwargs):
        if sequence == "<<TreeviewSelect>>":
            return super().event_generate(sequence, **kwargs)
        return self._sheet.event_generate(sequence, **kwargs)

    def apply_zoom(self, row_height: int):
        self._sheet.set_options(
            default_row_height=row_height,
            font=FONTS.body(),
            header_font=FONTS.small(bold=True),
        )

    def _sync_selection_from_sheet(self):
        try:
            rows = sorted(self._sheet.get_selected_rows())
        except Exception:
            rows = []
        selected = [
            self._row_to_id[row]
            for row in rows
            if 0 <= row < len(self._row_to_id)
        ]
        if selected != self._selected_ids:
            self._selected_ids = selected
            self.event_generate("<<TreeviewSelect>>")

    def _on_button_release(self, event):
        try:
            column_index = self._sheet.identify_column(event, allow_end=False)
            row_index = self._sheet.identify_row(event, allow_end=False)
        except Exception:
            return
        if column_index is not None and row_index is None:
            column = self._columns[column_index] if column_index < len(self._columns) else None
            if column:
                self._sort_by_column(column)

    def _sort_by_column(self, column: str):
        if not self._row_to_id:
            return
        reverse = not self._sort_reverse if self._sort_column == column else False
        self._sort_column = column
        self._sort_reverse = reverse
        selected = set(self._selected_ids)

        def sort_value(item_id: str):
            if column == "#0":
                value = self._item_text.get(item_id, "")
            else:
                value_index = self._value_index(column)
                values = self._item_values.get(item_id, ())
                value = values[value_index] if value_index is not None and value_index < len(values) else ""
            try:
                return (0, float(value))
            except (TypeError, ValueError):
                return (1, str(value).lower())

        self._row_to_id.sort(key=sort_value, reverse=reverse)
        self._id_to_row = {item_id: index for index, item_id in enumerate(self._row_to_id)}
        self._apply_headers()
        self._redraw_from_cache()
        if selected:
            self.selection_set([item_id for item_id in self._row_to_id if item_id in selected], emit=False)

    def _redraw_from_cache(self):
        rows = [
            {
                "iid": item_id,
                "text": self._item_text.get(item_id, ""),
                "values": self._item_values.get(item_id, ()),
                "tags": self._item_tags.get(item_id, ()),
            }
            for item_id in self._row_to_id
        ]
        self.set_bookmark_rows(rows)

    def _apply_headers(self):
        labels = []
        for column in self._columns:
            label = self._headers.get(column, "")
            label = label.replace(" ▲", "").replace(" ▼", "")
            if column == self._sort_column:
                label += " ▼" if self._sort_reverse else " ▲"
            labels.append(label)
        self._sheet.headers(labels, reset_col_positions=False, redraw=True)

    def _apply_column_widths(self):
        for column, width in self._column_widths.items():
            col_index = self._column_index(column)
            if col_index is not None:
                self._sheet.column_width(col_index, width=width, redraw=False)

    def _apply_row_highlights(self, redraw: bool = True):
        if not self._row_to_id:
            return
        self._sheet.dehighlight_all(redraw=False)
        grouped: Dict[tuple, List[int]] = {}
        for row_index, item_id in enumerate(self._row_to_id):
            style = self._style_for_tags(self._item_tags.get(item_id, ()))
            grouped.setdefault((style.get("background"), style.get("foreground")), []).append(row_index)
        for (bg, fg), rows in grouped.items():
            if bg or fg:
                self._sheet.highlight_rows(
                    rows,
                    bg=bg,
                    fg=fg,
                    highlight_index=False,
                    redraw=False,
                )
        if redraw:
            self._sheet.redraw()

    def _style_for_tags(self, tags: Iterable[str]) -> Dict[str, str]:
        style: Dict[str, str] = {}
        for tag in tags:
            tag_style = self._tag_styles.get(tag, {})
            if "background" in tag_style:
                style["background"] = tag_style["background"]
            if "foreground" in tag_style:
                style["foreground"] = tag_style["foreground"]
        return style

    def _column_index(self, column: str) -> int | None:
        try:
            return self._columns.index(column)
        except ValueError:
            return None

    def _value_index(self, column: str) -> int | None:
        col_index = self._column_index(column)
        if col_index is None or col_index == 0:
            return None
        return col_index - 1


BookmarkListWidget = VirtualBookmarkSheet if TKSHEET_AVAILABLE else SortableTreeview
