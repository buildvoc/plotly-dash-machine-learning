from __future__ import annotations

import hashlib
import os
import json
from pathlib import Path
from dash import Dash, html, dcc, Input, Output, State, no_update
import dash_cytoscape as cyto

from .graph_builder import (
    build_graph_from_docling_json,
    list_docling_files,
    GraphPayload,
)

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Enable stable extra layouts
try:
    cyto.load_extra_layouts()
except Exception:
    pass


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def to_cytoscape_elements(graph: GraphPayload):
    return graph.nodes + graph.edges


def pages_from_nodes(nodes):
    return sorted(
        {
            n.get("data", {}).get("page")
            for n in nodes
            if n.get("data", {}).get("page") is not None
        }
    )


def _source_label(path: str) -> str:
    if not path:
        return "No document selected"

    name = os.path.basename(path)
    try:
        digest = hashlib.md5(Path(path).read_bytes()).hexdigest()[:12]
        return f"{name} · {digest}"
    except OSError:
        return name


def _graph_stats(graph: GraphPayload) -> str:
    return f"{len(graph.nodes)} nodes · {len(graph.edges)} edges"


# -------------------------------------------------
# Layout + Styles (dark-mode, inverted demo)
# -------------------------------------------------
LAYOUTS = [
    ("Dagre (sequence)", "dagre"),
    ("Breadthfirst", "breadthfirst"),
    ("Force-directed (COSE)", "cose"),
    ("COSE-Bilkent", "cose-bilkent"),
    ("Cola (read text)", "cola"),
    ("Euler (quality force)", "euler"),
]


def layout_for(name: str, scaling_ratio: int):
    s = max(50, min(int(scaling_ratio or 250), 800))
    name = name or "dagre"

    if name == "dagre":
        return {
            "name": "dagre",
            "rankDir": "TB",
            "rankSep": int(80 + (s * 0.6)),
            "nodeSep": int(30 + (s * 0.25)),
            "fit": True,
            "padding": 30,
        }

    if name == "cola":
        return {
            "name": "cola",
            "avoidOverlap": True,
            "handleDisconnected": True,
            "nodeSpacing": int(20 + (s * 0.15)),
            "edgeLength": int(60 + (s * 0.35)),
            "flow": {"axis": "y", "minSeparation": 40},
            "fit": True,
            "padding": 30,
        }

    if name in ("cose", "cose-bilkent", "euler"):
        return {
            "name": name,
            "animate": True,
            "randomize": False,
            "idealEdgeLength": int(60 + (s * 0.25)),
            "nodeRepulsion": int(2000 + (s * 12)),
            "gravity": 0.25,
            "numIter": 1000,
            "fit": True,
            "padding": 30,
        }

    return {"name": name, "fit": True, "padding": 30}


def base_stylesheet(node_size, font_size, text_max_width, show_edge_labels):
    palette = {
        "ink": "#0B1020",
        "panel": "#111827",
        "muted": "#94A3B8",
        "text": "#E5E7EB",
        "document": "#7C3AED",
        "section": "#22D3EE",
        "item": "#14B8A6",
        "edge": "#94A3B8",
        "edge_alt": "#A5B4FC",
        "selection": "#FBBF24",
    }

    return [
        {
            "selector": "node",
            "style": {
                "label": "data(label)",
                "font-size": f"{font_size}px",
                "text-wrap": "wrap",
                "text-max-width": f"{text_max_width}px",
                "color": palette["text"],
                "text-outline-width": 1,
                "text-outline-color": palette["ink"],
                "width": f"{node_size}px",
                "height": f"{node_size}px",
                "z-index": 9999,
                "background-color": palette["panel"],
                "border-width": 1.5,
                "border-color": palette["edge_alt"],
            },
        },
        {
            "selector": ".document",
            "style": {
                "background-color": palette["document"],
                "border-color": "#C084FC",
                "shadow-blur": 20,
                "shadow-color": "rgba(124,58,237,0.5)",
            },
        },
        {
            "selector": ".section",
            "style": {
                "background-color": palette["section"],
                "border-color": "#67E8F9",
            },
        },
        {
            "selector": ".item",
            "style": {
                "background-color": palette["item"],
                "border-color": "#5EEAD4",
            },
        },
        {
            "selector": "edge",
            "style": {
                "curve-style": "bezier",
                "line-color": palette["edge"],
                "target-arrow-color": palette["edge"],
                "target-arrow-shape": "triangle",
                "arrow-scale": 0.9,
                "opacity": 0.7,
                "label": "data(rel)" if show_edge_labels else "",
                "font-size": "9px",
                "color": palette["text"],
                "z-index": 5000,
                "width": "mapData(weight, 1, 3, 1.5, 5)",
            },
        },
        {
            "selector": ".hier",
            "style": {
                "line-color": palette["edge_alt"],
                "target-arrow-color": palette["edge_alt"],
            },
        },
        {
            "selector": ":selected",
            "style": {
                "border-width": 3,
                "border-color": palette["selection"],
                "line-color": palette["selection"],
                "target-arrow-color": palette["selection"],
                "text-outline-color": palette["ink"],
            },
        },
    ]


