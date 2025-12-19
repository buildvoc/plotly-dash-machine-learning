from __future__ import annotations

import os
import json
import csv
import io
import zipfile
from xml.sax.saxutils import escape
from dash import Dash, html, dcc, Input, Output, State, no_update, ALL
import dash_cytoscape as cyto
import dash

from .graph_builder import (
    build_adjacency_indexes,
    build_graph_from_docling_json,
    expand_group,
    filter_revealed,
    group_key,
    initial_reveal,
    list_docling_files,
    GraphPayload,
)
from .theme import (
    get_cytoscape_stylesheet,
    get_edge_colors,
    get_edge_style,
    get_edge_legend_items,
    get_node_colors,
    get_node_legend_items,
    get_theme_tokens,
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


def _build_edge_index(edges):
    return {e["data"]["id"]: e for e in edges if e.get("data", {}).get("id")}


def _build_elements(nodes, edges, node_ids, edge_ids):
    node_map = {n["data"]["id"]: n for n in nodes if n.get("data", {}).get("id")}
    edge_map = {e["data"]["id"]: e for e in edges if e.get("data", {}).get("id")}
    elements = [node_map[nid] for nid in node_ids if nid in node_map]
    elements.extend(edge_map[eid] for eid in edge_ids if eid in edge_map)
    return elements


def _direction_label(direction: str) -> str:
    return "→" if direction == "out" else "←"


def _group_edges(adjacency, node_id: str, direction: str, edge_type: str):
    if not adjacency:
        return []
    index = adjacency.get("out") if direction == "out" else adjacency.get("in")
    return index.get(node_id, {}).get(edge_type, [])

# -------------------------------------------------
# Layout + Styles (dark-mode, inverted demo)
# -------------------------------------------------
LAYOUTS = [
    ("Dagre (sequence)", "dagre"),
    ("Breadthfirst", "breadthfirst"),
    ("Force-directed (COSE)", "cose"),
    ("COSE-Bilkent", "cose-bilkent"),
    ("fCoSE", "fcose"),
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

    if name in ("cose", "cose-bilkent", "euler", "fcose"):
        return {
            "name": name,
            "animate": True,
            "randomize": False,
            "idealEdgeLength": "data(edge_length)" if name in ("cose-bilkent", "fcose") else int(60 + (s * 0.25)),
            "nodeRepulsion": int(2000 + (s * 12)),
            "gravity": 0.25,
            "numIter": 1000,
            "fit": True,
            "padding": 30,
        }

    return {"name": name, "fit": True, "padding": 30}


GRAPH_BASE_STYLE = {
    "width": "100%",
    "height": "85vh",
}

DEFAULT_BATCH_SIZE = 10


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
    "theme": "dark",
    "scale_node_size": True,
    "scale_edge_width": True,
    "min_node_weight": 1,
    "min_edge_weight": 1,
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
        dcc.Store(id="store_adjacency"),
        dcc.Store(id="store_revealed"),
        dcc.Store(id="store_paging"),
        dcc.Store(id="store_selected"),
        dcc.Download(id="download_csv"),
        dcc.Download(id="download_xlsx"),

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
                                **GRAPH_BASE_STYLE,
                                "backgroundColor": get_theme_tokens(DEFAULT_VIEW["theme"])["background"],
                            },
                            wheelSensitivity=0.01,
                            minZoom=0.25,
                            maxZoom=2.0,
                            layout=layout_for(
                                DEFAULT_VIEW["layout"],
                                DEFAULT_VIEW["scaling_ratio"],
                            ),
                            stylesheet=get_cytoscape_stylesheet(
                                DEFAULT_VIEW["theme"],
                                node_size=DEFAULT_VIEW["node_size"],
                                font_size=DEFAULT_VIEW["font_size"],
                                text_max_width=DEFAULT_VIEW["text_max_width"],
                                show_edge_labels=DEFAULT_VIEW["show_edge_labels"],
                                scale_node_size=DEFAULT_VIEW["scale_node_size"],
                                scale_edge_width=DEFAULT_VIEW["scale_edge_width"],
                                show_arrows=True,
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
                                                        html.Div("Theme", className="control-label"),
                                                        dcc.RadioItems(
                                                            id="theme",
                                                            options=[
                                                                {"label": "Light", "value": "light"},
                                                                {"label": "Dark", "value": "dark"},
                                                            ],
                                                            value=DEFAULT_VIEW["theme"],
                                                            inputClassName="control-radio",
                                                            labelClassName="control-radio__label",
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
                                                        html.Div("Filters", className="control-label"),
                                                        dcc.Dropdown(
                                                            id="node_type_filter",
                                                            multi=True,
                                                            placeholder="Filter node types",
                                                        ),
                                                        dcc.Dropdown(
                                                            id="edge_type_filter",
                                                            multi=True,
                                                            placeholder="Filter edge types",
                                                        ),
                                                        dcc.Dropdown(
                                                            id="node_search",
                                                            placeholder="Search node by name",
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
                                                html.Div(
                                                    className="control-section control-section--tight",
                                                    children=[
                                                        dcc.Checklist(
                                                            id="view_toggles",
                                                            options=[
                                                                {"label": " Show arrows", "value": "arrows"},
                                                                {"label": " Focus mode", "value": "focus"},
                                                                {"label": " Hide Page nodes", "value": "hide_pages"},
                                                                {"label": " Hide isolated nodes", "value": "hide_isolated"},
                                                            ],
                                                            value=["arrows"],
                                                            inputClassName="control-checkbox",
                                                            labelClassName="control-checkbox__label",
                                                        ),
                                                    ],
                                                ),
                                                html.Div(
                                                    className="control-section",
                                                    children=[
                                                        html.Div("Weights", className="control-label"),
                                                        dcc.Checklist(
                                                            id="weight_toggles",
                                                            options=[
                                                                {"label": " Scale node size by weight", "value": "node"},
                                                                {"label": " Scale edge width by weight", "value": "edge"},
                                                                {"label": " Keep context when filtering", "value": "context"},
                                                            ],
                                                            value=["node", "edge"],
                                                            inputClassName="control-checkbox",
                                                            labelClassName="control-checkbox__label",
                                                        ),
                                                    ],
                                                ),
                                                html.Div(
                                                    className="control-section",
                                                    children=[
                                                        html.Div("Min node weight", className="control-label"),
                                                        dcc.Slider(
                                                            id="min_node_weight",
                                                            min=1,
                                                            max=15,
                                                            step=0.5,
                                                            value=DEFAULT_VIEW["min_node_weight"],
                                                        ),
                                                    ],
                                                ),
                                                html.Div(
                                                    className="control-section",
                                                    children=[
                                                        html.Div("Min edge weight", className="control-label"),
                                                        dcc.Slider(
                                                            id="min_edge_weight",
                                                            min=1,
                                                            max=10,
                                                            step=1,
                                                            value=DEFAULT_VIEW["min_edge_weight"],
                                                        ),
                                                    ],
                                                ),
                                                html.Div(
                                                    className="control-section",
                                                    children=[
                                                        html.Div("Exports", className="control-label"),
                                                        html.Button("Download CSV", id="export_csv", className="control-button"),
                                                        html.Button("Download XLSX", id="export_xlsx", className="control-button"),
                                                    ],
                                                ),
                                                html.Div(
                                                    className="control-section",
                                                    children=[
                                                        html.Button("Reset view", id="reset_view", className="control-button"),
                                                    ],
                                                ),
                                                html.Div(
                                                    className="control-section",
                                                    children=[
                                                        html.Div("Hover details", className="control-label"),
                                                        html.Pre(id="hover-node-output", style={"whiteSpace": "pre-wrap"}),
                                                        html.Pre(id="hover-edge-output", style={"whiteSpace": "pre-wrap"}),
                                                    ],
                                                ),
                                                html.Div(
                                                    className="control-section",
                                                    children=[
                                                        html.Div("Inspector", className="control-label"),
                                                        html.Div(id="inspector_panel"),
                                                    ],
                                                ),
                                                html.Details(
                                                    id="legend_container",
                                                    open=True,
                                                    children=[],
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


# -------------------------------------------------
# Callbacks
# -------------------------------------------------
@app.callback(
    Output("graph", "elements"),
    Output("store_graph", "data"),
    Output("store_node_index", "data"),
    Output("store_adjacency", "data"),
    Output("store_revealed", "data"),
    Output("store_paging", "data"),
    Output("store_selected", "data"),
    Output("node_type_filter", "options"),
    Output("edge_type_filter", "options"),
    Output("node_search", "options"),
    Input("file", "value"),
)
def load_graph(path):
    if not path:
        return [], None, None, None, None, None, None, [], [], []

    g = build_graph_from_docling_json(path)

    node_index = {n["data"]["id"]: n for n in g.nodes if n.get("data", {}).get("id")}
    out_index, in_index = build_adjacency_indexes(g.edges)
    revealed_nodes, revealed_edges, paging, core_nodes = initial_reveal(
        node_index,
        out_index,
        DEFAULT_BATCH_SIZE,
    )
    store_revealed = {
        "nodes": list(revealed_nodes),
        "edges": list(revealed_edges),
        "core_nodes": list(core_nodes),
    }

    elements = _build_elements(g.nodes, g.edges, revealed_nodes, revealed_edges)

    store_graph = {"nodes": g.nodes, "edges": g.edges}
    store_adjacency = {"out": out_index, "in": in_index}

    node_types = sorted({n["data"].get("type") for n in g.nodes if n.get("data")})
    edge_types = sorted({e["data"].get("rel") for e in g.edges if e.get("data")})
    node_type_options = [{"label": t, "value": t} for t in node_types if t]
    edge_type_options = [{"label": t, "value": t} for t in edge_types if t]
    search_options = [
        {"label": f'{n["data"].get("name")} ({n["data"].get("type")})', "value": n["data"]["id"]}
        for n in g.nodes
        if n.get("data", {}).get("name")
    ]

    return (
        elements,
        store_graph,
        node_index,
        store_adjacency,
        store_revealed,
        paging,
        None,
        node_type_options,
        edge_type_options,
        search_options,
    )


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


@app.callback(Output("page_range_value", "children"), Input("page_range", "value"))
def show_page_range(value):
    if not value:
        return ""

    start, end = value
    if start == end:
        return f"Showing page {start}"

    return f"Showing pages {start} to {end}"


@app.callback(
    Output("graph", "layout"),
    Input("layout", "value"),
    Input("scaling_ratio", "value"),
)
def update_layout(name, scaling):
    return layout_for(name, scaling)


@app.callback(
    Output("graph", "elements", allow_duplicate=True),
    Input("store_graph", "data"),
    Input("store_node_index", "data"),
    Input("store_revealed", "data"),
    Input("store_selected", "data"),
    Input("node_type_filter", "value"),
    Input("edge_type_filter", "value"),
    Input("page_range", "value"),
    Input("min_node_weight", "value"),
    Input("min_edge_weight", "value"),
    Input("weight_toggles", "value"),
    Input("view_toggles", "value"),
    prevent_initial_call=True,
)
def update_elements(
    store_graph,
    node_index,
    store_revealed,
    selected_node_id,
    node_type_filter,
    edge_type_filter,
    page_range,
    min_node_weight,
    min_edge_weight,
    weight_toggles,
    view_toggles,
):
    if not store_graph or not node_index or not store_revealed:
        return no_update

    revealed_nodes = set(store_revealed.get("nodes", []))
    revealed_edges = set(store_revealed.get("edges", []))
    edge_index = _build_edge_index(store_graph.get("edges", []))

    node_types = set(node_type_filter or []) or None
    edge_types = set(edge_type_filter or []) or None
    keep_context = "context" in (weight_toggles or [])
    hide_pages = "hide_pages" in (view_toggles or [])
    hide_isolated = "hide_isolated" in (view_toggles or [])
    page_bounds = tuple(page_range) if page_range else None

    filtered_nodes, filtered_edges = filter_revealed(
        revealed_nodes,
        revealed_edges,
        node_index,
        edge_index,
        node_types=node_types,
        edge_types=edge_types,
        hide_pages=hide_pages,
        hide_isolated=hide_isolated,
        page_range=page_bounds,
        min_node_weight=float(min_node_weight or 0),
        min_edge_weight=float(min_edge_weight or 0),
        keep_context=keep_context,
    )

    elements = _build_elements(store_graph.get("nodes", []), store_graph.get("edges", []), filtered_nodes, filtered_edges)

    if selected_node_id:
        incident_edges = set()
        neighbor_nodes = {selected_node_id}
        for edge_id in filtered_edges:
            edge = edge_index.get(edge_id, {})
            data = edge.get("data", {})
            source = data.get("source")
            target = data.get("target")
            if selected_node_id in (source, target):
                incident_edges.add(edge_id)
                neighbor_nodes.update([source, target])

        focus_mode = "focus" in (view_toggles or [])

        updated = []
        for el in elements:
            data = el.get("data", {})
            classes = el.get("classes", "")
            if "source" in data:
                if data.get("id") in incident_edges:
                    classes = f"{classes} highlight-edge".strip()
                elif focus_mode:
                    classes = f"{classes} dimmed".strip()
            else:
                if data.get("id") == selected_node_id:
                    el = {**el, "selected": True}
                    classes = f"{classes} highlight-node".strip()
                elif focus_mode and data.get("id") not in neighbor_nodes:
                    classes = f"{classes} dimmed".strip()
            updated.append({**el, "classes": classes})
        elements = updated

    return elements


@app.callback(
    Output("store_selected", "data"),
    Input("graph", "tapNodeData"),
    prevent_initial_call=True,
)
def select_node_from_graph(node_data):
    if not node_data:
        return no_update
    return node_data.get("id") or no_update


@app.callback(
    Output("store_selected", "data", allow_duplicate=True),
    Output("store_revealed", "data", allow_duplicate=True),
    Input("node_search", "value"),
    State("store_revealed", "data"),
    State("store_graph", "data"),
    prevent_initial_call=True,
)
def select_node_from_search(node_id, store_revealed, store_graph):
    if not node_id or not store_revealed or not store_graph:
        return no_update, no_update

    revealed_nodes = set(store_revealed.get("nodes", []))
    revealed_edges = set(store_revealed.get("edges", []))
    if node_id not in revealed_nodes:
        revealed_nodes.add(node_id)
        edge_index = _build_edge_index(store_graph.get("edges", []))
        for edge in edge_index.values():
            data = edge.get("data", {})
            if node_id in (data.get("source"), data.get("target")):
                revealed_edges.add(data.get("id"))
                revealed_nodes.update([data.get("source"), data.get("target")])

    store_revealed = {
        **store_revealed,
        "nodes": list(revealed_nodes),
        "edges": list(revealed_edges),
    }
    return node_id, store_revealed


@app.callback(
    Output("store_revealed", "data"),
    Output("store_paging", "data"),
    Output("store_selected", "data"),
    Input("reset_view", "n_clicks"),
    State("store_node_index", "data"),
    State("store_adjacency", "data"),
    prevent_initial_call=True,
)
def reset_view(n_clicks, node_index, adjacency):
    if not n_clicks or not node_index or not adjacency:
        return no_update, no_update, no_update

    revealed_nodes, revealed_edges, paging, core_nodes = initial_reveal(
        node_index,
        adjacency.get("out", {}),
        DEFAULT_BATCH_SIZE,
    )
    return (
        {"nodes": list(revealed_nodes), "edges": list(revealed_edges), "core_nodes": list(core_nodes)},
        paging,
        None,
    )


@app.callback(
    Output("store_revealed", "data", allow_duplicate=True),
    Output("store_paging", "data", allow_duplicate=True),
    Input({"type": "expand-group", "node_id": ALL, "direction": ALL, "edge_type": ALL}, "n_clicks"),
    Input({"type": "collapse-group", "node_id": ALL, "direction": ALL, "edge_type": ALL}, "n_clicks"),
    State("store_revealed", "data"),
    State("store_paging", "data"),
    State("store_adjacency", "data"),
    State("store_graph", "data"),
    prevent_initial_call=True,
)
def update_group_reveal(_, __, store_revealed, store_paging, adjacency, store_graph):
    if not store_revealed or not adjacency or not store_graph:
        return no_update, no_update

    ctx = dash.callback_context
    if not ctx.triggered_id:
        return no_update, no_update

    trigger = ctx.triggered_id
    node_id = trigger.get("node_id")
    direction = trigger.get("direction")
    edge_type = trigger.get("edge_type")
    if not node_id or not direction or not edge_type:
        return no_update, no_update

    revealed_nodes = set(store_revealed.get("nodes", []))
    revealed_edges = set(store_revealed.get("edges", []))
    paging = dict(store_paging or {})
    key = group_key(node_id, direction, edge_type)
    current_offset = int(paging.get(key, 0))

    if trigger.get("type") == "expand-group":
        revealed_nodes, revealed_edges, next_offset = expand_group(
            revealed_nodes,
            revealed_edges,
            adjacency.get("out", {}),
            adjacency.get("in", {}),
            node_id,
            direction,
            edge_type,
            current_offset,
            DEFAULT_BATCH_SIZE,
        )
        paging[key] = next_offset
    else:
        new_offset = max(0, current_offset - DEFAULT_BATCH_SIZE)
        edges = _group_edges(adjacency, node_id, direction, edge_type)
        removed_edge_ids = {entry["edge_id"] for entry in edges[new_offset:current_offset]}
        revealed_edges -= removed_edge_ids

        edge_index = _build_edge_index(store_graph.get("edges", []))
        remaining_nodes = set(store_revealed.get("core_nodes", []))
        for edge_id in revealed_edges:
            data = edge_index.get(edge_id, {}).get("data", {})
            remaining_nodes.update([data.get("source"), data.get("target")])

        revealed_nodes = {nid for nid in revealed_nodes if nid in remaining_nodes}
        paging[key] = new_offset

    return (
        {**store_revealed, "nodes": list(revealed_nodes), "edges": list(revealed_edges)},
        paging,
    )


@app.callback(
    Output("store_selected", "data", allow_duplicate=True),
    Output("store_revealed", "data", allow_duplicate=True),
    Input({"type": "select-node", "node_id": ALL}, "n_clicks"),
    State("store_revealed", "data"),
    State("store_graph", "data"),
    prevent_initial_call=True,
)
def select_node_from_inspector(_, store_revealed, store_graph):
    ctx = dash.callback_context
    if not ctx.triggered_id or not store_revealed or not store_graph:
        return no_update, no_update
    node_id = ctx.triggered_id.get("node_id")
    if not node_id:
        return no_update, no_update

    revealed_nodes = set(store_revealed.get("nodes", []))
    revealed_edges = set(store_revealed.get("edges", []))
    if node_id not in revealed_nodes:
        revealed_nodes.add(node_id)
        edge_index = _build_edge_index(store_graph.get("edges", []))
        for edge in edge_index.values():
            data = edge.get("data", {})
            if node_id in (data.get("source"), data.get("target")):
                revealed_edges.add(data.get("id"))
                revealed_nodes.update([data.get("source"), data.get("target")])

    updated_revealed = {**store_revealed, "nodes": list(revealed_nodes), "edges": list(revealed_edges)}
    return node_id, updated_revealed


@app.callback(
    Output("graph", "stylesheet"),
    Input("edge_labels", "value"),
    Input("weight_toggles", "value"),
    Input("view_toggles", "value"),
    Input("theme", "value"),
)
def update_styles(edge_labels, weight_toggles, view_toggles, theme):
    weight_toggles = weight_toggles or []
    return get_cytoscape_stylesheet(
        theme or DEFAULT_VIEW["theme"],
        node_size=DEFAULT_VIEW["node_size"],
        font_size=DEFAULT_VIEW["font_size"],
        text_max_width=DEFAULT_VIEW["text_max_width"],
        show_edge_labels="on" in (edge_labels or []),
        scale_node_size="node" in weight_toggles,
        scale_edge_width="edge" in weight_toggles,
        show_arrows="arrows" in (view_toggles or []),
    )


@app.callback(
    Output("graph", "style"),
    Input("theme", "value"),
)
def update_graph_style(theme):
    tokens = get_theme_tokens(theme or DEFAULT_VIEW["theme"])
    return {
        **GRAPH_BASE_STYLE,
        "backgroundColor": tokens["background"],
    }


def build_legend(theme: str):
    tokens = get_theme_tokens(theme)
    node_items = []
    for item in get_node_legend_items():
        colors = get_node_colors(item["type"])
        node_items.append(
            html.Div(
                className="legend-row",
                children=[
                    html.Span(className="legend-swatch", style={"backgroundColor": colors[theme]}),
                    html.Span(item["label"], className="legend-label"),
                ],
            )
        )

    edge_items = []
    for item in get_edge_legend_items():
        colors = get_edge_colors(item["type"])
        edge_style = get_edge_style(item["type"])
        edge_items.append(
            html.Div(
                className="legend-row",
                children=[
                    html.Span(
                        className="legend-line",
                        style={
                            "borderColor": colors[theme],
                            "borderStyle": edge_style.get("line-style", "solid"),
                            "borderWidth": "3px" if edge_style.get("thick") else "2px",
                        },
                    ),
                    html.Span(item["label"], className="legend-label"),
                ],
            )
        )

    return [
        html.Summary("Legend", className="legend-summary"),
        html.Div(
            className="legend-body",
            children=[
                html.Div("Node Types", className="legend-title"),
                html.Div(node_items, className="legend-list"),
                html.Div("Edge Types", className="legend-title"),
                html.Div(edge_items, className="legend-list"),
            ],
        ),
    ]


@app.callback(
    Output("legend_container", "children"),
    Output("legend_container", "style"),
    Input("theme", "value"),
)
def update_legend(theme):
    tokens = get_theme_tokens(theme or DEFAULT_VIEW["theme"])
    style = {
        "backgroundColor": tokens["panel"],
        "color": tokens["text"],
        "border": f"1px solid {tokens['panel_border']}",
    }
    return build_legend(theme or DEFAULT_VIEW["theme"]), style


def _filter_edge_entries(
    entries,
    node_index,
    edge_types,
    node_types,
    hide_pages,
    page_range,
    min_node_weight,
    min_edge_weight,
    direction,
):
    filtered = []
    for entry in entries:
        edge_type = entry.get("type")
        if edge_types and edge_type not in edge_types:
            continue
        if min_edge_weight is not None and float(entry.get("weight") or 0) < min_edge_weight:
            continue
        neighbor_id = entry.get("target") if direction == "out" else entry.get("source")
        neighbor = node_index.get(neighbor_id, {})
        data = neighbor.get("data", {})
        node_type = data.get("type")
        if node_types and node_type not in node_types:
            continue
        if hide_pages and node_type == "Page":
            continue
        if page_range and data.get("page") is not None:
            if not (page_range[0] <= data.get("page") <= page_range[1]):
                continue
        if min_node_weight is not None and float(data.get("weight") or 0) < min_node_weight:
            continue
        filtered.append({**entry, "neighbor_id": neighbor_id})
    return filtered


@app.callback(
    Output("inspector_panel", "children"),
    Output("inspector_panel", "style"),
    Input("store_selected", "data"),
    Input("store_graph", "data"),
    Input("store_node_index", "data"),
    Input("store_adjacency", "data"),
    Input("store_revealed", "data"),
    Input("store_paging", "data"),
    Input("node_type_filter", "value"),
    Input("edge_type_filter", "value"),
    Input("page_range", "value"),
    Input("min_node_weight", "value"),
    Input("min_edge_weight", "value"),
    Input("view_toggles", "value"),
    Input("theme", "value"),
)
def update_inspector(
    selected_node_id,
    store_graph,
    node_index,
    adjacency,
    store_revealed,
    store_paging,
    node_type_filter,
    edge_type_filter,
    page_range,
    min_node_weight,
    min_edge_weight,
    view_toggles,
    theme,
):
    tokens = get_theme_tokens(theme or DEFAULT_VIEW["theme"])
    style = {
        "backgroundColor": tokens["panel"],
        "color": tokens["text"],
        "border": f"1px solid {tokens['panel_border']}",
        "padding": "10px",
        "borderRadius": "8px",
    }
    if not selected_node_id or not node_index or not adjacency:
        return "Select a node to inspect.", style

    node = node_index.get(selected_node_id, {})
    data = node.get("data", {})
    node_title = data.get("name") or data.get("label") or data.get("id")
    node_type = data.get("type", "Unknown")
    description = data.get("description") or ""

    revealed_edges = set(store_revealed.get("edges", [])) if store_revealed else set()
    node_types = set(node_type_filter or []) or None
    edge_types = set(edge_type_filter or []) or None
    hide_pages = "hide_pages" in (view_toggles or [])
    page_bounds = tuple(page_range) if page_range else None

    sections = []
    for direction in ("out", "in"):
        direction_edges = []
        index = adjacency.get("out" if direction == "out" else "in", {}).get(selected_node_id, {})
        for edge_type, entries in index.items():
            filtered_entries = _filter_edge_entries(
                entries,
                node_index,
                edge_types,
                node_types,
                hide_pages,
                page_bounds,
                float(min_node_weight or 0),
                float(min_edge_weight or 0),
                direction,
            )
            if not filtered_entries:
                continue
            total_count = len(filtered_entries)
            key = group_key(selected_node_id, direction, edge_type)
            stored_offset = int((store_paging or {}).get(key, 0))
            visible_entries = filtered_entries[:offset]
            revealed_count = sum(1 for entry in filtered_entries if entry.get("edge_id") in revealed_edges)
            offset = max(stored_offset, min(revealed_count, total_count))
            visible_entries = filtered_entries[:offset]

            node_rows = []
            for entry in visible_entries:
                neighbor_id = entry["neighbor_id"]
                neighbor = node_index.get(neighbor_id, {})
                ndata = neighbor.get("data", {})
                neighbor_label = ndata.get("name") or ndata.get("label") or neighbor_id
                node_rows.append(
                    html.Button(
                        f'{ndata.get("type")} · {neighbor_label}',
                        id={"type": "select-node", "node_id": neighbor_id},
                        className="inspector-node",
                    )
                )

            controls = []
            if offset < total_count:
                controls.append(
                    html.Button(
                        "Expand",
                        id={"type": "expand-group", "node_id": selected_node_id, "direction": direction, "edge_type": edge_type},
                        className="control-button",
                    )
                )
            if offset > 0:
                controls.append(
                    html.Button(
                        "Collapse",
                        id={"type": "collapse-group", "node_id": selected_node_id, "direction": direction, "edge_type": edge_type},
                        className="control-button",
                    )
                )

            direction_edges.append(
                html.Div(
                    className="inspector-group",
                    children=[
                        html.Div(
                            f'{_direction_label(direction)} {edge_type} ({revealed_count}/{total_count})',
                            className="inspector-group__title",
                        ),
                        html.Div(node_rows or [html.Div("No revealed nodes", className="inspector-empty")]),
                        html.Div(controls, className="inspector-controls"),
                    ],
                )
            )

        if direction_edges:
            sections.append(
                html.Div(
                    className="inspector-section",
                    children=[
                        html.Div(f"{_direction_label(direction)} {direction.title()} connections", className="inspector-section__title"),
                        html.Div(direction_edges),
                    ],
                )
            )

    return (
        html.Div(
            children=[
                html.Div(node_title, className="inspector-title"),
                html.Div(node_type, className="inspector-subtitle"),
                html.Div(description, className="inspector-description"),
                html.Div(sections or "No connections match the current filters.", className="inspector-connections"),
            ]
        ),
        style,
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


def _column_letter(index: int) -> str:
    letter = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letter = chr(65 + remainder) + letter
    return letter


def _sheet_xml(rows):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">')
    lines.append("<sheetData>")
    for r_index, row in enumerate(rows, start=1):
        lines.append(f'<row r="{r_index}">')
        for c_index, value in enumerate(row, start=1):
            cell_ref = f"{_column_letter(c_index)}{r_index}"
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                lines.append(f'<c r="{cell_ref}"><v>{value}</v></c>')
            else:
                safe = escape(str(value))
                lines.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{safe}</t></is></c>')
        lines.append("</row>")
    lines.append("</sheetData>")
    lines.append("</worksheet>")
    return "\n".join(lines)


def _build_xlsx(nodes_rows, edges_rows):
    workbook = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Nodes" sheetId="1" r:id="rId1"/>
    <sheet name="Edges" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>
"""
    rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
</Relationships>
"""
    root_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
"""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", rels)
        zf.writestr("xl/worksheets/sheet1.xml", _sheet_xml(nodes_rows))
        zf.writestr("xl/worksheets/sheet2.xml", _sheet_xml(edges_rows))
    return output.getvalue()


def _build_export_rows(store_graph):
    node_index = {n["data"]["id"]: n for n in store_graph.get("nodes", [])}
    nodes_rows = [["Type", "Name", "Image", "Weight"]]
    for node in store_graph.get("nodes", []):
        data = node["data"]
        nodes_rows.append(
            [
                data.get("type", ""),
                data.get("name", ""),
                data.get("image", ""),
                round(float(data.get("weight") or 1), 3),
            ]
        )

    edges_rows = [["From Type", "From Name", "To Type", "To Name", "Weight"]]
    for edge in store_graph.get("edges", []):
        data = edge["data"]
        source = node_index.get(data.get("source"), {}).get("data", {})
        target = node_index.get(data.get("target"), {}).get("data", {})
        edges_rows.append(
            [
                source.get("type", ""),
                source.get("name", ""),
                target.get("type", ""),
                target.get("name", ""),
                round(float(data.get("weight") or 1), 3),
            ]
        )
    return nodes_rows, edges_rows


@app.callback(
    Output("download_csv", "data"),
    Input("export_csv", "n_clicks"),
    State("store_graph", "data"),
    prevent_initial_call=True,
)
def export_csv(n_clicks, store_graph):
    if not n_clicks or not store_graph:
        return no_update

    nodes_rows, edges_rows = _build_export_rows(store_graph)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        nodes_buffer = io.StringIO()
        edges_buffer = io.StringIO()
        csv.writer(nodes_buffer).writerows(nodes_rows)
        csv.writer(edges_buffer).writerows(edges_rows)
        zf.writestr("nodes.csv", nodes_buffer.getvalue())
        zf.writestr("edges.csv", edges_buffer.getvalue())
    return dcc.send_bytes(output.getvalue(), "graph_commons_csv.zip")


@app.callback(
    Output("download_xlsx", "data"),
    Input("export_xlsx", "n_clicks"),
    State("store_graph", "data"),
    prevent_initial_call=True,
)
def export_xlsx(n_clicks, store_graph):
    if not n_clicks or not store_graph:
        return no_update

    nodes_rows, edges_rows = _build_export_rows(store_graph)
    return dcc.send_bytes(_build_xlsx(nodes_rows, edges_rows), "graph_commons.xlsx")


@app.callback(
    Output("hover-node-output", "children"),
    Input("graph", "mouseoverNodeData"),
)
def show_hover_node(data):
    if not data:
        return "Hover a node to see details."

    return "\n".join(
        [
            f"Type: {data.get('type')}",
            f"Name: {data.get('name')}",
            f"Weight: {round(float(data.get('weight') or 0), 3)}",
            f"Degree: {data.get('degree')}",
            f"Text length: {data.get('text_length')}",
            f"Children count: {data.get('children_count')}",
        ]
    )


@app.callback(
    Output("hover-edge-output", "children"),
    Input("graph", "mouseoverEdgeData"),
)
def show_hover_edge(data):
    if not data:
        return "Hover an edge to see details."

    return "\n".join(
        [
            f"Edge Type: {data.get('rel')}",
            f"Weight: {round(float(data.get('weight') or 0), 3)}",
            f"Source: {data.get('source_type')} · {data.get('source_name')}",
            f"Target: {data.get('target_type')} · {data.get('target_name')}",
        ]
    )


# -------------------------------------------------
# Run
# -------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050)
