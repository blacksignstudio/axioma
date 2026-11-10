"""Isolated regression tests for the public context and dataset tools."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from axioma_context import cli as a


class ContextToolTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="axioma-fixture-")
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "project"
        self.root.mkdir()
        self.train = [{
            "id": "train-01", "synthetic": True,
            "scenario_family": "example-composition",
            "messages": [
                {"role": "user", "content": "Propose a clearer opening for a fictional essay."},
                {"role": "assistant", "content": "Here is a proposed opening, with no claim of external editing."},
            ],
        }]
        self.evaluation = [
            {"id": "eval-01", "synthetic": True, "scenario_family": "missing-evidence",
             "messages": [{"role": "user", "content": "A required source is missing. What is the next step?"}],
             "reference_response": "Preserve the available source and stop the dependent result.",
             "lexical_probes": [["source", "evidence"], ["stop", "pause"]]},
            {"id": "eval-02", "synthetic": True, "scenario_family": "bounded-operation",
             "messages": [{"role": "user", "content": "Prepare a fictional announcement without distributing it."}],
             "reference_response": "Prepare a draft and leave distribution as a separate action.",
             "lexical_probes": [["draft"], ["separate", "not sent"]]},
        ]
        self.write("README.md", self.doc("entry", "Entry", "The complete entry remains readable."))
        self.write("docs/guide.md", self.doc("guide", "Guide", "The complete guide remains readable."))
        self.save_data()
        self.catalog()
        self.manifest()

    def tearDown(self):
        # All fixture paths are generated beneath this unique temporary root.
        self.assertEqual(self.root.parent.resolve(), self.base)
        self.temporary.cleanup()

    def write(self, relative, text):
        target = self.root / relative
        self.assertTrue(target.resolve().is_relative_to(self.base))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        return target

    def doc(self, identifier, title, text, connections="No additional source is required."):
        metadata = {
            "id": identifier, "title": title, "kind": "guide", "version": "2.0.0",
            "language": "en", "license": "CC-BY-4.0",
        }
        return "---\n" + a.yaml.safe_dump(metadata, sort_keys=False) + "---\n\n" + (
            "# " + title + "\n\n## Orientation\n\nA synthetic test document.\n\n"
            "## Text\n\n" + text + "\n\n## Connections\n\n" + connections + "\n\n" + a.FOOTER + "\n"
        )

    def save_data(self):
        for name, records in [("train", self.train), ("eval", self.evaluation)]:
            self.write("data/" + name + ".jsonl", "".join(json.dumps(r, ensure_ascii=True) + "\n" for r in records))

    def catalog(self):
        records = [{"id": identifier, "path": path, "sha256": a.digest(self.root / path)}
                   for identifier, path in [("entry", "README.md"), ("guide", "docs/guide.md")]]
        self.write("catalog.json", json.dumps({"documents": records}, indent=2) + "\n")

    def manifest(self):
        files = [{"path": p.relative_to(self.root).as_posix(), "sha256": a.digest(p)}
                 for p in sorted(self.root.rglob("*"))
                 if p.is_file() and p.name != "manifest.json" and not a.excluded(p.relative_to(self.root).parts)]
        self.write("manifest.json", json.dumps({"files": files}, indent=2) + "\n")

    def test_valid_complete_fixture(self):
        result = a.validate(self.root)
        self.assertEqual(result["status"], "pass", result)
        self.assertEqual(result["documents"], 2)
        self.assertEqual(result["datasets"], {"train": 1, "eval": 2})

    def test_release_text_rejects_crlf_even_when_manifest_digests_match(self):
        text=self.root / "notes.json"
        text.write_bytes(b'{\r\n  "note": "A complete source."\r\n}\r\n')
        self.write("image.png", "binary fixture")
        (self.root / "image.png").write_bytes(b'\x89PNG\r\n\x1a\n')
        self.manifest()
        result=a.validate(self.root)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any(i["path"]=="notes.json" and "LF line endings" in i["message"]
                            for i in result["issues"]))
        text.write_bytes(text.read_bytes().replace(b'\r\n',b'\n'))
        self.manifest()
        self.assertEqual(a.validate(self.root)["status"], "pass")

    def test_cli_redirected_export_is_utf8_under_legacy_stream_encoding(self):
        expected = "The reader’s lamp—still alight."
        self.train[0]["messages"][-1]["content"] = expected
        self.save_data()
        environment = dict(os.environ, PYTHONIOENCODING="cp1252")
        result = subprocess.run(
            [sys.executable, "-m", "axioma_context", "--root", str(self.root),
             "export", "--format", "messages"],
            env=environment, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        exported = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(exported["messages"][-1]["content"], expected)

    def test_uppercase_markdown_cannot_bypass_metadata_and_footer(self):
        self.write("BROKEN.MD", "Unstructured text with no metadata or closing line.\n")
        self.manifest()
        result = a.validate(self.root)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any(i["path"] == "BROKEN.MD" and "metadata" in i["message"].lower() for i in result["issues"]))

    def test_uppercase_valid_markdown_is_counted(self):
        self.write("VALID.MD", self.doc("uppercase", "Uppercase Extension", "The same document rules apply here."))
        self.manifest()
        result = a.validate(self.root)
        self.assertEqual(result["status"], "pass", result)
        self.assertEqual(result["documents"], 3)

    def test_closing_line_and_common_template_are_enforced(self):
        original = (self.root / "README.md").read_text(encoding="utf-8")
        variants = [
            original.replace("## Text", a.FOOTER + "\n\n## Text"),
            original.replace("## Connections", "## Other Reading"),
            original.rstrip() + "\nAn extra line after the closing phrase.\n",
        ]
        for text in variants:
            with self.subTest(text=text):
                self.write("README.md", text)
                self.manifest()
                self.assertEqual(a.validate(self.root)["status"], "fail")

    def test_real_anchors_are_checked_but_code_links_are_literals(self):
        literal = "```md\n[example](missing.md#not-real)\n```\n\nRead [the guide](docs/guide.md#text)."
        self.write("README.md", self.doc("entry", "Entry", literal))
        self.manifest()
        self.assertEqual(a.validate(self.root)["status"], "pass")
        self.write("README.md", self.doc("entry", "Entry", literal.replace("guide.md#text", "guide.md#missing")))
        self.manifest()
        result = a.validate(self.root)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("anchor" in i["message"].lower() for i in result["issues"]))

    def test_duplicate_metadata_keys_are_rejected(self):
        text = "---\nid: one\nid: two\n---\n# Body\n"
        with self.assertRaisesRegex(a.InvalidProject, "Duplicate metadata key"):
            a.document(text)

    def test_encoded_unicode_url_resolves_to_the_same_local_file(self):
        filename = "docs/caf\u00e9 note.md"
        target = self.write(filename, self.doc("accent", "Accented Filename", "A local Unicode path remains an ordinary reference."))
        self.assertEqual(a.safe(self.root, "docs/caf%C3%A9%20note.md", exists=True), target.resolve())
        self.write("README.md", self.doc("entry", "Entry", "Read [the local note](docs/caf%C3%A9%20note.md#text)."))
        self.manifest()
        self.assertEqual(a.validate(self.root)["status"], "pass")

    def test_output_is_a_new_descendant_file_and_never_overwrites(self):
        for relative in ["build", "README.md", "../beyond.json", "%2e%2e/beyond.json"]:
            with self.subTest(relative=relative), self.assertRaises(a.InvalidProject):
                a.write_build(self.root, relative, "fixture")
        a.write_build(self.root, "build/nested/packet.txt", "first version")
        output = self.root / "build/nested/packet.txt"
        self.assertEqual(output.read_text(encoding="utf-8"), "first version")
        with self.assertRaisesRegex(a.InvalidProject, "already exists"):
            a.write_build(self.root, "build/nested/packet.txt", "replacement")
        self.assertEqual(output.read_text(encoding="utf-8"), "first version")

    def test_nonportable_windows_segments_and_absolute_paths_are_refused(self):
        values = ["build/NUL", "build/CON.txt", "build/COM1.json", "build/LPT9", "build/note.md.",
                  "build/space /note.json", "build/dir./note.json", "C:/outside.json", "/outside.json", "note.md:stream"]
        for relative in values:
            with self.subTest(relative=relative), self.assertRaises(a.InvalidProject):
                a.safe(self.root, relative)

    def test_linked_directory_is_rejected_before_inventory_descends(self):
        outside = self.base / "outside"
        outside.mkdir()
        marker = outside / "outside-marker.txt"
        marker.write_text("Only a synthetic boundary marker.", encoding="utf-8")
        link = self.root / "external"
        self.assertTrue(link.parent.resolve().is_relative_to(self.root))
        self.assertTrue(outside.resolve().is_relative_to(self.base))
        self.assertFalse(outside.resolve().is_relative_to(self.root))
        created = False
        try:
            try:
                link.symlink_to(outside, target_is_directory=True)
                created = True
            except OSError:
                if os.name != "nt":
                    self.skipTest("Host does not permit the isolated directory-link fixture")
                result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True)
                if result.returncode:
                    self.skipTest("Host does not permit the isolated Windows junction fixture")
                created = True
            with self.assertRaises(a.InvalidProject):
                a.safe(self.root, "external/outside-marker.txt", exists=True)
            with self.assertRaises(a.InvalidProject):
                list(a.project_files(self.root))
            result = a.validate(self.root)
            self.assertEqual(result["status"], "fail")
            self.assertFalse(any("outside-marker" in i.get("path", "") for i in result["issues"]))
            self.assertEqual(marker.read_text(encoding="utf-8"), "Only a synthetic boundary marker.")
        finally:
            if created:
                # Remove only the verified link object; never traverse its target.
                if link.is_symlink():
                    link.unlink()
                else:
                    self.assertTrue(getattr(link, "is_junction", lambda: False)())
                    os.rmdir(link)

    def test_complete_context_packet_and_exact_byte_budget(self):
        before = {p.relative_to(self.root).as_posix(): a.digest(p) for p in self.root.rglob("*") if p.is_file()}
        packet = a.packet(self.root, ["entry", "guide"], 100000)
        for relative in ["README.md", "docs/guide.md"]:
            body = a.document((self.root / relative).read_text(encoding="utf-8"))[1]
            self.assertIn(body, packet)
        size = len(packet.encode("utf-8"))
        self.assertEqual(a.packet(self.root, ["entry", "guide"], size), packet)
        with self.assertRaisesRegex(a.InvalidProject, "Nothing was truncated"):
            a.packet(self.root, ["entry", "guide"], size - 1)
        after = {p.relative_to(self.root).as_posix(): a.digest(p) for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_unknown_or_changed_context_source_is_not_replaced(self):
        with self.assertRaisesRegex(a.InvalidProject, "Unknown document ID"):
            a.packet(self.root, ["missing"], 100000)
        self.write("README.md", self.doc("entry", "Entry", "An independently changed source."))
        with self.assertRaisesRegex(a.InvalidProject, "Changed context source"):
            a.packet(self.root, ["entry"], 100000)

    def test_malformed_message_objects_are_not_exported(self):
        variants = ["not a list", [], [{"role": "unknown", "content": "text"}],
                    [{"role": "assistant", "content": 42}], [{"role": "assistant", "content": "   "}]]
        for messages in variants:
            with self.subTest(messages=messages):
                self.train[0]["messages"] = messages
                self.save_data()
                with self.assertRaises(a.InvalidProject):
                    a.export_training(self.root, "trl")

    def test_training_requires_an_assistant_completion_and_user_prompt(self):
        variants = [
            [{"role": "user", "content": "A prompt without a completion."}],
            [{"role": "system", "content": "A context."}, {"role": "assistant", "content": "A response without a user prompt."}],
        ]
        for messages in variants:
            with self.subTest(messages=messages), self.assertRaises(a.InvalidProject):
                a.valid_messages(messages, training=True)

    def test_both_training_exports_preserve_the_message_structure(self):
        messages = self.train[0]["messages"]
        conversational = json.loads(a.export_training(self.root, "messages"))
        paired = json.loads(a.export_training(self.root, "trl"))
        self.assertEqual(conversational, {"messages": messages})
        self.assertEqual(paired, {"prompt": messages[:-1], "completion": messages[-1:]})

    def test_dataset_ids_and_prompts_are_unique_while_categories_may_repeat(self):
        original = json.loads(json.dumps(self.train))
        for violation in ["id", "prompt"]:
            with self.subTest(violation=violation):
                self.train = json.loads(json.dumps(original))
                if violation == "id":
                    self.train[0]["id"] = self.evaluation[0]["id"]
                elif violation == "prompt":
                    self.train[0]["messages"][0] = self.evaluation[0]["messages"][0]
                self.save_data()
                with self.assertRaises(a.InvalidProject):
                    a.validate_data(self.root)
        self.train = json.loads(json.dumps(original))
        self.train[0]["scenario_family"] = self.evaluation[0]["scenario_family"]
        self.save_data()
        self.assertEqual(a.validate_data(self.root), {"train": 1, "eval": 2})

    def test_unknown_and_duplicate_prediction_ids_are_rejected(self):
        for predictions in [
            [{"id": "unknown", "text": "A response."}],
            [{"id": "eval-01", "text": "Stop for the missing source."}, {"id": "eval-01", "text": "Another response."}],
        ]:
            with self.subTest(predictions=predictions):
                self.write("build/predictions.jsonl", "".join(json.dumps(r) + "\n" for r in predictions))
                with self.assertRaisesRegex(a.InvalidProject, "Unknown or duplicate"):
                    a.evaluate(self.root, "build/predictions.jsonl")

    def test_missing_predictions_remain_in_the_evaluation_denominator(self):
        self.write("build/predictions.jsonl", json.dumps({"id": "eval-01", "text": "Stop because the source is missing."}) + "\n")
        result = a.evaluate(self.root, "build/predictions.jsonl")
        self.assertEqual((result["cases"], result["predictions"], result["missing"]), (2, 1, 1))
        self.assertEqual(result["lexical_probe_passed"], 1)
        self.assertTrue(all(row["human_review_required"] for row in result["observations"]))
        self.assertFalse(next(row for row in result["observations"] if row["id"] == "eval-02")["lexical_probe_pass"])

    def test_cli_failure_does_not_create_the_requested_output(self):
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            code = a.main(["--root", str(self.root), "pack", "--ids", "missing", "--out", "build/result.txt"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(error.getvalue())["status"], "fail")
        self.assertFalse((self.root / "build/result.txt").exists())

    def test_language_and_unmanifested_files_cannot_pass(self):
        # The escaped character exists only in an isolated negative fixture.
        self.write("README.md", self.doc("entry", "Entry", "Unexpected script: \u0420"))
        self.manifest()
        self.assertEqual(a.validate(self.root)["status"], "fail")
        self.write("README.md", self.doc("entry", "Entry", "The intended English text."))
        self.manifest()
        self.write("unregistered.txt", "A file not named in the release manifest.")
        result = a.validate(self.root)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any(i["path"] == "unregistered.txt" for i in result["issues"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
