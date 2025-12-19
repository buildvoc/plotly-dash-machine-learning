from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Iterable, List, Tuple

from dash import ALL, Dash, Input, Output, State, dcc, html, no_update, ctx
import dash_cytoscape as cyto

from .graph_builder import build_graph_from_docling_json, list_docling_files
from .graph_styles import apply_theme_to_elements, base_stylesheet

APP_DIR = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Enable stable extra layouts
try:
    cyto.load_extra_layouts()
except Exception:
    pass


# -------------------------------------------------
# Helpers
# -------------------------------------------------

def safe_base_stylesheet(
    theme: str,
    scale_node_size: bool,
    scale_edge_width: bool,
    show_edge_labels: bool,
    show_arrows: bool,
) -> List[Dict[str, Any]]:
    try:
        return base_stylesheet(
            theme,
            scale_node_size,
            scale_edge_width,
            show_edge_labels,
            show_arrows,
        )
    except Exception:
        logger.exception("Failed to build stylesheet")
        return []


def _filter_graph(
    graph: Dict[str, Any],
    node_types: Iterable[str],
    edge_types: Iterable[str],
    hide_page_nodes: bool,
    hide_isolated_nodes: bool,
    min_node_weight: float,
    min_edge_weight: float,
    keep_context_nodes: bool,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    nodes = graph.get("nodes", []) if graph else []
    edges = graph.get("edges", []) if graph else []

    node_type_filter = {t for t in (node_types or [])}
    edge_type_filter = {t for t in (edge_types or [])}

    def node_passes(node: Dict[str, Any]) -> bool:
        data = node.get("data", {})
        node_type = data.get("type")
        weight = data.get("weight", 0)
        if hide_page_nodes and node_type == "Page":
            return False
        if node_type_filter and node_type not in node_type_filter:
            return False
        return weight >= (min_node_weight or 0)

    def edge_passes(edge: Dict[str, Any]) -> bool:
        data = edge.get("data", {})
        edge_type = data.get("type")
        weight = data.get("weight", 0)
        if edge_type_filter and edge_type not in edge_type_filter:
            return False
        return weight >= (min_edge_weight or 0)

    candidate_nodes = [node for node in nodes if node_passes(node)]
    candidate_edges = [edge for edge in edges if edge_passes(edge)]

    nodes_by_id = {node["data"]["id"]: node for node in nodes}
    filtered_node_ids = {node["data"]["id"] for node in candidate_nodes}

    edge_node_ids = {
        node_id
        for edge in candidate_edges
        for node_id in (edge["data"].get("source"), edge["data"].get("target"))
        if node_id
    }

    if keep_context_nodes:
        context_node_ids = set()
        for edge in candidate_edges:
            source = edge["data"].get("source")
            target = edge["data"].get("target")
            if source in filtered_node_ids or target in filtered_node_ids:
                if source:
                    context_node_ids.add(source)
                if target:
                    context_node_ids.add(target)
        filtered_node_ids |= context_node_ids

    filtered_node_ids |= edge_node_ids

    filtered_nodes = [
        nodes_by_id[node_id]
        for node_id in sorted(filtered_node_ids)
        if node_id in nodes_by_id and node_passes(nodes_by_id[node_id])
    ]

    filtered_edges = [
        edge
        for edge in candidate_edges
        if edge["data"].get("source") in filtered_node_ids
        and edge["data"].get("target") in filtered_node_ids
    ]

    if hide_isolated_nodes:
        connected = set()
        for edge in filtered_edges:
            connected.add(edge["data"].get("source"))
            connected.add(edge["data"].get("target"))
        filtered_nodes = [node for node in filtered_nodes if node["data"]["id"] in connected]

    return filtered_nodes, filtered_edges


def _apply_highlight(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    highlight_ids: Iterable[str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    highlight_set = {hid for hid in (highlight_ids or [])}
    if not highlight_set:
        return nodes, edges

    highlighted_nodes = []
    for node in nodes:
        node_id = node.get("data", {}).get("id")
        classes = node.get("classes", "")
        if node_id in highlight_set:
            classes = f"{classes} highlight".strip()
        else:
            classes = f"{classes} dimmed".strip()
        highlighted_nodes.append({**node, "classes": classes})

    highlighted_edges = []
    for edge in edges:
        data = edge.get("data", {})
        classes = edge.get("classes", "")
        if data.get("source") in highlight_set or data.get("target") in highlight_set:
            classes = f"{classes} highlight".strip()
        else:
            classes = f"{classes} dimmed".strip()
        highlighted_edges.append({**edge, "classes": classes})

    return highlighted_nodes, highlighted_edges


def _group_connections(
    edges: List[Dict[str, Any]],
    node_id: str,
) -> Dict[str, List[str]]:
    groups: Dict[str, List[str]] = {}
    for edge in edges:
        data = edge.get("data", {})
        edge_type = data.get("type")
        source = data.get("source")
        target = data.get("target")
        if source == node_id:
            key = f"Outgoing::{edge_type}"
            groups.setdefault(key, []).append(target)
        elif target == node_id:
            key = f"Incoming::{edge_type}"
            groups.setdefault(key, []).append(source)
    return groups


def _export_rows(graph: Dict[str, Any]) -> Tuple[List[List[Any]], List[List[Any]]]:
    nodes = graph.get("nodes", []) if graph else []
    edges = graph.get("edges", []) if graph else []
    node_lookup = {node["data"]["id"]: node for node in nodes}

    node_rows = [["Node Type", "Name", "Description", "Image", "Weight"]]
    for node in nodes:
        data = node.get("data", {})
        node_rows.append(
            [
                data.get("type", ""),
                data.get("label", ""),
                data.get("description", ""),
                data.get("image", ""),
                data.get("weight", 0),
            ]
        )

    edge_rows = [["From Type", "From Name", "Edge Type", "To Type", "To Name", "Weight"]]
    for edge in edges:
        data = edge.get("data", {})
        source = node_lookup.get(data.get("source"), {}).get("data", {})
        target = node_lookup.get(data.get("target"), {}).get("data", {})
        edge_rows.append(
            [
                source.get("type", ""),
                source.get("label", ""),
                data.get("type", ""),
                target.get("type", ""),
                target.get("label", ""),
                data.get("weight", 0),
            ]
        )

    return node_rows, edge_rows


def _csv_bytes(rows: List[List[Any]]) -> bytes:
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _xlsx_bytes(sheets: Dict[str, List[List[Any]]]) -> bytes:
    import io
    import zipfile

    def column_name(index: int) -> str:
        name = ""
        while index:
            index, rem = divmod(index - 1, 26)
            name = chr(65 + rem) + name
        return name

    def xml_escape(value: str) -> str:
        return (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\"", "&quot;")
            .replace("'", "&apos;")
        )

    shared_strings: List[str] = []
    shared_index: Dict[str, int] = {}

    def shared_string(value: str) -> int:
        if value not in shared_index:
            shared_index[value] = len(shared_strings)
            shared_strings.append(value)
        return shared_index[value]

    worksheets = {}
    for sheet_index, (sheet_name, rows) in enumerate(sheets.items(), start=1):
        row_xml = []
        for row_idx, row in enumerate(rows, start=1):
            cell_xml = []
            for col_idx, value in enumerate(row, start=1):
                cell_ref = f"{column_name(col_idx)}{row_idx}"
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    cell_xml.append(f"<c r=\"{cell_ref}\"><v>{value}</v></c>")
                else:
                    idx = shared_string(xml_escape(str(value)))
                    cell_xml.append(f"<c r=\"{cell_ref}\" t=\"s\"><v>{idx}</v></c>")
            row_xml.append(f"<row r=\"{row_idx}\">{''.join(cell_xml)}</row>")
        worksheet_xml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
            f"<sheetData>{''.join(row_xml)}</sheetData>"
            "</worksheet>"
        )
        worksheets[f"xl/worksheets/sheet{sheet_index}.xml"] = worksheet_xml

    shared_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<sst xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
        f"count=\"{len(shared_strings)}\" uniqueCount=\"{len(shared_strings)}\">"
        + "".join(f"<si><t>{value}</t></si>" for value in shared_strings)
        + "</sst>"
    )

    workbook_sheets = []
    rels = []
    for index, sheet_name in enumerate(sheets.keys(), start=1):
        workbook_sheets.append(
            f"<sheet name=\"{sheet_name}\" sheetId=\"{index}\" r:id=\"rId{index}\"/>"
        )
        rels.append(
            f"<Relationship Id=\"rId{index}\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet{index}.xml\"/>"
        )

    workbook_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
        "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">"
        f"<sheets>{''.join(workbook_sheets)}</sheets>"
        "</workbook>"
    )

    workbook_rels_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        + "".join(rels)
        + "</Relationships>"
    )

    rels_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/>"
        "</Relationships>"
    )

    content_types = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
        "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
        "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
        "<Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>"
        "<Override PartName=\"/xl/sharedStrings.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml\"/>"
        + "".join(
            f"<Override PartName=\"/xl/worksheets/sheet{index}.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>"
            for index in range(1, len(sheets) + 1)
        )
        + "</Types>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels_xml)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        archive.writestr("xl/sharedStrings.xml", shared_xml)
        for path, data in worksheets.items():
            archive.writestr(path, data)

    return buffer.getvalue()


