from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional, Tuple

DOCLING_JSON_ROOT = "/home/hp/docling-ws/data/docling"

MIN_TEXT_LEN = 40
MAX_TEXTS_PER_GROUP = 800

SKIP_TEXT_LABELS = {
    "page_header", "page_footer", "header", "footer",
    "footnote", "pagenum", "page_number", "artifact", "decorative",
}

USE_BBOX_SORT = True


def _nid(value: str) -> str:
    return "n_" + hashlib.md5(value.encode("utf-8")).hexdigest()[:12]


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _short(text: str, limit: int = 160) -> str:
    text = (text or "").replace("\n", " ")
    return text[:limit] + ("…" if len(text) > limit else "")


def _first_prov(item: Dict[str, Any]) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
    prov = item.get("prov") or item.get("provenance") or item.get("provenances")
    if isinstance(prov, list) and prov:
        p0 = prov[0]
        if isinstance(p0, dict):
            bbox = p0.get("bbox")
            return p0.get("page_no"), (bbox if isinstance(bbox, dict) else None)
    return None, None


def list_docling_files() -> List[str]:
    out: List[str] = []
    for root, _, files in os.walk(DOCLING_JSON_ROOT):
        for f in files:
            if f.lower().endswith(".json"):
                out.append(os.path.join(root, f))
    return sorted(out)


def _is_noise_text(label: str, text: str) -> bool:
    lbl = (label or "").strip().lower()
    t = "" if text is None else str(text)

    if lbl in SKIP_TEXT_LABELS:
        return True

    # keep whitespace
    if t.strip() == "":
        return False

    if MIN_TEXT_LEN is not None and len(t) < MIN_TEXT_LEN:
        return True

    return False


def _bbox_sort_key(bbox: Optional[Dict[str, Any]]) -> Tuple[float, float]:
    """
    Sort top-to-bottom then left-to-right.

    Docling bbox looks like:
      {l,t,r,b,coord_origin:"BOTTOMLEFT"}
    For BOTTOMLEFT, higher 't' is higher on page, so we sort by -t (descending).
    """
    if not bbox:
        return (0.0, 0.0)

    # Prefer Docling bbox keys
    if "l" in bbox and "t" in bbox:
        l = float(bbox.get("l", 0.0))
        t = float(bbox.get("t", 0.0))
        origin = str(bbox.get("coord_origin") or "").upper()

        if origin == "BOTTOMLEFT":
            return (-t, l)   # top-first (descending t), then left
        else:
            # fallback: assume t already top-first
            return (t, l)

    # Fallback shapes
    if "x0" in bbox and "y0" in bbox:
        return (float(bbox.get("y0", 0.0)), float(bbox.get("x0", 0.0)))

    return (0.0, 0.0)


