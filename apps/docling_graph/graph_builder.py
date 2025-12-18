from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
DEFAULT_JSON_ROOT = os.path.join(REPO_ROOT, "data", "docling")


def _candidate_json_roots() -> List[str]:
    """Return potential JSON roots, preferring repo data then workspace copy."""
    sibling_workspace = os.path.abspath(os.path.join(REPO_ROOT, "docling-ws", "data", "docling"))
    parent_workspace = os.path.abspath(os.path.join(REPO_ROOT, os.pardir, "docling-ws", "data", "docling"))
    return [DEFAULT_JSON_ROOT, sibling_workspace, parent_workspace]


def _docling_json_root() -> str:
    override = os.environ.get("DOCLING_JSON_ROOT")
    if override:
        return (
            os.path.abspath(os.path.join(REPO_ROOT, override))
            if not os.path.isabs(override)
            else override
        )

    for candidate in _candidate_json_roots():
        if os.path.isdir(candidate):
            return candidate

    return DEFAULT_JSON_ROOT


DOCLING_JSON_ROOT = _docling_json_root()

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
    if isinstance(prov, dict):
        return prov.get("page_no"), prov.get("bbox")

    if "page_no" in item:
        return item.get("page_no"), item.get("bbox")

    return None, None


def _short(text: str, limit: int = 120) -> str:
    t = (text or "").replace("\n", " ").strip()
    return t[:limit] + ("…" if len(t) > limit else "")


def list_docling_files(json_root: Optional[str] = None) -> List[str]:
    results: List[str] = []
    search_root = json_root or _docling_json_root()

    if not os.path.isdir(search_root):
        return results

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