# -------------------------------------------------
# Layout + Styles
# -------------------------------------------------
LAYOUTS = [
    ("Dagre (sequence)", "dagre"),
    ("Breadthfirst", "breadthfirst"),
    ("Force-directed (COSE)", "cose"),
    ("COSE-Bilkent", "cose-bilkent"),
    ("Cola (read text)", "cola"),
    ("Euler (quality force)", "euler"),
]


def layout_for(name: str, scaling_ratio: int) -> Dict[str, Any]:
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


# -------------------------------------------------
# App + Defaults
# -------------------------------------------------
files = list_docling_files()

DEFAULT_VIEW = {
    "layout": "dagre",
    "scaling_ratio": 250,
    "show_edge_labels": False,
    "show_arrows": True,
    "scale_node_size": True,
    "scale_edge_width": True,
}

DEFAULT_THEME = "dark"

app = Dash(
    __name__,
    title="Docling Graph Viewer",
    assets_folder=os.path.join(APP_DIR, "assets"),
)
server = app.server


# -------------------------------------------------
# Layout
# -------------------------------------------------
app.layout = html.Div(
    className="docling-app",
    children=[
        dcc.Store(id="store_graph"),
        dcc.Store(id="store_filtered_graph"),
        dcc.Store(id="store_metadata"),
        dcc.Store(id="store_selected_node"),
        dcc.Store(id="store_inspector_expansion", data={}),
        dcc.Store(id="store_highlight", data=[]),
        dcc.Store(id="store_theme", data=DEFAULT_THEME),
        dcc.Download(id="download-export"),
        html.Div(
            className="app-grid",
            children=[
                html.Div(
                    className="panel-left",
                    children=[
                        html.Div("Graph controls", className="panel-title"),
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
                                html.Div("Search", className="control-label"),
                                dcc.Dropdown(
                                    id="search_node",
                                    options=[],
                                    placeholder="Search by node name",
                                    clearable=True,
                                ),
                            ],
                        ),
                        html.Div(
                            className="control-section",
                            children=[
                                html.Div("Node Types", className="control-label"),
                                dcc.Dropdown(
                                    id="node_type_filter",
                                    options=[],
                                    multi=True,
                                    placeholder="Filter node types",
                                ),
                            ],
                        ),
                        html.Div(
                            className="control-section",
                            children=[
                                html.Div("Edge Types", className="control-label"),
                                dcc.Dropdown(
                                    id="edge_type_filter",
                                    options=[],
                                    multi=True,
                                    placeholder="Filter edge types",
                                ),
                            ],
                        ),
                        html.Div(
                            className="control-section",
                            children=[
                                html.Div("Min node weight", className="control-label"),
                                dcc.Slider(
                                    id="min_node_weight",
                                    min=0,
                                    max=25,
                                    step=1,
                                    value=0,
                                ),
                            ],
                        ),
                        html.Div(
                            className="control-section",
                            children=[
                                html.Div("Min edge weight", className="control-label"),
                                dcc.Slider(
                                    id="min_edge_weight",
                                    min=0,
                                    max=10,
                                    step=1,
                                    value=0,
                                ),
                            ],
                        ),
                        html.Div(
                            className="control-section",
                            children=[
                                dcc.Checklist(
                                    id="graph_toggles",
                                    options=[
                                        {"label": " Hide Page nodes", "value": "hide_pages"},
                                        {"label": " Hide isolated nodes", "value": "hide_isolated"},
                                        {"label": " Show edge labels", "value": "edge_labels"},
                                        {"label": " Show arrows", "value": "arrows"},
                                        {"label": " Keep context nodes", "value": "keep_context"},
                                        {"label": " Scale node size", "value": "scale_node"},
                                        {"label": " Scale edge width", "value": "scale_edge"},
                                    ],
                                    value=[
                                        "arrows",
                                        "scale_node",
                                        "scale_edge",
                                    ],
                                    inputClassName="control-checkbox",
                                    labelClassName="control-checkbox__label",
                                )
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
                                html.Button("Reset view", id="reset_view", className="btn-primary"),
                            ],
                        ),
                        html.Div(
                            className="control-section",
                            children=[
                                html.Button("Export CSV", id="export_csv", className="btn"),
                                html.Button("Export XLSX", id="export_xlsx", className="btn"),
                            ],
                        ),
                    ],
                ),
                html.Div(
                    className="panel-main",
                    children=[
                        cyto.Cytoscape(
                            id="graph",
                            style={
                                "width": "100%",
                                "height": "85vh",
                                "backgroundColor": "var(--gc-graph-bg)",
                            },
                            wheelSensitivity=0.01,
                            minZoom=0.25,
                            maxZoom=2.0,
                            layout=layout_for(
                                DEFAULT_VIEW["layout"],
                                DEFAULT_VIEW["scaling_ratio"],
                            ),
                            stylesheet=safe_base_stylesheet(
                                DEFAULT_THEME,
                                DEFAULT_VIEW["scale_node_size"],
                                DEFAULT_VIEW["scale_edge_width"],
                                DEFAULT_VIEW["show_edge_labels"],
                                DEFAULT_VIEW["show_arrows"],
                            ),
                            elements=[],
                        ),
                    ],
                ),
                html.Div(
                    className="panel-right",
                    children=[
                        html.Div("Inspector", className="panel-title"),
                        html.Div(id="inspector_panel", className="inspector-panel"),
                        html.Button("Reset highlights", id="reset_highlight", className="btn"),
                    ],
                ),
            ],
        ),
        html.Div(
            className="debug-panel",
            children=[
                html.Div("Debug JSON", className="panel-title"),
                html.Pre(id="tap-node-json-output", className="debug-output"),
                html.Pre(id="tap-edge-json-output", className="debug-output"),
            ],
        ),
    ],
)


