from __future__ import annotations

import hashlib
from typing import Dict, List


THEME_TOKENS = {
    "light": {
        "background": "#F8FAFC",
        "panel": "#FFFFFF",
        "panel_border": "#E2E8F0",
        "text": "#0F172A",
        "label": "#0B1220",
        "edge_label": "#334155",
        "selected": "#2563EB",
        "hover": "#60A5FA",
    },
    "dark": {
        "background": "#0B0F17",
        "panel": "#0F172A",
        "panel_border": "#1F2937",
        "text": "#E5E7EB",
        "label": "#F8FAFC",
        "edge_label": "#CBD5E1",
        "selected": "#FBBF24",
        "hover": "#94A3B8",
    },
}

NODE_COLOR_MAP = {
    "document": {"light": "#2563EB", "dark": "#60A5FA"},
    "body": {"light": "#0EA5E9", "dark": "#38BDF8"},
    "page": {"light": "#475569", "dark": "#94A3B8"},
    "section_header": {"light": "#7C3AED", "dark": "#C4B5FD"},
    "heading": {"light": "#7C3AED", "dark": "#C4B5FD"},
    "title": {"light": "#7C3AED", "dark": "#C4B5FD"},
    "paragraph": {"light": "#16A34A", "dark": "#4ADE80"},
    "table": {"light": "#F59E0B", "dark": "#FBBF24"},
    "picture": {"light": "#EC4899", "dark": "#F472B6"},
    "footer": {"light": "#6B7280", "dark": "#9CA3AF"},
    "page_header": {"light": "#0F766E", "dark": "#5EEAD4"},
    "unknown": {"light": "#64748B", "dark": "#94A3B8"},
}

FALLBACK_NODE_COLORS = [
    {"light": "#0EA5E9", "dark": "#7DD3FC"},
    {"light": "#8B5CF6", "dark": "#C4B5FD"},
    {"light": "#10B981", "dark": "#6EE7B7"},
    {"light": "#F97316", "dark": "#FDBA74"},
    {"light": "#E11D48", "dark": "#FDA4AF"},
]

EDGE_COLOR_MAP = {
    "HAS_BODY": {"light": "#1D4ED8", "dark": "#60A5FA"},
    "HAS_PAGE": {"light": "#1E40AF", "dark": "#93C5FD"},
    "CONTAINS": {"light": "#0F172A", "dark": "#E2E8F0"},
    "NEXT": {"light": "#334155", "dark": "#CBD5E1"},
    "ON_PAGE": {"light": "#475569", "dark": "#94A3B8"},
}

EDGE_STYLE_MAP = {
    "HAS_BODY": {"line-style": "solid", "thick": True},
    "HAS_PAGE": {"line-style": "solid", "thick": True},
    "CONTAINS": {"line-style": "solid", "thick": False},
    "NEXT": {"line-style": "dashed", "thick": False},
    "ON_PAGE": {"line-style": "dotted", "thick": False},
}


def normalize_node_type(node_type: str | None) -> str:
    if not node_type:
        return "unknown"
    return str(node_type).strip().lower().replace(" ", "_")


def get_node_colors(node_type: str | None) -> Dict[str, str]:
    normalized = normalize_node_type(node_type)
    if normalized in NODE_COLOR_MAP:
        return NODE_COLOR_MAP[normalized]
    digest = hashlib.md5(normalized.encode("utf-8")).hexdigest()
    index = int(digest[:2], 16) % len(FALLBACK_NODE_COLORS)
    return FALLBACK_NODE_COLORS[index]


def get_edge_colors(edge_type: str | None) -> Dict[str, str]:
    return EDGE_COLOR_MAP.get(edge_type or "", EDGE_COLOR_MAP["CONTAINS"])


def get_edge_style(edge_type: str | None) -> Dict[str, str | bool]:
    return EDGE_STYLE_MAP.get(edge_type or "", EDGE_STYLE_MAP["CONTAINS"])


