import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from apps.docling_graph import graph_builder as gb
from tests.test_expand_on_click import _install_dash_stubs

FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures" / "docling"
SMALL_FIXTURE = FIXTURES_ROOT / "regulations" / "uksi-2010-2214-regulation-38.json"


class DoclingGraphBuilderFixtureTests(unittest.TestCase):
    def test_candidate_roots_include_hp_workspace_path(self):
        hp_root = os.path.abspath("/home/hp/docling-ws/docling-ws/data/docling")

        self.assertIn(hp_root, gb._candidate_json_roots())

    def test_discovery_finds_fixture_jsons(self):
        building_files = gb.list_docling_files(str(FIXTURES_ROOT / "building_standards"))
        regulation_files = gb.list_docling_files(str(FIXTURES_ROOT / "regulations"))

        building_names = {Path(f).name for f in building_files}
        regulation_names = {Path(f).name for f in regulation_files}

        self.assertEqual(building_names, {"2025_Amendments_to_Approved_Document_B_volume_1_and_volume_2.json"})
        self.assertEqual(regulation_names, {"uksi-2010-2214-regulation-38.json"})

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

    def test_mermaid_relationships_applied(self):
        doc = {
            "body": {
                "self_ref": "#/body",
                "children": [{"$ref": "#/groups/0"}, {"$ref": "#/pictures/0"}],
            },
            "groups": [
                {
                    "self_ref": "#/groups/0",
                    "parent": {"$ref": "#/body"},
                    "children": [{"$ref": "#/texts/0"}],
                }
            ],
            "texts": [
                {
                    "self_ref": "#/texts/0",
                    "parent": {"$ref": "#/groups/0"},
                    "text": "group text " * 5,
                },
                {
                    "self_ref": "#/texts/1",
                    "parent": {"$ref": "#/body"},
                    "text": "body text " * 5,
                },
            ],
            "pictures": [
                {
                    "self_ref": "#/pictures/0",
                    "parent": {"$ref": "#/body"},
                    "captions": [{"$ref": "#/texts/1"}],
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

        id_to_ref = {n["data"]["id"]: n["data"].get("ref") for n in payload.nodes}

        edges = {
            (id_to_ref.get(e["data"]["source"]), id_to_ref.get(e["data"]["target"]), e["data"]["rel"])
            for e in payload.edges
            if id_to_ref.get(e["data"]["target"]) is not None
        }

        self.assertIn(("#/body", "#/groups/0", "children"), edges)
        self.assertIn(("#/body", "#/pictures/0", "children"), edges)
        self.assertIn(("#/groups/0", "#/texts/0", "children"), edges)
        self.assertIn(("#/texts/0", "#/groups/0", "parent"), edges)
        self.assertIn(("#/texts/1", "#/body", "parent"), edges)
        self.assertIn(("#/pictures/0", "#/texts/1", "captions"), edges)
        self.assertTrue(any(e[2] == "document" for e in edges))

    def test_list_docling_files_is_recursive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            top_level = root / "root.json"
            nested_dir = root / "nested"
            nested_dir.mkdir()
            nested = nested_dir / "nested.json"

            top_level.write_text("{}", encoding="utf-8")
            nested.write_text("{}", encoding="utf-8")

            results = gb.list_docling_files(tmpdir)

        self.assertEqual(results, [str(nested), str(top_level)])

    def test_list_docling_files_recurses_over_fixture_tree(self):
        results = gb.list_docling_files(str(FIXTURES_ROOT))

        names = [Path(p).name for p in results]

        self.assertIn("2025_Amendments_to_Approved_Document_B_volume_1_and_volume_2.json", names)
        self.assertIn("uksi-2010-2214-regulation-38.json", names)

    def test_list_docling_files_sorted_by_filename(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "b.JSON"
            second = root / "A.json"
            first.write_text("{}", encoding="utf-8")
            second.write_text("{}", encoding="utf-8")

            results = gb.list_docling_files(tmpdir)

        self.assertEqual(results, [str(second), str(first)])

    def test_documents_endpoint_disables_caching_and_reflects_scan_root(self):
        previous_root = os.environ.get("DOCLING_DOCS_DIR")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                doc_path = root / "test.json"
                doc_path.write_text("{}", encoding="utf-8")

                os.environ["DOCLING_DOCS_DIR"] = str(root)

                _install_dash_stubs()
                sys.modules.pop("apps.docling_graph.main", None)
                from apps.docling_graph import main as main_app

                importlib.reload(main_app)

                response = main_app.list_documents_api()

            payload = response.get_json()

            self.assertEqual(response.headers.get("Cache-Control"), "no-store")
            self.assertEqual(payload.get("scan_root"), str(root))
            self.assertEqual(payload.get("documents"), [str(doc_path)])
        finally:
            if previous_root is None:
                os.environ.pop("DOCLING_DOCS_DIR", None)
            else:
                os.environ["DOCLING_DOCS_DIR"] = previous_root

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