# -------------------------------------------------
# Callbacks
# -------------------------------------------------
@app.callback(
    Output("graph", "elements"),
    Output("store_graph", "data"),
    Output("store_metadata", "data"),
    Input("file", "value"),
)
def load_graph(path):
    if not path:
        return [], None, None

    graph = build_graph_from_docling_json(path)
    node_types = sorted({n["data"].get("type", "") for n in graph.nodes})
    edge_types = sorted({e["data"].get("type", "") for e in graph.edges})
    search_options = [
        {"label": n["data"].get("label"), "value": n["data"].get("id")}
        for n in graph.nodes
    ]
    metadata = {
        "node_types": node_types,
        "edge_types": edge_types,
        "search_options": search_options,
    }
    store_graph = {"nodes": graph.nodes, "edges": graph.edges}
    return [], store_graph, metadata


@app.callback(
    Output("node_type_filter", "options"),
    Output("edge_type_filter", "options"),
    Output("search_node", "options"),
    Input("store_metadata", "data"),
)
def update_filters(metadata):
    if not metadata:
        return [], [], []
    node_options = [{"label": t, "value": t} for t in metadata.get("node_types", [])]
    edge_options = [{"label": t, "value": t} for t in metadata.get("edge_types", [])]
    return node_options, edge_options, metadata.get("search_options", [])


