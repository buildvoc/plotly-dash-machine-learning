from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
DEFAULT_JSON_ROOT = os.path.join(REPO_ROOT, "data", "docling")


def _docling_json_root() -> str:
    override_raw = os.environ.get("DOCLING_JSON_ROOT")
    override = os.path.expanduser(os.path.expandvars(override_raw or ""))
    if not override:
        return DEFAULT_JSON_ROOT

    if not os.path.isabs(override):
        return os.path.abspath(os.path.join(REPO_ROOT, override))

    return override


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


def list_docling_files() -> List[str]:
    results: List[str] = []
    for root, _, files in os.walk(DOCLING_JSON_ROOT):
        for name in files:
            if name.lower().endswith(".json"):
                results.append(os.path.join(root, name))
    return sorted(results)


def _is_noise_text(label: str, text: str) -> bool:
    lbl = (label or "").strip().lower()
    t = (text or "").strip()

    if not t:
        return True
    if MIN_TEXT_LEN is not None and len(t) < MIN_TEXT_LEN and lbl != "section_header":
        return True
    if lbl in SKIP_TEXT_LABELS:
        return True
    return False


def _ref_from(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str):
            return ref
    return None


def _index_items(doc: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    by_ref: Dict[str, Dict[str, Any]] = {}

    def add(obj: Dict[str, Any]):
        ref = obj.get("self_ref")
        if isinstance(ref, str):
            by_ref[ref] = obj

    for value in doc.values():
        if isinstance(value, dict) and "self_ref" in value:
            add(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and "self_ref" in item:
                    add(item)

    return by_ref


def _iter_child_refs(item: Dict[str, Any]):
    for key, value in item.items():
        if key in {"parent", "self_ref"}:
            continue

        if isinstance(value, list):
            for v in value:
                ref = _ref_from(v)
                if ref:
                    yield ref
        else:
            ref = _ref_from(value)
            if ref:
                yield ref


def build_graph_from_docling_json(path: str) -> List[Dict[str, Any]]:
    """
    Graph:
        DOCUMENT → BODY (and furniture) → DOCSTRUCT items → leaf items

    Traverses the Docling hierarchy using $ref links, creating nodes for any
    referenced item (groups, texts, pictures, tables, etc.) while preserving
    provenance such as page numbers and content layers. Text nodes still carry
    short + full labels for layout switching.
    """
    doc = _load_json(path)
    elements: List[Dict[str, Any]] = []

    doc_id = _nid(path)
    doc_name = os.path.basename(path)

    elements.append(
        {
            "data": {
                "id": doc_id,
                "type": "DOCUMENT",
                "label_short": f"DOCUMENT: {doc_name}",
                "label_full": f"DOCUMENT: {doc_name}",
                "label": f"DOCUMENT: {doc_name}",
            },
            "classes": "document",
        }
    )

    by_ref = _index_items(doc)
    visited: Dict[str, Optional[str]] = {}
    page_counts: Dict[int, int] = {}
    edges_seen: Set[Tuple[str, str]] = set()

    def make_node(ref: str, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        label_raw = str(item.get("label") or item.get("name") or "item")
        type_val = label_raw.upper()
        text_val = item.get("text")
        content_layer = item.get("content_layer")
        page_no, bbox = _first_prov(item)

        if isinstance(text_val, str):
            if _is_noise_text(label_raw, text_val):
                return None

            if page_no is not None:
                if MAX_TEXTS_PER_PAGE is not None and page_counts.get(page_no, 0) >= MAX_TEXTS_PER_PAGE:
                    return None
                page_counts[page_no] = page_counts.get(page_no, 0) + 1

            label_full = f"{type_val}: {text_val}"
            label_short = f"{type_val}: {_short(text_val, 140)}"
        else:
            label_full = label_raw
            label_short = label_raw

        data = {
            "id": _nid(ref),
            "type": type_val,
            "label_short": label_short,
            "label_full": label_full,
            "label": label_full,
        }

        if content_layer is not None:
            data["content_layer"] = content_layer

        if page_no is not None:
            data["page"] = page_no
        if bbox is not None:
            data["bbox"] = bbox

        node_class = "section" if any(_iter_child_refs(item)) else "item"

        return {"data": data, "classes": node_class}

    def walk(ref: str) -> Optional[str]:
        if ref in visited:
            return visited[ref]

        item = by_ref.get(ref)
        if not item:
            return None

        node = make_node(ref, item)
        if node is None:
            visited[ref] = None  # mark as seen even if skipped
            return None

        visited[ref] = node["data"]["id"]
        elements.append(node)

        for child_ref in _iter_child_refs(item):
            child_id = walk(child_ref)
            if child_id:
                edge = (node["data"]["id"], child_id)
                if edge not in edges_seen:
                    edges_seen.add(edge)
                    elements.append({"data": {"source": edge[0], "target": edge[1]}, "classes": "hier"})

        return node["data"]["id"]

    for root in (doc.get("body"), doc.get("furniture")):
        if not isinstance(root, dict):
            continue
        root_ref = root.get("self_ref")
        if not isinstance(root_ref, str):
            continue

        root_id = walk(root_ref)
        if root_id:
            elements.append({"data": {"source": doc_id, "target": root_id}, "classes": "hier"})

    return elements