# -------------------------------------------------
# App + Defaults
# -------------------------------------------------
files = list_docling_files()

DEFAULT_VIEW = {
    "layout": "dagre",
    "scaling_ratio": 250,
    "node_size": 22,
    "font_size": 10,
    "text_max_width": 520,
    "show_edge_labels": False,
}

app = Dash(
    __name__,
    title="Docling Graph Viewer",
    assets_folder=os.path.join(APP_DIR, "assets"),
)
server = app.server


# -------------------------------------------------
# Layout (demo-style + stores)
# -------------------------------------------------
app.layout = html.Div(
    children=[
        dcc.Store(id="store_graph"),
        dcc.Store(id="store_node_index"),

        html.Div(
            className="row",
            children=[
                # LEFT — Graph
                html.Div(
                    className="eight columns",
                    children=[
                        cyto.Cytoscape(
                            id="graph",
                            style={
                                "width": "100%",
                                "height": "85vh",
                                "backgroundColor": "#0B0F17",
                            },
                            wheelSensitivity=0.01,
                            minZoom=0.25,
                            maxZoom=2.0,
                            layout=layout_for(
                                DEFAULT_VIEW["layout"],
                                DEFAULT_VIEW["scaling_ratio"],
                            ),
                            stylesheet=base_stylesheet(
                                DEFAULT_VIEW["node_size"],
                                DEFAULT_VIEW["font_size"],
                                DEFAULT_VIEW["text_max_width"],
                                DEFAULT_VIEW["show_edge_labels"],
                            ),
                            elements=[],
                        )
                    ],
                ),

                # RIGHT — Control Panel
                html.Div(
                    className="four columns",
                    children=[
                        dcc.Tabs(
                            className="control-tabs",
                            colors={
                                "border": "#111827",
                                "primary": "#7c3aed",
                                "background": "#0b0f17",
                            },
                            children=[
                                dcc.Tab(
                                    className="control-tab",
                                    selected_className="control-tab--selected",
                                    label="Control Panel",
                                    children=[
                                        html.Div(
                                            className="control-panel",
                                            children=[
                                                html.Div(
                                                    className="control-panel__header",
                                                    children=[
                                                        html.Div("Graph controls", className="control-title"),
                                                        html.Span("Dark mode", className="pill pill--invert"),
                                                    ],
                                                ),
                                                html.Div(
                                                    className="control-section",
                                                    children=[
                                                        html.Div("Document", className="control-label"),
                                                        dcc.Dropdown(
                                                            id="file",
                                                            options=[{"label": f, "value": f} for f in files],
                                                            value=(files[0] if files else None),
                                                            clearable=False,
                                                        ),
                                                        html.Div(
                                                            id="data_source_label",
                                                            className="control-subtext",
                                                        ),
                                                        html.Div(
                                                            id="graph_counts",
                                                            className="control-subtext",
                                                        ),
                                                    ],
                                                ),
                                                html.Div(
                                                    className="control-section",
                                                    children=[
                                                        html.Div("Page range", className="control-label"),
                                                        dcc.RangeSlider(
                                                            id="page_range",
                                                            min=1,
                                                            max=1,
                                                            step=1,
                                                            value=[1, 1],
                                                            marks={},
                                                            allowCross=False,
                                                        ),
                                                        html.Div(
                                                            id="page_range_value",
                                                            className="control-subtext",
                                                        ),
                                                    ],
                                                ),
                                                html.Div(
                                                    className="control-section",
                                                    children=[
                                                        html.Div("Layout", className="control-label"),
                                                        dcc.Dropdown(
                                                            id="layout",
                                                            options=[{"label": l, "value": v} for l, v in LAYOUTS],
                                                            value=DEFAULT_VIEW["layout"],
                                                            clearable=False,
                                                        ),
                                                    ],
                                                ),
                                                html.Div(
                                                    className="control-section",
                                                    children=[
                                                        html.Div("Scaling ratio", className="control-label"),
                                                        dcc.Slider(
                                                            id="scaling_ratio",
                                                            min=50,
                                                            max=800,
                                                            step=10,
                                                            value=DEFAULT_VIEW["scaling_ratio"],
                                                        ),
                                                    ],
                                                ),
                                                html.Div(
                                                    className="control-section",
                                                    children=[
                                                        html.Div("Expand", className="control-label"),
                                                        dcc.RadioItems(
                                                            id="expand_mode",
                                                            options=[
                                                                {"label": "Children (hier)", "value": "children"},
                                                                {"label": "All outgoing", "value": "out"},
                                                                {"label": "All incoming", "value": "in"},
                                                            ],
                                                            value="children",
                                                            inputClassName="control-radio",
                                                            labelClassName="control-radio__label",
                                                        ),
                                                    ],
                                                ),
                                                html.Div(
                                                    className="control-section control-section--tight",
                                                    children=[
                                                        dcc.Checklist(
                                                            id="edge_labels",
                                                            options=[{"label": " Show edge labels", "value": "on"}],
                                                            value=[],
                                                            inputClassName="control-checkbox",
                                                            labelClassName="control-checkbox__label",
                                                        ),
                                                    ],
                                                ),
                                            ],
                                        )
                                    ],
                                ),
                                dcc.Tab(
                                    className="control-tab",
                                    selected_className="control-tab--selected",
                                    label="JSON",
                                    children=[
                                        html.Div(
                                            className="control-panel control-panel--secondary",
                                            children=[
                                                html.Div(
                                                    className="control-panel__header",
                                                    children=[
                                                        html.Div("Click to inspect", className="control-title"),
                                                        html.Span("debug", className="pill"),
                                                    ],
                                                ),
                                                html.Pre(id="tap-node-json-output", style={"height": "35vh", "overflowY": "auto"}),
                                                html.Pre(id="tap-edge-json-output", style={"height": "35vh", "overflowY": "auto"}),
                                            ],
                                        )
                                    ],
                                ),
                            ]
                        )
                    ],
                ),
            ],
        ),
    ]
)
def load_graph(path):
    if not path:
        return [], None, None, "No document selected", ""

    try:
        g = build_graph_from_docling_json(path)
    except ValueError as exc:
        return [], None, None, f"Error: {exc}", ""

    node_index = {n["data"]["id"]: n for n in g.nodes if n.get("data", {}).get("id")}

    # Genesis node: document
    doc_node = next((n for n in g.nodes if n["data"].get("type") == "document"), None)
    elements = [doc_node] if doc_node else []

    store_graph = {"nodes": g.nodes, "edges": g.edges}

    return elements, store_graph, node_index, _source_label(path), _graph_stats(g)