def _normalize_docling_document(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Docling JSON must be an object.")

    if "document" in payload:
        doc = payload.get("document")
        if not isinstance(doc, dict):
            raise ValueError("`document` must be a JSON object when provided.")
        return doc

    doc = payload
    if not any(isinstance(doc.get(k), (list, dict)) for k in ("items", "texts", "body", "groups")):
        raise ValueError("Docling document missing supported content keys: items/texts/body/groups.")

    return doc


def _parent_ref(item: Dict[str, Any]) -> Optional[str]:
    parent = item.get("parent")
    if isinstance(parent, dict):
        ref = parent.get("$ref")
        if isinstance(ref, str):
            return ref
    return None


def _child_refs(item: Dict[str, Any]) -> List[str]:
    refs: List[str] = []
    children = item.get("children")
    if isinstance(children, list):
        for child in children:
            if isinstance(child, str):
                refs.append(child)
                continue
            if isinstance(child, dict):
                ref = child.get("$ref")
                if isinstance(ref, str):
                    refs.append(ref)
    return refs


def _should_skip_item(item: Dict[str, Any]) -> bool:
    raw_label = str(item.get("label") or item.get("type") or "text")
    raw_text = str(item.get("text") or "")
    return _is_noise_text(raw_label, raw_text) if raw_text else False


def _collect_docling_items(doc: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    items: Dict[str, Dict[str, Any]] = {}
    containers = {
        "body": doc.get("body"),
        "items": doc.get("items"),
        "texts": doc.get("texts"),
        "groups": doc.get("groups"),
        "tables": doc.get("tables"),
        "pictures": doc.get("pictures"),
        "furniture": doc.get("furniture"),
    }

    for container, value in containers.items():
        if isinstance(value, list):
            for idx, item in enumerate(value):
                if not isinstance(item, dict):
                    continue
                ref = item.get("self_ref") or f"#/{container}/{idx}"
                item.setdefault("self_ref", ref)
                items[ref] = item
        elif isinstance(value, dict):
            ref = value.get("self_ref") or f"#/{container}"
            value.setdefault("self_ref", ref)
            items[ref] = value

    return items


def _build_hierarchy_edges(items: Dict[str, Dict[str, Any]], allowed_refs: Set[str]) -> Set[Tuple[str, str]]:
    edges: Set[Tuple[str, str]] = set()

    for ref, item in items.items():
        if ref not in allowed_refs:
            continue

        for child_ref in _child_refs(item):
            if child_ref in allowed_refs:
                edges.add((ref, child_ref))

        parent_ref = _parent_ref(item)
        if parent_ref and parent_ref in allowed_refs:
            edges.add((parent_ref, ref))

    return edges


# -----------------------------
# Core builder
# -----------------------------
def build_graph_from_docling_json(path: str) -> GraphPayload:
    """
    Graph shape:
        DOCUMENT → NODE → CHILD NODE
    """
    doc = _normalize_docling_document(_load_json(path))
    items = _collect_docling_items(doc)

    if not items:
        raise ValueError("No Docling items were found in the provided JSON.")

    allowed_refs: Set[str] = set()
    page_counts: Dict[int, int] = defaultdict(int)

    for ref, item in items.items():
        if _should_skip_item(item):
            continue

        page_no, _ = _first_prov(item)
        if page_no is not None:
            if page_counts[page_no] >= MAX_TEXTS_PER_PAGE:
                continue
            page_counts[page_no] += 1

        allowed_refs.add(ref)

    # Always keep the document body when present
    if "#/body" in items:
        allowed_refs.add("#/body")

    if not allowed_refs:
        raise ValueError("Docling document has no usable items after filtering.")

    edges_refs = _build_hierarchy_edges(items, allowed_refs)

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    doc_id = _nid(path)
    doc_name = os.path.basename(path)

    nodes.append(
        {
            "data": {
                "id": doc_id,
                "type": "document",
                "label_short": f"DOCUMENT: {doc_name}",
                "label_full": f"DOCUMENT: {doc_name}",
                "label": f"DOCUMENT: {doc_name}",
                "source_path": path,
            },
            "classes": "document",
        }
    )

    for ref in sorted(allowed_refs):
        item = items[ref]
        page_no, bbox = _first_prov(item)
        text_value = str(item.get("text") or "")
        name_value = str(item.get("name") or item.get("label") or item.get("type") or ref)
        node_label = _short(text_value or name_value, 240)

        node_type = "text" if text_value else ("section" if _child_refs(item) else "item")
        node_class = "item" if node_type == "text" else "section"

        nodes.append(
            {
                "data": {
                    "id": _nid(ref),
                    "ref": ref,
                    "type": node_type,
                    "content_layer": item.get("content_layer"),
                    "text": text_value,
                    "page": page_no,
                    "bbox": bbox,
                    "label_short": node_label,
                    "label_full": f"{name_value}: {node_label}" if text_value else name_value,
                    "label": node_label,
                },
                "classes": node_class,
            }
        )

    # Graph edges between nodes
    for parent_ref, child_ref in sorted(edges_refs):
        edges.append(
            {
                "data": {
                    "id": _nid(f"{parent_ref}__{child_ref}"),
                    "source": _nid(parent_ref),
                    "target": _nid(child_ref),
                    "rel": "hier",
                    "weight": 2 if _child_refs(items.get(child_ref, {})) else 1,
                },
                "classes": "hier",
            }
        )

    # Connect document to roots (nodes whose parents are not kept)
    child_targets = {child_ref for _, child_ref in edges_refs}
    for ref in sorted(allowed_refs):
        parent_ref = _parent_ref(items[ref])
        if (not parent_ref or parent_ref not in allowed_refs) and ref not in child_targets:
            edges.append(
                {
                    "data": {
                        "id": _nid(f"{doc_id}__{ref}"),
                        "source": doc_id,
                        "target": _nid(ref),
                        "rel": "hier",
                        "weight": 3,
                    },
                    "classes": "hier",
                }
            )

    return GraphPayload(nodes=nodes, edges=edges)


# -----------------------------
# Tests
# -----------------------------


class GraphBuilderTests(unittest.TestCase):
    def test_is_noise_text_filters_short_or_skipped_labels(self):
        self.assertTrue(_is_noise_text("body", "too short"))
        self.assertTrue(_is_noise_text("header", "x" * (MIN_TEXT_LEN + 5)))
        self.assertFalse(_is_noise_text("body", "x" * (MIN_TEXT_LEN + 5)))

    def test_build_graph_from_docling_json_emits_document_and_children(self):
        doc = {
            "body": {"self_ref": "#/body", "children": [{"$ref": "#/texts/0"}]},
            "texts": [
                {
                    "self_ref": "#/texts/0",
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

        self.assertEqual(len(payload.nodes), 3)
        self.assertEqual(len(payload.edges), 2)

        node_ids = {n["data"]["id"] for n in payload.nodes}
        edge_pairs = {(e["data"]["source"], e["data"]["target"]) for e in payload.edges}

        doc_id = _nid(tmp_path)
        body_id = _nid("#/body")
        text_id = _nid("#/texts/0")

        self.assertEqual(edge_pairs, {(doc_id, body_id), (body_id, text_id)})
        self.assertIn(doc_id, node_ids)
        self.assertIn(body_id, node_ids)
        self.assertIn(text_id, node_ids)

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
