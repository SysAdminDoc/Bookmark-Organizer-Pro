"""Bookmark relationship graph construction and layout."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from bookmark_organizer_pro import constants as app_constants
from bookmark_organizer_pro.models import Bookmark


@dataclass
class GraphNode:
    id: str
    label: str
    type: str
    weight: int = 1
    x: float = 0.0
    y: float = 0.0


@dataclass
class GraphEdge:
    id: str
    source: str
    target: str
    kind: str
    weight: int = 1


@dataclass
class BookmarkGraph:
    nodes: List[GraphNode]
    edges: List[GraphEdge]

    def to_dict(self) -> dict:
        return {
            "nodes": [asdict(node) for node in self.nodes],
            "edges": [asdict(edge) for edge in self.edges],
        }


def _slug(value: str) -> str:
    text = re.sub(r"\s+", "-", str(value or "").strip().lower())
    text = re.sub(r"[^a-z0-9_.:-]+", "-", text).strip("-")
    text = re.sub(r"-+", "-", text)
    return text or "unknown"


def _label(value: str, fallback: str = "Untitled") -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text[:80] if text else fallback


def _add_node(nodes: Dict[str, GraphNode], node_id: str, label: str, node_type: str) -> None:
    node = nodes.get(node_id)
    if node is None:
        nodes[node_id] = GraphNode(id=node_id, label=label, type=node_type)
    else:
        node.weight += 1


def _add_edge(edges: Dict[Tuple[str, str, str], GraphEdge], source: str, target: str, kind: str) -> None:
    key = (source, target, kind)
    edge = edges.get(key)
    if edge is None:
        edge_id = f"{kind}:{source}->{target}"
        edges[key] = GraphEdge(id=edge_id, source=source, target=target, kind=kind)
    else:
        edge.weight += 1


def build_bookmark_graph(
    bookmarks: Iterable[Bookmark],
    max_bookmarks: int = 300,
    include_tags: bool = True,
    include_categories: bool = True,
    include_domains: bool = True,
) -> BookmarkGraph:
    """Build a bookmark-to-tag/category/domain relationship graph."""
    nodes: Dict[str, GraphNode] = {}
    edges: Dict[Tuple[str, str, str], GraphEdge] = {}
    for bookmark in list(bookmarks)[:max(0, int(max_bookmarks))]:
        bookmark_id = f"bookmark:{bookmark.id}"
        _add_node(nodes, bookmark_id, _label(bookmark.title or bookmark.url), "bookmark")

        if include_categories and bookmark.category:
            category_label = bookmark.full_category_path
            category_id = f"category:{_slug(category_label)}"
            _add_node(nodes, category_id, _label(category_label, "Uncategorized"), "category")
            _add_edge(edges, bookmark_id, category_id, "category")

        if include_domains and bookmark.domain:
            domain_id = f"domain:{_slug(bookmark.domain)}"
            _add_node(nodes, domain_id, bookmark.domain, "domain")
            _add_edge(edges, bookmark_id, domain_id, "domain")

        if include_tags:
            seen_tags = set()
            for tag in list(bookmark.tags) + list(bookmark.ai_tags):
                tag_label = str(tag or "").strip()
                tag_key = tag_label.lower()
                if not tag_label or tag_key in seen_tags:
                    continue
                seen_tags.add(tag_key)
                tag_id = f"tag:{_slug(tag_label)}"
                _add_node(nodes, tag_id, tag_label, "tag")
                _add_edge(edges, bookmark_id, tag_id, "tag")

    return BookmarkGraph(
        nodes=sorted(nodes.values(), key=lambda node: node.id),
        edges=sorted(edges.values(), key=lambda edge: edge.id),
    )


def _stable_unit(node_id: str, salt: str) -> float:
    digest = hashlib.sha1(f"{salt}:{node_id}".encode("utf-8")).hexdigest()
    return int(digest[:12], 16) / float(0xFFFFFFFFFFFF)


def apply_force_layout(
    graph: BookmarkGraph,
    width: int = 960,
    height: int = 640,
    iterations: int = 80,
) -> BookmarkGraph:
    """Apply a deterministic force-directed layout to graph nodes."""
    if not graph.nodes:
        return graph
    width = max(240, int(width))
    height = max(180, int(height))
    margin = 36.0
    area = float(width * height)
    k = math.sqrt(area / max(1, len(graph.nodes)))
    effective_iterations = max(1, int(iterations))
    if len(graph.nodes) > 250:
        effective_iterations = min(effective_iterations, 35)
    positions: Dict[str, List[float]] = {}
    for node in graph.nodes:
        angle = _stable_unit(node.id, "angle") * math.tau
        radius = 0.2 + (_stable_unit(node.id, "radius") * 0.35)
        positions[node.id] = [
            width / 2 + math.cos(angle) * width * radius,
            height / 2 + math.sin(angle) * height * radius,
        ]

    node_ids = [node.id for node in graph.nodes]
    temp = min(width, height) / 8.0
    for step in range(effective_iterations):
        disp = {node_id: [0.0, 0.0] for node_id in node_ids}
        for i, source in enumerate(node_ids):
            sx, sy = positions[source]
            for target in node_ids[i + 1:]:
                tx, ty = positions[target]
                dx = sx - tx
                dy = sy - ty
                distance = max(0.01, math.hypot(dx, dy))
                force = (k * k) / distance
                fx = dx / distance * force
                fy = dy / distance * force
                disp[source][0] += fx
                disp[source][1] += fy
                disp[target][0] -= fx
                disp[target][1] -= fy

        for edge in graph.edges:
            sx, sy = positions[edge.source]
            tx, ty = positions[edge.target]
            dx = sx - tx
            dy = sy - ty
            distance = max(0.01, math.hypot(dx, dy))
            force = (distance * distance / k) * max(1, edge.weight) * 0.04
            fx = dx / distance * force
            fy = dy / distance * force
            disp[edge.source][0] -= fx
            disp[edge.source][1] -= fy
            disp[edge.target][0] += fx
            disp[edge.target][1] += fy

        cooling = temp * (1.0 - (step / effective_iterations))
        for node_id in node_ids:
            dx, dy = disp[node_id]
            distance = max(0.01, math.hypot(dx, dy))
            px, py = positions[node_id]
            px += dx / distance * min(distance, cooling)
            py += dy / distance * min(distance, cooling)
            positions[node_id] = [
                min(width - margin, max(margin, px)),
                min(height - margin, max(margin, py)),
            ]

    for node in graph.nodes:
        node.x, node.y = positions[node.id]
    return graph


def export_bookmark_graph_json(
    bookmarks: Iterable[Bookmark],
    output_path: Path | None = None,
    max_bookmarks: int = 300,
    width: int = 960,
    height: int = 640,
) -> Path:
    """Build, lay out, and export a bookmark graph as JSON."""
    graph = build_bookmark_graph(bookmarks, max_bookmarks=max_bookmarks)
    apply_force_layout(graph, width=width, height=height)
    path = Path(output_path) if output_path is not None else app_constants.EXPORTS_DIR / "bookmark-graph.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path
