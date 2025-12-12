import os
import dash
from dash import Dash, html, dcc, Input, Output, State
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

LAYOUT_CHOICES = [
    ("Dagre (directed)", "dagre"),
    ("Breadthfirst", "breadthfirst"),
    ("COSE-Bilkent", "cose-bilkent"),
    ("Cola", "cola"),
    ("COSE", "cose"),
    ("Grid", "grid"),
    ("Circle", "circle"),
]

def _layout_options():
    return [{"label": l, "value": v} for l, v in LAYOUT_CHOICES]

def _default_layout():
    return "dagre"

files = list_docling_files()

app.layout = html.Div(
    style={"padding": "10px"},
    children=[
        html.H3("Docling Graph Viewer"),

        dcc.Store(id="layout-store", data={}),
        dcc.Store(id="zoom-store", data=1.0),

        html.Div(
            style={"display": "flex", "gap": "8px", "flexWrap": "wrap"},
            children=[
                dcc.Dropdown(
                    id="docling-file",
                    options=[{"label": p, "value": p} for p in files],
                    value=(files[0] if files else None),
                    clearable=False,
                    style={"minWidth": "520px", "flex": "1"},
                ),
                dcc.Dropdown(
                    id="page-filter",
                    placeholder="Page (optional)",
                    clearable=True,
                    style={"minWidth": "180px"},
                ),
                dcc.Dropdown(
                    id="type-filter",
                    placeholder="Type: ALL",
                    clearable=False,
                    multi=False,
                    style={"minWidth": "180px"},
                ),
                dcc.Dropdown(
                    id="layout-name",
                    options=_layout_options(),
                    value=_default_layout(),
                    clearable=False,
                    style={"minWidth": "240px"},
                ),
                html.Button("Fit", id="fit-btn"),
            ],
        ),

        cyto.Cytoscape(
            id="graph",
            elements=[],
            layout={"name": _default_layout(), "fit": True},
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
                        "text-max-width": "220px",
                        "color": "#e5e7eb",
                    },
                },
                {"selector": ".document", "style": {"background-color": "#2563eb"}},
                {"selector": ".section", "style": {"background-color": "#111827"}},
                {"selector": ".item", "style": {"background-color": "#374151"}},
                {"selector": "edge.seq", "style": {"line-style": "dotted", "opacity": 0.6}},
            ],
        ),
    ],
)

# -----------------------------
# Populate page + type filters
# -----------------------------
@app.callback(
    Output("page-filter", "options"),
    Output("type-filter", "options"),
    Output("type-filter", "value"),
    Input("docling-file", "value"),
)
def populate_filters(path):
    if not path:
        return [], [], "ALL"

    els = build_graph_from_docling_json(path)
    pages = sorted({e["data"].get("page") for e in els if e.get("data", {}).get("page") is not None})
    types = sorted({e["data"].get("type") for e in els if e.get("data", {}).get("type")})

    return (
        [{"label": f"Page {p}", "value": p} for p in pages],
        [{"label": "ALL", "value": "ALL"}] + [{"label": t, "value": t} for t in types],
        "ALL",
    )

# -----------------------------
# Load + filter graph
# -----------------------------
@app.callback(
    Output("graph", "elements"),
    Input("docling-file", "value"),
    Input("page-filter", "value"),
    Input("type-filter", "value"),
)
def load_graph(path, page_filter, type_filter):
    if not path:
        return []

    els = build_graph_from_docling_json(path)

    if page_filter is None and (type_filter in (None, "ALL")):
        return els

    keep = set()
    for e in els:
        d = e.get("data", {})
        if d.get("type") == "document":
            keep.add(d.get("id"))
        else:
            page_ok = page_filter is None or d.get("page") == page_filter
            type_ok = type_filter in (None, "ALL") or d.get("type") == type_filter
            if page_ok and type_ok:
                keep.add(d.get("id"))

    out = []
    for e in els:
        d = e.get("data", {})
        if "id" in d and d["id"] in keep:
            out.append(e)
        elif d.get("source") in keep and d.get("target") in keep:
            out.append(e)

    return out


@app.callback(
    Output("graph", "layout"),
    Input("layout-name", "value"),
    Input("fit-btn", "n_clicks"),
)
def apply_layout(name, _):
    return {"name": name or _default_layout(), "fit": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050)
