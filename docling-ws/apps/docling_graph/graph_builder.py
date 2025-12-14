from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
DEFAULT_JSON_ROOT = os.path.join(REPO_ROOT, "data", "docling")
DOCLING_JSON_ROOT = os.environ.get("DOCLING_JSON_ROOT", DEFAULT_JSON_ROOT)

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
    if MIN_TEXT_LEN is not None and len(t) < MIN_TEXT_LEN:
        return True
    if lbl in SKIP_TEXT_LABELS:
        return True
    return False


def build_graph_from_docling_json(path: str) -> List[Dict[str, Any]]:
    """
    Graph:
        DOCUMENT → PAGE → TEXT

    Stores BOTH:
      - label_short (for compact layouts like Dagre)
      - label_full  (for reading layouts like Cola)
    """
    doc = _load_json(path)
    elements: List[Dict[str, Any]] = []

    doc_id = _nid(path)
    doc_name = os.path.basename(path)

    elements.append(
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
        return elements

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

    for page_no in sorted(pages.keys()):
        page_id = _nid(f"{path}::page::{page_no}")

        elements.append(
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

        elements.append({"data": {"source": doc_id, "target": page_id}, "classes": "hier"})

        page_texts = pages[page_no]
        if MAX_TEXTS_PER_PAGE is not None:
            page_texts = page_texts[:MAX_TEXTS_PER_PAGE]

        for t in page_texts:
            ref = t.get("self_ref") or t.get("id")
            if not isinstance(ref, str):
                ref = f"{path}::p{page_no}::{hashlib.md5(str(t).encode()).hexdigest()}"

            text_id = _nid(ref)

            raw_text = str(t.get("text") or "")
            dtype = str(t.get("label") or "text").upper()
            content_layer = t.get("content_layer")
            _, bbox = _first_prov(t)

            label_full = f"{dtype}: {raw_text}"
            label_short = f"{dtype}: {_short(raw_text, 140)}"

            elements.append(
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

            elements.append({"data": {"source": page_id, "target": text_id}, "classes": "hier"})

    return elements
