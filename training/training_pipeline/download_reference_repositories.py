"""Download selected documentation at pinned GitHub commits, without checkout.

No packages, models, binaries, build scripts, hooks or agent skills are installed
or executed. Source files are included only as explicitly selected examples.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from download_ibm_cobol import now


BASE = Path(__file__).resolve().parents[1] / "TRAINING"
TOPIC = "https://github.com/topics/ibm-i?o=asc&s=forks"
COMMUNITY = [
    ("Strom-Capital/mcp-server-db2i", ["docs", "examples"], "SQL gateway, identity, masking, audit and deployment reference"),
    ("Sittlon/mcp-server-db2i", ["docs", "examples"], "Alternative local-model Db2 MCP integration reference"),
    ("SH4RKKK/ibm-i-source-mcp", ["docs", "examples"], "Source-member operations over SSH; privileged tools are reference only"),
    ("SH4RKKK/ibm-i-5250-mcp", ["docs", "examples"], "Interactive 5250 testing reference; not installed or connected"),
    ("h0w4r/MCP-IBMiDocs", ["docs"], "Local documentation retrieval design; excludes bundled corpus, models and skills"),
    ("eduardopessin/cobol4i", ["docs", "examples", "tools/equivalence"], "ILE COBOL dialect and equivalence-test documentation"),
    ("naveenneog/Plumbline", ["docs", "legacy", "tests"], "Requirements traceability and conformance-test reference; excludes legacy source downloader"),
    ("javierh77/ibmi-sql-toolkit", ["network", "performance", "upgrade"], "IBM i SQL service examples; statements require review before execution"),
    ("PowerTrueSYS/ptxray-public", ["docs", "examples"], "Local audit and security-assessment documentation; no scans executed"),
    ("PounceAI/bob-control", ["docs", "examples"], "Agent task-board and orchestration design; not approved for unattended execution"),
    ("ElVatoEste/Bindle", ["docs", "examples"], "ILE dependencies and builds; GPL-licensed reference kept distinct"),
    ("IBM/ibmi-tobi", ["docs", "tests/fixtures", "tests/test_project", ".github/workflows"], "Official native object builds; formerly ibmi-bob, distinct from IBM Bob AI"),
    ("codefori/vscode-ibmi", ["schemas", "types", ".github/workflows"], "Maintainer reference for source-member editing and development workflows"),
    ("codefori/docs", ["pages", "docs", "content", "src/content"], "Code for IBM i user and extension API documentation"),
]
ENGINEERING = [
    ("IBM/JTOpen", ["doc", "docs", "javadoc"], "IBM Toolbox JDBC and native-object access reference"),
    ("pacman82/odbc-api", ["odbc-api/src/guide.rs", "odbc-api/examples"], "Rust ODBC integration reference; IBM i compatibility must be tested"),
    ("rpgleparser/rpgleparser", ["src/main/antlr4", "src/test/resources"], "Fixed/free-format RPG grammar and public parser fixtures"),
    ("codefori/vscode-rpgle", ["docs", "syntaxes", "schemas"], "RPG editing, language tooling and syntax reference"),
    ("tools-400/irpgunit", ["docs/files", "docs/help", "host/samples", "host/examples", "host/iRPGUnit/QLLIST/LGPL.3.0.TXT", "host/iRPGUnit/QINCLUDE/COPYRIGHT.RPGLE"], "Native IBM i unit testing, prerequisites and examples"),
    ("docling-project/docling", ["docs"], "Local PDF/table extraction, offline artifacts and provenance"),
    ("py-pdf/pypdf", ["docs"], "PDF extraction limits, text coordinates and encryption handling"),
    ("vllm-project/vllm", ["docs/deployment", "docs/serving", "docs/usage", "docs/getting_started", "docs/configuration"], "Local inference, security, telemetry, serving and structured output"),
    ("ollama/ollama", ["docs"], "Local inference API, cloud-disable controls and model deployment"),
    ("ggml-org/llama.cpp", ["docs", "tools/server/README.md"], "Local model-server and constrained-generation reference"),
    ("UKPLab/sentence-transformers", ["docs/sentence_transformer", "docs/cross_encoder"], "Embeddings, reranking and retrieval evaluation"),
    ("pgvector/pgvector", ["docs"], "Vector indexes and hybrid retrieval on PostgreSQL"),
    ("modelcontextprotocol/modelcontextprotocol", ["docs", "specification"], "Tool protocol, transport, authentication and security references"),
    ("OWASP/CheatSheetSeries", ["cheatsheets/RAG_Security_Cheat_Sheet.md", "cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.md", "cheatsheets/MCP_Security_Cheat_Sheet.md", "cheatsheets/Secure_Coding_with_AI_Cheat_Sheet.md", "cheatsheets/Secure_AI_Model_Ops_Cheat_Sheet.md", "cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.md", "cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.md", "cheatsheets/Authorization_Cheat_Sheet.md", "cheatsheets/Secrets_Management_Cheat_Sheet.md", "cheatsheets/Logging_Cheat_Sheet.md", "cheatsheets/File_Upload_Cheat_Sheet.md", "cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.md", "cheatsheets/Docker_Security_Cheat_Sheet.md"], "RAG, tool, ingestion, SQL, authorization and supply-chain security"),
]
USE_GIT = False
DOC_SUFFIXES = {".md", ".mdx", ".rst", ".adoc", ".txt", ".html", ".htm", ".pdf"}
EXAMPLE_SUFFIXES = {".sql", ".rpgle", ".rpg", ".clle", ".cl", ".dds", ".cbl", ".cob", ".cpy",
                    ".json", ".yaml", ".yml", ".toml", ".xml", ".g4", ".ts", ".py", ".java", ".cs", ".rs"}
BLOCKED_PARTS = {"node_modules", ".git", ".agents", ".claude", ".codex", "skills", "vendor", "models", "dist", "build"}


def session():
    client = requests.Session()
    retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
    client.mount("https://", HTTPAdapter(max_retries=retry))
    return client


def get_json(url):
    with session() as client:
        response = client.get(url, timeout=(15, 45))
        response.raise_for_status()
        return response.json()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git_tree(root, name, previous):
    """Read public Git metadata without using the quota-limited REST API.

    Partial bare clones hold commit/tree objects, not model files or binaries.
    No checkout, hooks, submodule initialization or build steps are performed.
    """
    cache = root / "git-cache" / (name.replace("/", "--") + ".git")
    url = f"https://github.com/{name}.git"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "clone", "--bare", "--filter=blob:none", "--depth", "1", url, str(cache)],
                       check=True, capture_output=True, timeout=180, env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    def command(*args):
        return subprocess.check_output(["git", "--git-dir", str(cache), *args], timeout=90).decode()
    if command("remote", "get-url", "origin").strip() != url:
        raise ValueError("Existing cache origin differs; left unchanged")
    commit = (previous or {}).get("commit") or command("rev-parse", "HEAD").strip()
    found = subprocess.run(["git", "--git-dir", str(cache), "cat-file", "-e", commit + "^{tree}"], capture_output=True)
    if found.returncode:
        command("fetch", "--depth", "1", "origin", commit)
    tree = []
    # Do not use ls-tree -l: obtaining blob sizes would defeat partial cloning.
    for record in command("ls-tree", "-r", "-z", commit).split("\0"):
        if not record:
            continue
        header, path = record.split("\t", 1)
        mode, kind, blob = header.split()
        tree.append({"path": path, "mode": mode, "type": kind, "sha": blob})
    return ({"full_name": name, "default_branch": command("symbolic-ref", "--short", "HEAD").strip(),
             "html_url": f"https://github.com/{name}", "license": {"spdx_id": (previous or {}).get("github_license", "review-retained-license")}},
            commit, {"tree": tree, "sha": command("rev-parse", commit + "^{tree}").strip(), "truncated": False})


def selected(path, prefixes):
    name = PurePosixPath(path)
    if name.is_absolute() or ".." in name.parts or set(name.parts) & BLOCKED_PARTS:
        return False
    if path.startswith("docs/examples/data/"):
        return False
    if name.name.lower() in {"agents.md", "claude.md", "skill.md", ".cursorrules"}:
        return False
    if re.match(r"^(license|copying|notice|copyright|lgpl|gpl|epl)([._-]|$)", name.name, re.I):
        return True
    in_scope = len(name.parts) == 1 or any(path == p or path.startswith(p + "/") for p in prefixes)
    if not in_scope:
        return False
    if name.suffix.lower() in DOC_SUFFIXES or name.name.lower() in {"readme", "changelog", "authors"}:
        return True
    return name.suffix.lower() in EXAMPLE_SUFFIXES and len(name.parts) > 1


def fetch_file(root, repository, commit, entry, previous):
    path = entry["path"]
    local = Path("repositories") / repository.replace("/", "--") / path
    destination = root / local
    result = {"repository_path": path, "path": local.as_posix(), "git_blob_sha": entry["sha"],
              "source_url": f"https://raw.githubusercontent.com/{repository}/{commit}/{quote(path, safe='/')}",
              "status": "pending"}
    if previous and previous.get("status") == "downloaded" and destination.is_file():
        if digest(destination.read_bytes()) == previous["sha256"]:
            return previous
    try:
        with session() as client:
            response = client.get(result["source_url"], timeout=(15, 45))
            response.raise_for_status()
            data = response.content
        if len(data) > 2_000_000:
            raise ValueError("Selected reference exceeds 2 MB limit")
        if entry.get("size") is not None and len(data) != entry["size"]:
            raise ValueError("Downloaded size differs from Git tree")
        blob_hash = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        if blob_hash != entry["sha"]:
            raise ValueError("Downloaded contents differ from pinned Git blob")
        if b"\x00" in data and not (path.lower().endswith(".pdf") and data.startswith(b"%PDF-")):
            raise ValueError("Unexpected binary data in selected reference file")
        if destination.exists() and digest(destination.read_bytes()) != digest(data):
            raise ValueError("Existing local file differs; preserved without overwriting")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            destination.write_bytes(data)
        result.update(status="downloaded", sha256=digest(data), bytes=len(data), downloaded_at=now())
    except Exception as exc:
        result.update(status="failed", error=str(exc))
    return result


def repository_snapshot(root, spec, previous):
    requested, prefixes, purpose = spec
    if previous and previous.get("status") == "downloaded" and previous.get("selected_prefixes") == prefixes:
        if all((root / f["path"]).is_file() and digest((root / f["path"]).read_bytes()) == f["sha256"] for f in previous["files"]):
            return previous
    result = {"repository": requested, "purpose": purpose, "selected_prefixes": prefixes,
              "status": "pending", "authority": "IBM maintainer" if requested.startswith("IBM/") else "community maintainer",
              "ingestion_status": "reference_only_pending_review"}
    try:
        if USE_GIT:
            metadata, commit, tree = git_tree(root, requested, previous)
        else:
            metadata = get_json(f"https://api.github.com/repos/{requested}")
        name = metadata["full_name"]
        branch = metadata["default_branch"]
        commit = commit if USE_GIT else previous.get("commit") if previous else None
        if not commit:
            command = ["git", "ls-remote", "--heads", f"https://github.com/{name}.git", f"refs/heads/{branch}"]
            output = subprocess.check_output(command, text=True, timeout=45).strip()
            commit = output.split()[0]
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("Invalid pinned commit")
        if not USE_GIT:
            tree = get_json(f"https://api.github.com/repos/{name}/git/trees/{commit}?recursive=1")
        if tree.get("truncated"):
            raise ValueError("GitHub tree is truncated; refusing to claim a complete selected snapshot")
        files = [e for e in tree["tree"] if e["type"] == "blob" and e.get("mode") in ("100644", "100755")
                 and e.get("size", 0) <= 2_000_000 and selected(e["path"], prefixes)]
        result.update(repository=name, source_url=metadata["html_url"], requested_repository=requested,
                      default_branch=branch, commit=commit, tree_sha=tree["sha"],
                      github_license=(metadata.get("license") or {}).get("spdx_id", "unidentified"),
                      publisher_claims_unverified=True, files=[])
        old = {e["repository_path"]: e for e in (previous or {}).get("files", [])}
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(fetch_file, root, name, commit, entry, old.get(entry["path"])) for entry in files]
            for future in as_completed(futures):
                result["files"].append(future.result())
        result["files"].sort(key=lambda f: f["path"])
        result["license_files"] = [f["path"] for f in result["files"] if
                                   re.match(r"^(license|copying|notice|copyright|lgpl|gpl|epl)([._-]|$)", PurePosixPath(f["path"]).name, re.I)]
        result["status"] = "downloaded" if result["files"] and all(f["status"] == "downloaded" for f in result["files"]) else "incomplete"
        if not result["license_files"]:
            result["rights_warning"] = "No license file selected; do not ingest until rights are resolved"
    except Exception as exc:
        result.update(status="failed", error=str(exc))
    return result


def scan_topic(root, selected_repositories):
    discovered, snapshots = {}, []
    for page_number in (1, 2, 3):
        url = TOPIC + f"&page={page_number}"
        with session() as client:
            response = client.get(url, timeout=(15, 45))
            response.raise_for_status()
        destination = root / "sources" / f"github-ibm-i-topic-page-{page_number}.html"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            destination.write_bytes(response.content)
        data = destination.read_bytes()
        snapshots.append({"url": url, "path": destination.relative_to(root).as_posix(), "sha256": digest(data), "bytes": len(data)})
        soup = BeautifulSoup(data, "lxml")
        for article in soup.select("article"):
            heading = article.select_one("h3")
            if not heading:
                continue
            names = [a["href"].strip("/") for a in heading.select("a[href]") if len(a["href"].strip("/").split("/")) == 2]
            if not names:
                continue
            name = names[-1]
            description = " ".join(p.get_text(" ", strip=True) for p in article.select("p"))
            selected_repo = name in selected_repositories
            discovered[name] = {"repository": name, "url": "https://github.com/" + name,
                                "publisher_description": description, "source_page": url,
                                "selected": selected_repo,
                                "selection_reason": "Fills a documented engineering gap; reference only" if selected_repo else
                                "Not selected: overlap, peripheral topic, unresolved licensing, or outside the on-premises assistant scope"}
    return snapshots, list(discovered.values())


def main():
    global USE_GIT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", choices=["community", "engineering"], required=True)
    parser.add_argument("--via-git", action="store_true", help="Use read-only Git metadata instead of GitHub REST API")
    args = parser.parse_args()
    USE_GIT = args.via_git
    specs = COMMUNITY if args.collection == "community" else ENGINEERING
    name = "ibm-i-community" if args.collection == "community" else "enterprise-engineering-reference"
    root = BASE / name
    root.mkdir(parents=True, exist_ok=True)
    previous = json.loads((root / "manifest.json").read_text()) if (root / "manifest.json").exists() else {}
    old = {r.get("requested_repository", r["repository"]): r for r in previous.get("repositories", [])}
    snapshots, discovered = scan_topic(root, {s[0] for s in specs}) if args.collection == "community" else ([], [])
    manifest = {"schema_version": 1, "updated_at": now(), "collection": name,
                "scope": "Pinned documentation, schemas and selected reference examples; no ingestion or execution",
                "rights": "Preserve licenses; selection is not authorization to fine-tune, redistribute, or vendor into the product",
                "topic_snapshots": snapshots, "topic_repositories": discovered, "repositories": []}
    def save():
        staging = root / "manifest.json.tmp"
        staging.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        staging.replace(root / "manifest.json")
    save()
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(repository_snapshot, root, spec, old.get(spec[0])) for spec in specs]
        for future in as_completed(futures):
            result = future.result()
            manifest["repositories"].append(result)
            print(f"{result['status']}: {result['repository']} ({len(result.get('files', []))} files) {result.get('error', '')}", flush=True)
            save()
    with (root / "INDEX.tsv").open("w", newline="") as output:
        writer = csv.writer(output, delimiter="\t")
        writer.writerow(["repository", "purpose", "license_label", "commit", "file", "status", "source_url"])
        for repository in manifest["repositories"]:
            for item in repository.get("files", []):
                writer.writerow([repository["repository"], repository["purpose"], repository.get("github_license"),
                                 repository.get("commit"), item["path"], item["status"], item["source_url"]])
    print(json.dumps({"topic_repositories_scanned": len(discovered), "selected_repositories": len(specs),
                      "downloaded_files": sum(f["status"] == "downloaded" for r in manifest["repositories"] for f in r.get("files", [])),
                      "incomplete_repositories": sum(r["status"] != "downloaded" for r in manifest["repositories"])}, indent=2), flush=True)


if __name__ == "__main__":
    main()
