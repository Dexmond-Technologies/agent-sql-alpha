"""Archive selected documentation linked by IBM's IBM i OSS resource directory.

Downloads documentation and reference examples only. Never runs installers,
package managers, build scripts, or examples from the downloaded projects.
Existing repository checkouts are preserved, not reset or automatically updated.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from download_ibm_cobol import now


ROOT = Path(__file__).resolve().parents[1] / "TRAINING/ibm-i-open-source"
HUB = "https://ibm.github.io/ibmi-oss-resources/"
# None means the complete (small) documentation repository. Sparse clones
# include top-level README, LICENSE and other top-level files automatically.
REPOSITORIES = [
    ("IBM/ibmi-oss-resources", None, "IBM's resource directory and its provenance"),
    ("IBM/ibmi-oss-docs", None, "PASE, RPM/offline mirrors, SSH, TLS, ODBC, languages and operations"),
    ("IBM/ibmi-oss-examples", ["python", "nodejs", "odbc", "java", "nginx", "postgresql"], "Reference integration and deployment examples"),
    ("IBM/python-itoolkit", ["docs", "examples"], "Python program/CL interoperation through XMLSERVICE"),
    ("IBM/nodejs-itoolkit", ["docs", "examples"], "Node.js program/CL interoperation through XMLSERVICE"),
    ("IBM/sqlalchemy-ibmi", ["docs", "examples"], "Python Db2 for i dialect, library lists, naming and transactions"),
    ("IBM/xmlservice", ["docs", "examples"], "IBM i program-call interface and data marshaling"),
    ("IBM/node-odbc", ["docs", "examples"], "ODBC connections, prepared statements, pooling and diagnostics"),
    ("IBM/nodejs-idb-connector", ["docs", "examples"], "Native on-host Db2 connector documentation"),
    ("IBM/nodejs-idb-pconnector", ["docs", "examples"], "Native on-host pooled Db2 connector documentation"),
    ("IBM/ibmichroot", ["config"], "IBM i chroot reference; not a substitute for a security sandbox"),
]
SITES = [
    "https://ibmi-oss-docs.readthedocs.io/en/latest/",
    "https://nodejs-itoolkit.readthedocs.io/en/latest/",
    "https://python-itoolkit.readthedocs.io/en/latest/",
    "https://sqlalchemy-ibmi.readthedocs.io/en/latest/",
    "https://xmlservice.readthedocs.io/en/latest/",
]
SINGLE_PAGES = [
    HUB,
    "https://loopback.io/doc/en/lb4/DB2-for-i-connector.html",
    "https://www.ibm.com/support/pages/ibm-i-tutorials-demos-and-sql-examples-0",
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(destination, *args):
    return subprocess.run(["git", "-C", str(destination), *args], check=True,
                          capture_output=True, text=True, timeout=180).stdout.strip()


def clone_repository(spec):
    name, selection, purpose = spec
    destination = ROOT / "repositories" / name.replace("/", "--")
    url = f"https://github.com/{name}.git"
    result = {"repository": name, "source_url": url, "discovered_from": HUB,
              "purpose": purpose, "selected_directories": selection or "complete repository",
              "status": "pending", "path": destination.relative_to(ROOT).as_posix()}
    try:
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            cmd = ["git", "-c", "core.hooksPath=/dev/null", "clone", "--depth", "1", "--filter=blob:none"]
            if selection:
                cmd.append("--sparse")
            cmd.extend([url, str(destination)])
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=240,
                           env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
            if selection:
                git(destination, "sparse-checkout", "set", *selection)
        if git(destination, "remote", "get-url", "origin") != url:
            raise ValueError("Existing directory has a different origin; left unchanged")
        result["commit"] = git(destination, "rev-parse", "HEAD")
        result["commit_date"] = git(destination, "show", "-s", "--format=%cI", "HEAD")
        result["working_tree_changes"] = git(destination, "status", "--porcelain")
        files = []
        # Hash only checked-out regular tracked files. Do not traverse symlinks.
        for relative in git(destination, "ls-files", "-z").split("\0"):
            if not relative:
                continue
            path = destination / relative
            if path.is_file() and not path.is_symlink():
                data = path.read_bytes()
                files.append({"path": relative, "bytes": len(data), "sha256": sha(data)})
        result.update(status="downloaded", downloaded_at=now(), files=files,
                      license_files=[i["path"] for i in files if any(x in Path(i["path"]).name.lower()
                                      for x in ("license", "copying", "notice"))])
    except Exception as exc:
        result.update(status="failed", error=str(exc))
    return result


def page(url, previous):
    if previous and previous.get("status") == "downloaded":
        path = ROOT / previous["path"]
        if path.is_file() and sha(path.read_bytes()) == previous["sha256"]:
            return previous
    result = {"url": url, "discovered_from": HUB, "status": "pending"}
    try:
        # Explicit TLS verification; bounded GETs and no credentials.
        response = requests.get(url, timeout=(15, 45))
        response.raise_for_status()
        if urlsplit(response.url).scheme != "https":
            raise ValueError("Unexpected non-HTTPS redirect")
        if urlsplit(response.url).hostname != urlsplit(url).hostname:
            raise ValueError("Unexpected cross-host redirect")
        data = response.content
        soup = BeautifulSoup(data, "lxml")
        # Read the Docs publishes some redirects as static meta-refresh pages.
        # Follow only same-host HTTPS targets; do not execute their JavaScript.
        for unused in range(3):
            redirect = soup.find("meta", attrs={"http-equiv": re.compile("^refresh$", re.I)})
            if not redirect:
                break
            match = re.search(r"url\s*=\s*(.+)$", redirect.get("content", ""), re.I)
            if not match:
                raise ValueError("Malformed documentation redirect")
            target = urljoin(response.url, match[1].strip().strip("\"'"))
            if urlsplit(target).scheme != "https" or urlsplit(target).hostname != urlsplit(url).hostname:
                raise ValueError("Unexpected documentation redirect destination")
            result.setdefault("meta_redirects", []).append(target)
            response = requests.get(target, timeout=(15, 45))
            response.raise_for_status()
            if urlsplit(response.url).scheme != "https" or urlsplit(response.url).hostname != urlsplit(url).hostname:
                raise ValueError("Unexpected documentation redirect response")
            data = response.content
            soup = BeautifulSoup(data, "lxml")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        section = soup.select_one("[role=main]") or soup.select_one("main") or soup.select_one("article") or soup.body
        if not section or len(section.get_text(" ", strip=True)) < 40 or not title:
            raise ValueError("No substantive document body")
        if any(term in title.lower() for term in ("access denied", "not found", "just a moment")):
            raise ValueError(f"Error page: {title}")
        host = urlsplit(url).hostname
        relative = Path("pages") / host / f"{sha(url.encode())[:12]}.html"
        destination = ROOT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and sha(destination.read_bytes()) != sha(data):
            destination = destination.with_name(destination.stem + "--" + sha(data)[:10] + ".html")
        if not destination.exists():
            destination.write_bytes(data)
        links = sorted({urljoin(response.url, a["href"]).split("#")[0] for a in soup.select("a[href]")})
        result.update(status="downloaded", title=title, effective_url=response.url,
                      path=destination.relative_to(ROOT).as_posix(), bytes=len(data), sha256=sha(data),
                      downloaded_at=now(), links=links)
    except Exception as exc:
        result.update(status="failed", error=str(exc))
    return result


def save(repositories, pages):
    manifest = {"schema_version": 1, "updated_at": now(), "platform": "IBM i", "resource_directory": HUB,
                "scope": "Selected first-party project documentation and reference examples. No software installed or executed.",
                "rights": "Repository LICENSE/NOTICE files retained. No blanket fine-tuning or redistribution permission inferred.",
                "omitted": "Social channels, customer stories, marketing, newsletters, videos, and broad third-party blog collections.",
                "repositories": repositories, "pages": list(pages.values())}
    temporary = ROOT / "manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(ROOT / "manifest.json")


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    repositories, pages = [], {}
    if (ROOT / "manifest.json").exists():
        previous = json.loads((ROOT / "manifest.json").read_text())
        pages = {p["url"]: p for p in previous.get("pages", [])}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(clone_repository, spec) for spec in REPOSITORIES]
        for future in as_completed(futures):
            result = future.result()
            repositories.append(result)
            print(f"{result['status']}: {result['repository']} ({len(result.get('files', []))} files)", flush=True)
            save(repositories, pages)
    pending, seen = set(SINGLE_PAGES + SITES), set()
    while pending:
        if len(seen) > 300:
            raise RuntimeError("Documentation crawl limit reached; review discovery scope")
        batch = sorted(pending - seen)
        if not batch:
            break
        pending = set()
        seen.update(batch)
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(page, url, pages.get(url)) for url in batch]
            for future in as_completed(futures):
                result = future.result()
                pages[result["url"]] = result
                print(f"{result['status']}: {result['url']}", flush=True)
                if result["status"] == "downloaded":
                    for link in result.get("links", []):
                        # Follow documentation pages only inside these five
                        # explicitly selected project/version prefixes.
                        if (any(link.startswith(site) for site in SITES) and
                            (link.endswith(".html") or link in SITES) and
                            "?" not in link and "/_" not in link and
                            not link.endswith(("search.html", "genindex.html", "py-modindex.html"))):
                            pending.add(link)
                save(repositories, pages)
    print(json.dumps({"repositories": len(repositories), "files": sum(len(r.get("files", [])) for r in repositories),
                      "pages": len(pages), "failures": sum(r["status"] == "failed" for r in repositories + list(pages.values()))}, indent=2), flush=True)


if __name__ == "__main__":
    main()
