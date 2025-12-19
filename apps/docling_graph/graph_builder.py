from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
import math
from typing import Any, Dict, List, Optional, Tuple

from .theme import get_node_colors

DOCLING_JSON_ROOT = "/home/hp/docling-ws/data/docling"

MIN_TEXT_LEN = 40
MAX_TEXTS_PER_PAGE = 250

SKIP_TEXT_LABELS = {
    "page_header",
    "page_footer",
    "header",
    "footer",
    "footnote",
    "pagenum",
    "page_number",
    "artifact",
    "decorative",
}


# -----------------------------
# Graph contract
# -----------------------------
@dataclass(frozen=True)
class GraphPayload:
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]


# -----------------------------
# Helpers
# -----------------------------
def _nid(value: str) -> str:
    return "n_" + hashlib.md5(value.encode("utf-8")).hexdigest()[:12]


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _first_prov(item: Dict[str, Any]) -> Tuple[Optional[int], Optional[Any]]:
    prov = item.get("prov") or item.get("provenance") or item.get("provenances")
    if isinstance(prov, list) and prov:
        p0 = prov[0]
        if isinstance(p0, dict):
            return p0.get("page_no"), p0.get("bbox")
    return None, None


def _short(text: str, limit: int = 120) -> str:
    t = (text or "").replace("\n", " ").strip()
    return t[:limit] + ("…" if len(t) > limit else "")


def list_docling_files(json_root: Optional[str] = None) -> List[str]:
    results: List[str] = []
    search_root = json_root or DOCLING_JSON_ROOT

    for root, _, files in os.walk(search_root):
        for name in files:
            if name.lower().endswith(".json"):
                results.append(os.path.join(root, name))
    return sorted(results)


def _is_noise_text(label: str, text: str) -> bool:
    lbl = (label or "").strip().lower()
    t = (text or "").strip()

    if not t:
        return True
    if MIN_TEXT_LEN is not None and len(t) < MIN_TEXT_LEN:
        return True
    if lbl in SKIP_TEXT_LABELS:
        return True
    return False


# -----------------------------
# Core builder
# -----------------------------
def _collect_pages_from_texts(texts: Iterable[Any]) -> Dict[int, List[Dict[str, Any]]]:
    pages: Dict[int, List[Dict[str, Any]]] = {}

    if not isinstance(texts, Iterable):
        return pages

    for t in texts:
        if not isinstance(t, dict):
            continue

        raw_label = str(t.get("label") or "text")
        raw_text = str(t.get("text") or "")

        if _is_noise_text(raw_label, raw_text):
            continue

        page_no, _ = _first_prov(t)
        if page_no is None:
            continue

        pages.setdefault(page_no, []).append(t)

    return pages