def build_graph_from_docling_json(path: str) -> List[Dict[str, Any]]:
    """
    Document → Section(Group) → Text
    PLUS: include orphan texts whose parent is #/body under a synthetic BODY section.
    """
    doc = _load_json(path)
    elements: List[Dict[str, Any]] = []

    doc_id = _nid(path)
    elements.append(
        {
            "data": {"id": doc_id, "label": f"DOCUMENT: {os.path.basename(path)}", "type": "document"},
            "classes": "document",
        }
    )

    groups = doc.get("groups")
    texts = doc.get("texts")
    if not isinstance(texts, list):
        return elements

    # index texts by ref
    tidx: Dict[str, Dict[str, Any]] = {}
    ordered_text_refs: List[str] = []
    for t in texts:
        if not isinstance(t, dict):
            continue
        ref = t.get("self_ref") or t.get("id")
        if isinstance(ref, str):
            tidx[ref] = t
            ordered_text_refs.append(ref)

    # index groups by ref (if any)
    gidx: Dict[str, Dict[str, Any]] = {}
    ordered_groups: List[str] = []
    if isinstance(groups, list):
        for g in groups:
            if not isinstance(g, dict):
                continue
            ref = g.get("self_ref") or g.get("id")
            if isinstance(ref, str):
                gidx[ref] = g
                ordered_groups.append(ref)

    # Track which text refs have been included via groups
    included_text_refs = set()

    # Create section nodes for groups + edges from document
    for gref in ordered_groups:
        g = gidx[gref]
        page, bbox = _first_prov(g)
        gid = _nid(gref)
        glabel = str(g.get("label") or "group")

        elements.append(
            {
                "data": {"id": gid, "label": f"SECTION: {_short(glabel, 120)}", "type": "section", "page": page, "bbox": bbox},
                "classes": "section",
            }
        )
        elements.append({"data": {"source": doc_id, "target": gid}, "classes": "hier"})

    # Build group -> text and seq edges inside each group
    for gref in ordered_groups:
        g = gidx[gref]
        gid = _nid(gref)

        child_refs: List[str] = []
        children = g.get("children")
        if isinstance(children, list):
            for ch in children:
                cref = ch.get("$ref") if isinstance(ch, dict) else (ch if isinstance(ch, str) else None)
                if isinstance(cref, str) and cref in tidx:
                    child_refs.append(cref)

        nodes: List[Tuple[str, Optional[int], Optional[Dict[str, Any]]]] = []
        for cref in child_refs[:MAX_TEXTS_PER_GROUP]:
            t = tidx[cref]
            raw_label = str(t.get("label") or "text")
            raw_text = "" if t.get("text") is None else str(t.get("text"))
            if _is_noise_text(raw_label, raw_text):
                continue

            page, bbox = _first_prov(t)
            nodes.append((cref, page, bbox))

        if USE_BBOX_SORT:
            nodes.sort(key=lambda x: ((x[1] or 0), _bbox_sort_key(x[2])))

        seq_ids: List[str] = []
        for cref, page, bbox in nodes:
            included_text_refs.add(cref)

            tid = _nid(cref)
            seq_ids.append(tid)

            t = tidx[cref]
            raw_text = "" if t.get("text") is None else str(t.get("text"))

            dtype = "whitespace" if raw_text.strip() == "" else "text"
            preview = "␠␠␠ (WHITESPACE)" if dtype == "whitespace" else _short(raw_text, 180)

            elements.append(
                {
                    "data": {
                        "id": tid,
                        "label": f"{dtype.upper()}: {preview}",
                        "type": dtype,
                        "text": raw_text,     # full text available
                        "page": page,
                        "bbox": bbox,
                    },
                    "classes": "item",
                }
            )
            elements.append({"data": {"source": gid, "target": tid}, "classes": "hier"})

        for s, t_ in zip(seq_ids, seq_ids[1:]):
            elements.append({"data": {"source": s, "target": t_}, "classes": "seq"})

    # -----------------------------
    # NEW: BODY section for orphan texts (parent == #/body)
    # -----------------------------
    body_ref = "#/body"
    body_section_id = _nid(body_ref)

    body_text_nodes: List[Tuple[str, Optional[int], Optional[Dict[str, Any]]]] = []
    for tref in ordered_text_refs:
        if tref in included_text_refs:
            continue
        t = tidx[tref]
        parent = t.get("parent")
        parent_ref = parent.get("$ref") if isinstance(parent, dict) else None
        if parent_ref != body_ref:
            continue

        raw_label = str(t.get("label") or "text")
        raw_text = "" if t.get("text") is None else str(t.get("text"))
        if _is_noise_text(raw_label, raw_text):
            continue

        page, bbox = _first_prov(t)
        body_text_nodes.append((tref, page, bbox))

    if body_text_nodes:
        # add BODY section node once
        elements.append(
            {
                "data": {"id": body_section_id, "label": "SECTION: BODY", "type": "section"},
                "classes": "section",
            }
        )
        elements.append({"data": {"source": doc_id, "target": body_section_id}, "classes": "hier"})

        if USE_BBOX_SORT:
            body_text_nodes.sort(key=lambda x: ((x[1] or 0), _bbox_sort_key(x[2])))

        seq_ids: List[str] = []
        for tref, page, bbox in body_text_nodes:
            tid = _nid(tref)
            seq_ids.append(tid)

            t = tidx[tref]
            raw_text = "" if t.get("text") is None else str(t.get("text"))
            dtype = "whitespace" if raw_text.strip() == "" else "text"
            preview = "␠␠␠ (WHITESPACE)" if dtype == "whitespace" else _short(raw_text, 180)

            elements.append(
                {
                    "data": {
                        "id": tid,
                        "label": f"{dtype.upper()}: {preview}",
                        "type": dtype,
                        "text": raw_text,
                        "page": page,
                        "bbox": bbox,
                    },
                    "classes": "item",
                }
            )
            elements.append({"data": {"source": body_section_id, "target": tid}, "classes": "hier"})

        for s, t_ in zip(seq_ids, seq_ids[1:]):
            elements.append({"data": {"source": s, "target": t_}, "classes": "seq"})

    return elements
