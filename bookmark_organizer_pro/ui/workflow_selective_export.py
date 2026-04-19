"""Selective bookmark export dialog."""

from __future__ import annotations

import csv
from datetime import datetime
import html as html_module
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, List

from bookmark_organizer_pro.constants import APP_VERSION
from bookmark_organizer_pro.importers import OPMLExporter
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.managers import BookmarkManager
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.utils.runtime import atomic_json_write, csv_safe_cell

from .foundation import FONTS, format_compact_count, pluralize
from .quick_add import DEFAULT_CATEGORY
from .tk_interactions import make_keyboard_activatable
from .widget_controls import ModernButton, ThemedWidget, Tooltip
from .widget_runtime import apply_window_chrome, get_theme

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
        self.geometry("600x660")
        self.minsize(560, 600)
        self.configure(bg=theme.bg_primary)
        self.transient(parent)
        self.grab_set()
        
        apply_window_chrome(self)
        
        # Header
        header = tk.Frame(self, bg=theme.bg_dark, height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(
            header, text="📤 Selective Export", bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.header()
        ).pack(side=tk.LEFT, padx=20, pady=15)

        tk.Label(
            header,
            text="Choose the exact scope and format before writing a file.",
            bg=theme.bg_dark, fg=theme.text_secondary,
            font=FONTS.small()
        ).pack(side=tk.LEFT, padx=(0, 20), pady=(18, 0))
        
        # Content
        content = tk.Frame(self, bg=theme.bg_primary)
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        # Format selection
        tk.Label(
            content, text="Export Format", bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.body(bold=True)
        ).pack(anchor="w")

        tk.Label(
            content,
            text="HTML works well for browsers. JSON preserves app data. CSV is best for spreadsheets.",
            bg=theme.bg_primary, fg=theme.text_muted,
            font=FONTS.small(), wraplength=520, justify=tk.LEFT
        ).pack(anchor="w", pady=(2, 0))
        
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
            content, text="Categories", bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.body(bold=True)
        ).pack(anchor="w", pady=(10, 5))

        self.export_summary_label = tk.Label(
            content, text="", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.small(),
            anchor="w"
        )
        self.export_summary_label.pack(fill=tk.X, pady=(0, 6))
        
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
        
        select_all_btn = tk.Label(
            select_frame, text="Select All", bg=theme.bg_secondary,
            fg=theme.accent_primary, font=FONTS.small(),
            cursor="hand2"
        )
        select_all_btn.pack(side=tk.LEFT, padx=(0, 15))
        
        select_none_btn = tk.Label(
            select_frame, text="Select None", bg=theme.bg_secondary,
            fg=theme.accent_primary, font=FONTS.small(),
            cursor="hand2"
        )
        select_none_btn.pack(side=tk.LEFT)

        make_keyboard_activatable(select_all_btn, lambda: self._select_all(True))
        make_keyboard_activatable(select_none_btn, lambda: self._select_all(False))
        Tooltip(select_all_btn, "Select every category")
        Tooltip(select_none_btn, "Clear category selection")
        
        # Category checkboxes
        self.cat_vars: Dict[str, tk.BooleanVar] = {}
        categories = list(bookmark_manager.category_manager.get_sorted_categories())
        category_names = {cat for cat in categories if cat}
        for bookmark in bookmark_manager.get_all_bookmarks():
            category_names.add(bookmark.category or DEFAULT_CATEGORY)
        categories = sorted(category_names, key=lambda value: value.lower())
        counts = bookmark_manager.get_category_counts()

        if not categories:
            tk.Label(
                cat_inner,
                text="No categories yet. Add or import bookmarks first.",
                bg=theme.bg_secondary, fg=theme.text_secondary,
                font=FONTS.body(), padx=10, pady=20,
                justify=tk.LEFT
            ).pack(anchor="w", fill=tk.X)
        
        for cat in categories:
            count = counts.get(cat, 0)
            var = tk.BooleanVar(value=True)
            self.cat_vars[cat] = var
            
            cb = ttk.Checkbutton(
                cat_inner, text=f"{cat} ({format_compact_count(count)})",
                variable=var, command=self._update_export_summary
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
        
        self.export_button = ModernButton(
            btn_frame, text="Export Bookmarks", command=self._export,
            style="primary", icon="📤"
        )
        self.export_button.pack(side=tk.RIGHT)

        self.format_var.trace_add('write', lambda *args: self._update_export_summary())
        self.bind("<Escape>", lambda e: self.destroy())
        self._update_export_summary()
        
        self.center_window()
    
    def _select_all(self, select: bool):
        """Select all or none"""
        for var in self.cat_vars.values():
            var.set(select)
        self._update_export_summary()

    def _selected_bookmarks(self) -> List[Bookmark]:
        selected_cats = {cat for cat, var in self.cat_vars.items() if var.get()}
        if not selected_cats:
            return []
        bookmarks = []
        for cat in selected_cats:
            bookmarks.extend(self.bookmark_manager.get_bookmarks_by_category(cat))
        return bookmarks

    def _update_export_summary(self):
        """Keep export scope visible before the user writes a file."""
        selected_cats = [cat for cat, var in self.cat_vars.items() if var.get()]
        bookmark_count = len(self._selected_bookmarks())
        fmt = self.format_var.get().upper()
        if not selected_cats:
            summary = "Choose at least one category before exporting."
            button_text = "Choose Categories"
            state = "disabled"
        elif bookmark_count == 0:
            summary = f"{pluralize(len(selected_cats), 'category')} selected, but no bookmarks match."
            button_text = "Nothing to Export"
            state = "disabled"
        else:
            summary = (
                f"{pluralize(bookmark_count, 'bookmark')} selected across "
                f"{pluralize(len(selected_cats), 'category')} as {fmt}."
            )
            button_text = f"Export {format_compact_count(bookmark_count)}"
            state = "normal"
        self.export_summary_label.configure(text=summary)
        if getattr(self, "export_button", None):
            self.export_button.set_text(button_text)
            self.export_button.set_state(state)

    def _bookmark_export_dict(self, bookmark: Bookmark) -> Dict[str, Any]:
        """Serialize one bookmark according to selected export options."""
        data = bookmark.to_dict()
        if not self.include_tags_var.get():
            data.pop("tags", None)
            data.pop("ai_tags", None)
        if not self.include_notes_var.get():
            data.pop("notes", None)
        if not self.include_metadata_var.get():
            for key in (
                "created_at", "updated_at", "modified_at", "visited_at",
                "last_visited", "last_checked", "visit_count", "http_status",
                "ai_confidence"
            ):
                data.pop(key, None)
        return data

    def _group_bookmarks(self, bookmarks: List[Bookmark]) -> Dict[str, List[Bookmark]]:
        grouped: Dict[str, List[Bookmark]] = {}
        for bm in bookmarks:
            grouped.setdefault(bm.category or "Uncategorized", []).append(bm)
        return grouped

    def _export_selected_html(self, bookmarks: List[Bookmark], filepath: str):
        grouped = self._group_bookmarks(bookmarks)
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write('<!DOCTYPE NETSCAPE-Bookmark-file-1>\n')
            f.write('<!-- Exported by Bookmark Organizer Pro -->\n')
            f.write('<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">\n')
            f.write('<TITLE>Bookmarks</TITLE>\n<H1>Bookmarks</H1>\n<DL><p>\n')
            for category in sorted(grouped):
                f.write(f'    <DT><H3>{html_module.escape(str(category), quote=True)}</H3>\n    <DL><p>\n')
                for bm in grouped[category]:
                    attrs = f'HREF="{html_module.escape(str(bm.url or ""), quote=True)}"'
                    if self.include_metadata_var.get() and getattr(bm, "add_date", ""):
                        attrs += f' ADD_DATE="{html_module.escape(str(bm.add_date), quote=True)}"'
                    if self.include_tags_var.get() and bm.tags:
                        attrs += f' TAGS="{html_module.escape(",".join(map(str, bm.tags)), quote=True)}"'
                    f.write(f'        <DT><A {attrs}>{html_module.escape(str(bm.title or ""), quote=True)}</A>\n')
                    if self.include_notes_var.get() and bm.notes:
                        f.write(f'        <DD>{html_module.escape(str(bm.notes), quote=True)}\n')
                f.write('    </DL><p>\n')
            f.write('</DL><p>\n')

    def _export_selected_json(self, bookmarks: List[Bookmark], filepath: str):
        selected_categories = {bm.category for bm in bookmarks}
        data = {
            "version": 4,
            "exported_at": datetime.now().isoformat(),
            "app_version": APP_VERSION,
            "categories": {
                name: cat.to_dict()
                for name, cat in self.bookmark_manager.category_manager.categories.items()
                if name in selected_categories
            },
            "bookmarks": [self._bookmark_export_dict(bm) for bm in bookmarks],
        }
        if self.include_tags_var.get():
            data["tags"] = [
                tag.to_dict()
                for tag in self.bookmark_manager.tag_manager.tags.values()
            ]
        target = Path(filepath)
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_json_write(target, data)

    def _export_selected_csv(self, bookmarks: List[Bookmark], filepath: str):
        columns = ["Title", "URL", "Category"]
        if self.include_tags_var.get():
            columns.append("Tags")
        if self.include_notes_var.get():
            columns.append("Notes")
        if self.include_metadata_var.get():
            columns.extend(["Created", "Visits", "Is Pinned"])

        target = Path(filepath)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            for bm in bookmarks:
                row = [csv_safe_cell(bm.title), csv_safe_cell(bm.url), csv_safe_cell(bm.category)]
                if self.include_tags_var.get():
                    row.append(csv_safe_cell(",".join(bm.tags)))
                if self.include_notes_var.get():
                    row.append(csv_safe_cell(bm.notes))
                if self.include_metadata_var.get():
                    row.extend([bm.created_at, bm.visit_count, bm.is_pinned])
                writer.writerow(row)

    @staticmethod
    def _markdown_text(value) -> str:
        """Escape text for Markdown labels and inline code-ish content."""
        text = str(value or "").replace("\\", "\\\\")
        return (
            text.replace("[", "\\[")
                .replace("]", "\\]")
                .replace("(", "\\(")
                .replace(")", "\\)")
                .replace("`", "\\`")
        )

    @staticmethod
    def _markdown_url(value) -> str:
        """Keep Markdown link destinations on one line and avoid closing parens."""
        return str(value or "").replace("\r", "").replace("\n", "").replace("(", "%28").replace(")", "%29")

    def _export_selected_markdown(self, bookmarks: List[Bookmark], filepath: str):
        grouped = self._group_bookmarks(bookmarks)
        target = Path(filepath)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write("# Bookmarks\n\n")
            f.write(f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
            f.write(f"Total: {len(bookmarks)} bookmarks\n\n---\n\n")
            for category in sorted(grouped):
                f.write(f"## {self._markdown_text(category)}\n\n")
                for bm in grouped[category]:
                    f.write(f"- [{self._markdown_text(bm.title)}]({self._markdown_url(bm.url)})")
                    if self.include_tags_var.get() and bm.tags:
                        f.write(" " + " ".join(f"`{self._markdown_text(tag)}`" for tag in bm.tags))
                    f.write("\n")
                    if self.include_notes_var.get() and bm.notes:
                        note = self._markdown_text(bm.notes).replace("\n", "\n  > ")
                        f.write(f"  > {note}\n")
                    if self.include_metadata_var.get():
                        created = self._markdown_text(bm.created_at or "Unknown")
                        f.write(f"  - Added: {created}; Visits: {bm.visit_count}\n")
                f.write("\n")
    
    def _export(self):
        """Perform export"""
        selected_cats = [cat for cat, var in self.cat_vars.items() if var.get()]
        
        if not selected_cats:
            messagebox.showwarning(
                "Choose a category",
                "Select at least one category to export.",
                parent=self
            )
            return
        
        bookmarks = self._selected_bookmarks()
        
        if not bookmarks:
            messagebox.showwarning(
                "Nothing to export",
                "The selected categories do not contain any bookmarks.",
                parent=self
            )
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
            filetypes=[extensions[fmt], ("All files", "*.*")],
            parent=self
        )
        
        if not filepath:
            return
        
        # Export
        try:
            if fmt == "html":
                self._export_selected_html(bookmarks, filepath)
            elif fmt == "json":
                self._export_selected_json(bookmarks, filepath)
            elif fmt == "csv":
                self._export_selected_csv(bookmarks, filepath)
            elif fmt == "md":
                self._export_selected_markdown(bookmarks, filepath)
            elif fmt == "opml":
                OPMLExporter.export(bookmarks, filepath)
            
            self.result = {
                "filepath": filepath,
                "format": fmt,
                "count": len(bookmarks)
            }
            
            messagebox.showinfo(
                "Export complete",
                f"Exported {len(bookmarks)} bookmark{'s' if len(bookmarks) != 1 else ''} to {Path(filepath).name}.",
                parent=self
            )
            if callable(self.on_export):
                self.on_export(self.result)
            self.destroy()
        
        except Exception as e:
            log.warning("Selective export failed", exc_info=True)
            messagebox.showerror(
                "Export failed",
                f"Could not export bookmarks:\n\n{e}",
                parent=self
            )
    
    def center_window(self):
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')