def build_graph_from_docling_json(path: str) -> GraphPayload:
    """
    Graph shape:
        DOCUMENT → PAGE → TEXT

    Nodes and edges are returned separately
    for Cytoscape stability and incremental expansion.
    """
    doc = _load_json(path)

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    doc_id = _nid(path)
    body_id = _nid(f"{path}::body")
    doc_name = os.path.basename(path)

    # DOCUMENT node
    nodes.append(
        {
            "data": {
                "id": doc_id,
                "type": "Document",
                "name": doc_name,
                "label_short": f"DOCUMENT: {doc_name}",
                "label_full": f"DOCUMENT: {doc_name}",
                "label": f"DOCUMENT: {doc_name}",
            },
            "classes": "document",
        }
    )

    nodes.append(
        {
            "data": {
                "id": body_id,
                "type": "Body",
                "name": "Body",
                "label_short": "BODY",
                "label_full": "BODY",
                "label": "BODY",
            },
            "classes": "body",
        }
    )

    edges.append(
        {
            "data": {
                "id": _nid(f"{doc_id}__{body_id}__HAS_BODY"),
                "source": doc_id,
                "target": body_id,
                "rel": "HAS_BODY",
                "type": "HAS_BODY",
            },
            "classes": "has-body",
        }
    )

    pages = _collect_pages_from_texts(doc.get("texts"))

    # PAGE + TEXT nodes
    for page_no in sorted(pages.keys()):
        page_id = _nid(f"{path}::page::{page_no}")

        nodes.append(
            {
                "data": {
                    "id": page_id,
                    "type": "Page",
                    "name": f"Page {page_no}",
                    "page": page_no,
                    "label_short": f"PAGE {page_no}",
                    "label_full": f"PAGE {page_no}",
                    "label": f"PAGE {page_no}",
                },
                "classes": "page",
            }
        )

        edges.append(
            {
                "data": {
                    "id": _nid(f"{doc_id}__{page_id}__HAS_PAGE"),
                    "source": doc_id,
                    "target": page_id,
                    "rel": "HAS_PAGE",
                    "type": "HAS_PAGE",
                },
                "classes": "has-page",
            }
        )

        page_texts = pages[page_no][:MAX_TEXTS_PER_PAGE]
        previous_text_id: Optional[str] = None

        for t in page_texts:
            ref = t.get("self_ref") or t.get("id") or repr(t)
            text_id = _nid(ref)

            raw_text = str(t.get("text") or "")
            dtype = str(t.get("label") or "text").upper()
            content_layer = t.get("content_layer")
            _, bbox = _first_prov(t)

            label_full = f"{dtype}: {raw_text}"
            label_short = f"{dtype}: {_short(raw_text, 140)}"

            nodes.append(
                {
                    "data": {
                        "id": text_id,
                        "type": dtype,
                        "name": _short(raw_text, 140),
                        "content_layer": content_layer,
                        "text": raw_text,
                        "page": page_no,
                        "bbox": bbox,
                        "label_short": label_short,
                        "label_full": label_full,
                        "label": label_full,
                    },
                    "classes": "text",
                }
            )

            edges.append(
                {
                    "data": {
                        "id": _nid(f"{body_id}__{text_id}__CONTAINS"),
                        "source": body_id,
                        "target": text_id,
                        "rel": "CONTAINS",
                        "type": "CONTAINS",
                    },
                    "classes": "contains",
                }
            )

            edges.append(
                {
                    "data": {
                        "id": _nid(f"{page_id}__{text_id}__ON_PAGE"),
                        "source": page_id,
                        "target": text_id,
                        "rel": "ON_PAGE",
                        "type": "ON_PAGE",
                    },
                    "classes": "on-page",
                }
            )

            if previous_text_id:
                edges.append(
                    {
                        "data": {
                            "id": _nid(f"{previous_text_id}__{text_id}__NEXT"),
                            "source": previous_text_id,
                            "target": text_id,
                            "rel": "NEXT",
                            "type": "NEXT",
                        },
                        "classes": "next",
                    }
                )

            previous_text_id = text_id

    _apply_weights(nodes, edges)

    return GraphPayload(nodes=nodes, edges=edges)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def _edge_weight(rel: str, target_node: Dict[str, Any]) -> float:
    if rel == "CONTAINS":
        text = str(target_node.get("data", {}).get("text") or "")
        if text:
            return _clamp(math.ceil(len(text) / 200), 1, 10)
        return 1
    return 1


