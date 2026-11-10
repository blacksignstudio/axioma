"""Whole compositions preserve every part, source byte span and old heading ID."""
import hashlib
import unittest

from axioma_context.cli import InvalidProject
from axioma_context.graph import _sections
from axioma_context.graph_components import ROMANS, compositions


class ComponentTests(unittest.TestCase):
    def fixture(self):
        text = "---\nid: compound\ntitle: Source\nkind: literary\n---\n\n# Source\n\n## Text\n\n"
        for name in ("AXIOMA", "HUMANA"):
            text += f"### TRANSMISSIO ∞ {name}\n\nAn introduction, not the whole.\n\n"
            text += "".join(f"### {r} — Part\n\n{name} passage {r}.\n\n" for r in ROMANS)
            text += "### ∞ END PROTOCOL\n\nThe final passage remains.\n\n"
        return text + "## Connections\n\nNavigation is outside both compositions.\n"

    def test_two_exact_wholes_keep_thirteen_parts_and_real_urls(self):
        record = {"id": "compound", "path": "compound.md"}
        text = self.fixture()
        blocks, _, _, _, lines = _sections(record, text)
        old_ids = [b["id"] for b in blocks]
        spans, edges = compositions(record, blocks, lines)
        self.assertEqual([b["id"] for b in blocks], old_ids)
        self.assertEqual(len(spans), 2)
        for span in spans:
            actual = "".join(lines[span["line_start"] - 1:span["line_end"]])
            self.assertEqual(len(span["part_ids"]), 13)
            self.assertIn("passage XIII.", actual)
            self.assertIn("The final passage remains.", actual)
            self.assertNotIn("Navigation is outside", actual)
            self.assertEqual(span["content_sha256"], hashlib.sha256(actual.encode()).hexdigest())
            self.assertIsNone(span["anchor"])
            self.assertTrue(any(b["anchor"] == span["source_anchor"] for b in blocks))
            self.assertEqual(sum(e.get("role") == "part" and e["source"] == span["id"] for e in edges), 13)
            intro = next(b for b in blocks if b["id"] == span["intro_id"])
            self.assertEqual(intro["whole_component_id"], span["id"])
            self.assertLess(intro["line_end"], span["line_end"])

    def test_missing_part_refuses_a_false_whole(self):
        text = self.fixture().replace("### VII — Part", "### Omitted — Part", 1)
        record = {"id": "compound", "path": "compound.md"}
        blocks, _, _, _, lines = _sections(record, text)
        with self.assertRaisesRegex(InvalidProject, "I–XIII"):
            compositions(record, blocks, lines)


if __name__ == "__main__":
    unittest.main()
