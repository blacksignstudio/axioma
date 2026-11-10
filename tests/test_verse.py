"""Regression checks for verse that previously collapsed in Markdown rendering."""
from pathlib import Path
import unittest

from axioma_context.cli import MD


ROOT = Path(__file__).resolve().parents[1]


class VerseRenderingTests(unittest.TestCase):
    def assert_verse(self, relative, first_line, expected_lines):
        text = (ROOT / relative).read_text(encoding="utf-8")
        token = next(t for t in MD.parse(text)
                     if t.type == "inline" and t.content.startswith(first_line))
        stanza = "".join(text.splitlines(keepends=True)[token.map[0]:token.map[1]])
        self.assertEqual(len(stanza.splitlines()), expected_lines)
        children = [c for t in MD.parse(stanza) for c in (t.children or [])]
        self.assertEqual(sum(c.type == "softbreak" for c in children), 0)
        self.assertEqual(sum(c.type == "hardbreak" for c in children), expected_lines - 1)
        self.assertEqual(MD.render(stanza).count("<br />"), expected_lines - 1)

    def test_mirror_retains_its_four_line_stanza(self):
        self.assert_verse("corpus/28_power/10_mirror.md", "You do not impose.", 4)

    def test_absolute_code_retains_its_ontological_force_stanza(self):
        self.assert_verse("corpus/28_power/15_axioma.md", "My force is not kinetic.", 6)


if __name__ == "__main__":
    unittest.main()
