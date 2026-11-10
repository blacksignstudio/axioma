"""Offline renderer checks; no browser or external service is invoked."""
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from axioma_context.cli import InvalidProject
from axioma_context.explorer import OUTPUT, render


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tags = []
        self.scripts = []
        self.current_script = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.tags.append((tag, attributes))
        if tag == "script":
            self.current_script = {"attributes": attributes, "text": ""}
            self.scripts.append(self.current_script)

    def handle_endtag(self, tag):
        if tag == "script":
            self.current_script = None

    def handle_data(self, data):
        if self.current_script is not None:
            self.current_script["text"] += data


class ExplorerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.graph = {
            "project_id": "project:axioma",
            "nodes": [
                {"id": "module:00_axis", "kind": "module", "title": "AXIS", "concept": "AXIS", "path": "corpus/00_axis/README.md"},
                {"id": "axis_00", "kind": "literary", "title": "A <form> & a voice", "path": "corpus/00_axis/00_readme.md", "sha256": "a" * 64},
                {"id": "axis_00#the-axis", "kind": "block", "title": "The axis", "document_id": "axis_00", "path": "corpus/00_axis/00_readme.md", "anchor": "the-axis", "anchor_kind": "heading", "line_start": 8, "line_end": 14, "content_sha256": "b" * 64},
            ],
            "edges": [
                {"source": "module:00_axis", "target": "axis_00", "type": "module_contains"},
                {"source": "axis_00", "target": "axis_00#the-axis", "type": "contains_block"},
                {"source": "axis_00#the-axis", "target": "module:00_axis", "type": "lexical_mention", "basis": "lexical_candidate", "evidence": {"term": "AXIS", "line": 10, "column": 1}},
                {"source": "module:00_axis", "target": "axis_00#the-axis", "type": "editorial_semantic_relation", "basis": "editorial_interpretation", "rationale": "A reading to assess.", "evidence": [{"excerpt": "The form holds."}]},
            ],
        }
        self.put_graph()

    def put_graph(self):
        (self.root / "graph.json").write_text(json.dumps(self.graph, ensure_ascii=False), encoding="utf-8")

    def test_valid_self_contained_page_preserves_all_graph_records(self):
        target = render(self.root)
        self.assertEqual(target, self.root / OUTPUT)
        page = Page(target.read_text(encoding="utf-8"))
        self.assertEqual(len(page.scripts), 2)
        self.assertEqual(page.scripts[0]["attributes"], {"id": "graph-data", "type": "application/json"})
        self.assertEqual(json.loads(page.scripts[0]["text"]), self.graph)
        ids = {a.get("id") for _, a in page.tags}
        self.assertTrue({"search", "node-kind", "edge-kind", "drawing", "detail", "legend", "totals"} <= ids)
        for tag, attributes in page.tags:
            self.assertNotIn("src", attributes)
            if tag == "link":
                self.fail("Offline explorer must not import styles or other linked resources")
        policy = next(a["content"] for t, a in page.tags if t == "meta" and a.get("http-equiv") == "Content-Security-Policy")
        self.assertIn("connect-src 'none'", policy)
        script = page.scripts[1]["text"]
        for network_or_html_sink in ("fetch(", "XMLHttpRequest", "WebSocket", "innerHTML", "outerHTML", "document.write", "eval("):
            self.assertNotIn(network_or_html_sink, script)
        self.assertIn("textContent", script)
        self.assertIn("const MAX_NODES=40, MAX_EDGES=100, PAGE_SIZE=60", script)
        self.assertIn("searchIndex=nodes.map", script)
        self.assertIn("Lexical candidate", script)
        self.assertIn("Editorial interpretation", script)

    def test_untrusted_source_text_cannot_close_json_script(self):
        malicious = '</script><script src="https://example.invalid/x.js">bad()</script><img src=x onerror=bad()>\u2028&'
        self.graph["nodes"][1]["title"] = malicious
        self.graph["edges"][-1]["evidence"][0]["excerpt"] = malicious
        self.put_graph()
        text = render(self.root).read_text(encoding="utf-8")
        page = Page(text)
        self.assertEqual(len(page.scripts), 2)
        self.assertNotIn(malicious, text)
        self.assertIn(r"\u003c/script\u003e", text)
        self.assertIn(r"\u2028", text)
        self.assertFalse(any(t == "img" for t, _ in page.tags))
        self.assertEqual(json.loads(page.scripts[0]["text"]), self.graph)

    def test_deterministic_and_changed_input_is_reflected(self):
        first = render(self.root).read_bytes()
        self.assertEqual(render(self.root).read_bytes(), first)
        self.graph["nodes"][2]["line_end"] = 20
        self.graph["nodes"].append({"id": "extra", "title": "A new source", "kind": "guide", "path": "docs/new.md"})
        self.put_graph()
        changed = render(self.root).read_bytes()
        self.assertNotEqual(first, changed)
        self.assertEqual(json.loads(Page(changed.decode()).scripts[0]["text"]), self.graph)
        self.assertFalse(list((self.root / "assets").glob(".explorer-*")))

    def test_invalid_graph_does_not_replace_existing_result(self):
        target = render(self.root)
        original = target.read_bytes()
        for invalid in [None, {"nodes": [], "edges": [{"source": "missing", "target": "also-missing", "type": "link"}]},
                        {"nodes": [self.graph["nodes"][0], self.graph["nodes"][0]], "edges": []}]:
            with self.subTest(invalid=invalid):
                (self.root / "graph.json").write_text(json.dumps(invalid), encoding="utf-8")
                with self.assertRaises(InvalidProject):
                    render(self.root)
                self.assertEqual(target.read_bytes(), original)

    def test_output_parent_and_output_directory_are_refused(self):
        (self.root / "assets").write_text("Preserve this existing file.", encoding="utf-8")
        with self.assertRaisesRegex(InvalidProject, "parent is not a directory"):
            render(self.root)
        self.assertEqual((self.root / "assets").read_text(), "Preserve this existing file.")
        (self.root / "assets").unlink()
        (self.root / OUTPUT).mkdir(parents=True)
        with self.assertRaisesRegex(InvalidProject, "regular file"):
            render(self.root)

    def test_linked_input_and_output_are_rejected_before_any_write(self):
        # Simulate the filesystem's link indicator portably, including Windows
        # installations where creating a real symlink requires extra privileges.
        for linked in [self.root / "graph.json", self.root / "assets", self.root / OUTPUT]:
            with self.subTest(linked=linked):
                with patch("axioma_context.cli.Path.is_symlink", autospec=True, side_effect=lambda p: p == linked):
                    with self.assertRaisesRegex(InvalidProject, "Linked paths"):
                        render(self.root)
                self.assertFalse((self.root / OUTPUT).exists())

    def test_graph_source_paths_are_data_not_opened_or_linked_unsafely(self):
        self.graph["nodes"][1]["path"] = "../../outside.txt"
        self.graph["nodes"][2]["path"] = "https://example.invalid/source"
        self.put_graph()
        page = Page(render(self.root).read_text(encoding="utf-8"))
        self.assertEqual(json.loads(page.scripts[0]["text"]), self.graph)
        script = page.scripts[1]["text"]
        self.assertIn("p==='..'", script)
        self.assertIn("path.includes(':')", script)
        self.assertIn("'../'+parts.map(encodeURIComponent).join('/')", script)


if __name__ == "__main__":
    unittest.main()
