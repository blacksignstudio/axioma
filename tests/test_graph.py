"""Behavioral checks for complete, attributable graph generation."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from axioma_context.cli import FOOTER, InvalidProject
from axioma_context.graph import generate


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.outer = Path(self.temporary.name)
        self.root = self.outer / "repository"
        self.root.mkdir()
        self.records = []
        self.doc("README.md", "project:entry", "Project", "guide", "A reference corpus.")
        self.doc("docs/atlas.md", "guide:atlas", "Atlas", "guide", "AXIS and WILL are editorial reading neighbours.")
        self.doc("corpus/00_axis/README.md", "module:00_axis", "AXIS", "module", "The bearing.")
        self.doc("corpus/01_will/README.md", "module:01_will", "WILL", "module", "A direction.")
        self.doc("corpus/00_axis/00_readme.md", "axis_00", "A <form> & a voice", "literary",
                 "### 01 — Axis\n\nThe AXIS carries the form.\n\n<a id=\"portal\"></a>\n\n"
                 "### Ordinary sentence\n\nI will respond.\n\n"
                 "### Noun and concept\n\nThe will is steady.\n\nWILL names direction.\n\n"
                 "### Harmonic Question Index\n\nThe index here is a philosophical image, not a route list.\n\n"
                 "### Trace Without Index\n\nA trace remains meaningful without a lookup table.\n\n"
                 "### Navigation of the working edition\n\nA generated introduction.\n\n[Next](01_manifest.md)\n\n"
                 "### Working Edition Navigation\n\nA generated route.\n\n[Next](01_manifest.md)\n\n"
                 "### Repeat\n\nA first passage.\n\n### Repeat\n\nA second passage.")
        self.doc("corpus/00_axis/01_manifest.md", "axis_01", "Another bearing", "literary", "The axis remains.")
        self.doc("corpus/01_will/00_readme.md", "will_00", "Direction", "literary",
                 "Direction remains revisable.\n\n[A section](../00_axis/00_readme.md#01-axis) and "
                 "[an explicit gate](../00_axis/00_readme.md#portal).")
        self.put("LICENSE", "A synthetic fixture notice.\n")
        self.put("src/example.py", "value = 1\n")
        for name in ["build/ignored.md", "dist/ignored.md", ".venv/ignored.md",
                     "__pycache__/ignored.md", "src/example.egg-info/ignored.md", ".git/ignored.md"]:
            self.put(name, "Excluded fixture.\n")
        self.save_catalog()

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def doc(self, name, identifier, title, kind, text):
        # JSON strings are valid YAML quoted scalars and avoid fixture ambiguity.
        body = ("---\n" + "\n".join(f"{key}: {json.dumps(value)}" for key, value in
                {"id": identifier, "title": title, "kind": kind, "version": "2.0.0",
                 "language": "en", "license": "CC-BY-4.0"}.items()) +
                f"\n---\n\n# {title}\n\n## Orientation\n\nA fixture.\n\n## Text\n\n{text}"
                f"\n\n## Connections\n\n[Project]({self.project_link(name)})\n\n{FOOTER}\n")
        self.put(name, body)
        self.records.append({"id": identifier, "title": title, "kind": kind,
                             "path": name, "sha256": hashlib.sha256((self.root / name).read_bytes()).hexdigest()})

    @staticmethod
    def project_link(name):
        return "../" * len(Path(name).parts[:-1]) + "README.md"

    def save_catalog(self):
        self.put("catalog.json", json.dumps({"documents": self.records}))

    def update_digest(self, name):
        next(r for r in self.records if r["path"] == name)["sha256"] = hashlib.sha256((self.root / name).read_bytes()).hexdigest()
        self.save_catalog()

    def test_all_files_and_blocks_are_connected_and_svg_counts_are_real(self):
        summary = generate(self.root, {"documents": self.records})
        graph_bytes = (self.root / "graph.json").read_bytes()
        graph = json.loads(graph_bytes)
        files = {n["path"] for n in graph["nodes"] if n["kind"] != "block"}
        expected = {r["path"] for r in self.records} | {
            "catalog.json", "LICENSE", "src/example.py", "graph.json", "manifest.json",
            "assets/corpus-graph.svg", "assets/graph-explorer.html"}
        self.assertEqual(files, expected)
        identifiers = {n["id"] for n in graph["nodes"]}
        self.assertEqual(len(identifiers), len(graph["nodes"]))
        peers = {i: set() for i in identifiers}
        for edge in graph["edges"]:
            self.assertIn(edge["source"], identifiers)
            self.assertIn(edge["target"], identifiers)
            peers[edge["source"]].add(edge["target"])
            peers[edge["target"]].add(edge["source"])
        seen, pending = set(), [graph["project_id"]]
        while pending:
            node = pending.pop()
            if node not in seen:
                seen.add(node)
                pending.extend(peers[node] - seen)
        self.assertEqual(seen, identifiers)
        self.assertTrue(all(peers.values()))
        self.assertEqual((summary["literary_chapters"], summary["modules"]), (3, 2))
        for node in graph["nodes"]:
            if node.get("derived"):
                self.assertNotIn("sha256", node)
        svg = ET.fromstring((self.root / "assets/corpus-graph.svg").read_text(encoding="utf-8"))
        circles = list(svg.iter("{http://www.w3.org/2000/svg}circle"))
        self.assertEqual(sum(c.attrib.get("class") == "chapter-dot" for c in circles), 3)
        self.assertEqual(sum(c.attrib.get("class") == "module-hub" for c in circles), 2)
        self.assertIn("A &lt;form&gt; &amp; a voice", (self.root / "assets/corpus-graph.svg").read_text(encoding="utf-8"))
        generate(self.root, self.records)
        self.assertEqual(graph_bytes, (self.root / "graph.json").read_bytes())

    def test_block_ranges_fragments_and_lexical_evidence_are_attributable(self):
        self.put("semantic-relations.json", json.dumps({"schema_version": "1.0", "status": "proposed",
                 "relations": [{"source_id": "axis_00#01-axis", "target_id": "will_00#text",
                 "relation": "supports", "rationale": "An editorial reading.",
                 "evidence": [{"path": "corpus/00_axis/00_readme.md", "anchor": "01-axis",
                               "excerpt": "The AXIS carries the form."},
                              {"path": "corpus/01_will/00_readme.md", "anchor": "text",
                               "excerpt": "Direction remains revisable."}]}]}))
        generate(self.root, self.records)
        graph = json.loads((self.root / "graph.json").read_text(encoding="utf-8"))
        nodes = {n["id"]: n for n in graph["nodes"]}
        self.assertIn("axis_00#repeat", nodes)
        self.assertIn("axis_00#repeat-1", nodes)
        self.assertEqual(nodes["axis_00#harmonic-question-index"]["block_type"], "content")
        self.assertEqual(nodes["axis_00#trace-without-index"]["block_type"], "content")
        self.assertEqual(nodes["axis_00#navigation-of-the-working-edition"]["block_type"], "navigation")
        self.assertEqual(nodes["axis_00#working-edition-navigation"]["block_type"], "navigation")
        self.assertEqual(nodes["axis_00#connections"]["block_type"], "navigation")
        self.assertEqual(nodes["axis_00#portal"]["anchor_kind"], "explicit")
        for node in nodes.values():
            if node["kind"] != "block":
                continue
            lines = (self.root / node["path"]).read_bytes().decode("utf-8").splitlines(keepends=True)
            segment = "".join(lines[node["line_start"] - 1:node["line_end"]])
            self.assertEqual(hashlib.sha256(segment.encode("utf-8")).hexdigest(), node["content_sha256"])
            self.assertGreaterEqual(node["line_end"], node["line_start"])
        links = [e for e in graph["edges"] if e["type"] == "local_markdown_link"]
        self.assertTrue(any(e["target"] == "axis_00#01-axis" for e in links))
        self.assertTrue(any(e["target"] == "axis_00#portal" for e in links))
        lexical = [e for e in graph["edges"] if e["type"] == "lexical_mention"]
        self.assertFalse(any(e["source"] == "axis_00#ordinary-sentence" and e["target"] == "module:01_will" for e in lexical))
        mentions = [e for e in lexical if e["source"] == "axis_00#noun-and-concept" and e["target"] == "module:01_will"]
        self.assertEqual(len(mentions), 1)
        line = (self.root / "corpus/00_axis/00_readme.md").read_text(encoding="utf-8").splitlines()[mentions[0]["evidence"]["line"] - 1]
        self.assertIn(mentions[0]["evidence"]["term"], line)
        self.assertEqual(mentions[0]["basis"], "lexical_candidate")
        self.assertEqual(sum(e["type"] == "editorial_semantic_relation" for e in graph["edges"]), 1)
        self.assertTrue(any(e["type"] == "editorial_module_relation" and e["source_path"] == "docs/atlas.md" for e in graph["edges"]))

    def test_changed_catalog_source_is_refused_before_derived_writes(self):
        self.put("graph.json", "existing result\n")
        path = self.root / "corpus/00_axis/00_readme.md"
        path.write_text(path.read_text(encoding="utf-8") + "Changed source.\n", encoding="utf-8")
        with self.assertRaisesRegex(InvalidProject, "Changed graph source"):
            generate(self.root, self.records)
        self.assertEqual((self.root / "graph.json").read_text(encoding="utf-8"), "existing result\n")
        self.assertFalse((self.root / "assets").exists())

    def test_reviewed_readings_need_both_sources_and_interpretations_remain_chapters(self):
        self.doc("corpus/00_axis/16_identity.md", "axis_16", "Right to correct", "interpretation",
                 "The bronze hinge retains an aperture.\n")
        self.save_catalog()
        relation = {"source_id": "axis_00#01-axis", "target_id": "will_00#text",
                    "relation": "complements", "rationale": "Bearing is read beside revisable direction.",
                    "review_status": "curator_reviewed", "reviewed_by": "fixture-reader",
                    "evidence": [{"path": "corpus/00_axis/00_readme.md", "anchor": "01-axis",
                                  "excerpt": "The AXIS carries the form."},
                                 {"path": "corpus/01_will/00_readme.md", "anchor": "text",
                                  "excerpt": "Direction remains revisable."}]}
        self.put("reading-relations.json", json.dumps({"relations": [relation]}))
        summary = generate(self.root, self.records)
        self.assertEqual((summary["reading_chapters"], summary["literary_chapters"],
                          summary["interpretation_chapters"]), (4, 3, 1))
        svg = ET.fromstring((self.root / "assets/corpus-graph.svg").read_text(encoding="utf-8"))
        self.assertEqual(sum(c.attrib.get("class") == "chapter-dot" for c in
                             svg.iter("{http://www.w3.org/2000/svg}circle")), 4)
        graph = json.loads((self.root / "graph.json").read_text(encoding="utf-8"))
        reading = next(e for e in graph["edges"] if e["type"] == "curated_section_reading")
        self.assertEqual(reading["reviewed_by"], "fixture-reader")
        self.assertEqual({e["block_id"] for e in reading["evidence"]},
                         {relation["source_id"], relation["target_id"]})
        saved = (self.root / "graph.json").read_bytes()
        for change, message in [({"reviewed_by": ""}, "actual reviewed_by"),
                                ({"evidence": relation["evidence"][:1]}, "both endpoint"),
                                ({"target_id": "module:01_will"}, "target sections")]:
            with self.subTest(change=change):
                self.put("reading-relations.json", json.dumps({"relations": [{**relation, **change}]}))
                with self.assertRaisesRegex(InvalidProject, message):
                    generate(self.root, self.records)
                self.assertEqual(saved, (self.root / "graph.json").read_bytes())

    def test_invalid_routes_semantic_ids_and_output_parents_do_not_write(self):
        original = (self.root / "README.md").read_text(encoding="utf-8")
        for href in ["../outside.md", "corpus/00_axis/00_readme.md#missing-anchor", "missing.md"]:
            with self.subTest(href=href):
                self.put("README.md", original + f"\n[Invalid route]({href})\n")
                self.update_digest("README.md")
                with self.assertRaises(InvalidProject):
                    generate(self.root, self.records)
                self.assertFalse((self.root / "graph.json").exists())
        self.put("README.md", original)
        self.update_digest("README.md")
        self.put("semantic-relations.json", json.dumps({"relations": [{"source_id": "axis_00#missing", "target_id": "module:01_will", "relation": "supports"}]}))
        with self.assertRaises(InvalidProject):
            generate(self.root, self.records)
        self.assertFalse((self.root / "graph.json").exists())
        valid = {"source_id": "axis_00#01-axis", "target_id": "will_00#text",
                 "relation": "supports", "rationale": "An editorial reading.",
                 "evidence": [{"path": "corpus/00_axis/00_readme.md", "anchor": "01-axis",
                               "excerpt": "The AXIS carries the form."},
                              {"path": "corpus/01_will/00_readme.md", "anchor": "text",
                               "excerpt": "Direction remains revisable."}]}
        invalid_relations = [
            ({**valid, "rationale": "  "}, "nonempty rationale"),
            ({**valid, "evidence": []}, "requires evidence"),
            ({**valid, "evidence": [{**valid["evidence"][0], "excerpt": ""}]}, "nonempty excerpt"),
            ({**valid, "evidence": [{**valid["evidence"][0], "excerpt": "A quotation that is no longer in the source."}]}, "Stale editorial semantic excerpt"),
        ]
        for relation, message in invalid_relations:
            with self.subTest(semantic_failure=message):
                self.put("semantic-relations.json", json.dumps({"relations": [relation]}))
                with self.assertRaisesRegex(InvalidProject, message):
                    generate(self.root, self.records)
                self.assertFalse((self.root / "graph.json").exists())
                self.assertFalse((self.root / "assets").exists())
        (self.root / "semantic-relations.json").unlink()
        self.put("assets", "An existing file is not an output directory.\n")
        with self.assertRaisesRegex(InvalidProject, "parent is not a directory"):
            generate(self.root, self.records)
        self.assertFalse((self.root / "graph.json").exists())
        self.assertEqual((self.root / "assets").read_text(encoding="utf-8"), "An existing file is not an output directory.\n")


if __name__ == "__main__":
    unittest.main()
