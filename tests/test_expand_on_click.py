from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path

import pytest

from tests.helpers import build_graph_state


FIXTURE = Path(__file__).parent / "fixtures" / "docling" / "regulations" / "uksi-2010-2214-regulation-38.json"


def _install_dash_stubs():
    if "dash" not in sys.modules:
        dash_stub = types.ModuleType("dash")

        class _Element:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        class _Namespace:
            def __getattr__(self, _name):
                return _Element

        class _Server:
            def __init__(self):
                self.routes = {}

            def route(self, path, **_kwargs):
                def decorator(func):
                    self.routes[path] = func
                    return func

                return decorator

        class _IO:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        class Dash:
            def __init__(self, *args, **kwargs):
                self.server = _Server()

            def callback(self, *args, **kwargs):
                def decorator(func):
                    return func

                return decorator

            def run(self, *args, **kwargs):
                return None

        dash_stub.Dash = Dash
        dash_stub.html = _Namespace()
        dash_stub.dcc = _Namespace()
        dash_stub.Input = _IO
        dash_stub.Output = _IO
        dash_stub.State = _IO
        dash_stub.no_update = object()
        sys.modules["dash"] = dash_stub
    else:
        dash_stub = sys.modules["dash"]

    if "dash_cytoscape" not in sys.modules:
        dash_cytoscape_stub = types.ModuleType("dash_cytoscape")
        dash_cytoscape_stub.Cytoscape = dash_stub.html.__getattr__("cytoscape")  # type: ignore[arg-type]
        dash_cytoscape_stub.load_extra_layouts = lambda: None
        sys.modules["dash_cytoscape"] = dash_cytoscape_stub

    if "flask" not in sys.modules:
        flask_stub = types.ModuleType("flask")

        class Response:
            def __init__(self, data=None, mimetype=None):
                self.data = data or ""
                self.mimetype = mimetype
                self.headers = {}

            def get_json(self):
                try:
                    return json.loads(self.data)
                except Exception:
                    return None

        flask_stub.Response = Response
        sys.modules["flask"] = flask_stub

    return sys.modules["dash"].no_update  # type: ignore[attr-defined]


def _assert_root_connections(result, root_id):
    nodes = {
        element["data"]["id"]
        for element in result
        if "source" not in element.get("data", {})
    }
    edges = [element for element in result if "source" in element.get("data", {})]

    assert root_id in nodes

    root_edges = [
        edge for edge in edges if edge["data"].get("source") == root_id or edge["data"].get("target") == root_id
    ]
    assert root_edges

    for edge in root_edges:
        assert edge["data"]["source"] in nodes
        assert edge["data"]["target"] in nodes


@pytest.mark.parametrize("elements", [None, []])
@pytest.mark.parametrize("page_range_override", [None, "fixture"])
def test_expand_on_click_handles_missing_elements_and_page_ranges(elements, page_range_override):
    document_node, store_graph, node_index, page_range = build_graph_state(FIXTURE)

    no_update = _install_dash_stubs()
    sys.modules.pop("apps.docling_graph.main", None)
    main = importlib.import_module("apps.docling_graph.main")

    selected_page_range = page_range if page_range_override == "fixture" else None

    result = main.expand_on_click(
        document_node["data"],
        elements,
        store_graph,
        node_index,
        mode="children",
        page_range=selected_page_range,
    )

    assert result is not no_update

    _assert_root_connections(result, document_node["data"]["id"])


def test_expand_on_click_handles_empty_graph_state():
    document_node, store_graph, node_index, _page_range = build_graph_state(FIXTURE)

    no_update = _install_dash_stubs()
    sys.modules.pop("apps.docling_graph.main", None)
    main = importlib.import_module("apps.docling_graph.main")

    result = main.expand_on_click(
        document_node["data"],
        elements=None,
        store_graph={},
        node_index=None,
        mode="children",
        page_range=None,
    )

    assert result is no_update


def test_expand_on_click_returns_related_edges_for_non_document_nodes():
    document_node, store_graph, node_index, _page_range = build_graph_state(FIXTURE)

    no_update = _install_dash_stubs()
    sys.modules.pop("apps.docling_graph.main", None)
    main = importlib.import_module("apps.docling_graph.main")

    target_edge = next(
        ed
        for ed in store_graph["edges"]
        if ed["data"].get("rel") in {"parent", "children", "captions"}
    )
    node_id = target_edge["data"]["source"]

    result = main.expand_on_click(
        node_index[node_id]["data"],
        elements=[],
        store_graph=store_graph,
        node_index=node_index,
        mode="children",
        page_range=None,
    )

    assert result is not no_update

    nodes = {
        element["data"]["id"]
        for element in result
        if "source" not in element.get("data", {})
    }
    edge_ids = {
        element["data"]["id"]
        for element in result
        if "source" in element.get("data", {})
    }

    assert target_edge["data"]["id"] in edge_ids
    assert target_edge["data"]["source"] in nodes
    assert target_edge["data"]["target"] in nodes
