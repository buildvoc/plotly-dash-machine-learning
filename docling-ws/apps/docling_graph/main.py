import os
from dash import Dash, html, dcc, Input, Output, State, no_update
import dash_cytoscape as cyto

from .graph_builder import build_graph_from_docling_json, list_docling_files

APP_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    cyto.load_extra_layouts()
except Exception:
    pass

app = Dash(
    __name__,
    title="Docling Graph Viewer",
    assets_folder=os.path.join(APP_DIR, "assets"),
)

files = list_docling_files()

LAYOUTS = [
    ("Dagre (sequence)", "dagre"),
    ("Breadthfirst", "breadthfirst"),
    ("Force-directed (COSE)", "cose"),
    ("COSE-Bilkent", "cose-bilkent"),
    ("Cola (read text)", "cola"),
    ("Force-Atlas2 (plugin)", "forceatlas2"),
]


def _page_set(elements):
    return sorted(
        {e["data"].get("page") for e in elements if e.get("data", {}).get("page") is not None}
    )


def _base_stylesheet(node_size: int, font_size: int, text_max_width: int, show_edge_labels: bool, show_edge_weights: bool):
    edge_label = "data(label)" if show_edge_labels else ""
    if show_edge_weights:
        # if weight exists, append it (fallback to label only)
        # Cytoscape doesn't support string concat here reliably; use weight alone if toggled
        edge_label = "data(weight)"

    return [
        {
            "selector": "node",
            "style": {
                "label": "data(label)",
                "font-size": f"{font_size}px",
                "text-wrap": "wrap",
                "text-max-width": f"{text_max_width}px",
                "color": "#e5e7eb",
                "width": f"{node_size}px",
                "height": f"{node_size}px",
            },
        },
        {
            "selector": "edge",
            "style": {
                "curve-style": "bezier",
                "line-color": "#94a3b8",
                "target-arrow-color": "#94a3b8",
                "target-arrow-shape": "triangle",
                "arrow-scale": 0.8,
                "label": edge_label,
                "font-size": "9px",
                "text-rotation": "autorotate",
                "text-background-opacity": 0.6,
                "text-background-color": "#0b1220",
                "text-background-padding": "2px",
                "color": "#cbd5e1",
            },
        },
        {"selector": ".document", "style": {"background-color": "#2563eb"}},
        {"selector": ".section", "style": {"background-color": "#111827"}},
        {"selector": ".item", "style": {"background-color": "#374151"}},
        # selection highlight
        {"selector": ":selected", "style": {"border-width": 3, "border-color": "#fbbf24"}},
    ]


