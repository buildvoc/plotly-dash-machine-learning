import json
import tempfile
import unittest
from pathlib import Path

from apps.docling_graph import graph_builder as gb

FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures" / "docling"
SMALL_FIXTURE = FIXTURES_ROOT / "regulations" / "uksi-2010-2214-regulation-38.json"


class DoclingGraphBuilderFixtureTests(unittest.TestCase):
    def test_discovery_finds_fixture_jsons(self):
        files = gb.list_docling_files(str(FIXTURES_ROOT))
        names = {Path(f).name for f in files}

        self.assertIn("2025_Amendments_to_Approved_Document_B_volume_1_and_volume_2.json", names)
        self.assertIn("uksi-2010-2214-regulation-38.json", names)

    def test_loader_normalizes_docling_document(self):
        plain = {"texts": []}
        wrapped = {"document": {"texts": []}}

        self.assertEqual(gb._normalize_docling_document(plain), plain)
        self.assertEqual(gb._normalize_docling_document(wrapped), wrapped["document"])

        with self.assertRaises(ValueError):
            gb._normalize_docling_document({"document": []})
        with self.assertRaises(ValueError):
            gb._normalize_docling_document("not a dict")

    def test_graph_builder_emits_nodes_and_edges_for_fixture(self):
        payload = gb.build_graph_from_docling_json(str(SMALL_FIXTURE))
        node_ids = {n["data"]["id"] for n in payload.nodes}

        self.assertGreater(len(payload.nodes), 0)
        self.assertGreater(len(payload.edges), 0)

        for edge in payload.edges:
            self.assertIn(edge["data"]["source"], node_ids)
            self.assertIn(edge["data"]["target"], node_ids)

    def test_provenance_optional_does_not_crash(self):
        doc = {
            "body": {"self_ref": "#/body", "children": [{"$ref": "#/texts/0"}]},
            "texts": [
                {
                    "self_ref": "#/texts/0",
                    "label": "body",
                    "text": "sample text " * 5,
                }
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(doc, tmp)
            tmp_path = tmp.name

        try:
            payload = gb.build_graph_from_docling_json(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        pages = {n["data"].get("page") for n in payload.nodes}
        self.assertIn(None, pages)
        self.assertGreater(len(payload.edges), 0)


if __name__ == "__main__":
    unittest.main()
