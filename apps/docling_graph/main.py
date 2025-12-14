from __future__ import annotations

import os
import json
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
    return [
        {
            "selector": "node",
            "style": {
                "label": "data(label)",
                "font-size": f"{font_size}px",
                "text-wrap": "wrap",
                "text-max-width": f"{text_max_width}px",
                "color": "#E5E7EB",
                "text-outline-width": 1,
                "text-outline-color": "#0B1220",
                "width": f"{node_size}px",
                "height": f"{node_size}px",
                "z-index": 9999,
            },
        },
        {
            "selector": "edge",
            "style": {
                "curve-style": "bezier",
                "line-color": "#64748B",
                "target-arrow-color": "#64748B",
                "target-arrow-shape": "triangle",
                "arrow-scale": 0.8,
                "opacity": 0.55,
                "label": "data(rel)" if show_edge_labels else "",
                "font-size": "9px",
                "color": "#CBD5E1",
                "z-index": 5000,
            },
        },
        {"selector": ".document", "style": {"background-color": "#1D4ED8"}},
        {"selector": ".section", "style": {"background-color": "#111827"}},
        {"selector": ".item", "style": {"background-color": "#334155"}},
        {"selector": ":selected", "style": {"border-width": 3, "border-color": "#FBBF24"}},
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
                            children=[
                                dcc.Tab(
                                    label="Control Panel",
                                    children=[
                                        html.Div(
                                            style={"padding": "10px"},
                                            children=[
                                                html.Label("Document"),
                                                dcc.Dropdown(
                                                    id="file",
                                                    options=[{"label": f, "value": f} for f in files],
                                                    value=(files[0] if files else None),
                                                    clearable=False,
                                                ),
                                                html.Hr(),

                                                html.Label("Page range"),
                                                dcc.RangeSlider(
                                                    id="page_range",
                                                    min=1,
                                                    max=1,
                                                    step=1,
                                                    value=[1, 1],
                                                    marks={},
                                                    allowCross=False,
                                                ),
                                                html.Hr(),

                                                html.Label("Layout"),
                                                dcc.Dropdown(
                                                    id="layout",
                                                    options=[{"label": l, "value": v} for l, v in LAYOUTS],
                                                    value=DEFAULT_VIEW["layout"],
                                                    clearable=False,
                                                ),

                                                html.Label("Scaling ratio"),
                                                dcc.Slider(
                                                    id="scaling_ratio",
                                                    min=50,
                                                    max=800,
                                                    step=10,
                                                    value=DEFAULT_VIEW["scaling_ratio"],
                                                ),

                                                html.Hr(),
                                                html.Label("Expand"),
                                                dcc.RadioItems(
                                                    id="expand_mode",
                                                    options=[
                                                        {"label": "Children (hier)", "value": "children"},
                                                        {"label": "All outgoing", "value": "out"},
                                                        {"label": "All incoming", "value": "in"},
                                                    ],
                                                    value="children",
                                                ),

                                                html.Hr(),
                                                dcc.Checklist(
                                                    id="edge_labels",
                                                    options=[{"label": " Show edge labels", "value": "on"}],
                                                    value=[],
                                                ),
                                            ],
                                        )
                                    ],
                                ),
                                dcc.Tab(
                                    label="JSON",
                                    children=[
                                        html.Div(
                                            style={"padding": "10px"},
                                            children=[
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


# -------------------------------------------------
# Callbacks
# -------------------------------------------------
@app.callback(
    Output("graph", "elements"),
    Output("store_graph", "data"),
    Output("store_node_index", "data"),
    Input("file", "value"),
)
def load_graph(path):
    if not path:
        return [], None, None

    g = build_graph_from_docling_json(path)

    node_index = {n["data"]["id"]: n for n in g.nodes if n.get("data", {}).get("id")}

    # Genesis node: document
    doc_node = next((n for n in g.nodes if n["data"].get("type") == "document"), None)
    elements = [doc_node] if doc_node else []

    store_graph = {"nodes": g.nodes, "edges": g.edges}

    return elements, store_graph, node_index


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

    g = build_graph_from_docling_json(path)
    pages = pages_from_nodes(g.nodes)
    if not pages:
        return 1, 1, [1, 1], {}

    pmin, pmax = pages[0], pages[-1]
    return pmin, pmax, [pmin, min(pmax, pmin + 3)], {p: str(p) for p in pages if p == pmin or p == pmax or p % 5 == 0}


@app.callback(
    Output("graph", "elements", allow_duplicate=True),
    Input("graph", "tapNodeData"),
    State("graph", "elements"),
    State("store_graph", "data"),
    State("store_node_index", "data"),
    State("expand_mode", "value"),
    prevent_initial_call=True,
)
def expand_on_click(node_data, elements, store_graph, node_index, mode):
    if not node_data or not store_graph:
        return no_update

    node_id = node_data.get("id")
    if not node_id:
        return no_update

    existing_nodes = {e["data"]["id"] for e in elements if "id" in e.get("data", {})}
    existing_edges = {e["data"]["id"] for e in elements if "source" in e.get("data", {})}

    # Prevent re-expansion
    for e in elements:
        if e.get("data", {}).get("id") == node_id and e["data"].get("expanded"):
            return no_update

    for e in elements:
        if e.get("data", {}).get("id") == node_id:
            e["data"]["expanded"] = True

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

        new_edges.append(ed)
        for nid in (src, tgt):
            if nid not in existing_nodes and nid in node_index:
                new_nodes.append(node_index[nid])

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
