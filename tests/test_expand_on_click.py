from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

from tests.helpers import build_graph_state


FIXTURE = Path(__file__).parent / "fixtures" / "docling" / "regulations" / "uksi-2010-2214-regulation-38.json"


def _install_dash_stubs():
    dash_stub = types.ModuleType("dash")

    class _Element:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class _Namespace:
        def __getattr__(self, _name):
            return _Element

    class _IO:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class Dash:
        def __init__(self, *args, **kwargs):
            self.server = None

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

    dash_cytoscape_stub = types.ModuleType("dash_cytoscape")
    dash_cytoscape_stub.Cytoscape = _Element
    dash_cytoscape_stub.load_extra_layouts = lambda: None

    sys.modules.setdefault("dash", dash_stub)
    sys.modules.setdefault("dash_cytoscape", dash_cytoscape_stub)

    return dash_stub.no_update


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
