"""Table widgets used by the desktop bookmark list."""

from __future__ import annotations

import tkinter as tk
import math
import unicodedata
from datetime import date, datetime, timezone
from numbers import Real
from pathlib import Path
from tkinter import ttk
from typing import Dict, Iterable, List, Mapping, Sequence

from bookmark_organizer_pro.constants import SETTINGS_FILE
from bookmark_organizer_pro.services.settings_store import (
    SettingsStore,
    load_settings,
)
from bookmark_organizer_pro.ui.foundation import FONTS, DesignTokens

try:  # pragma: no cover - exercised when the optional GUI dependency exists
    from tksheet import Sheet
except Exception:  # pragma: no cover - fallback keeps the app usable
    Sheet = None


TKSHEET_AVAILABLE = Sheet is not None

BOOKMARK_TABLE_ACTIONS = (
    {"id": "open", "keys": "Enter"},
    {"id": "toggle_pin", "keys": "Space"},
    {"id": "actions", "keys": "Shift+F10"},
    {"id": "sort", "keys": "Shift+F10"},
)
SEMANTIC_TABLE_STATES = frozenset(("loading", "ready", "empty", "error"))


def _item_id_key(item_id: str) -> tuple:
    """Sort numeric identifiers numerically and all other IDs predictably."""
    text = str(item_id)
    try:
        return (0, int(text))
    except ValueError:
        normalized = unicodedata.normalize("NFKC", text).casefold()
        return (1, normalized, text)


