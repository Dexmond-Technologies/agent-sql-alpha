"""Restore the reference library from publisher sources and recorded Git commits.

Run from the repository root:
    PYTHONPATH=training python -m training_pipeline.bootstrap
This downloads reference data; it neither trains a model nor runs reference code.
"""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

BASE = Path(__file__).resolve().parents[1]
SNAPSHOTS = BASE / "reference-snapshots"
LIBRARY = BASE / "TRAINING"


def git(root, *arguments):
    result = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-C", str(root), *arguments],
        check=True, capture_output=True, text=True, timeout=600,
        env=dict(os.environ, GIT_TERMINAL_PROMPT="0"),
    )
    return result.stdout.strip()


def checkout_snapshot(destination, source):
    """Create a pinned checkout; never reset or overwrite an existing checkout."""
    if destination.exists():
        if not (destination / ".git").is_dir():
            raise ValueError(f"Existing directory is not a Git checkout: {destination}")
        if git(destination, "remote", "get-url", "origin") != source["url"]:
            raise ValueError(f"Origin mismatch; directory preserved: {destination}")
        if git(destination, "rev-parse", "HEAD") != source["commit"]:
            raise ValueError(f"Revision mismatch; directory preserved: {destination}")
        if git(destination, "status", "--porcelain"):
            raise ValueError(f"Modified checkout preserved: {destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="reference-clone-", dir=destination.parent) as temporary:
        checkout = Path(temporary) / "checkout"
        subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", "clone", "--filter=blob:none",
             "--depth", "1", "--no-checkout", source["url"], str(checkout)],
            check=True, timeout=600, env=dict(os.environ, GIT_TERMINAL_PROMPT="0"),
        )
        git(checkout, "config", "core.hooksPath", "/dev/null")
        git(checkout, "fetch", "--depth", "1", "origin", source["commit"])
        if source.get("sparse_directories"):
            git(checkout, "sparse-checkout", "set", "--cone", *source["sparse_directories"])
        git(checkout, "checkout", "--detach", source["commit"])
        checkout.rename(destination)


def seed_metadata(library=LIBRARY, snapshots=SNAPSHOTS):
    """Copy recorded metadata only where it is missing; preserve resumed runs."""
    for source in sorted(snapshots.rglob("*")):
        if source.is_file() and source.name != "general-repositories.json":
            destination = library / source.relative_to(snapshots)
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)


def general_sources():
    sources = json.loads((SNAPSHOTS / "general-repositories.json").read_text())["repositories"]
    for source in sources:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", source["directory"]):
            raise ValueError("Invalid source directory in snapshot metadata")
        if not re.fullmatch(r"[0-9a-f]{40}", source["commit"]):
            raise ValueError("Invalid source revision in snapshot metadata")
        if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", source["url"]):
            raise ValueError("General reference origins must be public GitHub HTTPS URLs")
        print(f"Restoring {source['directory']} at {source['commit']}", flush=True)
        checkout_snapshot(LIBRARY / source["directory"], source)

    pages = [
        ("microsoft-sql-docs/language-reference.md", "https://raw.githubusercontent.com/MicrosoftDocs/sql-docs/live/docs/t-sql/language-reference.md"),
        ("microsoft-learn-odbc-sql/sql.md", "https://raw.githubusercontent.com/MicrosoftDocs/cpp-docs/main/docs/data/odbc/sql.md"),
        ("microsoft-learn-odbc-sql/sql.html", "https://learn.microsoft.com/en-us/cpp/data/odbc/sql?view=msvc-170"),
    ]
    for relative, url in pages:
        destination = LIBRARY / relative
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="reference-page-") as temporary:
            payload = Path(temporary) / "payload"
            subprocess.run(
                ["curl", "-fsSL", "--proto", "=https", "--proto-redir", "=https",
                 "--connect-timeout", "15", "--max-time", "120", "--retry", "2",
                 "--max-filesize", "2097152", "--output", str(payload), url],
                check=True, timeout=400,
            )
            shutil.copy2(payload, destination)


def run(script, *arguments):
    import sys
    subprocess.run([sys.executable, str(BASE / "training_pipeline" / script), *arguments], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--general-only", action="store_true", help="Restore the general SQL references only")
    args = parser.parse_args()
    seed_metadata()
    general_sources()
    if not args.general_only:
        # Seed OSS checkouts before its downloader runs so recorded revisions are retained.
        manifest = json.loads((LIBRARY / "ibm-i-open-source/manifest.json").read_text())
        for source in manifest["repositories"]:
            if source.get("commit"):
                selection = source.get("selected_directories")
                checkout_snapshot(LIBRARY / "ibm-i-open-source" / source["path"], {
                    "url": source["source_url"], "commit": source["commit"],
                    "sparse_directories": selection if isinstance(selection, list) else [],
                })
        run("download_ibmi.py")
        run("download_ibm_cobol.py")
        run("download_ibmi_oss.py")
        run("download_reference_repositories.py", "--collection", "community", "--via-git")
        run("download_reference_repositories.py", "--collection", "engineering", "--via-git")
        run("download_engineering_pages.py")
        run("verify_ibm_collections.py")
        # Verification checks successful downloads. Separately expose unavailable URLs.
        failures = []
        for path in LIBRARY.glob("*/manifest.json"):
            manifest = json.loads(path.read_text())
            for key in ("resources", "repositories", "pages"):
                records = manifest.get(key, [])
                if isinstance(records, dict):
                    records = records.values()
                for record in records:
                    if record.get("status") != "downloaded":
                        failures.append({"collection": path.parent.name,
                                         "source": record.get("url", record.get("source_url")),
                                         "error": record.get("error", "Incomplete download")})
        report = LIBRARY / "bootstrap-unavailable.json"
        report.write_text(json.dumps(failures, indent=2) + "\n")
        print(f"Unavailable sources: {len(failures)}; details: {report}", flush=True)
        if failures:
            raise SystemExit("Library restored with unavailable sources; review the report and retry before training.")
    print("Reference downloads finished. IBM extraction and model training remain separate steps.")


if __name__ == "__main__":
    main()
