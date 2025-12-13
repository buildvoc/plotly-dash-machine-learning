import os
from dash import Dash, html, dcc, Input, Output
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

# Added:
# - Force-directed (COSE) as a friendly label for cose
# - Force-Atlas2 (plugin)
LAYOUTS = [
    ("Dagre (sequence)", "dagre"),
    ("Breadthfirst", "breadthfirst"),
    ("Force-directed (COSE)", "cose"),          # ✅ Option 1
    ("COSE-Bilkent", "cose-bilkent"),
    ("Cola (read text)", "cola"),
    ("Force-Atlas2 (plugin)", "forceatlas2"),   # ✅ Option 2
]


def _page_set(elements):
    return sorted(
        {e["data"].get("page") for e in elements if e.get("data", {}).get("page") is not None}
    )


app.layout = html.Div(
    style={"padding": "10px"},
    children=[
        html.H3("Docling Graph Viewer"),

        html.Div(
            style={
                "display": "flex",
                "gap": "14px",
                "flexWrap": "wrap",
                "alignItems": "center",
            },
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
                        html.Div("Page range", style={"fontSize": "12px", "opacity": 0.8}),
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

                dcc.Dropdown(
                    id="type",
                    placeholder="Type: ALL",
                    clearable=False,
                    style={"width": "160px"},
                ),
                dcc.Dropdown(
                    id="layer",
                    placeholder="Layer: ALL",
                    clearable=False,
                    style={"width": "180px"},
                ),
                dcc.Dropdown(
                    id="layout",
                    options=[{"label": l, "value": v} for l, v in LAYOUTS],
                    value="dagre",
                    clearable=False,
                    style={"width": "240px"},
                ),
            ],
        ),

        cyto.Cytoscape(
            id="graph",
            style={"width": "100%", "height": "85vh"},
            wheelSensitivity=0.01,
            minZoom=0.25,
            maxZoom=2.0,
            stylesheet=[
                {
                    "selector": "node",
                    "style": {
                        "label": "data(label)",
                        "font-size": "10px",
                        "text-wrap": "wrap",
                        "text-max-width": "520px",
                        "color": "#e5e7eb",
                    },
                },
                {"selector": ".document", "style": {"background-color": "#2563eb"}},
                {"selector": ".section", "style": {"background-color": "#111827"}},
                {"selector": ".item", "style": {"background-color": "#374151"}},
            ],
        ),
    ],
)

# ------------------------------------------------------------
# Populate range slider + Type/Layer options
# ------------------------------------------------------------
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
        return (
            1,
            1,
            [1, 1],
            {},
            [{"label": "ALL", "value": "ALL"}],
            "ALL",
            [{"label": "ALL", "value": "ALL"}],
            "ALL",
        )

    els = build_graph_from_docling_json(path)
    pages = _page_set(els) or [1]
    pmin, pmax = pages[0], pages[-1]

    default_hi = min(pmax, pmin + 3)
    default_value = [pmin, default_hi]

    marks = {}
    for p in pages:
        if p == pmin or p == pmax or p % 5 == 0:
            marks[p] = str(p)

    types = sorted(
        {e["data"].get("type") for e in els if e.get("data", {}).get("type")}
    )
    layers = sorted(
        {e["data"].get("content_layer") for e in els if e.get("data", {}).get("content_layer")}
    )

    type_opts = [{"label": "ALL", "value": "ALL"}] + [
        {"label": t, "value": t} for t in types
    ]
    layer_opts = [{"label": "ALL", "value": "ALL"}] + [
        {"label": l, "value": l} for l in layers
    ]

    return pmin, pmax, default_value, marks, type_opts, "ALL", layer_opts, "ALL"


# ------------------------------------------------------------
# Update elements AND switch label mode based on layout
# ------------------------------------------------------------
@app.callback(
    Output("graph", "elements"),
    Input("file", "value"),
    Input("page_range", "value"),
    Input("type", "value"),
    Input("layer", "value"),
    Input("layout", "value"),
)
def update_elements(path, page_range, typ, layer, layout_name):
    if not path:
        return []

    els = build_graph_from_docling_json(path)

    # label mode:
    # - dagre: short labels (readable)
    # - others: full labels (reading)
    use_short = (layout_name == "dagre")

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

    return out


# ------------------------------------------------------------
# Layout tuning: Dagre + Cola + Force-directed + ForceAtlas2
# ------------------------------------------------------------
@app.callback(
    Output("graph", "layout"),
    Input("layout", "value"),
)
def set_layout(name):
    name = name or "dagre"

    if name == "dagre":
        return {
            "name": "dagre",
            "rankDir": "TB",
            "rankSep": 180,
            "nodeSep": 80,
            "edgeSep": 20,
            "fit": True,
            "padding": 30,
        }

    if name == "cola":
        return {
            "name": "cola",
            "nodeSpacing": 60,
            "edgeLength": 140,
            "avoidOverlap": True,
            "handleDisconnected": True,
            "flow": {"axis": "y", "minSeparation": 50},
            "fit": True,
            "padding": 30,
        }

    # ✅ Option 1 (force-directed): COSE
    if name == "cose":
        return {
            "name": "cose",
            "animate": True,
            "randomize": True,
            "idealEdgeLength": 120,
            "nodeRepulsion": 4500,
            "gravity": 0.25,
            "numIter": 1000,
            "fit": True,
            "padding": 30,
        }

    # ✅ Option 2 (Force-Atlas2): requires plugin JS in assets
    if name == "forceatlas2":
        return {
            "name": "forceatlas2",
            "animate": True,
            "randomize": False,
            "iterations": 1200,
            "gravity": 1.0,
            "scalingRatio": 2.0,
            "strongGravityMode": False,
            "slowDown": 1.0,
            "barnesHutOptimize": True,
            "barnesHutTheta": 0.9,
            "fit": True,
            "padding": 30,
        }

    return {"name": name, "fit": True, "padding": 30}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050)