@app.callback(
    Output("graph", "elements", allow_duplicate=True),
    Output("store_filtered_graph", "data"),
    Input("store_graph", "data"),
    Input("node_type_filter", "value"),
    Input("edge_type_filter", "value"),
    Input("graph_toggles", "value"),
    Input("min_node_weight", "value"),
    Input("min_edge_weight", "value"),
    Input("store_theme", "data"),
    Input("store_highlight", "data"),
    prevent_initial_call=False,
)
def apply_filters(
    graph,
    node_types,
    edge_types,
    toggles,
    min_node_weight,
    min_edge_weight,
    theme,
    highlight_ids,
):
    if not graph:
        return [], None

    toggles = toggles or []
    hide_page_nodes = "hide_pages" in toggles
    hide_isolated = "hide_isolated" in toggles
    keep_context = "keep_context" in toggles

    nodes, edges = _filter_graph(
        graph,
        node_types,
        edge_types,
        hide_page_nodes,
        hide_isolated,
        min_node_weight or 0,
        min_edge_weight or 0,
        keep_context,
    )

    themed_nodes, themed_edges = apply_theme_to_elements(nodes, edges, theme or DEFAULT_THEME)
    themed_nodes, themed_edges = _apply_highlight(themed_nodes, themed_edges, highlight_ids)

    filtered_graph = {"nodes": themed_nodes, "edges": themed_edges}
    return themed_nodes + themed_edges, filtered_graph


