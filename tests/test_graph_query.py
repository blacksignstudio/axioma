"""Isolated graph queries disclose clipping and refuse stale references."""
from contextlib import redirect_stdout, redirect_stderr
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from axioma_context.cli import InvalidProject, main
from axioma_context.graph_query import query


class GraphQueryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "memory.md"
        self.source.write_text("# Memory\n\nA retained form.\n", encoding="utf-8")
        sha = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.graph = {"nodes": [
            {"id": "memory_00", "kind": "literary", "title": "Memory", "path": "memory.md", "sha256": sha},
            *[{"id": f"memory_00#part-{i}", "kind": "block", "title": f"Memory part {i}",
               "path": "memory.md", "document_id": "memory_00"} for i in range(3)]],
            "edges": [{"source": "memory_00", "target": f"memory_00#part-{i}", "type": "section_contains"}
                      for i in range(3)] + [
                {"source": "memory_00#part-0", "target": "memory_00#part-1",
                 "type": "editorial_semantic_relation", "relation": "contrasts_with"}]}
        self.save_graph()

    def save_graph(self):
        path = self.root / "graph.json"
        path.write_text(json.dumps(self.graph), encoding="utf-8")
        (self.root / "manifest.json").write_text(json.dumps({"files": [
            {"path": "graph.json", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]}), encoding="utf-8")

    def test_search_and_block_neighbors_are_bounded_and_typed(self):
        result = query(self.root, search="MEMORY", limit=2)
        self.assertEqual((result["matches"]["available"], result["matches"]["returned"],
                          result["matches"]["truncated"]), (4, 2, True))
        result = query(self.root, identifier="memory_00", limit=2)
        self.assertEqual((result["edges"]["available"], result["edges"]["returned"], result["edges"]["truncated"]), (3, 2, True))
        self.assertEqual((result["neighbors"]["available"], result["neighbors"]["returned"]), (3, 2))
        result = query(self.root, identifier="memory_00#part-0", relation="contrasts_with")
        self.assertEqual(result["neighbors"]["items"][0]["id"], "memory_00#part-1")
        self.assertEqual(result["edges"]["returned"], 1)
        self.assertFalse(result["edges"]["truncated"])

    def test_stale_graph_and_changed_underlying_block_source_are_refused(self):
        path = self.root / "graph.json"
        path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        with self.assertRaisesRegex(InvalidProject, "Graph digest differs"):
            query(self.root, search="memory")
        self.save_graph()
        self.source.write_text("Changed source.\n", encoding="utf-8")
        with self.assertRaisesRegex(InvalidProject, "Changed graph source"):
            query(self.root, identifier="memory_00#part-0")

    def test_self_manifest_is_usable_without_a_false_verified_claim(self):
        self.graph["nodes"].append({"id": "file:manifest.json", "kind": "file",
                                    "title": "manifest.json", "path": "manifest.json", "derived": True})
        self.graph["edges"].append({"source": "memory_00", "target": "file:manifest.json",
                                    "type": "project_contains"})
        self.save_graph()
        result = query(self.root, search="manifest")
        self.assertEqual(result["matches"]["items"][0]["id"], "file:manifest.json")
        status = result["source_verification"]["manifest.json"]
        self.assertEqual(status["status"], "unverified-self")
        self.assertEqual(status["detail"], "not self-hashable; manifest is the local trust root")
        self.assertNotIn("sha256", status)
        stream = io.StringIO()
        with redirect_stdout(stream):
            self.assertEqual(main(["--root", str(self.root), "graph", "--search", "manifest"]), 0)
        self.assertEqual(json.loads(stream.getvalue())["source_verification"]["manifest.json"]["status"],
                         "unverified-self")
        result = query(self.root, identifier="file:manifest.json")
        self.assertEqual(result["focus"]["id"], "file:manifest.json")
        self.assertEqual(result["source_verification"]["manifest.json"]["status"], "unverified-self")
        self.assertEqual(result["source_verification"]["memory.md"]["status"], "sha256-verified")
        self.source.write_text("Changed source.\n", encoding="utf-8")
        with self.assertRaisesRegex(InvalidProject, "Changed graph source"):
            query(self.root, identifier="file:manifest.json")

    def test_invalid_requests_and_cli_integration_preserve_read_only_behavior(self):
        for limit in (0, 101, True, "8"):
            with self.subTest(limit=limit), self.assertRaisesRegex(InvalidProject, "limit"):
                query(self.root, search="memory", limit=limit)
        with self.assertRaisesRegex(InvalidProject, "Unknown graph ID"):
            query(self.root, identifier="missing")
        with self.assertRaisesRegex(InvalidProject, "Unknown graph relation"):
            query(self.root, identifier="memory_00", relation="imagined")
        with self.assertRaisesRegex(InvalidProject, "exactly one"):
            query(self.root, search="memory", identifier="memory_00")
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        stream = io.StringIO()
        with redirect_stdout(stream):
            self.assertEqual(main(["--root", str(self.root), "graph", "--search", "memory", "--limit", "2"]), 0)
        self.assertEqual(json.loads(stream.getvalue())["matches"]["returned"], 2)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["graph", "--search", "memory", "--id", "memory_00"])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_whole_component_text_is_exact_and_never_silently_clipped(self):
        text = self.source.read_bytes().decode("utf-8")
        self.graph["nodes"].append({"id": "memory_00#~component-whole", "kind": "block",
            "block_type": "component", "title": "Whole", "path": "memory.md",
            "document_id": "memory_00", "line_start": 1, "line_end": 3,
            "content_sha256": hashlib.sha256(text.encode()).hexdigest()})
        self.save_graph()
        result = query(self.root, identifier="memory_00#~component-whole")
        self.assertEqual(result["text"], {"scope": "whole_component", "complete": True,
                                         "utf8_bytes": len(text.encode()), "content": text})
        with self.assertRaisesRegex(InvalidProject, "exceeds max-bytes"):
            query(self.root, identifier="memory_00#~component-whole", max_bytes=1024)
        self.graph["nodes"][-1]["line_end"] = 2
        self.save_graph()
        with self.assertRaisesRegex(InvalidProject, "span digest differs"):
            query(self.root, identifier="memory_00#~component-whole")
        with self.assertRaisesRegex(InvalidProject, "text requires"):
            query(self.root, search="memory", include_text=True)
        stream = io.StringIO()
        with redirect_stdout(stream):
            self.assertEqual(main(["--root", str(self.root), "graph", "--id", "memory_00", "--text",
                                   "--max-bytes", "32768"]), 0)
        self.assertEqual(json.loads(stream.getvalue())["text"]["content"], text)

    def test_returned_edge_witness_sources_are_verified_even_when_not_endpoints(self):
        witness = self.root / "witness.md"
        witness.write_text("A bronze hinge remains.\n", encoding="utf-8")
        self.graph["nodes"].append({"id": "witness", "kind": "guide", "path": "witness.md",
                                  "sha256": hashlib.sha256(witness.read_bytes()).hexdigest()})
        self.graph["edges"][-1]["evidence"] = [{"path": "witness.md", "excerpt": "A bronze hinge"}]
        self.save_graph()
        result = query(self.root, identifier="memory_00#part-0", relation="contrasts_with")
        self.assertEqual(result["source_verification"]["witness.md"]["status"], "sha256-verified")
        witness.write_text("Altered supporting evidence.\n", encoding="utf-8")
        with self.assertRaisesRegex(InvalidProject, "Changed graph source: witness.md"):
            query(self.root, identifier="memory_00#part-0", relation="contrasts_with")


if __name__ == "__main__":
    unittest.main()
