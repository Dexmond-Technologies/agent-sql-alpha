import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from training_pipeline.prepare import (DocBookText, classify_license, decode, digest,
                                       index_chunks, make_chunks, markdown, validate, windows)
from training_pipeline.search import search


class PreparationTests(unittest.TestCase):
    def test_markdown_keeps_literal_sql_and_template_examples(self):
        source = "---\ntitle: SQL\n---\n{% hint style=\"info\" %}Note{% endhint %}\n```sql\nSELECT '<sub>x</sub>', 'a  b', '{{value}}';\n```"
        result, flags = markdown(source)
        self.assertIn("# SQL", result)
        self.assertNotIn("{% hint", result)
        self.assertIn("SELECT '<sub>x</sub>', 'a  b', '{{value}}';", result)
        self.assertEqual(flags, [])

    def test_sgml_preserves_operators_code_and_unknown_entities(self):
        parser = DocBookText("20devel")
        parser.feed('<title>Queries</title><para>A <literal>SELECT</literal>.</para><screen>SELECT 1 &lt; 2, \'a  b\';\n  SELECT 2;</screen><para>&version; &unresolved;</para>')
        self.assertIn("SELECT 1 < 2, 'a  b';\n  SELECT 2;", parser.text())
        self.assertIn("20devel", parser.text())
        self.assertEqual(parser.unresolved, {"unresolved"})

    def test_utf16_sql(self):
        text, encoding = decode("SELECT 'λ';".encode("utf-16"))
        self.assertEqual(text, "SELECT 'λ';")
        self.assertEqual(encoding, "utf-16")

    def test_chunk_bounds_and_complete_coverage(self):
        text = ("A paragraph with SELECT a FROM b;\n\n" * 100) + "x" * 400
        spans = list(windows(text, 300, 40))
        covered = set()
        for start, end, chunk in spans:
            self.assertEqual(text[start:end], chunk)
            self.assertLessEqual(len(chunk), 300)
            covered.update(range(start, end))
        self.assertEqual(len(covered), len(text))

    def test_page_license_overrides_repository_default(self):
        source = {"notice": "LICENSE", "license": "MIT"}
        self.assertEqual(classify_license(source, "ordinary"), ("MIT", "notice-recorded"))
        self.assertEqual(classify_license(source, "This page is licensed: GPLv2\n")[1], "review-required")
        self.assertEqual(classify_license(source, "This was adapted from elsewhere.")[1], "review-required")

    def test_shared_chunks_do_not_cross_splits(self):
        common = "SELECT name FROM customers;\n" * 15
        docs = []
        for suffix in [" WHERE active = 1;", " WHERE active = 0;"]:
            text = common + suffix
            docs.append({"id": digest(text), "text": text, "quality_flags": [], "training_eligible": True,
                         "provenance": [{"dialect": "tsql", "source_id": "fixture", "source_url": "fixture"}]})
        config = {"chunk_chars": 200, "overlap_chars": 30, "split_seed": "test"}
        chunks, _ = make_chunks(docs, config)
        self.assertEqual(docs[0]["split"], docs[1]["split"])
        self.assertEqual(docs[0]["group_id"], docs[1]["group_id"])
        self.assertEqual(validate(docs, chunks, config), [])
        self.assertEqual(chunks, make_chunks(docs, config)[0])

    def test_readonly_search_filters_and_literal_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "search.sqlite"
            index_chunks(database, [{"id": "1", "text": "window functions", "dialects": ["postgresql"],
                                    "source_urls": ["source"], "split": "test", "training_eligible": True}])
            self.assertEqual(len(search(database, "window functions", "postgresql")), 1)
            self.assertEqual(search(database, "window", "tsql"), [])
            self.assertEqual(search(database, "window", split="train"), [])
            self.assertEqual(search(database, "' OR 1=1; DROP TABLE chunks;"), [])


if __name__ == "__main__":
    unittest.main()