def get_cytoscape_stylesheet(
    theme: str,
    *,
    node_size: int,
    font_size: int,
    text_max_width: int,
    show_edge_labels: bool,
    scale_node_size: bool,
    scale_edge_width: bool,
    show_arrows: bool,
) -> List[Dict[str, Dict[str, str]]]:
    tokens = THEME_TOKENS[theme]
    node_width = "data(size)" if scale_node_size else f"{node_size}px"
    node_height = "data(size)" if scale_node_size else f"{node_size}px"
    edge_width = "data(width)" if scale_edge_width else 1.5

    arrow_shape = "triangle" if show_arrows else "none"
    arrow_scale = 0.8 if show_arrows else 0

    stylesheet = [
        {
            "selector": "node",
            "style": {
                "label": "data(label)",
                "font-size": f"{font_size}px",
                "text-wrap": "wrap",
                "text-max-width": f"{text_max_width}px",
                "color": tokens["label"],
                "text-outline-width": 1,
                "text-outline-color": tokens["background"],
                "width": node_width,
                "height": node_height,
                "border-width": 1,
                "border-color": tokens["panel_border"],
                "background-color": f"data(color_{theme})",
                "z-index": 9999,
            },
        },
        {
            "selector": "edge",
            "style": {
                "curve-style": "bezier",
                "line-color": tokens["edge_label"],
                "target-arrow-color": tokens["edge_label"],
                "target-arrow-shape": arrow_shape,
                "arrow-scale": arrow_scale,
                "opacity": 0.65,
                "label": "data(rel)" if show_edge_labels else "",
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
                "border-color": tokens["selected"],
            },
        },
        {
            "selector": "node:hover",
            "style": {
                "border-width": 2,
                "border-color": tokens["hover"],
                "shadow-blur": 8,
                "shadow-color": tokens["hover"],
                "shadow-opacity": 0.35,
            },
        },
        {
            "selector": "edge:hover",
            "style": {
                "line-color": tokens["hover"],
                "target-arrow-color": tokens["hover"],
            },
        },
        {
            "selector": ".dimmed",
            "style": {
                "opacity": 0.15,
                "text-opacity": 0.15,
            },
        },
        {
            "selector": ".highlight-edge",
            "style": {
                "line-color": tokens["selected"],
                "target-arrow-color": tokens["selected"],
                "width": 3,
            },
        },
        {
            "selector": ".highlight-node",
            "style": {
                "border-width": 3,
                "border-color": tokens["selected"],
            },
        },
    ]

    for edge_type, colors in EDGE_COLOR_MAP.items():
        edge_style = EDGE_STYLE_MAP.get(edge_type, {})
        style = {
            "line-color": colors[theme],
            "target-arrow-color": colors[theme],
        }
        if edge_style.get("line-style"):
            style["line-style"] = edge_style["line-style"]
        if edge_style.get("thick"):
            style["width"] = "data(width)" if scale_edge_width else 2.5
        stylesheet.append(
            {
                "selector": f'edge[rel = "{edge_type}"]',
                "style": style,
            }
        )

    return stylesheet


def get_theme_tokens(theme: str) -> Dict[str, str]:
    return THEME_TOKENS[theme]


def get_node_legend_items() -> List[Dict[str, str]]:
    return [
        {"label": "Document", "type": "Document"},
        {"label": "Body", "type": "Body"},
        {"label": "Page", "type": "Page"},
        {"label": "Section header", "type": "SECTION_HEADER"},
        {"label": "Heading / Title", "type": "HEADING"},
        {"label": "Paragraph", "type": "PARAGRAPH"},
        {"label": "Table", "type": "TABLE"},
        {"label": "Picture", "type": "PICTURE"},
        {"label": "Footer", "type": "FOOTER"},
        {"label": "Page header", "type": "PAGE_HEADER"},
        {"label": "Unknown", "type": "unknown"},
    ]


def get_edge_legend_items() -> List[Dict[str, str]]:
    return [
        {"label": "HAS_BODY", "type": "HAS_BODY"},
        {"label": "HAS_PAGE", "type": "HAS_PAGE"},
        {"label": "CONTAINS", "type": "CONTAINS"},
        {"label": "NEXT", "type": "NEXT"},
        {"label": "ON_PAGE", "type": "ON_PAGE"},
    ]
