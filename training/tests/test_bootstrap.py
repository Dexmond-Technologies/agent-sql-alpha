import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from training_pipeline.bootstrap import SNAPSHOTS, checkout_snapshot, seed_metadata


class BootstrapTests(unittest.TestCase):
    def test_seed_metadata_preserves_resumed_manifests(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshots, library = root / "snapshots", root / "library"
            (snapshots / "collection").mkdir(parents=True)
            (snapshots / "collection/manifest.json").write_text('{"original": true}')
            (snapshots / "CATALOG.md").write_text("Recorded references")
            (snapshots / "general-repositories.json").write_text("{}")
            seed_metadata(library, snapshots)
            (library / "collection/manifest.json").write_text('{"resumed": true}')
            seed_metadata(library, snapshots)
            self.assertEqual(json.loads((library / "collection/manifest.json").read_text()), {"resumed": True})
            self.assertTrue((library / "CATALOG.md").exists())
            self.assertFalse((library / "general-repositories.json").exists())

    def test_pinned_checkout_and_modified_directory_preservation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            def git(*arguments):
                return subprocess.check_output(["git", "-C", str(source), *arguments], text=True).strip()
            git("init", "-q")
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.invalid")
            (source / "docs").mkdir()
            (source / "docs/reference.md").write_text("Pinned reference\n")
            git("add", ".")
            git("commit", "-qm", "Pinned reference")
            commit = git("rev-parse", "HEAD")
            (source / "docs/reference.md").write_text("Newer reference\n")
            git("commit", "-qam", "Newer reference")
            spec = {"url": str(source), "commit": commit, "sparse_directories": ["docs"]}
            destination = root / "restored"
            checkout_snapshot(destination, spec)
            self.assertEqual((destination / "docs/reference.md").read_text(), "Pinned reference\n")
            checkout_snapshot(destination, spec)
            (destination / "docs/reference.md").write_text("Local changes\n")
            with self.assertRaisesRegex(ValueError, "Modified checkout preserved"):
                checkout_snapshot(destination, spec)
            self.assertEqual((destination / "docs/reference.md").read_text(), "Local changes\n")
            with self.assertRaisesRegex(ValueError, "Revision mismatch"):
                checkout_snapshot(destination, {**spec, "commit": git("rev-parse", "HEAD")})

    def test_committed_snapshot_manifests_have_required_metadata(self):
        general = json.loads((SNAPSHOTS / "general-repositories.json").read_text())
        self.assertEqual(len(general["repositories"]), 7)
        manifests = sorted(SNAPSHOTS.glob("*/manifest.json"))
        self.assertEqual(len(manifests), 6)
        for path in manifests:
            with self.subTest(collection=path.parent.name):
                manifest = json.loads(path.read_text())
                self.assertEqual(manifest["schema_version"], 1)
                self.assertTrue(manifest["rights"])


if __name__ == "__main__":
    unittest.main()
