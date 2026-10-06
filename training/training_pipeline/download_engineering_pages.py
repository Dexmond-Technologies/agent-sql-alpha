"""Snapshot selected primary engineering standards and product documentation.

This is a bounded list, not a general web crawler. No ingestion or installation.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from download_ibm_cobol import now


ROOT = Path(__file__).resolve().parents[1] / "TRAINING/enterprise-web-reference"
SOURCES = [
    ("https://www.unixodbc.org/doc/UserManual/", "unixODBC user manual", "Connectivity"),
    ("https://www.unixodbc.org/doc/AdministratorManual/", "unixODBC administrator manual", "Connectivity"),
    ("https://www.unixodbc.org/doc/ProgrammerManual/", "unixODBC programmer manual", "Connectivity"),
    ("https://docs.rs/odbc-api/latest/odbc_api/guide/", "Rust ODBC API guide", "Connectivity"),
    ("https://sqlite.org/fts5.html", "SQLite FTS5", "Retrieval"),
    ("https://sqlite.org/copyright.html", "SQLite copyright and public domain statement", "Rights"),
    ("https://www.postgresql.org/docs/current/textsearch.html", "PostgreSQL full text search overview", "Retrieval"),
    ("https://www.postgresql.org/docs/current/textsearch-controls.html", "PostgreSQL text search ranking and controls", "Retrieval"),
    ("https://www.postgresql.org/docs/current/ddl-rowsecurity.html", "PostgreSQL row security policies", "Authorization"),
    ("https://www.postgresql.org/docs/current/ddl-priv.html", "PostgreSQL privileges", "Authorization"),
    ("https://www.unicode.org/reports/tr15/", "Unicode normalization forms", "Text fidelity"),
    ("https://docs.semgrep.dev/supported-languages", "Semgrep supported languages", "Security scanning"),
    ("https://docs.semgrep.dev/semgrep-ce-languages", "Semgrep CE supported languages", "Security scanning"),
    ("https://docs.semgrep.dev/deployment/oss-deployment", "Semgrep CE in CI", "Security scanning"),
    ("https://docs.semgrep.dev/cli-reference", "Semgrep CLI reference", "Security scanning"),
    ("https://docs.semgrep.dev/metrics", "Semgrep metrics and telemetry", "On premises"),
    ("https://docs.ollama.com/faq", "Ollama local deployment and cloud disable controls", "On premises"),
    ("https://docling-project.github.io/docling/usage/advanced_options/", "Docling offline models and remote service controls", "Ingestion"),
    ("https://docs.vllm.ai/en/latest/usage/usage_stats/", "vLLM usage statistics and opt out", "On premises"),
    ("https://docs.vllm.ai/en/latest/usage/security/", "vLLM security guidance", "On premises"),
    ("https://openid.net/specs/openid-connect-core-1_0.html", "OpenID Connect Core 1.0", "Authorization"),
    ("https://www.rfc-editor.org/rfc/rfc9700.html", "OAuth 2.0 security best current practice RFC 9700", "Authorization"),
    ("https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf", "NIST AI Risk Management Framework", "Governance"),
    ("https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf", "NIST Generative AI Profile", "Governance"),
    ("https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-218.pdf", "NIST Secure Software Development Framework", "Governance"),
    ("https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-218A.pdf", "NIST Secure Software Development Practices for Generative AI", "Governance"),
    ("https://opentelemetry.io/docs/security/", "OpenTelemetry security", "Internal analytics"),
    ("https://opentelemetry.io/docs/security/handling-sensitive-data/", "OpenTelemetry sensitive data handling", "Internal analytics"),
    ("https://opentelemetry.io/docs/collector/configuration/", "OpenTelemetry Collector configuration", "Internal analytics"),
    ("https://slsa.dev/spec/v1.2/", "SLSA 1.2 specification overview", "Supply chain"),
    ("https://slsa.dev/spec/v1.2/build-requirements", "SLSA 1.2 build requirements", "Supply chain"),
    ("https://slsa.dev/spec/v1.2/provenance", "SLSA 1.2 provenance", "Supply chain"),
    ("https://spdx.dev/wp-content/uploads/sites/31/2024/12/SPDX-3.0.1-1.pdf", "SPDX 3.0.1 specification", "Supply chain"),
    ("https://spdx.github.io/spdx-spec/v3.0.1/scope/", "SPDX 3.0.1 scope", "Supply chain"),
]
ALLOWED_HOSTS = {urlsplit(u).hostname for u, unused, category in SOURCES} | {"www.sqlite.org", "rfc-editor.org"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fetch(source, previous):
    url, title, category = source
    if previous and previous.get("status") == "downloaded":
        path = ROOT / previous["path"]
        if path.is_file() and sha(path.read_bytes()) == previous["sha256"]:
            return previous
    result = {"url": url, "title": title, "category": category, "status": "pending",
              "authority": "standard publisher or project maintainer", "ingestion_status": "pending_rights_and_scope_review"}
    try:
        with tempfile.TemporaryDirectory(prefix="engineering-reference-") as temp:
            target = Path(temp) / "payload"
            command = ["curl", "-fsSL", "--proto", "=https", "--proto-redir", "=https", "--connect-timeout", "15",
                       "--max-time", "90", "--retry", "1", "--max-filesize", "50000000",
                       "--output", str(target), "--write-out", "%{json}", url]
            proc = subprocess.run(command, capture_output=True, text=True, timeout=200)
            metadata = json.loads(proc.stdout or "{}")
            if proc.returncode:
                raise ValueError(proc.stderr[-400:])
            effective = metadata.get("url_effective", url)
            if urlsplit(effective).hostname not in ALLOWED_HOSTS:
                raise ValueError("Unexpected redirect host")
            data = target.read_bytes()
            pdf = data.startswith(b"%PDF-")
            if url.endswith(".pdf") and not pdf:
                raise ValueError("Expected PDF but received another content type")
            if not pdf:
                soup = BeautifulSoup(data, "lxml")
                heading = soup.title.get_text(" ", strip=True) if soup.title else ""
                if re.search(r"access denied|page not found|404|just a moment", heading, re.I):
                    raise ValueError(f"Error page: {heading}")
                body = soup.select_one("article") or soup.select_one("main") or soup.body or soup
                body_text = body.get_text(" ", strip=True)
                if "This manual has not been complete yet." in body_text and url.startswith("https://www.unixodbc.org/"):
                    result.update(document_status="publisher_placeholder", ingestion_status="exclude_publisher_placeholder",
                                  warning="Publisher has not supplied this manual; snapshot is evidence of the gap, not documentation")
                elif len(body_text) < 100:
                    raise ValueError("No substantive document body")
                result["html_title"] = heading
            relative = Path("documents" if pdf else "pages") / (re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-") + "--" + sha(url.encode())[:10] + (".pdf" if pdf else ".html"))
            destination = ROOT / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and sha(destination.read_bytes()) != sha(data):
                raise ValueError("Existing snapshot differs; preserved")
            if not destination.exists():
                destination.write_bytes(data)
            result.update(status="downloaded", path=relative.as_posix(), kind="pdf" if pdf else "html", effective_url=effective,
                          sha256=sha(data), bytes=len(data), downloaded_at=now())
    except Exception as exc:
        result.update(status="failed", error=str(exc))
    return result


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    old = json.loads((ROOT / "manifest.json").read_text()) if (ROOT / "manifest.json").exists() else {}
    previous = {i["url"]: i for i in old.get("resources", [])}
    manifest = {"schema_version": 1, "updated_at": now(), "scope": "Selected primary engineering documentation; not IBM i dialect authority",
                "rights": "Publisher notices retained; rights and redistribution must be reviewed before ingestion or delivery", "resources": []}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(fetch, source, previous.get(source[0])) for source in SOURCES]
        for future in as_completed(futures):
            item = future.result()
            manifest["resources"].append(item)
            print(item["status"], item["title"], item.get("error", ""), flush=True)
            staging = ROOT / "manifest.json.tmp"
            staging.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            staging.replace(ROOT / "manifest.json")
    with (ROOT / "INDEX.tsv").open("w", newline="") as output:
        writer = csv.writer(output, delimiter="\t")
        writer.writerow(["category", "title", "path", "status", "source_url"])
        for i in manifest["resources"]:
            writer.writerow([i["category"], i["title"], i.get("path", ""), i["status"], i["url"]])


if __name__ == "__main__":
    main()
