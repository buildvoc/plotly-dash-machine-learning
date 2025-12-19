from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable, List, Tuple


NODE_PALETTE = [
    "#38BDF8",
    "#A78BFA",
    "#F472B6",
    "#34D399",
    "#FBBF24",
    "#60A5FA",
    "#FB7185",
    "#4ADE80",
    "#F59E0B",
    "#22D3EE",
]

EDGE_PALETTE = [
    "#94A3B8",
    "#A78BFA",
    "#F472B6",
    "#34D399",
    "#FBBF24",
    "#60A5FA",
]

THEMES = {
    "dark": {
        "bg": "#0B0F17",
        "panel": "#0F172A",
        "text": "#E5E7EB",
        "muted": "#94A3B8",
        "outline": "#0B1220",
        "edge": "#64748B",
        "edge_label": "#CBD5E1",
        "selection": "#FBBF24",
        "dim": 0.15,
    },
    "light": {
        "bg": "#F8FAFC",
        "panel": "#FFFFFF",
        "text": "#0F172A",
        "muted": "#475569",
        "outline": "#E2E8F0",
        "edge": "#64748B",
        "edge_label": "#334155",
        "selection": "#F59E0B",
        "dim": 0.2,
    },
}


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in value.strip().lower()).strip("-")


def _color_for_type(type_name: str, palette: List[str]) -> str:
    digest = hashlib.md5(type_name.encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(palette)
    return palette[index]


def apply_theme_to_elements(
    nodes: Iterable[Dict[str, Any]],
    edges: Iterable[Dict[str, Any]],
    theme: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    themed_nodes = []
    themed_edges = []
    node_color_cache: Dict[str, str] = {}
    edge_color_cache: Dict[str, str] = {}

    for node in nodes:
        data = node.get("data", {})
        node_type = data.get("type", "")
        if node_type not in node_color_cache:
            node_color_cache[node_type] = _color_for_type(node_type, NODE_PALETTE)
        color = node_color_cache[node_type]
        themed_node = {**node, "data": {**data, "color": color}}
        themed_node["classes"] = f"node-type-{_slug(node_type)}"
        themed_nodes.append(themed_node)

    for edge in edges:
        data = edge.get("data", {})
        edge_type = data.get("type", "")
        if edge_type not in edge_color_cache:
            edge_color_cache[edge_type] = _color_for_type(edge_type, EDGE_PALETTE)
        color = edge_color_cache[edge_type]
        themed_edge = {**edge, "data": {**data, "color": color}}
        themed_edge["classes"] = f"edge-type-{_slug(edge_type)}"
        themed_edges.append(themed_edge)

    return themed_nodes, themed_edges


def base_stylesheet(
    theme: str,
    scale_node_size: bool,
    scale_edge_width: bool,
    show_edge_labels: bool,
    show_arrows: bool,
) -> List[Dict[str, Any]]:
    tokens = THEMES.get(theme or "", THEMES["dark"])

    node_size = "data(size)" if scale_node_size else "32px"
    edge_width = "data(width)" if scale_edge_width else "2px"
    arrow_shape = "triangle" if show_arrows else "none"
    edge_label = "data(type)" if show_edge_labels else ""

    return [
        {
            "selector": "node",
            "style": {
                "label": "data(label)",
                "font-size": "10px",
                "text-wrap": "wrap",
                "text-max-width": "480px",
                "color": tokens["text"],
                "text-outline-width": 1,
                "text-outline-color": tokens["outline"],
                "width": node_size,
                "height": node_size,
                "background-color": "data(color)",
                "z-index": 9999,
            },
        },
        {
            "selector": "edge",
            "style": {
                "curve-style": "bezier",
                "line-color": "data(color)",
                "target-arrow-color": "data(color)",
                "target-arrow-shape": arrow_shape,
                "arrow-scale": 0.8,
                "opacity": 0.65,
                "label": edge_label,
                "font-size": "9px",
                "color": tokens["edge_label"],
                "width": edge_width,
                "z-index": 5000,
            },
        },
        {
            "selector": ":selected",
            "style": {
                "border-width": 3,
                "border-color": tokens["selection"],
            },
        },
        {
            "selector": ".highlight",
            "style": {
                "border-width": 3,
                "border-color": tokens["selection"],
                "opacity": 1,
            },
        },
        {
            "selector": ".dimmed",
            "style": {
                "opacity": tokens["dim"],
            },
        },
    ]