# -------------------------------------------------
# Callbacks
# -------------------------------------------------
@app.callback(
    Output("graph", "elements"),
    Output("store_graph", "data"),
    Output("store_node_index", "data"),
    Output("data_source_label", "children"),
    Output("graph_counts", "children"),
    Input("file", "value"),
)
def load_graph(path):
    if not path:
        return [], None, None, "No document selected", ""

    try:
        g = build_graph_from_docling_json(path)
    except ValueError as exc:
        return [], None, None, f"Error: {exc}", ""

    node_index = {n["data"]["id"]: n for n in g.nodes if n.get("data", {}).get("id")}

    # Genesis node: document
    doc_node = next((n for n in g.nodes if n["data"].get("type") == "document"), None)
    elements = [doc_node] if doc_node else []

    store_graph = {"nodes": g.nodes, "edges": g.edges}

    return elements, store_graph, node_index, _source_label(path), _graph_stats(g)


@app.callback(
    Output("page_range", "min"),
    Output("page_range", "max"),
    Output("page_range", "value"),
    Output("page_range", "marks"),
    Input("file", "value"),
)
def init_page_range(path):
    if not path:
        return 1, 1, [1, 1], {}

    try:
        g = build_graph_from_docling_json(path)
    except ValueError:
        return 1, 1, [1, 1], {}

    pages = pages_from_nodes(g.nodes)
    if not pages:
        return 1, 1, [1, 1], {}

    pmin, pmax = pages[0], pages[-1]
    return pmin, pmax, [pmin, min(pmax, pmin + 3)], {p: str(p) for p in pages if p == pmin or p == pmax or p % 5 == 0}


@app.callback(Output("page_range_value", "children"), Input("page_range", "value"))
def show_page_range(value):
    if not value:
        return ""

    start, end = value
    if start == end:
        return f"Showing page {start}"

    return f"Showing pages {start} to {end}"


