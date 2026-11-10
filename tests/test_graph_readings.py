"""A motif search must expose real paired text and leave unsupported gaps open."""
import unittest

from axioma_context.graph_readings import motif_candidates, section_records


class ReadingCandidateTests(unittest.TestCase):
    def sections(self):
        texts = {
            "a": "### Hinge\n\nThe bronze hinge carries an aperture.\n",
            "b": "### Opening\n\nAn aperture turns on the bronze hinge.\n",
            "c": "### Unmatched\n\nQuasar.\n"}
        docs = {i: {"kind": "literary", "sha256": i * 64} for i in texts}
        lines = {f"corpus/{i}/chapter.md": t.splitlines(keepends=True) for i, t in texts.items()}
        nodes = [{"id": i + "#section", "document_id": i, "kind": "block", "block_type": "content",
                  "title": i, "anchor": "section", "path": f"corpus/{i}/chapter.md",
                  "own_line_start": 1, "own_line_end": len(t.splitlines())} for i, t in texts.items()]
        return section_records(nodes, lines, docs), texts

    def test_exact_two_endpoint_witnesses_and_unresolved_are_not_curated(self):
        records, texts = self.sections()
        result = motif_candidates(records, max_neighbors=1)
        edge = result["a#section"][0]
        self.assertEqual(edge["target"], "b#section")
        self.assertEqual(edge["status"], "unreviewed_candidate")
        self.assertEqual(edge["confidence"], "candidate_only_not_a_probability")
        self.assertEqual(result["c#section"], [])
        for witness in edge["evidence"]:
            self.assertIn(witness["excerpt"], texts[witness["block_id"].split("#")[0]])
        self.assertEqual(result, motif_candidates(dict(reversed(list(records.items()))), max_neighbors=1))


if __name__ == "__main__":
    unittest.main()