def _typed_sort_key(value: object) -> tuple | None:
    """Normalize a typed source value without guessing from display text."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (0, parsed.astimezone(timezone.utc).timestamp())
    if isinstance(value, date):
        return (0, value.toordinal())
    if isinstance(value, bool):
        return (0, int(value))
    if isinstance(value, Real):
        numeric = float(value)
        if math.isfinite(numeric):
            return (0, numeric)
        return None
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    return (1, text)


def sort_table_item_ids(
    item_ids: Iterable[str],
    values_by_id: Mapping[str, Mapping[str, object]],
    column: str,
    *,
    reverse: bool = False,
) -> List[str]:
    """Return one deterministic table order with missing values always last."""
    present: List[str] = []
    missing: List[str] = []
    normalized: Dict[str, tuple] = {}
    for raw_item_id in item_ids:
        item_id = str(raw_item_id)
        key = _typed_sort_key(values_by_id.get(item_id, {}).get(column))
        if key is None:
            missing.append(item_id)
        else:
            normalized[item_id] = key
            present.append(item_id)

    # The first stable pass provides an invariant tie-breaker. The second
    # changes only the typed source-value direction, never tie ordering.
    present.sort(key=_item_id_key)
    present.sort(key=normalized.__getitem__, reverse=bool(reverse))
    missing.sort(key=_item_id_key)
    return [*present, *missing]


def build_table_semantic_snapshot(
    *,
    columns: Sequence[str],
    header_labels: Mapping[str, str],
    item_ids: Sequence[str],
    cells_by_id: Mapping[str, Sequence[object]],
    selected_ids: Iterable[str],
    sort_column: str | None,
    sort_reverse: bool,
    state: str,
    message: str,
) -> dict:
    """Build the adapter-neutral semantic table contract."""
    if state not in SEMANTIC_TABLE_STATES:
        raise ValueError(f"Unknown bookmark table state: {state}")
    ordered_ids = [str(item_id) for item_id in item_ids]
    selected = {str(item_id) for item_id in selected_ids}
    headers = [
        {
            "id": column,
            "label": str(header_labels.get(column, "")),
            "sort": (
                "descending" if sort_reverse else "ascending"
            ) if column == sort_column else "none",
        }
        for column in columns
    ]
    rows = []
    for position, item_id in enumerate(ordered_ids, start=1):
        values = tuple(cells_by_id.get(item_id, ()))
        rows.append({
            "id": item_id,
            "position": position,
            "set_size": len(ordered_ids),
            "selected": item_id in selected,
            "cells": [
                {
                    "column": column,
                    "value": str(values[index]) if index < len(values) else "",
                }
                for index, column in enumerate(columns)
            ],
        })
    return {
        "role": "table",
        "state": state,
        "message": str(message),
        "headers": headers,
        "rows": rows,
        "actions": [dict(action) for action in BOOKMARK_TABLE_ACTIONS],
    }


def accessible_list_mode_enabled(settings_file: Path = SETTINGS_FILE) -> bool:
    """Return the persisted preference for the native semantic table."""
    try:
        data = load_settings(settings_file)
    except (OSError, TypeError, ValueError):
        return False
    return bool(data.get("accessible_bookmark_list", False))


def save_accessible_list_mode(enabled: bool, settings_file: Path = SETTINGS_FILE) -> None:
    """Persist accessible table selection without discarding other settings."""
    SettingsStore(settings_file).set("accessible_bookmark_list", bool(enabled))


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
        self._base_headers: Dict[str, str] = {
            column: "" for column in ("#0", *tuple(columns))
        }
        self._updating_sort_headers = False
        self._sort_values: Dict[str, Dict[str, object]] = {}
        self._favicon_images: Dict[str, tk.PhotoImage] = {}
        self._placeholder_images: Dict[str, tk.PhotoImage] = {}
        self._semantic_state = "loading"
        self._semantic_message = ""
        
        # Setup column headers for sorting
        for col in columns:
            self.heading(col, command=lambda c=col: self._sort_by_column(c))
        
        # Also make #0 (tree column) sortable if shown
        self.heading("#0", command=lambda: self._sort_by_column("#0"))
    
    def heading(self, column, option=None, **kwargs):
        """Track stable header labels separately from sort indicators."""
        if (
            "text" in kwargs
            and not self._updating_sort_headers
            and hasattr(self, "_base_headers")
        ):
            self._base_headers[str(column)] = str(kwargs["text"])
        return super().heading(column, option, **kwargs)

    def set_bookmark_rows(self, rows: Sequence[dict]):
        """Replace native rows while preserving selection and active sorting."""
        selected = set(str(item) for item in self.selection())
        existing = self.get_children("")
        if existing:
            super().delete(*existing)
        self._sort_values = {}
        for row in rows:
            item_id = str(row["iid"])
            super().insert(
                "",
                "end",
                iid=item_id,
                text=str(row.get("text", "")),
                values=tuple(row.get("values", ())),
                tags=tuple(row.get("tags", ())),
            )
            self._sort_values[item_id] = dict(row.get("sort_values", {}))
        if self._sort_column:
            self._apply_sort(self._sort_column, emit=False)
        restored = [
            item_id for item_id in self.get_children("")
            if str(item_id) in selected
        ]
        if restored:
            self.selection_set(restored)

    def delete(self, *items):
        for item in items:
            self._sort_values.pop(str(item), None)
        return super().delete(*items)

    def _sort_source_values(self, column: str) -> Dict[str, Dict[str, object]]:
        source: Dict[str, Dict[str, object]] = {}
        for raw_item_id in self.get_children(""):
            item_id = str(raw_item_id)
            values = dict(self._sort_values.get(item_id, {}))
            if column not in values:
                values[column] = (
                    self.item(item_id, "text")
                    if column == "#0"
                    else self.set(item_id, column)
                )
            source[item_id] = values
        return source

    def _apply_sort(self, column: str, *, emit: bool = True):
        item_ids = [str(item) for item in self.get_children("")]
        ordered = sort_table_item_ids(
            item_ids,
            self._sort_source_values(column),
            column,
            reverse=self._sort_reverse,
        )
        for index, item_id in enumerate(ordered):
            self.move(item_id, "", index)
        self._apply_sort_headers()
        if emit:
            self.event_generate("<<TreeviewSort>>")

    def _sort_by_column(self, column: str):
        """Toggle and apply typed deterministic sorting for one column."""
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = False
        self._apply_sort(column)

    def sort_by_column(self, column: str):
        """Public keyboard/menu sorting surface shared with the virtual table."""
        if column not in ("#0", *tuple(self["columns"])):
            raise ValueError(f"Unknown bookmark table column: {column}")
        self._sort_by_column(column)
        return "break"

    def sort_state(self) -> tuple[str | None, bool]:
        """Return the active column and reverse flag for shell reconstruction."""
        return self._sort_column, self._sort_reverse

    def restore_sort_state(self, column: str | None, reverse: bool = False):
        """Restore an existing sort without toggling its direction."""
        if column is None:
            return
        if column not in ("#0", *tuple(self["columns"])):
            raise ValueError(f"Unknown bookmark table column: {column}")
        self._sort_column = column
        self._sort_reverse = bool(reverse)
        self._apply_sort(column)

    def _apply_sort_headers(self):
        self._updating_sort_headers = True
        try:
            for column in ("#0", *tuple(self["columns"])):
                label = self._base_headers.get(column, "")
                if column == self._sort_column:
                    indicator = "▼" if self._sort_reverse else "▲"
                    label = f"{label} {indicator}"
                super().heading(column, text=label)
        finally:
            self._updating_sort_headers = False

    def set_sort_values(self, item_id: str, values: Dict[str, object]):
        """Attach stable raw values for columns with human-formatted cells."""
        self._sort_values[str(item_id)] = dict(values)

    def set_semantic_state(self, state: str, message: str = ""):
        """Expose non-row table state through the native fallback contract."""
        if state not in SEMANTIC_TABLE_STATES:
            raise ValueError(f"Unknown bookmark table state: {state}")
        self._semantic_state = state
        self._semantic_message = str(message)

    def semantic_snapshot(self) -> dict:
        """Return an inspectable native-table-equivalent semantic projection."""
        columns = ("#0", *tuple(self["columns"]))
        item_ids = [str(item) for item in self.get_children("")]
        cells_by_id = {}
        for item_id in item_ids:
            values = tuple(self.item(item_id, "values"))
            cells = [str(self.item(item_id, "text"))]
            cells.extend(str(value) for value in values)
            cells_by_id[item_id] = cells
        return build_table_semantic_snapshot(
            columns=columns,
            header_labels=self._base_headers,
            item_ids=item_ids,
            cells_by_id=cells_by_id,
            selected_ids=self.selection(),
            sort_column=self._sort_column,
            sort_reverse=self._sort_reverse,
            state=self._semantic_state,
            message=self._semantic_message,
        )

    def column_at_event(self, event) -> str:
        """Return the logical column under a pointer event."""
        identified = super().identify_column(event.x)
        try:
            index = int(str(identified).lstrip("#"))
        except (TypeError, ValueError):
            return ""
        if index == 0:
            return "#0"
        columns = tuple(self["columns"])
        return str(columns[index - 1]) if index <= len(columns) else ""
    
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

        from .widget_runtime import get_theme
        theme = get_theme()

        bg = str(kwargs.pop("background", theme.bg_primary))
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
        self._item_sort_values: Dict[str, Dict[str, object]] = {}
        self._selected_ids: List[str] = []
        self._sort_column: str | None = None
        self._sort_reverse = False
        self._hovered_row: int | None = None
        self._suppress_selection_events = False
        self._semantic_state = "loading"
        self._semantic_message = ""

        self._sheet = Sheet(
            self,
            headers=[""] * len(self._columns),
            data=[],
            show_row_index=False,
            show_x_scrollbar=False,
            show_y_scrollbar=True,
            default_row_height=DesignTokens.TREEVIEW_ROW_HEIGHT,
            default_header_height=DesignTokens.TABLE_HEADER_HEIGHT,
            align="w",
            header_align="w",
            font=FONTS.body(),
            header_font=FONTS.small(bold=True),
            table_wrap="w",
            header_wrap="",
            rounded_boxes=False,
            show_vertical_grid=True,
            show_horizontal_grid=True,
            column_drag_and_drop_perform=False,
            row_drag_and_drop_perform=False,
            show_selected_cells_border=False,
            frame_bg=theme.bg_primary,
            table_bg=theme.bg_primary,
            table_fg=theme.text_primary,
            table_grid_fg=theme.border_muted,
            table_selected_rows_bg=theme.selection,
            table_selected_rows_fg=theme.text_primary,
            table_selected_rows_border_fg=theme.accent_primary,
            table_selected_cells_bg=theme.selection,
            table_selected_cells_fg=theme.text_primary,
            table_selected_cells_border_fg=theme.accent_primary,
            table_selected_columns_bg=theme.selection,
            table_selected_columns_fg=theme.text_primary,
            header_bg=theme.bg_secondary,
            header_fg=theme.text_secondary,
            header_grid_fg=theme.border_muted,
            header_border_fg=theme.border_muted,
            header_selected_cells_bg=theme.bg_tertiary,
            header_selected_cells_fg=theme.text_primary,
            header_selected_columns_bg=theme.bg_tertiary,
            header_selected_columns_fg=theme.text_primary,
            top_left_bg=theme.bg_secondary,
            top_left_fg=theme.text_secondary,
            popup_menu_bg=theme.bg_secondary,
            popup_menu_fg=theme.text_primary,
            popup_menu_highlight_bg=theme.selection,
            popup_menu_highlight_fg=theme.text_primary,
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
        try:
            # Table-body clicks update the actionable selection; header clicks sort.
            self._sheet.MT.bind("<ButtonRelease-1>", self._on_table_release, add="+")
            self._sheet.MT.bind("<Motion>", self._on_table_motion, add="+")
            self._sheet.MT.bind("<Leave>", self._on_table_leave, add="+")
            self._sheet.CH.bind("<ButtonRelease-1>", self._on_header_release, add="+")
        except AttributeError:
            self._sheet.bind("<ButtonRelease-1>", self._on_header_release, add="+")

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
        self._item_sort_values = {
            str(row["iid"]): dict(row.get("sort_values", {}))
            for row in rows
        }
        if self._sort_column:
            self._row_to_id = sort_table_item_ids(
                self._row_to_id,
                self._sort_source_values(self._sort_column),
                self._sort_column,
                reverse=self._sort_reverse,
            )
            self._id_to_row = {
                item_id: index for index, item_id in enumerate(self._row_to_id)
            }

        data = [
            [self._item_text[item_id], *self._item_values[item_id]]
            for item_id in self._row_to_id
        ]
        self._suppress_selection_events = True
        try:
            self._sheet.set_sheet_data(
                data,
                reset_col_positions=False,
                reset_row_positions=True,
                reset_highlights=True,
                redraw=False,
            )
            self._sheet.set_all_row_heights(
                DesignTokens.TREEVIEW_ROW_HEIGHT,
                only_set_if_too_small=False,
                redraw=False,
            )
            self._apply_headers()
            self._apply_column_widths()
            self._apply_row_highlights(redraw=False)

            restored = [
                item_id for item_id in self._row_to_id
                if item_id in previous_selection
            ]
            if restored:
                self.selection_set(restored, emit=False)
            else:
                self._selected_ids = []
                self._sheet.deselect("all", redraw=False)
            self._sheet.redraw()
        finally:
            self._suppress_selection_events = False

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
                "sort_values": self._item_sort_values.get(existing, {}),
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
                "sort_values": self._item_sort_values.get(existing, {}),
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

        prior_suppression = self._suppress_selection_events
        self._suppress_selection_events = True
        try:
            self._sheet.deselect("all", redraw=False)
            for item_id in item_ids:
                self._sheet.select_row(
                    self._id_to_row[item_id],
                    redraw=False,
                    run_binding_func=False,
                )
            self._selected_ids = item_ids
        finally:
            self._suppress_selection_events = prior_suppression
        self._sheet.redraw()
        if emit:
            self.event_generate("<<TreeviewSelect>>")

    def selection_clear(self):
        prior_suppression = self._suppress_selection_events
        self._suppress_selection_events = True
        try:
            self._selected_ids = []
            self._sheet.deselect("all", redraw=True)
        finally:
            self._suppress_selection_events = prior_suppression
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

    def identify_row(self, event_or_y):
        try:
            y = event_or_y.y if hasattr(event_or_y, 'y') else int(event_or_y)
            row = self._sheet.MT.identify_row(y=y, allow_end=False)
        except Exception:
            row = None
        if row is None or row < 0 or row >= len(self._row_to_id):
            return ""
        return self._row_to_id[row]

    def column_at_event(self, event) -> str:
        """Return the logical column under a pointer event."""
        try:
            column = self._sheet.identify_column(event, allow_end=False)
        except Exception:
            return ""
        if column is None or column < 0 or column >= len(self._columns):
            return ""
        return self._columns[column]

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

    def set_semantic_state(self, state: str, message: str = ""):
        """Expose table states unavailable through tksheet's drawn canvas."""
        if state not in SEMANTIC_TABLE_STATES:
            raise ValueError(f"Unknown bookmark table state: {state}")
        self._semantic_state = state
        self._semantic_message = str(message)

    def semantic_snapshot(self) -> dict:
        """Return the same semantic projection as the native fallback."""
        cells_by_id = {
            item_id: [
                self._item_text.get(item_id, ""),
                *self._item_values.get(item_id, ()),
            ]
            for item_id in self._row_to_id
        }
        return build_table_semantic_snapshot(
            columns=self._columns,
            header_labels=self._headers,
            item_ids=self._row_to_id,
            cells_by_id=cells_by_id,
            selected_ids=self._selected_ids,
            sort_column=self._sort_column,
            sort_reverse=self._sort_reverse,
            state=self._semantic_state,
            message=self._semantic_message,
        )

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

    _MOUSE_TAGS = ("<Button", "<Double-", "<ButtonRelease", "<Control-Mouse", "<MouseWheel")

    def bind(self, sequence=None, func=None, add=None):
        if sequence == "<<TreeviewSelect>>":
            return super().bind(sequence, func, add)
        if sequence:
            if any(tag in sequence for tag in self._MOUSE_TAGS):
                try:
                    return self._sheet.MT.bind(sequence, func, add="+" if add is None else add)
                except AttributeError:
                    pass
            return self._sheet.bind(sequence, func, add=add)
        return super().bind(sequence, func, add)

    def unbind(self, sequence, funcid=None):
        if sequence == "<<TreeviewSelect>>":
            return super().unbind(sequence, funcid)
        if any(tag in sequence for tag in self._MOUSE_TAGS):
            try:
                return self._sheet.MT.unbind(sequence, funcid)
            except AttributeError:
                pass
        return self._sheet.unbind(sequence, funcid)

    def event_generate(self, sequence, **kwargs):
        if sequence == "<<TreeviewSelect>>":
            return super().event_generate(sequence, **kwargs)
        return self._sheet.event_generate(sequence, **kwargs)

    def apply_theme_colors(self):
        """Re-apply theme colors after a live theme switch."""
        from .widget_runtime import get_theme
        theme = get_theme()
        self.configure(bg=theme.bg_primary)
        self._sheet.set_options(
            frame_bg=theme.bg_primary,
            table_bg=theme.bg_primary,
            table_fg=theme.text_primary,
            table_grid_fg=theme.border_muted,
            table_selected_rows_bg=theme.selection,
            table_selected_rows_fg=theme.text_primary,
            table_selected_rows_border_fg=theme.accent_primary,
            table_selected_cells_bg=theme.selection,
            table_selected_cells_fg=theme.text_primary,
            table_selected_cells_border_fg=theme.accent_primary,
            table_selected_columns_bg=theme.selection,
            table_selected_columns_fg=theme.text_primary,
            header_bg=theme.bg_secondary,
            header_fg=theme.text_secondary,
            header_grid_fg=theme.border_muted,
            header_border_fg=theme.border_muted,
            header_selected_cells_bg=theme.bg_tertiary,
            header_selected_cells_fg=theme.text_primary,
            header_selected_columns_bg=theme.bg_tertiary,
            header_selected_columns_fg=theme.text_primary,
            top_left_bg=theme.bg_secondary,
            top_left_fg=theme.text_secondary,
            popup_menu_bg=theme.bg_secondary,
            popup_menu_fg=theme.text_primary,
            popup_menu_highlight_bg=theme.selection,
            popup_menu_highlight_fg=theme.text_primary,
            redraw=True,
        )
        self._apply_row_highlights()

    def apply_zoom(self, row_height: int):
        self._sheet.set_options(
            default_row_height=row_height,
            font=FONTS.body(),
            header_font=FONTS.small(bold=True),
        )
        self._sheet.set_all_row_heights(
            row_height,
            only_set_if_too_small=False,
            redraw=True,
        )

    def _sync_selection_from_sheet(self):
        if self._suppress_selection_events:
            return
        rows: set[int] = set()
        # Captures full-row selections AND rows touched by a single cell click.
        try:
            rows = set(self._sheet.get_selected_rows(get_cells_as_rows=True))
        except Exception:
            rows = set()
        # Fallback for the lone-cell-click case on tksheet builds that report
        # nothing through get_selected_rows.
        if not rows:
            try:
                current = self._sheet.get_currently_selected()
                row = getattr(current, "row", None)
                if isinstance(row, int) and row >= 0:
                    rows = {row}
            except Exception:
                rows = set()
        selected = [
            self._row_to_id[row]
            for row in sorted(rows)
            if 0 <= row < len(self._row_to_id)
        ]
        if selected != self._selected_ids:
            self._selected_ids = selected
            self.event_generate("<<TreeviewSelect>>")

    def _on_table_release(self, _event):
        # Guarantees the actionable selection tracks the visual selection even
        # when tksheet's "select" extra-binding does not fire for a plain click.
        self.after_idle(self._sync_selection_from_sheet)

    def _on_table_motion(self, event):
        """Apply a quiet row hover without disturbing semantic row tags."""
        try:
            row = self._sheet.identify_row(event, exclude_index=True, allow_end=False)
        except Exception:
            row = None
        if row == self._hovered_row:
            return
        self._hovered_row = row
        self._apply_row_highlights(redraw=False)
        if isinstance(row, int) and 0 <= row < len(self._row_to_id):
            from .widget_runtime import get_theme
            self._sheet.highlight_rows(
                row,
                bg=get_theme().bg_hover,
                highlight_index=False,
                redraw=False,
            )
        self._sheet.redraw()

    def _on_table_leave(self, _event=None):
        if self._hovered_row is None:
            return
        self._hovered_row = None
        self._apply_row_highlights()

    def _on_header_release(self, event):
        try:
            column_index = self._sheet.identify_column(event, allow_end=False)
        except Exception:
            return
        if column_index is None or column_index >= len(self._columns):
            return
        self._sort_by_column(self._columns[column_index])

    def _sort_source_values(self, column: str) -> Dict[str, Dict[str, object]]:
        source: Dict[str, Dict[str, object]] = {}
        for item_id in self._row_to_id:
            values = dict(self._item_sort_values.get(item_id, {}))
            if column not in values:
                if column == "#0":
                    values[column] = self._item_text.get(item_id, "")
                else:
                    value_index = self._value_index(column)
                    display_values = self._item_values.get(item_id, ())
                    values[column] = (
                        display_values[value_index]
                        if value_index is not None and value_index < len(display_values)
                        else ""
                    )
            source[item_id] = values
        return source

    def _sort_by_column(self, column: str):
        reverse = not self._sort_reverse if self._sort_column == column else False
        self._sort_column = column
        self._sort_reverse = reverse
        selected = set(self._selected_ids)
        self._row_to_id = sort_table_item_ids(
            self._row_to_id,
            self._sort_source_values(column),
            column,
            reverse=reverse,
        )
        self._id_to_row = {item_id: index for index, item_id in enumerate(self._row_to_id)}
        self._apply_headers()
        self._redraw_from_cache()
        if selected:
            self.selection_set([item_id for item_id in self._row_to_id if item_id in selected], emit=False)
        self.event_generate("<<TreeviewSort>>")

    def sort_by_column(self, column: str):
        """Public keyboard/menu sorting surface shared with native mode."""
        if column not in self._columns:
            raise ValueError(f"Unknown bookmark table column: {column}")
        self._sort_by_column(column)
        return "break"

    def sort_state(self) -> tuple[str | None, bool]:
        """Return the active column and reverse flag for shell reconstruction."""
        return self._sort_column, self._sort_reverse

    def restore_sort_state(self, column: str | None, reverse: bool = False):
        """Restore an existing sort without toggling its direction."""
        if column is None:
            return
        if column not in self._columns:
            raise ValueError(f"Unknown bookmark table column: {column}")
        self._sort_column = column
        self._sort_reverse = bool(reverse)
        selected = set(self._selected_ids)
        self._row_to_id = sort_table_item_ids(
            self._row_to_id,
            self._sort_source_values(column),
            column,
            reverse=self._sort_reverse,
        )
        self._id_to_row = {
            item_id: index for index, item_id in enumerate(self._row_to_id)
        }
        self._apply_headers()
        self._redraw_from_cache()
        if selected:
            self.selection_set(
                [
                    item_id for item_id in self._row_to_id
                    if item_id in selected
                ],
                emit=False,
            )
        self.event_generate("<<TreeviewSort>>")

    def _redraw_from_cache(self):
        rows = [
            {
                "iid": item_id,
                "text": self._item_text.get(item_id, ""),
                "values": self._item_values.get(item_id, ()),
                "tags": self._item_tags.get(item_id, ()),
                "sort_values": self._item_sort_values.get(item_id, {}),
            }
            for item_id in self._row_to_id
        ]
        self.set_bookmark_rows(rows)

    def _apply_headers(self):
        labels = []
        for column in self._columns:
            label = self._headers.get(column, "")
            if column == self._sort_column:
                indicator = "▼" if self._sort_reverse else "▲"
                label = f"{label} {indicator}"
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

    _DECORATIVE_TAGS = frozenset(("oddrow", "evenrow"))

    def _style_for_tags(self, tags: Iterable[str]) -> Dict[str, str]:
        style: Dict[str, str] = {}
        for tag in tags:
            if tag in self._DECORATIVE_TAGS:
                continue
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


def BookmarkListWidget(parent, columns: Sequence[str], **kwargs):
    """Build the virtual table or the native accessibility-compatible table."""
    accessible_mode = kwargs.pop("accessible_mode", None)
    if accessible_mode is None:
        accessible_mode = accessible_list_mode_enabled()
    widget_class = SortableTreeview if accessible_mode or not TKSHEET_AVAILABLE else VirtualBookmarkSheet
    return widget_class(parent, columns=columns, **kwargs)
