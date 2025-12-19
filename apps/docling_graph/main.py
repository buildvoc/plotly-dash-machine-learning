from __future__ import annotations

import os
import json
import csv
import io
import zipfile
from xml.sax.saxutils import escape
from dash import Dash, html, dcc, Input, Output, State, no_update
import dash_cytoscape as cyto

from .graph_builder import build_graph_from_docling_json, list_docling_files, GraphPayload
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


def base_stylesheet(
    node_size,
    font_size,
    text_max_width,
    show_edge_labels,
    scale_node_size,
    scale_edge_width,
):
    node_width = "data(size)" if scale_node_size else f"{node_size}px"
    node_height = "data(size)" if scale_node_size else f"{node_size}px"
    edge_width = "data(width)" if scale_edge_width else 1.5
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
                "width": node_width,
                "height": node_height,
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
                "width": edge_width,
                "z-index": 5000,
            },
        },
        {"selector": ".document", "style": {"background-color": "#1D4ED8"}},
        {"selector": ".body", "style": {"background-color": "#0EA5E9"}},
        {"selector": ".page", "style": {"background-color": "#111827"}},
        {"selector": ".text", "style": {"background-color": "#334155"}},
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
                            stylesheet=base_stylesheet(
                                DEFAULT_VIEW["node_size"],
                                DEFAULT_VIEW["font_size"],
                                DEFAULT_VIEW["text_max_width"],
                                DEFAULT_VIEW["show_edge_labels"],
                                DEFAULT_VIEW["scale_node_size"],
                                DEFAULT_VIEW["scale_edge_width"],
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
                                                        html.Div("Hover details", className="control-label"),
                                                        html.Pre(id="hover-node-output", style={"whiteSpace": "pre-wrap"}),
                                                        html.Pre(id="hover-edge-output", style={"whiteSpace": "pre-wrap"}),
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
    doc_node = next((n for n in g.nodes if n["data"].get("type") == "Document"), None)
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

    for e in elements:
        if e.get("data", {}).get("id") == node_id:
            e["data"]["expanded"] = True

    new_nodes = []
    new_edges = []

    child_edges = {"HAS_PAGE", "HAS_BODY", "CONTAINS", "ON_PAGE"}
    for ed in store_graph["edges"]:
        d = ed["data"]
        src, tgt, rel = d.get("source"), d.get("target"), d.get("rel")

        if mode == "children" and not (rel in child_edges and src == node_id):
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
    Input("min_node_weight", "value"),
    Input("min_edge_weight", "value"),
    Input("weight_toggles", "value"),
    State("graph", "elements"),
    prevent_initial_call=True,
)
def filter_elements_by_page(page_range, min_node_weight, min_edge_weight, weight_toggles, elements):
    if not page_range or not elements:
        return no_update

    keep_context = "context" in (weight_toggles or [])
    node_threshold = float(min_node_weight or 1)
    edge_threshold = float(min_edge_weight or 1)

    start_page, end_page = page_range
    allowed_nodes = set()
    filtered_nodes = []

    for el in elements:
        data = el.get("data", {})
        if "source" in data:
            continue

        page = data.get("page")
        weight = float(data.get("weight") or 0)
        if page is None or (start_page <= page <= end_page):
            if weight >= node_threshold:
                allowed_nodes.add(data.get("id"))
                filtered_nodes.append(el)

    filtered_edges = []
    context_nodes = set()
    for el in elements:
        data = el.get("data", {})
        if "source" not in data:
            continue
        weight = float(data.get("weight") or 0)
        if weight < edge_threshold:
            continue
        src = data.get("source")
        tgt = data.get("target")
        if src in allowed_nodes and tgt in allowed_nodes:
            filtered_edges.append(el)
        elif keep_context and (src in allowed_nodes or tgt in allowed_nodes):
            context_nodes.update([src, tgt])
            filtered_edges.append(el)

    if keep_context and context_nodes:
        for el in elements:
            data = el.get("data", {})
            if "source" in data:
                continue
            node_id = data.get("id")
            page = data.get("page")
            if node_id in context_nodes and (page is None or (start_page <= page <= end_page)):
                if node_id not in allowed_nodes:
                    allowed_nodes.add(node_id)
                    filtered_nodes.append(el)

    return filtered_nodes + filtered_edges


@app.callback(
    Output("graph", "stylesheet"),
    Input("edge_labels", "value"),
    Input("weight_toggles", "value"),
)
def update_styles(edge_labels, weight_toggles):
    weight_toggles = weight_toggles or []
    return base_stylesheet(
        DEFAULT_VIEW["node_size"],
        DEFAULT_VIEW["font_size"],
        DEFAULT_VIEW["text_max_width"],
        "on" in (edge_labels or []),
        "node" in weight_toggles,
        "edge" in weight_toggles,
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
