from __future__ import annotations

import json
import math
import os
import tempfile
import unittest
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


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

EDGE_CONTAINS = "CONTAINS"
EDGE_HAS_PAGE = "HAS_PAGE"
EDGE_HAS_BODY = "HAS_BODY"
EDGE_NEXT = "NEXT"
EDGE_ON_PAGE = "ON_PAGE"

NODE_DOCUMENT = "Document"
NODE_PAGE = "Page"
NODE_TEXT = "Text"


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

def _node_id(node_type: str, name: str) -> str:
    return f"{node_type}::{name}"


def _edge_id(
    from_type: str,
    from_name: str,
    edge_type: str,
    to_type: str,
    to_name: str,
) -> str:
    return f"{from_type}::{from_name}::{edge_type}::{to_type}::{to_name}"


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


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))


def _resolve_pointer(doc: Any, pointer: str) -> Any:
    current = doc
    for part in pointer.split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            try:
                idx = int(part)
            except ValueError:
                return None
            if idx >= len(current):
                return None
            current = current[idx]
        elif isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        else:
            return None
    return current


def resolve_refs(obj: Any, root: Any, seen: Optional[Dict[int, Any]] = None) -> Any:
    if seen is None:
        seen = {}

    obj_id = id(obj)
    if obj_id in seen:
        return seen[obj_id]

    if isinstance(obj, dict):
        if "$ref" in obj and isinstance(obj["$ref"], str):
            ref = obj["$ref"]
            if ref.startswith("#/"):
                resolved = _resolve_pointer(root, ref[2:])
                if resolved is not None:
                    resolved_value = resolve_refs(resolved, root, seen)
                    if len(obj) == 1:
                        return resolved_value
                    merged = {
                        **(resolved_value if isinstance(resolved_value, dict) else {}),
                        **{k: v for k, v in obj.items() if k != "$ref"},
                    }
                    return resolve_refs(merged, root, seen)
        resolved_dict = {}
        seen[obj_id] = resolved_dict
        for key, value in obj.items():
            resolved_dict[key] = resolve_refs(value, root, seen)
        return resolved_dict

    if isinstance(obj, list):
        resolved_list: List[Any] = []
        seen[obj_id] = resolved_list
        for item in obj:
            resolved_list.append(resolve_refs(item, root, seen))
        return resolved_list

    return obj


def list_docling_files(json_root: Optional[str] = None) -> List[str]:
    results: List[str] = []
    search_root = json_root or DOCLING_JSON_ROOT

    for root, _, files in os.walk(search_root):
        for name in files:
            if name.lower().endswith(".json"):
                results.append(os.path.join(root, name))
    return sorted(results)


# -----------------------------
# Core builder
# -----------------------------

