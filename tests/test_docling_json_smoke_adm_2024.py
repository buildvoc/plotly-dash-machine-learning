import json
import sys
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.docling_graph.graph_builder import build_elements_from_docling_json


ADM_PATH = Path(
    "docling-ws/data/docling/building_standards/ADM__V2_Amendment_Booklet_2024.json"
)


def _normalize_doc_root(doc):
    if isinstance(doc, dict):
        for key in ("document", "doc"):
            candidate = doc.get(key)
            if isinstance(candidate, dict):
                return candidate
    return doc


def _node_id(item, path):
    for key in ("self_ref", "id", "uid"):
        value = item.get(key)
        if value:
            return str(value)
    label = str(item.get("label") or item.get("type") or "node")
    page_no = None
    prov = item.get("prov") or item.get("provenance") or item.get("provenances")
    if isinstance(prov, list) and prov:
        page_no = prov[0].get("page_no")
    return f"{label}::{'/'.join(str(p) for p in path)}::{page_no or 'na'}"


def _collect_nodes_and_edges(doc_root):
    nodes = {}
    edges = []
    seen = set()
    stack = [(doc_root, ("root",))]

    while stack:
        item, path = stack.pop()
        if isinstance(item, dict):
            item_id = id(item)
            if item_id in seen:
                continue
            seen.add(item_id)

            node_id = _node_id(item, path)
            nodes[node_id] = item

            children = item.get("children")
            if isinstance(children, list):
                for idx, child in enumerate(children):
                    if isinstance(child, dict):
                        child_path = path + ("children", idx)
                        child_id = _node_id(child, child_path)
                        edges.append((node_id, child_id))
                        stack.append((child, child_path))

            for key, value in item.items():
                if isinstance(value, (dict, list)) and key != "children":
                    stack.append((value, path + (key,)))

        elif isinstance(item, list):
            item_id = id(item)
            if item_id in seen:
                continue
            seen.add(item_id)
            for idx, child in enumerate(item):
                stack.append((child, path + (idx,)))

    return nodes, edges


def _has_provenance(item):
    prov = item.get("prov") or item.get("provenance") or item.get("provenances")
    if isinstance(prov, list):
        return any(isinstance(p, dict) and (p.get("page_no") or p.get("bbox")) for p in prov)
    if isinstance(prov, dict):
        return bool(prov.get("page_no") or prov.get("bbox"))
    return False


@pytest.mark.skipif(not ADM_PATH.exists(), reason="ADM_2024 fixture not available")
def test_docling_json_smoke_adm_2024():
    with ADM_PATH.open("r", encoding="utf-8") as handle:
        doc = json.load(handle)

    doc_root = _normalize_doc_root(doc)
    nodes, edges = _collect_nodes_and_edges(doc_root)

    assert nodes, "No nodes collected from ADM doc"
    assert edges, "No hierarchy edges collected from ADM doc"

    node_ids = set(nodes.keys())
    dangling = [edge for edge in edges if edge[0] not in node_ids or edge[1] not in node_ids]
    assert not dangling, f"Found dangling edges: {dangling[:5]}"

    provenance_count = sum(1 for item in nodes.values() if _has_provenance(item))
    if provenance_count == 0:
        warnings.warn("No provenance found in ADM doc nodes; allowed but should be verified", RuntimeWarning)


@pytest.mark.skipif(not ADM_PATH.exists(), reason="ADM_2024 fixture not available")
def test_graph_builder_elements_adm_2024():
    with ADM_PATH.open("r", encoding="utf-8") as handle:
        doc = json.load(handle)

    elements = build_elements_from_docling_json(doc, doc_name=ADM_PATH.name)

    assert isinstance(elements, list)
    node_ids = set()
    edge_count = 0

    for element in elements:
        data = element.get("data", {})
        if "source" in data:
            edge_count += 1
            assert data.get("source")
            assert data.get("target")
        else:
            node_id = data.get("id")
            assert node_id
            assert node_id not in node_ids
            node_ids.add(node_id)

    assert node_ids
    assert edge_count > 0
