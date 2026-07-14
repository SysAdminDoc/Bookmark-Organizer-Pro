"""Desktop bookmark graph canvas."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog
from typing import Callable, Dict, Iterable, Optional

from bookmark_organizer_pro.i18n import _
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.bookmark_graph import (
    BookmarkGraph,
    GraphNode,
    apply_force_layout,
    build_bookmark_graph,
    export_bookmark_graph_json,
)

from .foundation import FONTS
from .tk_interactions import WHEEL_EVENTS, wheel_scroll_units
from .widget_controls import ModernButton
from .window_geometry import apply_screen_aware_geometry
from .widgets import apply_window_chrome, get_theme


_DIRECTION_VECTORS = {
    "Left": (-1, 0),
    "Right": (1, 0),
    "Up": (0, -1),
    "Down": (0, 1),
}


def _directional_node_id(
    nodes: Iterable[GraphNode],
    current_node_id: str | None,
    keysym: str,
) -> str | None:
    """Return the nearest graph node lying in the requested direction."""
    ordered = list(nodes)
    if not ordered:
        return None
    current = next((node for node in ordered if node.id == current_node_id), None)
    if current is None:
        return ordered[0].id
    direction = _DIRECTION_VECTORS.get(keysym)
    if direction is None:
        return current.id
    dx_sign, dy_sign = direction
    candidates = []
    for node in ordered:
        if node.id == current.id:
            continue
        dx = node.x - current.x
        dy = node.y - current.y
        forward = (dx * dx_sign) + (dy * dy_sign)
        if forward <= 0:
            continue
        sideways = abs((dx * dy_sign) - (dy * dx_sign))
        distance = (dx * dx) + (dy * dy)
        candidates.append((sideways / forward, distance, node.id))
    return min(candidates)[2] if candidates else current.id


def _node_colors():
    theme = get_theme()
    return {
        "bookmark": theme.accent_cyan,
        "tag": theme.accent_success,
        "category": theme.accent_warning,
        "domain": theme.accent_purple,
    }


class GraphViewDialog(tk.Toplevel):
    """Render bookmark relationships on a Tk canvas."""

    def __init__(
        self,
        parent,
        bookmarks: Iterable[Bookmark],
        on_open_bookmark: Optional[Callable[[Bookmark], None]] = None,
        max_bookmarks: int = 200,
    ):
        theme = get_theme()
        super().__init__(parent)
        self.bookmarks = list(bookmarks)
        self.bookmarks_by_node = {f"bookmark:{bm.id}": bm for bm in self.bookmarks}
        self.on_open_bookmark = on_open_bookmark
        self.max_bookmarks = max_bookmarks
        self.graph: BookmarkGraph = apply_force_layout(
            build_bookmark_graph(self.bookmarks, max_bookmarks=max_bookmarks),
            width=980,
            height=640,
            iterations=60,
        )
        self.node_lookup: Dict[str, GraphNode] = {node.id: node for node in self.graph.nodes}
        self.selected_node_id: str | None = None

        self.title(_("Bookmark Graph"))
        self.minsize(820, 560)
        apply_screen_aware_geometry(self, 1120, 760)
        self.configure(bg=theme.bg_primary)
        self.transient(parent)
        apply_window_chrome(self)

        self._build()
        self._draw_graph()
        self.bind("<Escape>", lambda _event: self.destroy())

    def _build(self) -> None:
        theme = get_theme()
        header = tk.Frame(self, bg=theme.bg_secondary, padx=16, pady=12)
        header.pack(fill=tk.X)
        title_stack = tk.Frame(header, bg=theme.bg_secondary)
        title_stack.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(
            title_stack,
            text=_("Bookmark Graph"),
            bg=theme.bg_secondary,
            fg=theme.text_primary,
            font=FONTS.header(bold=True),
            anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            title_stack,
            text=_("Explore relationships between bookmarks, tags, categories, and domains."),
            bg=theme.bg_secondary,
            fg=theme.text_secondary,
            font=FONTS.small(),
            anchor="w",
        ).pack(fill=tk.X, pady=(3, 0))
        ModernButton(
            header,
            text=_("Export"),
            command=self._export_graph,
            style="primary",
        ).pack(side=tk.RIGHT, padx=(12, 0))

        body = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg=theme.bg_primary, sashwidth=4)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        canvas_frame = tk.Frame(body, bg=theme.bg_primary)
        self.canvas = tk.Canvas(
            canvas_frame,
            bg=theme.bg_primary,
            takefocus=1,
            highlightthickness=1,
            highlightbackground=theme.border_muted,
            highlightcolor=theme.accent_primary,
            scrollregion=(0, 0, 1040, 700),
        )
        xbar = tk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        ybar = tk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)
        body.add(canvas_frame, minsize=560)

        side = tk.Frame(body, bg=theme.bg_secondary, padx=12, pady=12)
        body.add(side, minsize=260)
        self.stats_label = tk.Label(
            side,
            text=_("{nodes} nodes / {edges} edges").format(nodes=len(self.graph.nodes), edges=len(self.graph.edges)),
            bg=theme.bg_secondary,
            fg=theme.text_secondary,
            font=FONTS.body(),
            anchor="w",
        )
        self.stats_label.pack(fill=tk.X)
        self.detail_title = tk.Label(
            side,
            text=_("Selected"),
            bg=theme.bg_secondary,
            fg=theme.text_primary,
            font=FONTS.body(bold=True),
            anchor="w",
        )
        self.detail_title.pack(fill=tk.X, pady=(16, 6))
        self.detail_text = tk.Text(
            side,
            height=12,
            wrap=tk.WORD,
            bg=theme.bg_primary,
            fg=theme.text_primary,
            relief=tk.FLAT,
            padx=8,
            pady=8,
            font=FONTS.small(),
        )
        self.detail_text.pack(fill=tk.BOTH, expand=True)
        self.detail_text.insert("1.0", _("Select a node to inspect its relationship details."))
        self.detail_text.configure(state=tk.DISABLED)

        legend = tk.Frame(side, bg=theme.bg_secondary)
        legend.pack(fill=tk.X, pady=(10, 0))
        tk.Label(
            legend, text=_("Legend"), bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.small(bold=True),
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 4))
        for node_type in ("bookmark", "tag", "category", "domain"):
            row = tk.Frame(legend, bg=theme.bg_secondary)
            row.pack(fill=tk.X, pady=1)
            tk.Frame(row, bg=_node_colors()[node_type], width=10, height=10).pack(side=tk.LEFT, padx=(0, 6))
            tk.Label(
                row, text=node_type.title(), bg=theme.bg_secondary,
                fg=theme.text_muted, font=FONTS.small(), anchor="w",
            ).pack(side=tk.LEFT)

        self.status = tk.Label(
            side,
            text=_("Select a node. Use Tab or arrow keys to navigate; Enter opens bookmarks."),
            bg=theme.bg_secondary,
            fg=theme.text_muted,
            font=FONTS.small(),
            anchor="w",
            justify=tk.LEFT,
            wraplength=240,
        )
        self.status.pack(fill=tk.X, pady=(10, 0))

        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<Double-Button-1>", self._on_canvas_double_click)
        for sequence in WHEEL_EVENTS:
            self.canvas.bind(sequence, self._on_mousewheel)
        self.canvas.bind("<Tab>", self._on_tab_navigation)
        self.canvas.bind("<Shift-Tab>", self._on_tab_navigation)
        if self.canvas.tk.call("tk", "windowingsystem") == "x11":
            self.canvas.bind("<ISO_Left_Tab>", self._on_tab_navigation)
        for key in ("<Left>", "<Right>", "<Up>", "<Down>"):
            self.canvas.bind(key, self._on_arrow_navigation)
        self.canvas.bind("<Return>", self._on_keyboard_activate)
        self.canvas.bind("<space>", self._on_keyboard_activate)

    def _draw_graph(self) -> None:
        theme = get_theme()
        self.canvas.delete("all")
        if not self.graph.nodes:
            self.canvas.create_text(
                520, 320,
                text=_("No graph data yet"),
                fill=theme.text_secondary,
                font=FONTS.subtitle(bold=True),
            )
            self.canvas.create_text(
                520, 348,
                text=_("Add bookmarks with tags, categories, or shared domains to build relationships."),
                fill=theme.text_muted,
                font=FONTS.small(),
            )
            return
        for edge in self.graph.edges:
            source = self.node_lookup.get(edge.source)
            target = self.node_lookup.get(edge.target)
            if source is None or target is None:
                continue
            self.canvas.create_line(
                source.x,
                source.y,
                target.x,
                target.y,
                fill=theme.border_muted,
                width=max(1, min(4, edge.weight)),
                tags=("graph", "edge"),
            )
        for node in self.graph.nodes:
            self._draw_node(node)

    def _draw_node(self, node: GraphNode) -> None:
        theme = get_theme()
        color = _node_colors().get(node.type, theme.accent_primary)
        size = 8 + min(10, node.weight)
        tag = f"node:{node.id}"
        self.canvas.create_rectangle(
            node.x - size,
            node.y - size,
            node.x + size,
            node.y + size,
            fill=color,
            outline=theme.bg_primary,
            width=2,
            tags=("graph", "node", "node-shape", f"node-shape:{node.id}", tag),
        )
        self.canvas.create_text(
            node.x + size + 5,
            node.y,
            text=node.label[:36],
            anchor="w",
            fill=theme.text_primary,
            font=FONTS.small(),
            tags=("graph", "node-label", tag),
        )

    def _node_id_from_event(self, event) -> str | None:
        current = self.canvas.find_withtag("current")
        if not current:
            return None
        for tag in self.canvas.gettags(current[0]):
            if tag.startswith("node:"):
                return tag.removeprefix("node:")
        return None

    def _on_canvas_press(self, event) -> None:
        node_id = self._node_id_from_event(event)
        if node_id:
            self._select_node(node_id)
            return
        self.canvas.scan_mark(event.x, event.y)

    def _on_canvas_drag(self, event) -> None:
        if self._node_id_from_event(event):
            return
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_canvas_double_click(self, event) -> None:
        node_id = self._node_id_from_event(event)
        if not node_id or not node_id.startswith("bookmark:"):
            return
        bookmark = self.bookmarks_by_node.get(node_id)
        if bookmark is not None and self.on_open_bookmark:
            self.on_open_bookmark(bookmark)

    def _on_mousewheel(self, event) -> None:
        units = wheel_scroll_units(event)
        if not units:
            return "break"
        factor = 1.1 if units < 0 else 0.9
        self.canvas.scale("graph", self.canvas.canvasx(event.x), self.canvas.canvasy(event.y), factor, factor)
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        return "break"

    def _on_tab_navigation(self, event) -> str:
        node_ids = [node.id for node in self.graph.nodes]
        if not node_ids:
            return "break"
        step = -1 if getattr(event, "state", 0) & 0x0001 else 1
        try:
            index = node_ids.index(self.selected_node_id)
        except ValueError:
            index = -1 if step > 0 else 0
        self._select_node(node_ids[(index + step) % len(node_ids)])
        return "break"

    def _on_arrow_navigation(self, event) -> str:
        node_id = _directional_node_id(self.graph.nodes, self.selected_node_id, event.keysym)
        if node_id is not None:
            self._select_node(node_id)
        return "break"

    def _on_keyboard_activate(self, _event=None) -> str:
        node_id = self.selected_node_id
        if node_id and node_id.startswith("bookmark:") and self.on_open_bookmark:
            bookmark = self.bookmarks_by_node.get(node_id)
            if bookmark is not None:
                self.on_open_bookmark(bookmark)
        return "break"

    def _select_node(self, node_id: str) -> None:
        node = self.node_lookup.get(node_id)
        if node is None:
            return
        self.selected_node_id = node_id
        theme = get_theme()
        self.canvas.itemconfigure("node-shape", outline=theme.bg_primary, width=2)
        self.canvas.itemconfigure(f"node-shape:{node_id}", outline=theme.accent_primary, width=4)
        connected = [
            edge for edge in self.graph.edges
            if edge.source == node_id or edge.target == node_id
        ]
        lines = [
            node.label,
            "",
            _("Type: {type}").format(type=node.type),
            _("Weight: {weight}").format(weight=node.weight),
            _("Connections: {count}").format(count=len(connected)),
        ]
        if node_id.startswith("bookmark:"):
            bookmark = self.bookmarks_by_node.get(node_id)
            if bookmark:
                lines.extend(["", bookmark.url, bookmark.full_category_path])
        self.detail_text.configure(state=tk.NORMAL)
        self.detail_text.delete("1.0", tk.END)
        self.detail_text.insert("1.0", "\n".join(lines))
        self.detail_text.configure(state=tk.DISABLED)
        self.status.configure(text=node.id)

    def _export_graph(self) -> None:
        output_path = filedialog.asksaveasfilename(
            parent=self,
            title=_("Export Graph JSON"),
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not output_path:
            return
        path = export_bookmark_graph_json(self.bookmarks, output_path=output_path, max_bookmarks=self.max_bookmarks)
        self.status.configure(text=_("Exported {name}").format(name=path.name))
