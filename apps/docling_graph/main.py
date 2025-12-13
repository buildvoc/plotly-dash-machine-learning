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

# -------------------------------------------------------------------
# Data
# -------------------------------------------------------------------
files = list_docling_files()

LAYOUTS = [
    ("Dagre", "dagre"),
    ("Breadthfirst", "breadthfirst"),
    ("COSE-Bilkent", "cose-bilkent"),
    ("Cola", "cola"),
    ("COSE", "cose"),
]

# -------------------------------------------------------------------
# Layout
# -------------------------------------------------------------------
app.layout = html.Div(
    style={"padding": "10px"},
    children=[
        html.H3("Docling Graph Viewer"),

        html.Div(
            style={"display": "flex", "gap": "8px", "flexWrap": "wrap"},
            children=[
                dcc.Dropdown(
                    id="file",
                    options=[{"label": f, "value": f} for f in files],
                    value=(files[0] if files else None),
                    clearable=False,
                    style={"minWidth": "520px"},
                ),
                dcc.Dropdown(
                    id="page",
                    placeholder="Page (optional)",
                    clearable=True,
                    style={"width": "140px"},
                ),
                dcc.Dropdown(
                    id="type",
                    placeholder="Type: ALL",
                    clearable=False,
                    multi=False,
                    style={"width": "160px"},
                ),
                dcc.Dropdown(
                    id="layer",
                    placeholder="Layer: ALL",
                    clearable=False,
                    multi=False,
                    style={"width": "180px"},
                ),
                dcc.Dropdown(
                    id="layout",
                    options=[{"label": l, "value": v} for l, v in LAYOUTS],
                    value="dagre",
                    clearable=False,
                    style={"width": "180px"},
                ),
            ],
        ),

        cyto.Cytoscape(
            id="graph",
            style={"width": "100%", "height": "85vh"},
            wheelSensitivity=0.01,
            minZoom=0.25,
            maxZoom=1.6,
            stylesheet=[
                {
                    "selector": "node",
                    "style": {
                        "label": "data(label)",
                        "font-size": "11px",
                        "text-wrap": "wrap",
                        "text-max-width": "240px",
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

# -------------------------------------------------------------------
# Populate filters from Docling schema
# -------------------------------------------------------------------
@app.callback(
    Output("page", "options"),
    Output("type", "options"),
    Output("type", "value"),
    Output("layer", "options"),
    Output("layer", "value"),
    Input("file", "value"),
)
def populate_filters(path):
    if not path:
        return [], [], "ALL", [], "ALL"

    els = build_graph_from_docling_json(path)

    pages = sorted(
        {e["data"].get("page") for e in els if e.get("data", {}).get("page") is not None}
    )
    types = sorted(
        {e["data"].get("type") for e in els if e.get("data", {}).get("type")}
    )
    layers = sorted(
        {
            e["data"].get("content_layer")
            for e in els
            if e.get("data", {}).get("content_layer")
        }
    )

    return (
        [{"label": f"Page {p}", "value": p} for p in pages],
        [{"label": "ALL", "value": "ALL"}] + [{"label": t, "value": t} for t in types],
        "ALL",
        [{"label": "ALL", "value": "ALL"}] + [{"label": l, "value": l} for l in layers],
        "ALL",
    )

# -------------------------------------------------------------------
# Graph update with schema filters (non-destructive)
# -------------------------------------------------------------------
@app.callback(
    Output("graph", "elements"),
    Input("file", "value"),
    Input("page", "value"),
    Input("type", "value"),
    Input("layer", "value"),
    Input("layout", "value"),
)
def update_graph(path, page, typ, layer, layout):
    if not path:
        return []

    els = build_graph_from_docling_json(path)

    # Fast path: nothing filtered
    if page is None and typ in (None, "ALL") and layer in (None, "ALL"):
        return els

    keep = set()

    for e in els:
        d = e.get("data", {})
        nid = d.get("id")

        if not nid:
            continue

        if d.get("type") == "document":
            keep.add(nid)
            continue

        page_ok = page is None or d.get("page") == page
        type_ok = typ in (None, "ALL") or d.get("type") == typ
        layer_ok = layer in (None, "ALL") or d.get("content_layer") == layer

        if page_ok and type_ok and layer_ok:
            keep.add(nid)

    out = []
    for e in els:
        d = e.get("data", {})
        if "id" in d and d["id"] in keep:
            out.append(e)
        elif d.get("source") in keep and d.get("target") in keep:
            out.append(e)

    return out

# -------------------------------------------------------------------
# Layout control
# -------------------------------------------------------------------
@app.callback(
    Output("graph", "layout"),
    Input("layout", "value"),
)
def set_layout(name):
    return {"name": name or "dagre", "fit": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050)