def _collect_text_items(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    texts = doc.get("texts")
    if isinstance(texts, list):
        return [t for t in texts if isinstance(t, dict)]
    return []


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


def _bucket_text_length(text: str) -> int:
    if not text:
        return 1
    return int(_clamp(math.ceil(len(text) / 200), 1, 10))


def _compute_node_weights(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> None:
    outgoing = defaultdict(list)
    incoming = defaultdict(list)

    for edge in edges:
        data = edge.get("data", {})
        source = data.get("source")
        target = data.get("target")
        if source:
            outgoing[source].append(edge)
        if target:
            incoming[target].append(edge)

    for node in nodes:
        data = node.get("data", {})
        node_id = data.get("id")
        description = data.get("description", "") or ""
        text_score = min(10, math.ceil(len(description) / 200)) if description else 0
        children_score = len(outgoing.get(node_id, []))
        degree_score = len(outgoing.get(node_id, [])) + len(incoming.get(node_id, []))
        weight = 1 + children_score + text_score + (degree_score * 0.5)
        data["weight"] = round(weight, 2)
        data["size"] = round(_clamp(20 + weight * 3, 20, 80), 2)


def _compute_edge_weights(edges: List[Dict[str, Any]], node_lookup: Dict[str, Dict[str, Any]]) -> None:
    for edge in edges:
        data = edge.get("data", {})
        edge_type = data.get("type")
        weight = 1
        if edge_type == EDGE_CONTAINS:
            target = node_lookup.get(data.get("target"), {})
            description = target.get("data", {}).get("description", "")
            weight = _bucket_text_length(description)
        data["weight"] = weight
        data["width"] = round(_clamp(1 + weight * 0.7, 1, 8), 2)


def _normalize_doc_root(doc: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(doc, dict):
        for key in ("document", "doc"):
            candidate = doc.get(key)
            if isinstance(candidate, dict):
                return candidate
    return doc


def _build_graph(doc: Dict[str, Any], doc_name: str) -> GraphPayload:
    resolved_doc = resolve_refs(_normalize_doc_root(doc), doc)

    nodes_by_id: Dict[str, Dict[str, Any]] = {}
    edges_by_id: Dict[str, Dict[str, Any]] = {}

    doc_name = doc_name or resolved_doc.get("title") or "Docling Document"
    doc_node_id = _node_id(NODE_DOCUMENT, doc_name)
    nodes_by_id[doc_node_id] = {
        "data": {
            "id": doc_node_id,
            "label": doc_name,
            "type": NODE_DOCUMENT,
            "description": resolved_doc.get("title") or doc_name,
            "weight": 1,
            "size": 20,
        },
        "classes": "node-type-document",
    }

    texts = _collect_text_items(resolved_doc)
    pages = _collect_pages_from_texts(texts)

    page_ids: Dict[int, str] = {}

    for page_no in sorted(pages.keys()):
        page_name = f"Page {page_no}"
        page_id = _node_id(NODE_PAGE, page_name)
        page_ids[page_no] = page_id
        nodes_by_id[page_id] = {
            "data": {
                "id": page_id,
                "label": page_name,
                "type": NODE_PAGE,
                "description": f"Page {page_no} of {doc_name}",
                "weight": 1,
                "size": 20,
                "page": page_no,
            },
            "classes": "node-type-page",
        }

        edge_id = _edge_id(NODE_DOCUMENT, doc_name, EDGE_HAS_PAGE, NODE_PAGE, page_name)
        edges_by_id[edge_id] = {
            "data": {
                "id": edge_id,
                "source": doc_node_id,
                "target": page_id,
                "type": EDGE_HAS_PAGE,
            },
            "classes": "edge-type-has-page",
        }

    sorted_pages = sorted(page_ids.items())
    for index, (page_no, page_id) in enumerate(sorted_pages[:-1]):
        next_page_no, next_page_id = sorted_pages[index + 1]
        from_name = f"Page {page_no}"
        to_name = f"Page {next_page_no}"
        edge_id = _edge_id(NODE_PAGE, from_name, EDGE_NEXT, NODE_PAGE, to_name)
        edges_by_id[edge_id] = {
            "data": {
                "id": edge_id,
                "source": page_id,
                "target": next_page_id,
                "type": EDGE_NEXT,
            },
            "classes": "edge-type-next",
        }

    for page_no in sorted(pages.keys()):
        page_id = page_ids[page_no]
        page_name = f"Page {page_no}"
        page_texts = pages[page_no][:MAX_TEXTS_PER_PAGE]

        for idx, t in enumerate(page_texts, start=1):
            raw_text = str(t.get("text") or "")
            label = str(t.get("label") or "text").strip() or "text"
            name = f"p{page_no}-{idx}: {_short(raw_text, 80)}"
            text_id = _node_id(NODE_TEXT, name)

            nodes_by_id[text_id] = {
                "data": {
                    "id": text_id,
                    "label": name,
                    "type": NODE_TEXT,
                    "description": raw_text,
                    "weight": 1,
                    "size": 20,
                    "page": page_no,
                    "label_type": label,
                },
                "classes": "node-type-text",
            }

            contains_id = _edge_id(NODE_PAGE, page_name, EDGE_CONTAINS, NODE_TEXT, name)
            edges_by_id[contains_id] = {
                "data": {
                    "id": contains_id,
                    "source": page_id,
                    "target": text_id,
                    "type": EDGE_CONTAINS,
                },
                "classes": "edge-type-contains",
            }

            on_page_id = _edge_id(NODE_TEXT, name, EDGE_ON_PAGE, NODE_PAGE, page_name)
            edges_by_id[on_page_id] = {
                "data": {
                    "id": on_page_id,
                    "source": text_id,
                    "target": page_id,
                    "type": EDGE_ON_PAGE,
                },
                "classes": "edge-type-on-page",
            }

            has_body_id = _edge_id(NODE_DOCUMENT, doc_name, EDGE_HAS_BODY, NODE_TEXT, name)
            edges_by_id[has_body_id] = {
                "data": {
                    "id": has_body_id,
                    "source": doc_node_id,
                    "target": text_id,
                    "type": EDGE_HAS_BODY,
                },
                "classes": "edge-type-has-body",
            }

    nodes = list(nodes_by_id.values())
    edges = list(edges_by_id.values())
    node_lookup = {node["data"]["id"]: node for node in nodes}

    _compute_edge_weights(edges, node_lookup)
    _compute_node_weights(nodes, edges)

    nodes = sorted(nodes, key=lambda n: n.get("data", {}).get("id", ""))
    edges = sorted(edges, key=lambda e: e.get("data", {}).get("id", ""))

    return GraphPayload(nodes=nodes, edges=edges)


def build_graph_from_docling_json(path: str) -> GraphPayload:
    doc = _load_json(path)
    doc_name = os.path.basename(path)
    return _build_graph(doc, doc_name)


def build_elements_from_docling_json(doc: Dict[str, Any], doc_name: str | None = None) -> List[Dict[str, Any]]:
    graph = _build_graph(doc, doc_name or doc.get("title") or "Docling Document")
    return graph.nodes + graph.edges


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
            "title": "Example",
            "texts": [
                {
                    "label": "body",
                    "text": "paragraph " * 10,
                    "prov": [{"page_no": 1, "bbox": [0, 0, 10, 10]}],
                }
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(doc, tmp)
            tmp_path = tmp.name

        try:
            payload = build_graph_from_docling_json(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        node_types = {n["data"]["type"] for n in payload.nodes}
        edge_types = {e["data"]["type"] for e in payload.edges}

        self.assertIn(NODE_DOCUMENT, node_types)
        self.assertIn(NODE_PAGE, node_types)
        self.assertIn(NODE_TEXT, node_types)
        self.assertIn(EDGE_CONTAINS, edge_types)
        self.assertIn(EDGE_HAS_PAGE, edge_types)
        self.assertIn(EDGE_HAS_BODY, edge_types)
        self.assertIn(EDGE_ON_PAGE, edge_types)

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

    def test_resolve_refs_inlines_json_pointer(self):
        doc = {"texts": [{"label": "body", "text": "abc"}], "ref": {"$ref": "#/texts/0"}}
        resolved = resolve_refs(doc, doc)
        self.assertEqual(resolved["ref"], {"label": "body", "text": "abc"})


if __name__ == "__main__":
    unittest.main()
