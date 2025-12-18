from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from apps.docling_graph.graph_builder import build_graph_from_docling_json


def build_graph_state(fixture_path: Path | str) -> Tuple[dict, Dict[str, dict], Dict[str, dict], List[int] | None]:
    """Load a Docling fixture and return minimal state for ``expand_on_click``.

    This helper avoids Dash dependencies by constructing the inputs the callback
    expects directly from a fixture payload.
    """

    payload = build_graph_from_docling_json(str(fixture_path))
    store_graph = {"nodes": payload.nodes, "edges": payload.edges}
    node_index = {node["data"]["id"]: node for node in payload.nodes}

    document_node = next(
        (node for node in payload.nodes if node.get("data", {}).get("type") == "document"),
        None,
    )
    if not document_node:
        raise ValueError("Fixture payload did not include a document node")

    pages = sorted(
        {
            node.get("data", {}).get("page")
            for node in payload.nodes
            if node.get("data", {}).get("page") is not None
        }
    )

    page_range = [pages[0], pages[-1]] if pages else None

    return document_node, store_graph, node_index, page_range
