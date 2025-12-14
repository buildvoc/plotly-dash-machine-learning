from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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
    doc_name = os.path.basename(path)

    # DOCUMENT node
    nodes.append(
        {
            "data": {
                "id": doc_id,
                "type": "document",
                "label_short": f"DOCUMENT: {doc_name}",
                "label_full": f"DOCUMENT: {doc_name}",
                "label": f"DOCUMENT: {doc_name}",
            },
            "classes": "document",
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
                    "type": "chunk",
                    "page": page_no,
                    "label_short": f"PAGE {page_no}",
                    "label_full": f"PAGE {page_no}",
                    "label": f"PAGE {page_no}",
                },
                "classes": "section",
            }
        )

        edges.append(
            {
                "data": {
                    "id": _nid(f"{doc_id}__{page_id}"),
                    "source": doc_id,
                    "target": page_id,
                    "rel": "hier",
                },
                "classes": "hier",
            }
        )

        page_texts = pages[page_no][:MAX_TEXTS_PER_PAGE]

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
                        "type": "text",
                        "content_layer": content_layer,
                        "text": raw_text,
                        "page": page_no,
                        "bbox": bbox,
                        "label_short": label_short,
                        "label_full": label_full,
                        "label": label_full,
                    },
                    "classes": "item",
                }
            )

            edges.append(
                {
                    "data": {
                        "id": _nid(f"{page_id}__{text_id}"),
                        "source": page_id,
                        "target": text_id,
                        "rel": "hier",
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

        self.assertEqual(len(payload.nodes), 3)
        self.assertEqual(len(payload.edges), 2)

        node_ids = {n["data"]["id"] for n in payload.nodes}
        edge_pairs = {(e["data"]["source"], e["data"]["target"]) for e in payload.edges}

        doc_id = _nid(tmp_path)
        page_id = _nid(f"{tmp_path}::page::1")
        text_id = next(n["data"]["id"] for n in payload.nodes if n["data"]["type"] == "text")

        self.assertIn(doc_id, node_ids)
        self.assertIn(page_id, node_ids)
        self.assertEqual(edge_pairs, {(doc_id, page_id), (page_id, text_id)})

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