def _layout_for(name: str, scaling_ratio: int):
    """
    'scaling_ratio' is modeled like GraphCommons' scaling ratio:
    - ForceAtlas2: scalingRatio
    - COSE: maps to nodeRepulsion + idealEdgeLength
    - Cola: maps to nodeSpacing + edgeLength
    - Dagre: maps to rankSep/nodeSep
    """
    name = name or "dagre"
    s = max(50, min(int(scaling_ratio or 250), 800))

    if name == "dagre":
        return {
            "name": "dagre",
            "rankDir": "TB",
            "rankSep": int(80 + (s * 0.6)),
            "nodeSep": int(30 + (s * 0.25)),
            "edgeSep": 20,
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

    if name == "cose":
        return {
            "name": "cose",
            "animate": True,
            "randomize": True,
            "idealEdgeLength": int(60 + (s * 0.25)),
            "nodeRepulsion": int(2000 + (s * 12)),
            "gravity": 0.25,
            "numIter": 1000,
            "fit": True,
            "padding": 30,
        }

    if name == "cose-bilkent":
        # bilkent uses edgeLength + nodeRepulsion style params too
        return {
            "name": "cose-bilkent",
            "animate": True,
            "randomize": True,
            "idealEdgeLength": int(60 + (s * 0.25)),
            "nodeRepulsion": int(2000 + (s * 12)),
            "gravity": 0.25,
            "numIter": 1200,
            "fit": True,
            "padding": 30,
        }

    if name == "forceatlas2":
        # requires plugin JS in assets + init script (see file below)
        return {
            "name": "forceatlas2",
            "animate": True,
            "randomize": False,
            "iterations": 1200,
            "scalingRatio": float(s),
            "gravity": 1.0,
            "strongGravityMode": False,
            "slowDown": 1.0,
            "barnesHutOptimize": True,
            "barnesHutTheta": 0.9,
            "fit": True,
            "padding": 30,
        }

    return {"name": name, "fit": True, "padding": 30}


# ---------------------------
# App state for "View options"
# ---------------------------
DEFAULT_VIEW = {
    "layout": "dagre",
    "scaling_ratio": 250,
    "node_size": 22,
    "shorten_labels": True,     # GraphCommons: "Shorten node labels"
    "adjust_labels": False,     # our lightweight toggle
    "show_edge_labels": False,
    "show_edge_weights": False,
    "font_size": 10,
    "text_max_width": 520,
}

app.layout = html.Div(
    className="app",
    children=[
        dcc.Store(id="view_state", data=DEFAULT_VIEW),

        html.Div(
            className="topbar",
            children=[
                html.Div(className="title", children="Docling Graph Viewer"),
                html.Button("View options", id="btn_view_options", className="btn"),
            ],
        ),

        html.Div(
            className="controls",
            children=[
                dcc.Dropdown(
                    id="file",
                    options=[{"label": f, "value": f} for f in files],
                    value=(files[0] if files else None),
                    clearable=False,
                    style={"minWidth": "520px"},
                ),
                html.Div(
                    style={"minWidth": "520px"},
                    children=[
                        html.Div("Page range", style={"fontSize": "12px", "opacity": 0.85}),
                        dcc.RangeSlider(
                            id="page_range",
                            min=1,
                            max=1,
                            step=1,
                            value=[1, 1],
                            marks={},
                            tooltip={"placement": "bottom", "always_visible": False},
                            allowCross=False,
                        ),
                    ],
                ),
                dcc.Dropdown(id="type", placeholder="Type: ALL", clearable=False, style={"width": "160px"}),
                dcc.Dropdown(id="layer", placeholder="Layer: ALL", clearable=False, style={"width": "180px"}),
            ],
        ),

        # Graph
        cyto.Cytoscape(
            id="graph",
            style={"width": "100%", "height": "85vh"},
            wheelSensitivity=1,
            minZoom=0.25,
            maxZoom=2.0,
            layout=_layout_for(DEFAULT_VIEW["layout"], DEFAULT_VIEW["scaling_ratio"]),
            stylesheet=_base_stylesheet(
                DEFAULT_VIEW["node_size"],
                DEFAULT_VIEW["font_size"],
                DEFAULT_VIEW["text_max_width"],
                DEFAULT_VIEW["show_edge_labels"],
                DEFAULT_VIEW["show_edge_weights"],
            ),
            elements=[],
        ),

        # Right-side "View options" panel (GraphCommons-like)
        html.Div(
            id="view_panel",
            className="panel hidden",
            children=[
                html.Div(
                    className="panel-header",
                    children=[
                        html.Div("View options", className="panel-title"),
                        html.Button("×", id="btn_close_panel", className="btn-close"),
                    ],
                ),

                html.Div(
                    className="panel-section",
                    children=[
                        html.Div("Layout", className="section-title"),
                        dcc.Dropdown(
                            id="opt_layout",
                            options=[{"label": l, "value": v} for l, v in LAYOUTS],
                            value=DEFAULT_VIEW["layout"],
                            clearable=False,
                        ),
                        html.Div("Scaling ratio", className="section-title", style={"marginTop": "10px"}),
                        dcc.Slider(
                            id="opt_scaling_ratio",
                            min=50,
                            max=800,
                            step=10,
                            value=DEFAULT_VIEW["scaling_ratio"],
                            marks={50: "50", 250: "250", 500: "500", 800: "800"},
                            tooltip={"placement": "bottom", "always_visible": False},
                        ),
                    ],
                ),

                html.Div(
                    className="panel-section",
                    children=[
                        html.Div("Nodes", className="section-title"),
                        html.Div(
                            className="row",
                            children=[
                                html.Div("Adjust node size", className="muted"),
                                html.Div(
                                    className="row",
                                    children=[
                                        html.Button("−", id="opt_node_minus", className="btn-small"),
                                        html.Button("+", id="opt_node_plus", className="btn-small"),
                                    ],
                                ),
                            ],
                        ),
                        dcc.Checklist(
                            id="opt_node_checks",
                            options=[
                                {"label": " Shorten node labels", "value": "shorten"},
                                {"label": " Adjust node label overlaps", "value": "adjust"},
                            ],
                            value=[
                                "shorten" if DEFAULT_VIEW["shorten_labels"] else None,
                            ],
                        ),
                        html.Button("Reset positions (re-run layout)", id="opt_reset_layout", className="btn", style={"marginTop": "8px"}),
                    ],
                ),

                html.Div(
                    className="panel-section",
                    children=[
                        html.Div("Edges", className="section-title"),
                        dcc.Checklist(
                            id="opt_edge_checks",
                            options=[
                                {"label": " Always display edge labels", "value": "labels"},
                                {"label": " Show edge weights on labels", "value": "weights"},
                            ],
                            value=[],
                        ),
                    ],
                ),

                html.Div(
                    className="panel-footer",
                    children=[
                        html.Button("Apply", id="opt_apply", className="btn-primary"),
                    ],
                ),
            ],
        ),
    ],
)


# ---------------------------
# Populate page slider + type/layer options
# ---------------------------
@app.callback(
    Output("page_range", "min"),
    Output("page_range", "max"),
    Output("page_range", "value"),
    Output("page_range", "marks"),
    Output("type", "options"),
    Output("type", "value"),
    Output("layer", "options"),
    Output("layer", "value"),
    Input("file", "value"),
)
def populate_filters(path):
    if not path:
        return 1, 1, [1, 1], {}, [{"label": "ALL", "value": "ALL"}], "ALL", [{"label": "ALL", "value": "ALL"}], "ALL"

    els = build_graph_from_docling_json(path)
    pages = _page_set(els) or [1]
    pmin, pmax = pages[0], pages[-1]

    default_hi = min(pmax, pmin + 3)
    default_value = [pmin, default_hi]

    marks = {}
    for p in pages:
        if p == pmin or p == pmax or p % 5 == 0:
            marks[p] = str(p)

    types = sorted({e["data"].get("type") for e in els if e.get("data", {}).get("type")})
    layers = sorted({e["data"].get("content_layer") for e in els if e.get("data", {}).get("content_layer")})

    type_opts = [{"label": "ALL", "value": "ALL"}] + [{"label": t, "value": t} for t in types]
    layer_opts = [{"label": "ALL", "value": "ALL"}] + [{"label": l, "value": l} for l in layers]

    return pmin, pmax, default_value, marks, type_opts, "ALL", layer_opts, "ALL"


# ---------------------------
# Panel open/close
# ---------------------------
@app.callback(
    Output("view_panel", "className"),
    Input("btn_view_options", "n_clicks"),
    Input("btn_close_panel", "n_clicks"),
    State("view_panel", "className"),
    prevent_initial_call=True,
)
def toggle_panel(open_clicks, close_clicks, current):
    current = current or "panel hidden"
    ctx = __import__("dash").callback_context
    if not ctx.triggered:
        return current
    trig = ctx.triggered[0]["prop_id"].split(".")[0]
    if trig == "btn_view_options":
        return "panel"  # show
    return "panel hidden"  # hide


# ---------------------------
# Node size +/- buttons update view_state draft values
# ---------------------------
@app.callback(
    Output("opt_scaling_ratio", "value"),
    Output("view_state", "data"),
    Input("opt_node_plus", "n_clicks"),
    Input("opt_node_minus", "n_clicks"),
    Input("opt_reset_layout", "n_clicks"),
    State("view_state", "data"),
    State("opt_scaling_ratio", "value"),
    prevent_initial_call=True,
)
def bump_node_size(n_plus, n_minus, n_reset, view, scaling):
    view = dict(view or DEFAULT_VIEW)
    ctx = __import__("dash").callback_context
    trig = ctx.triggered[0]["prop_id"].split(".")[0]

    if trig == "opt_node_plus":
        view["node_size"] = min(60, int(view.get("node_size", 22)) + 2)
    elif trig == "opt_node_minus":
        view["node_size"] = max(6, int(view.get("node_size", 22)) - 2)
    elif trig == "opt_reset_layout":
        # no direct position capture; we re-run layout by bumping a dummy param in state later on Apply
        view["_rerun"] = int(view.get("_rerun", 0)) + 1

    # keep slider value unchanged
    return scaling, view


# ---------------------------
# Apply view options to graph (stylesheet + layout)
# ---------------------------
@app.callback(
    Output("view_state", "data", allow_duplicate=True),
    Output("graph", "stylesheet"),
    Output("graph", "layout"),
    Output("graph", "elements"),
    Input("opt_apply", "n_clicks"),
    State("file", "value"),
    State("page_range", "value"),
    State("type", "value"),
    State("layer", "value"),
    State("opt_layout", "value"),
    State("opt_scaling_ratio", "value"),
    State("opt_node_checks", "value"),
    State("opt_edge_checks", "value"),
    State("view_state", "data"),
    prevent_initial_call=True,
)
def apply_view(n_apply, path, page_range, typ, layer, layout_name, scaling_ratio, node_checks, edge_checks, view):
    if not path:
        return no_update, no_update, no_update, []

    view = dict(view or DEFAULT_VIEW)
    node_checks = node_checks or []
    edge_checks = edge_checks or []

    view["layout"] = layout_name or "dagre"
    view["scaling_ratio"] = int(scaling_ratio or 250)
    view["shorten_labels"] = ("shorten" in node_checks)
    view["adjust_labels"] = ("adjust" in node_checks)
    view["show_edge_labels"] = ("labels" in edge_checks)
    view["show_edge_weights"] = ("weights" in edge_checks)

    # lightweight “adjust overlaps” effect: reduce font + width so labels collide less
    if view["adjust_labels"]:
        view["font_size"] = 9
        view["text_max_width"] = 320
    else:
        view["font_size"] = 10
        view["text_max_width"] = 520

    els = build_graph_from_docling_json(path)

    lo, hi = 1, 10**9
    if isinstance(page_range, (list, tuple)) and len(page_range) == 2:
        lo, hi = int(page_range[0]), int(page_range[1])

    keep = set()
    for e in els:
        d = e.get("data", {})
        nid = d.get("id")
        if not nid:
            continue

        if d.get("type") == "document":
            keep.add(nid)
            continue

        page = d.get("page")
        page_ok = True
        if page is not None:
            page_ok = lo <= int(page) <= hi

        type_ok = typ in (None, "ALL") or d.get("type") == typ
        layer_ok = layer in (None, "ALL") or d.get("content_layer") == layer

        if page_ok and type_ok and layer_ok:
            keep.add(nid)

    # label mode switch
    use_short = view["shorten_labels"] or (view["layout"] == "dagre")

    out = []
    for e in els:
        d = e.get("data", {})
        if "id" in d and d["id"] in keep:
            new_e = dict(e)
            new_d = dict(d)
            new_d["label"] = new_d.get("label_short") if use_short else new_d.get("label_full")
            new_e["data"] = new_d
            out.append(new_e)
        elif d.get("source") in keep and d.get("target") in keep:
            out.append(e)

    stylesheet = _base_stylesheet(
        node_size=view["node_size"],
        font_size=view["font_size"],
        text_max_width=view["text_max_width"],
        show_edge_labels=view["show_edge_labels"],
        show_edge_weights=view["show_edge_weights"],
    )

    layout = _layout_for(view["layout"], view["scaling_ratio"])

    # if reset requested, force randomize where supported
    if "_rerun" in view:
        if layout.get("name") in ("cose", "cose-bilkent", "cola"):
            layout["randomize"] = True
        # clear the flag
        view.pop("_rerun", None)

    return view, stylesheet, layout, out


# ---------------------------
# Keep panel controls in sync with stored view_state (on load/refresh)
# ---------------------------
@app.callback(
    Output("opt_layout", "value"),
    Output("opt_scaling_ratio", "value"),
    Output("opt_node_checks", "value"),
    Output("opt_edge_checks", "value"),
    Input("view_state", "data"),
)
def sync_panel(view):
    view = view or DEFAULT_VIEW
    node_vals = []
    if view.get("shorten_labels"):
        node_vals.append("shorten")
    if view.get("adjust_labels"):
        node_vals.append("adjust")

    edge_vals = []
    if view.get("show_edge_labels"):
        edge_vals.append("labels")
    if view.get("show_edge_weights"):
        edge_vals.append("weights")

    return view.get("layout", "dagre"), view.get("scaling_ratio", 250), node_vals, edge_vals


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050)