def _apply_weights(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> None:
    node_index = {n["data"]["id"]: n for n in nodes}

    for edge in edges:
        data = edge["data"]
        source = node_index.get(data.get("source"), {}).get("data", {})
        target = node_index.get(data.get("target"), {}).get("data", {})
        weight = _edge_weight(data.get("rel"), target or {})
        data["weight"] = weight
        data["width"] = _clamp(1 + (weight * 0.5), 1, 8)
        data["edge_length"] = _clamp(120 - (weight * 8), 30, 200)
        data["source_name"] = source.get("name")
        data["source_type"] = source.get("type")
        data["target_name"] = target.get("name")
        data["target_type"] = target.get("type")

    child_edges = {"HAS_PAGE", "HAS_BODY", "CONTAINS", "ON_PAGE"}
    children_count: Dict[str, int] = {}
    degree: Dict[str, int] = {}

    for edge in edges:
        src = edge["data"].get("source")
        tgt = edge["data"].get("target")
        rel = edge["data"].get("rel")
        degree[src] = degree.get(src, 0) + 1
        degree[tgt] = degree.get(tgt, 0) + 1
        if rel in child_edges:
            children_count[src] = children_count.get(src, 0) + 1

    for node in nodes:
        data = node["data"]
        node_id = data["id"]
        text = str(data.get("text") or "")
        text_len = len(text)
        count_children = children_count.get(node_id, 0)
        deg = degree.get(node_id, 0)
        content = min(5, text_len / 500) if text else 0
        connectivity = min(5, math.log1p(deg))
        weight = 1 + (count_children * 0.25) + content + connectivity
        data["text_length"] = text_len
        data["children_count"] = count_children
        data["degree"] = deg
        data["weight"] = weight

    for node in nodes:
        data = node["data"]
        if data.get("type") not in {"Document", "Body"}:
            continue
        node_id = data["id"]
        child_weights = [
            node_index[edge["data"]["target"]]["data"]["weight"]
            for edge in edges
            if edge["data"].get("source") == node_id
        ]
        if child_weights:
            top_weights = sorted(child_weights, reverse=True)[:5]
            data["weight"] = max(top_weights) + 1

    for node in nodes:
        data = node["data"]
        weight = float(data.get("weight") or 1)
        data["size"] = _clamp(20 + (weight * 6), 20, 80)
        colors = get_node_colors(data.get("type"))
        data["color_light"] = colors["light"]
        data["color_dark"] = colors["dark"]


# -----------------------------
# Tests
# -----------------------------


class GraphBuilderTests(unittest.TestCase):
    def test_is_noise_text_filters_short_or_skipped_labels(self):
        self.assertTrue(_is_noise_text("body", "too short"))
        self.assertTrue(_is_noise_text("header", "x" * (MIN_TEXT_LEN + 5)))
        self.assertFalse(_is_noise_text("body", "x" * (MIN_TEXT_LEN + 5)))

    def test_collect_pages_from_texts_filters_invalid_entries(self):
        long_text = "content " * 10
        pages = _collect_pages_from_texts(
            [
                {"label": "body", "text": long_text, "prov": [{"page_no": 2}]},
                {"label": "header", "text": long_text, "prov": [{"page_no": 3}]},
                {"label": "body", "text": "", "prov": [{"page_no": 4}]},
                "not a dict",
                {"label": "body", "text": long_text},
            ]
        )

        self.assertEqual(sorted(pages.keys()), [2])
        self.assertEqual(len(pages[2]), 1)

    def test_build_graph_from_docling_json_emits_document_page_and_text(self):
        doc = {
            "texts": [
                {
                    "label": "body",
                    "text": "paragraph " * 10,
                    "prov": [{"page_no": 1, "bbox": [0, 0, 10, 10]}],
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(doc, tmp)
            tmp_path = tmp.name

        try:
            payload = build_graph_from_docling_json(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        self.assertEqual(len(payload.nodes), 4)
        self.assertEqual(len(payload.edges), 4)

        node_ids = {n["data"]["id"] for n in payload.nodes}
        edge_pairs = {(e["data"]["source"], e["data"]["target"]) for e in payload.edges}

        doc_id = _nid(tmp_path)
        body_id = _nid(f"{tmp_path}::body")
        page_id = _nid(f"{tmp_path}::page::1")
        text_id = next(n["data"]["id"] for n in payload.nodes if n["data"].get("text"))

        self.assertIn(doc_id, node_ids)
        self.assertIn(body_id, node_ids)
        self.assertIn(page_id, node_ids)
        self.assertEqual(
            edge_pairs,
            {(doc_id, body_id), (doc_id, page_id), (body_id, text_id), (page_id, text_id)},
        )

    def test_list_docling_files_accepts_custom_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = Path(tmpdir) / "nested"
            nested.mkdir()

            first = nested / "a.json"
            second = nested / "B.JSON"
            first.write_text("{}", encoding="utf-8")
            second.write_text("{}", encoding="utf-8")

            results = list_docling_files(str(tmpdir))

        self.assertEqual(results, sorted([str(first), str(second)]))


if __name__ == "__main__":
    unittest.main()