@app.callback(
    Output("graph", "layout"),
    Input("layout", "value"),
    Input("scaling_ratio", "value"),
)
def update_layout(name, scaling):
    return layout_for(name, scaling)


@app.callback(
    Output("graph", "stylesheet"),
    Input("graph_toggles", "value"),
    Input("store_theme", "data"),
)
def update_styles(toggles, theme):
    toggles = toggles or []
    return safe_base_stylesheet(
        theme or DEFAULT_THEME,
        "scale_node" in toggles,
        "scale_edge" in toggles,
        "edge_labels" in toggles,
        "arrows" in toggles,
    )


@app.callback(
    Output("store_selected_node", "data"),
    Input("graph", "tapNodeData"),
    Input("search_node", "value"),
    State("store_filtered_graph", "data"),
    prevent_initial_call=True,
)
def select_node(tap_node, search_value, filtered_graph):
    trigger = ctx.triggered_id
    if trigger == "search_node" and search_value:
        return search_value
    if tap_node and tap_node.get("id"):
        return tap_node["id"]
    return no_update


@app.callback(
    Output("inspector_panel", "children"),
    Input("store_filtered_graph", "data"),
    Input("store_selected_node", "data"),
    Input("store_inspector_expansion", "data"),
)
def render_inspector(filtered_graph, selected_node_id, expansion_state):
    if not filtered_graph or not selected_node_id:
        return html.Div("Select a node to inspect.", className="muted")

    nodes = filtered_graph.get("nodes", [])
    edges = filtered_graph.get("edges", [])
    node_lookup = {node["data"]["id"]: node for node in nodes}
    node = node_lookup.get(selected_node_id)
    if not node:
        return html.Div("Select a node to inspect.", className="muted")

    data = node.get("data", {})
    groups = _group_connections(edges, selected_node_id)
    expansion_state = expansion_state or {}

    group_blocks = []
    for group_key in sorted(groups.keys()):
        direction, edge_type = group_key.split("::", 1)
        node_ids = groups[group_key]
        total = len(node_ids)
        shown = expansion_state.get(group_key, 10)
        display_ids = node_ids[:shown]

        connections = []
        for nid in display_ids:
            target_node = node_lookup.get(nid)
            label = target_node.get("data", {}).get("label", nid) if target_node else nid
            connections.append(html.Div(label, className="inspector-item"))

        footer = None
        if shown < total:
            footer = html.Button(
                f"Show more (+25)",
                id={"type": "expand-group", "group": group_key},
                className="btn-small",
            )

        group_blocks.append(
            html.Div(
                className="inspector-group",
                children=[
                    html.Div(
                        f"{direction} → {edge_type} ({total})",
                        className="inspector-group-title",
                    ),
                    html.Div(connections, className="inspector-list"),
                    footer,
                ],
            )
        )

    if not group_blocks:
        group_blocks.append(html.Div("No connections in current filter.", className="muted"))

    return html.Div(
        children=[
            html.Div(data.get("label", ""), className="inspector-title"),
            html.Div(data.get("type", ""), className="inspector-subtitle"),
            html.Div(data.get("description", ""), className="inspector-description"),
            html.Div(group_blocks),
        ]
    )


