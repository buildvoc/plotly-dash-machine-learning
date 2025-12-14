from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
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
    if MIN_TEXT_LEN is not None and len(t) < MIN_TEXT_LEN:
        return True
    if lbl in SKIP_TEXT_LABELS:
        return True
    return False


# -----------------------------
# Core builder
# -----------------------------
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

    texts = doc.get("texts")
    if not isinstance(texts, list):
        return GraphPayload(nodes=nodes, edges=edges)

    pages: Dict[int, List[Dict[str, Any]]] = {}

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
