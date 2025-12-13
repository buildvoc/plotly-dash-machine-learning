from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional, Tuple

# -------------------------------------------------------------------
# FIXED LOCATION OF DOCLING JSON OUTPUTS
# -------------------------------------------------------------------
DOCLING_JSON_ROOT = "/home/hp/docling-ws/data/docling"

# -------------------------------------------------------------------
# EPrints-style filtering (noise suppression)
# -------------------------------------------------------------------
MIN_TEXT_LEN = 40          # ignore tiny fragments
MAX_TEXTS_PER_PAGE = 250   # cap to avoid hairballs

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

# -------------------------------------------------------------------
# Utilities
# -------------------------------------------------------------------
def _nid(value: str) -> str:
    """Stable Cytoscape-safe node ID."""
    return "n_" + hashlib.md5(value.encode("utf-8")).hexdigest()[:12]


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _short(text: str, limit: int = 140) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def _first_prov(item: Dict[str, Any]) -> Tuple[Optional[int], Optional[Any]]:
    """Extract page_no + bbox if present."""
    prov = item.get("prov") or item.get("provenance") or item.get("provenances")
    if isinstance(prov, list) and prov:
        p0 = prov[0]
        if isinstance(p0, dict):
            return p0.get("page_no"), p0.get("bbox")
    return None, None


def list_docling_files() -> List[str]:
    """Recursively list all *.json files under DOCLING_JSON_ROOT."""
    results: List[str] = []
    for root, _, files in os.walk(DOCLING_JSON_ROOT):
        for name in files:
            if name.lower().endswith(".json"):
                results.append(os.path.join(root, name))
    return sorted(results)


# -------------------------------------------------------------------
# Filtering rules
# -------------------------------------------------------------------
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


# -------------------------------------------------------------------
# Chunk-first graph builder (PAGE-BASED)
# -------------------------------------------------------------------
def build_graph_from_docling_json(path: str) -> List[Dict[str, Any]]:
    """
    Graph model:
        Document → Page Chunk → Evidence (Text)

    Filters:
      - remove micro text fragments
      - remove empty text
      - remove known noise labels
      - cap evidence per page
    """
    doc = _load_json(path)
    elements: List[Dict[str, Any]] = []

    # ---------------------------------------------------------------
    # Document node
    # ---------------------------------------------------------------
    doc_node_id = _nid(path)
    elements.append(
        {
            "data": {
                "id": doc_node_id,
                "label": os.path.basename(path),
                "type": "document",
            },
            "classes": "document",
        }
    )

    texts = doc.get("texts")
    if not isinstance(texts, list):
        return elements

    # ---------------------------------------------------------------
    # Group filtered texts by page number
    # ---------------------------------------------------------------
    pages: Dict[int, List[Dict[str, Any]]] = {}

    for t in texts:
        if not isinstance(t, dict):
            continue

        label = str(t.get("label") or "text")
        text = str(t.get("text") or "")

        if _is_noise_text(label, text):
            continue

        page_no, _ = _first_prov(t)
        if page_no is None:
            continue

        pages.setdefault(page_no, []).append(t)

    # ---------------------------------------------------------------
    # Create page chunks + evidence nodes
    # ---------------------------------------------------------------
    for page_no in sorted(pages.keys()):
        chunk_id = _nid(f"{path}::page::{page_no}")

        # Page chunk node
        elements.append(
            {
                "data": {
                    "id": chunk_id,
                    "label": f"Page {page_no}",
                    "type": "chunk",
                    "page": page_no,
                },
                "classes": "section",
            }
        )

        # Document → Chunk edge
        elements.append(
            {
                "data": {"source": doc_node_id, "target": chunk_id},
                "classes": "hier",
            }
        )

        # Evidence nodes
        page_texts = pages[page_no]
        if MAX_TEXTS_PER_PAGE is not None:
            page_texts = page_texts[:MAX_TEXTS_PER_PAGE]

        for t in page_texts:
            ref = t.get("self_ref") or t.get("id")
            if not isinstance(ref, str):
                ref = f"{path}::p{page_no}::{hashlib.md5(str(t).encode('utf-8')).hexdigest()}"

            text_id = _nid(ref)
            label = str(t.get("label") or "text")
            text = str(t.get("text") or "")
            content_layer = t.get("content_layer")  # ✅ Docling schema
            _, bbox = _first_prov(t)

            elements.append(
                {
                    "data": {
                        "id": text_id,
                        "label": _short(label, 60),
                        "type": "text",
                        "content_layer": content_layer,
                        "text": _short(text, 800),
                        "page": page_no,
                        "bbox": bbox,
                    },
                    "classes": "item",
                }
            )

            # Chunk → Text edge
            elements.append(
                {
                    "data": {"source": chunk_id, "target": text_id},
                    "classes": "hier",
                }
            )

    return elements