@app.callback(
    Output("store_inspector_expansion", "data"),
    Output("store_highlight", "data"),
    Input({"type": "expand-group", "group": ALL}, "n_clicks"),
    Input("reset_highlight", "n_clicks"),
    State("store_inspector_expansion", "data"),
    State("store_filtered_graph", "data"),
    State("store_selected_node", "data"),
    prevent_initial_call=True,
)
def update_expansion(
    _clicks,
    reset_clicks,
    expansion_state,
    filtered_graph,
    selected_node_id,
):
    if ctx.triggered_id == "reset_highlight":
        return {}, []

    triggered = ctx.triggered_id
    if not isinstance(triggered, dict):
        return no_update, no_update

    group_key = triggered.get("group")
    expansion_state = expansion_state or {}
    current = expansion_state.get(group_key, 10)
    expansion_state[group_key] = current + 25

    highlight_ids: List[str] = []
    if filtered_graph and selected_node_id:
        groups = _group_connections(filtered_graph.get("edges", []), selected_node_id)
        highlight_ids = [selected_node_id] + groups.get(group_key, [])

    return expansion_state, highlight_ids


@app.callback(
    Output("graph", "elements", allow_duplicate=True),
    Output("graph", "elements", allow_duplicate=True),
    Output("store_selected_node", "data", allow_duplicate=True),
    Output("store_highlight", "data", allow_duplicate=True),
    Input("reset_view", "n_clicks"),
    State("store_filtered_graph", "data"),
    State("store_theme", "data"),
    prevent_initial_call=True,
)
def reset_view(_n_clicks, filtered_graph, theme):
    if not filtered_graph:
        return no_update, no_update, no_update
    nodes = filtered_graph.get("nodes", [])
    edges = filtered_graph.get("edges", [])
    themed_nodes, themed_edges = apply_theme_to_elements(nodes, edges, theme or DEFAULT_THEME)
    return themed_nodes + themed_edges, None, []


@app.callback(
    Output("download-export", "data"),
    Input("export_csv", "n_clicks"),
    Input("export_xlsx", "n_clicks"),
    State("store_filtered_graph", "data"),
    prevent_initial_call=True,
)
def export_graph(csv_clicks, xlsx_clicks, filtered_graph):
    if not filtered_graph:
        return no_update

    nodes_rows, edge_rows = _export_rows(filtered_graph)
    if ctx.triggered_id == "export_csv":
        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("graph_nodes.csv", _csv_bytes(nodes_rows))
            archive.writestr("graph_edges.csv", _csv_bytes(edge_rows))
        return dcc.send_bytes(buffer.getvalue(), "graph_export.zip")

    xlsx_bytes = _xlsx_bytes({"Nodes": nodes_rows, "Edges": edge_rows})
    return dcc.send_bytes(xlsx_bytes, "graph_export.xlsx")


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
