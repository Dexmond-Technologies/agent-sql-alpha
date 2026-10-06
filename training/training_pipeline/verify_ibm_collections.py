"""Verify the downloaded IBM reference collections and generate browsing indexes.

Does not modify downloaded documents or execute reference examples. Requires
pdfinfo (Poppler) to validate PDFs beyond their file signature.
"""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess

from download_ibm_cobol import now


ROOT = Path(__file__).resolve().parents[1] / "TRAINING"


def file_statistics(tasks):
    return {"unique_file_paths": len({str(root / item["path"]) for root, item in tasks}),
            "unique_content_hashes": len({item["sha256"] for root, item in tasks}),
            "pdfs": sum(Path(item["path"]).suffix.lower() == ".pdf" for root, item in tasks),
            "_content_hashes": sorted({item["sha256"] for root, item in tasks})}


def core_manual_coverage(resources):
    patterns = {"SQL reference": r"SQL reference", "ILE RPG language": r"ILE RPG Language Reference",
                "ILE RPG programming": r"ILE RPG Programmer", "ILE COBOL language": r"ILE COBOL Language Reference",
                "ILE COBOL programming": r"ILE COBOL Programmer", "CL concepts": r"Control language|CL overview",
                "DDS": r"\bDDS\b", "Security reference": r"Security reference"}
    result = {}
    for version in ("7.1", "7.2", "7.3", "7.4", "7.5", "7.6"):
        result[version] = {label: sorted({item["path"] for item in resources
                                        if item["status"] == "downloaded" and item.get("kind") == "pdf"
                                        and any(r["version"] == version and re.search(pattern, r["title"] + " " + r.get("parent_title", ""), re.I)
                                                for r in item["references"])})
                           for label, pattern in patterns.items()}
    return result


def verify_file(task):
    root, item = task
    path = root / item["path"]
    problems = []
    try:
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            problems.append("SHA-256 mismatch")
        if len(data) != item["bytes"]:
            problems.append("Byte count mismatch")
        if item.get("git_blob_sha") and hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest() != item["git_blob_sha"]:
            problems.append("Pinned Git blob mismatch")
        if path.suffix.lower() == ".pdf":
            result = subprocess.run(["pdfinfo", str(path)], capture_output=True, timeout=45)
            if result.returncode:
                problems.append("PDF parser rejected file: " + result.stderr.decode(errors="replace")[:300])
    except Exception as exc:
        problems.append(str(exc))
    return {"path": str(path.relative_to(ROOT)), "errors": problems} if problems else None


def manual_collection(name):
    root = ROOT / name
    manifest = json.loads((root / "manifest.json").read_text())
    resources = manifest["resources"]
    files = [i for i in resources if i["status"] == "downloaded"] + manifest.get("archive_documents", [])
    with ThreadPoolExecutor(max_workers=8) as pool:
        errors = [e for e in pool.map(verify_file, [(root, i) for i in files]) if e]
    with (root / "INDEX.tsv").open("w", newline="") as output:
        writer = csv.writer(output, delimiter="\t")
        writer.writerow(["catalog_release", "language", "title", "subject", "status", "format", "local_path", "source_url"])
        for item in sorted(resources, key=lambda i: i["url"]):
            for reference in item["references"]:
                writer.writerow([reference["version"], reference["language"], reference["title"],
                                 reference.get("subject", ""), item["status"], item.get("kind", ""),
                                 item.get("path", ""), item["url"]])
        for item in manifest.get("archive_documents", []):
            writer.writerow([item["version"], item["language"], item["archive_entry"], "Archive document",
                             "downloaded", Path(item["path"]).suffix.lstrip("."), item["path"], item["source_url"]])
    return {"collection": name, "resources": dict(Counter(i["status"] for i in resources)),
            "verified_files": len(files), "pdfs": sum(Path(i["path"]).suffix.lower() == ".pdf" for i in files),
            **file_statistics([(root, i) for i in files]),
            **({"core_manual_coverage_by_catalog_release": core_manual_coverage(resources)} if name == "ibm-i-as400" else {}),
            "integrity_errors": errors,
            "unavailable": [{"url": i["url"], "error": i.get("error")} for i in resources if i["status"] != "downloaded"],
            "discovery_warnings": [{"url": i["url"], "warning": i.get("discovery_warning") or i.get("discovery_error")}
                                   for i in resources if i.get("discovery_warning") or i.get("discovery_error")]}