@app.callback(
    Output("graph", "elements", allow_duplicate=True),
    Input("graph", "tapNodeData"),
    State("graph", "elements"),
    State("store_graph", "data"),
    State("store_node_index", "data"),
    State("expand_mode", "value"),
    State("page_range", "value"),
    prevent_initial_call=True,
)
def expand_on_click(node_data, elements, store_graph, node_index, mode, page_range):
    if not node_data or not store_graph or not page_range:
        return no_update

    node_id = node_data.get("id")
    if not node_id:
        return no_update

    start_page, end_page = page_range

    def in_range(page):
        return page is None or (start_page <= page <= end_page)

    existing_nodes = {e["data"]["id"] for e in elements if "id" in e.get("data", {})}
    existing_edges = {e["data"]["id"] for e in elements if "source" in e.get("data", {})}

    tapped_element = next((e for e in elements if e.get("data", {}).get("id") == node_id), None)
    is_expanded = bool(tapped_element and tapped_element.get("data", {}).get("expanded"))

    def matches_mode(edge_data):
        src, tgt = edge_data.get("source"), edge_data.get("target")

        if mode == "children":
            return src == node_id
        if mode == "out":
            return src == node_id
        if mode == "in":
            return tgt == node_id

        return False

    if is_expanded:
        # Contract: remove connected edges for the active mode and any orphaned nodes
        remaining_edges = [
            el
            for el in elements
            if "source" not in el.get("data", {}) or not matches_mode(el["data"])
        ]

        # Rebuild adjacency from remaining edges
        connected_nodes = set()
        for el in remaining_edges:
            data = el.get("data", {})
            if "source" in data:
                connected_nodes.add(data.get("source"))
                connected_nodes.add(data.get("target"))

        contracted_elements = []
        for el in remaining_edges:
            data = el.get("data", {})
            if "source" in data:
                contracted_elements.append(el)
                continue

            nid = data.get("id")
            if nid == node_id:
                el["data"]["expanded"] = False
                contracted_elements.append(el)
                continue

            # Keep the root document and any node still connected
            if data.get("type") == "document" or nid in connected_nodes:
                contracted_elements.append(el)

        return contracted_elements

    if tapped_element:
        tapped_element["data"]["expanded"] = True

    new_nodes = []
    new_edges = []

    for ed in store_graph["edges"]:
        d = ed["data"]
        src, tgt, rel = d.get("source"), d.get("target"), d.get("rel")

        if mode == "children" and not (rel == "hier" and src == node_id):
            continue
        if mode == "out" and src != node_id:
            continue
        if mode == "in" and tgt != node_id:
            continue

        if d["id"] in existing_edges:
            continue

        for nid in (src, tgt):
            if nid not in existing_nodes and nid in node_index:
                candidate = node_index[nid]
                if in_range(candidate.get("data", {}).get("page")):
                    new_nodes.append(candidate)

        if not in_range(node_index.get(src, {}).get("data", {}).get("page")):
            continue
        if not in_range(node_index.get(tgt, {}).get("data", {}).get("page")):
            continue

        new_edges.append(ed)

    if not new_nodes and not new_edges:
        return no_update

    return elements + new_nodes + new_edges


@app.callback(
    Output("graph", "layout"),
    Input("layout", "value"),
    Input("scaling_ratio", "value"),
)
def update_layout(name, scaling):
    return layout_for(name, scaling)


@app.callback(
    Output("graph", "elements", allow_duplicate=True),
    Input("page_range", "value"),
    State("graph", "elements"),
    prevent_initial_call=True,
)
def filter_elements_by_page(page_range, elements):
    if not page_range or not elements:
        return no_update

    start_page, end_page = page_range
    allowed_nodes = set()
    filtered_nodes = []

    for el in elements:
        data = el.get("data", {})
        if "source" in data:
            continue

        page = data.get("page")
        if page is None or (start_page <= page <= end_page):
            allowed_nodes.add(data.get("id"))
            filtered_nodes.append(el)

    filtered_edges = [
        el
        for el in elements
        if "source" in el.get("data", {})
        and el["data"].get("source") in allowed_nodes
        and el["data"].get("target") in allowed_nodes
    ]

    return filtered_nodes + filtered_edges


@app.callback(
    Output("graph", "stylesheet"),
    Input("edge_labels", "value"),
)
def update_styles(edge_labels):
    return base_stylesheet(
        DEFAULT_VIEW["node_size"],
        DEFAULT_VIEW["font_size"],
        DEFAULT_VIEW["text_max_width"],
        "on" in (edge_labels or []),
    )


@app.callback(
    Output("tap-node-json-output", "children"),
    Input("graph", "tapNode"),
)
def show_node(data):
    return json.dumps(data, indent=2)


@app.callback(
    Output("tap-edge-json-output", "children"),
    Input("graph", "tapEdge"),
)
def show_edge(data):
    return json.dumps(data, indent=2)


# -------------------------------------------------
# Run
# -------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050)
