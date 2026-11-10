"""Framing stays in the graph without becoming a fabricated semantic passage."""
import unittest

from axioma_context.graph import _sections


class FramingTests(unittest.TestCase):
    def classify(self, heading, body):
        text = f"---\nid: fixture\n---\n### {heading}\n\n{body}\n"
        blocks, *_ = _sections({"id": "fixture", "path": "fixture.md"}, text)
        self.assertEqual(len(blocks), 1)
        return blocks[0]

    def test_yaml_only_component_metadata_keeps_source_range(self):
        node = self.classify("Component Metadata", "```yaml\nid: a\ntype: covenant\n```")
        self.assertEqual(node["block_type"], "metadata")
        self.assertEqual(node["id"], "fixture#component-metadata")
        self.assertEqual((node["line_start"], node["line_end"]), (4, 9))

    def test_a_title_or_embedded_yaml_does_not_suppress_literary_content(self):
        for heading, body in [
            ("Component Metadata", "The name is a philosophical image."),
            ("Component Metadata", "```yaml\nid: a\n```\n\nA voice remains."),
            ("A YAML Image", "```yaml\nid: a\n```"),
            ("00. DISCLAIMER", "Silence disclaims its own beginning.")]:
            with self.subTest(heading=heading, body=body):
                self.assertEqual(self.classify(heading, body)["block_type"], "content")

    def test_explicit_original_genre_disclaimer_is_editorial_framing(self):
        node = self.classify("00. DISCLAIMER", "A work of speculative philosophy.\n\nHypothetical and symbolic.")
        self.assertEqual(node["block_type"], "editorial")


if __name__ == "__main__":
    unittest.main()
