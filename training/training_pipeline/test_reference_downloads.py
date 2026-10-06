"""Offline regression checks for reference selection and integrity helpers."""

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from download_ibm_cobol import article_bodies, canonical, expected_type, extract_archives, file_type
from download_reference_repositories import selected
import verify_ibm_collections as verification


class ReferenceDownloadTests(unittest.TestCase):
    def test_ibm_urls_use_https_and_encoded_paths(self):
        self.assertEqual(canonical("http://www.ibm.com/a doc.pdf#page=2"),
                         "https://www.ibm.com/a%20doc.pdf")
        self.assertEqual(canonical("https://www.ibm.com/a%20doc.pdf"),
                         "https://www.ibm.com/a%20doc.pdf")

    def test_non_ibm_or_non_http_urls_are_rejected(self):
        for url in ["https://ibm.com.example.org/book.pdf", "file:///tmp/book.pdf", "https://example.org/ibm.com"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                canonical(url)

    def test_signatures_are_not_extensions(self):
        self.assertEqual(expected_type("https://www.ibm.com/book.PDF?download=1"), "pdf")
        self.assertEqual(file_type(b"<html>Not a PDF</html>", "text/html"), "html")
        self.assertEqual(file_type(b"%PDF-1.7\n", "application/octet-stream"), "pdf")

    def test_announcement_bodies_do_not_generate_recursive_urls(self):
        item = {"status": "downloaded", "kind": "html", "references": [],
                "url": "https://www.ibm.com/docs/en/announcements/archive/ENUS123-456",
                "effective_url": "https://www.ibm.com/docs/en/announcements/archive/ENUS123-456"}
        bodies = article_bodies([item])
        self.assertEqual(len(bodies), 1)
        self.assertEqual(article_bodies([item] + [dict(bodies[0], status="downloaded", kind="html")]), [])

    def test_archive_metadata_is_not_a_document(self):
        with tempfile.TemporaryDirectory(prefix="reference-test-") as directory:
            root = Path(directory)
            with zipfile.ZipFile(root / "sample.zip", "w") as archive:
                archive.writestr("manual.pdf", b"%PDF-1.7\nfixture")
                archive.writestr("__MACOSX/._manual.pdf", b"AppleDouble fixture")
            item = {"status": "downloaded", "kind": "zip", "path": "sample.zip",
                    "url": "https://www.ibm.com/sample.zip",
                    "references": [{"version": "1.0", "language": "en"}]}
            documents, metadata = extract_archives([item], root)
            self.assertEqual(len(documents), 1)
            self.assertEqual(len(metadata), 1)
            self.assertTrue((root / documents[0]["path"]).read_bytes().startswith(b"%PDF-"))

    def test_reference_selection_excludes_active_packs_and_models(self):
        for path in ["AGENTS.md", "docs/SKILL.md", ".claude/rules.md", "docs/skills/example.md",
                     "models/model.json", "../README.md", "docs/examples/data/large.json"]:
            with self.subTest(path=path):
                self.assertFalse(selected(path, ["docs", "models"]))
        self.assertTrue(selected("docs/usage.md", ["docs"]))
        self.assertTrue(selected("host/iRPGUnit/QLLIST/LGPL.3.0.TXT", []))
        self.assertTrue(selected("docs/reference.pdf", ["docs"]))

    def test_integrity_checks_bytes_and_pinned_blob(self):
        with tempfile.TemporaryDirectory(prefix="reference-test-") as directory:
            root = Path(directory)
            data = b"Reference fixture\n"
            (root / "sample.txt").write_bytes(data)
            item = {"path": "sample.txt", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                    "git_blob_sha": hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()}
            with patch.object(verification, "ROOT", root):
                self.assertIsNone(verification.verify_file((root, item)))
                failure = verification.verify_file((root, dict(item, bytes=1, git_blob_sha="wrong")))
                self.assertIn("Byte count mismatch", failure["errors"])
                self.assertIn("Pinned Git blob mismatch", failure["errors"])


if __name__ == "__main__":
    unittest.main()