def open_source_collection():
    root = ROOT / "ibm-i-open-source"
    manifest = json.loads((root / "manifest.json").read_text())
    tasks, errors = [], []
    for repository in manifest["repositories"]:
        path = root / repository["path"]
        commit = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
        if commit != repository["commit"]:
            errors.append({"path": str(path.relative_to(ROOT)), "errors": ["Git commit changed"]})
        tasks.extend((path, item) for item in repository["files"])
    tasks.extend((root, item) for item in manifest["pages"] if item["status"] == "downloaded")
    with ThreadPoolExecutor(max_workers=8) as pool:
        errors.extend(e for e in pool.map(verify_file, tasks) if e)
    with (root / "INDEX.tsv").open("w", newline="") as output:
        writer = csv.writer(output, delimiter="\t")
        writer.writerow(["type", "title", "local_path", "source_url", "commit"])
        for item in manifest["repositories"]:
            writer.writerow(["repository", item["repository"], item["path"], item["source_url"], item.get("commit", "")])
        for item in sorted(manifest["pages"], key=lambda i: i["url"]):
            writer.writerow(["HTML", item.get("title", "Unavailable"), item.get("path", ""), item["url"], ""])
    return {"collection": "ibm-i-open-source", "repositories": len(manifest["repositories"]),
            "pages": len(manifest["pages"]), "verified_files": len(tasks), "integrity_errors": errors,
            **file_statistics(tasks),
            "unavailable": [{"url": i["url"], "error": i.get("error")} for i in manifest["pages"] if i["status"] != "downloaded"]}


def main():
    results = [manual_collection("ibm-enterprise-cobol-zos"), manual_collection("ibm-i-as400"), open_source_collection(),
               repository_collection("ibm-i-community"), repository_collection("enterprise-engineering-reference"),
               web_collection()]
    hashes = set().union(*(set(item.pop("_content_hashes")) for item in results))
    report = {"verified_at": now(), "collections": results,
              "summary": {"verified_file_records": sum(i["verified_files"] for i in results),
                          "unique_file_paths": sum(i["unique_file_paths"] for i in results),
                          "unique_content_hashes": len(hashes), "pdf_file_records": sum(i["pdfs"] for i in results),
                          "integrity_errors": sum(len(i["integrity_errors"]) for i in results),
                          "unavailable_source_urls": sum(len(i["unavailable"]) for i in results)},
              "note": "Counts include duplicate file records and editions; unique paths/hashes are reported separately. PDF parsing is not semantic extraction validation. Catalog release is not necessarily publication release. This is not release certification, a license grant, malware scanning or application testing."}
    (ROOT / "IBM_COLLECTION_VERIFICATION.json").write_text(json.dumps(report, indent=2) + "\n")
    for item in results:
        print(json.dumps({k: v for k, v in item.items() if k not in ("discovery_warnings", "unavailable", "core_manual_coverage_by_catalog_release")}))
        print(f"Unavailable: {len(item['unavailable'])}; discovery warnings: {len(item.get('discovery_warnings', []))}")
    print(json.dumps(report["summary"]))
    if any(item["integrity_errors"] for item in results):
        raise SystemExit(1)


def repository_collection(name):
    root = ROOT / name
    manifest = json.loads((root / "manifest.json").read_text())
    all_files = [i for r in manifest["repositories"] for i in r.get("files", [])]
    files = [i for i in all_files if i["status"] == "downloaded"]
    with ThreadPoolExecutor(max_workers=8) as pool:
        errors = [e for e in pool.map(verify_file, [(root, i) for i in files]) if e]
    return {"collection": name, "repositories": len(manifest["repositories"]),
            "verified_files": len(files), "pdfs": sum(Path(i["path"]).suffix.lower() == ".pdf" for i in files),
            **file_statistics([(root, i) for i in files]),
            "integrity_errors": errors,
            "repositories_missing_license_files": [r["repository"] for r in manifest["repositories"] if not r.get("license_files")],
            "unavailable": [{"url": i["source_url"], "error": i.get("error")} for i in all_files if i["status"] != "downloaded"]
                           + [{"url": r["source_url"], "error": r.get("error", "Incomplete repository snapshot")}
                              for r in manifest["repositories"] if r["status"] != "downloaded"]}


def web_collection():
    root = ROOT / "enterprise-web-reference"
    manifest = json.loads((root / "manifest.json").read_text())
    files = [i for i in manifest["resources"] if i["status"] == "downloaded"]
    with ThreadPoolExecutor(max_workers=8) as pool:
        errors = [e for e in pool.map(verify_file, [(root, i) for i in files]) if e]
    return {"collection": root.name, "verified_files": len(files),
            **file_statistics([(root, i) for i in files]),
            "pdfs": sum(i["kind"] == "pdf" for i in files), "integrity_errors": errors,
            "placeholders_excluded_from_ingestion": [i["url"] for i in files if i.get("document_status") == "publisher_placeholder"],
            "unavailable": [{"url": i["url"], "error": i.get("error")} for i in manifest["resources"] if i["status"] != "downloaded"]}


if __name__ == "__main__":
    main()
