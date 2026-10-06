"""Download documents linked by IBM's Enterprise COBOL for z/OS library.

Requires BeautifulSoup and lxml for parsing, and curl for verified HTTPS.
Run from agent-sql-alpha: python3 training/training_pipeline/download_ibm_cobol.py
The manifest records original URLs, release/language context, hashes and failures.
"""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import parse_qs, quote, urlencode, urldefrag, urljoin, urlsplit, urlunsplit
import zipfile

from bs4 import BeautifulSoup


LIBRARY_URL = "https://www.ibm.com/support/pages/enterprise-cobol-zos-documentation-library"
DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "TRAINING/ibm-enterprise-cobol-zos"
DOC_EXTENSIONS = {".pdf", ".zip", ".boo", ".bks", ".bki", ".xks", ".doc", ".docx", ".txt"}


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def slug(text):
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", text).strip("-.")[:95] or "document"


def canonical(url):
    url = urldefrag(url.strip())[0]
    parts = urlsplit(url)
    if parts.scheme not in ("https", "http"):
        raise ValueError(f"Unsupported URL scheme: {url}")
    if not parts.hostname or not (parts.hostname == "ibm.com" or parts.hostname.endswith(".ibm.com")):
        raise ValueError(f"Unexpected non-IBM document host: {url}")
    # All library downloads use HTTPS, including links written as HTTP on IBM's page.
    return urlunsplit(("https", parts.netloc,
                       quote(parts.path, safe="/%:@&=+$,;()~!*'-._"),
                       quote(parts.query, safe="/%?:@&=+$,;()~!*'-._"), ""))


def inventory(html):
    soup = BeautifulSoup(html, "lxml")
    resources = {}
    for section in soup.select(".ibm-tabs-content"):
        section_id = section.get("id", "")
        if not re.fullmatch(r"\d{2}", section_id):
            continue
        version = ".".join(section_id)
        for anchor in section.select("a[href]"):
            if anchor["href"].startswith("#"):
                continue
            url = canonical(urljoin(LIBRARY_URL, anchor["href"]))
            context = "\n".join(parent.get_text(" ", strip=True)[:200]
                                for parent in anchor.parents if parent.name in ("td", "tr"))
            language = "ja" if "PDF format - Japanese" in context else "en"
            row = anchor.find_parent("tr")
            cells = row.find_all(["td", "th"], recursive=False) if row else []
            title = cells[0].get_text(" ", strip=True) if cells else anchor.get_text(" ", strip=True)
            publication = cells[1].get_text(" ", strip=True) if len(cells) >= 3 else None
            if "Download all PDF" in title or title.startswith("PDF format"):
                title = "Complete PDF bundle"
            ref = {"version": version, "language": language, "title": title[:500],
                   "publication": publication, "source_url": anchor["href"], "source_page": LIBRARY_URL}
            item = resources.setdefault(url, {"url": url, "references": [], "status": "pending"})
            if ref not in item["references"]:
                item["references"].append(ref)
    if len(resources) < 200:
        raise ValueError(f"Incomplete library parsing: only {len(resources)} resources")
    return list(resources.values())


def expected_type(url):
    suffix = Path(urlsplit(url).path).suffix.lower()
    return suffix.lstrip(".") if suffix in DOC_EXTENSIONS else None


def file_type(data, mime):
    if data[:1024].lstrip().startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        return "zip"
    prefix = data[:2048].lstrip().lower()
    if "text/html" in mime or prefix.startswith((b"<!doctype html", b"<html")):
        return "html"
    return "binary"


def download(item, root):
    result = dict(item)
    if item.get("status") == "downloaded" and item.get("path"):
        existing = root / item["path"]
        if existing.is_file() and digest(existing.read_bytes()) == item.get("sha256"):
            return result
    url = canonical(item["url"])
    kind = expected_type(url)
    # A few IBM i availability manuals exceed 50 MB and the publisher throttles
    # their transfers. Give those a single longer attempt, not repeated resets.
    large_manual = Path(urlsplit(url).path).name in {"db2mipdf.pdf", "migpdf.pdf", "migmmpdf.pdf"}
    max_time, retries = (900, 0) if large_manual else (75, 2)
    with tempfile.TemporaryDirectory(prefix="ibm-cobol-download-") as temp:
        target = Path(temp) / "payload"
        cmd = ["curl", "--silent", "--show-error", "--fail", "--location", "--max-redirs", "8",
               "--proto", "=https", "--proto-redir", "=https", "--connect-timeout", "15",
               "--max-time", str(max_time), "--retry", str(retries), "--retry-delay", "1", "--max-filesize", "268435456",
               "--output", str(target), "--write-out", "%{json}", url]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=max_time * (retries + 1) + 20)
            metadata = json.loads(proc.stdout or "{}")
            result["http_status"] = metadata.get("http_code")
            result["effective_url"] = metadata.get("url_effective", url)
            if proc.returncode:
                raise RuntimeError(proc.stderr.strip()[-1200:] or f"curl exit {proc.returncode}")
            # Do not accept an unexpected external redirect as a library document.
            canonical(result["effective_url"])
            data = target.read_bytes()
            detected = file_type(data, metadata.get("content_type") or "")
            if not data:
                raise ValueError("Empty response")
            if kind in ("pdf", "zip") and detected != kind:
                raise ValueError(f"Expected {kind}, received {detected}")
            if kind and kind not in ("pdf", "zip") and detected == "html":
                raise ValueError(f"Expected {kind}, received HTML")
            if detected == "zip":
                with zipfile.ZipFile(target) as archive:
                    bad = archive.testzip()
                    if bad:
                        raise ValueError(f"ZIP CRC failure: {bad}")
            if detected == "html":
                page = BeautifulSoup(data, "lxml")
                title = page.title.get_text(" ", strip=True) if page.title else ""
                if re.search(r"access denied|403 forbidden|404 not found|page not found", title, re.I):
                    raise ValueError(f"Error page: {title}")
                result["html_title"] = title
                result["snapshot_only"] = not bool(page.select("article"))
            ref = item["references"][0]
            extension = detected if detected in ("pdf", "zip", "html") else (kind or "bin")
            basename = Path(urlsplit(url).path).stem
            if detected == "html":
                basename = slug(ref["title"])
            name = f"{slug(basename)}--{digest(url.encode())[:10]}.{extension}"
            category = "archives" if detected == "zip" else "pages" if detected == "html" else "documents"
            relative = Path(category) / ref["version"] / ref["language"] / name
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and digest(destination.read_bytes()) != digest(data):
                # Preserve previous snapshots instead of silently replacing them.
                destination = destination.with_name(destination.stem + "--" + digest(data)[:10] + destination.suffix)
            if not destination.exists():
                destination.write_bytes(data)
            result.update(status="downloaded", path=destination.relative_to(root).as_posix(),
                          kind=extension, bytes=len(data), sha256=digest(data), downloaded_at=now(),
                          content_type=metadata.get("content_type"))
            result.pop("error", None)
        except (Exception, subprocess.TimeoutExpired) as exc:
            result.update(status="failed", error=str(exc), attempted_at=now())
            # Some legacy IBM links redirect to HTTP archive URLs. Never make
            # the insecure request: explicitly retry the IBM target over HTTPS.
            redirect = result.get("effective_url", "")
            if redirect.startswith("http://"):
                try:
                    secure = canonical(redirect)
                except ValueError:
                    secure = None
                if secure and secure != url:
                    recovered = download(dict(item, url=secure, status="pending"), root)
                    if recovered["status"] == "downloaded":
                        recovered.update(url=url, mirror_source_url=secure,
                                         original_attempt={"url": url, "insecure_redirect_not_followed": redirect})
                        return recovered
            # IBM's library still points some BookManager files at the retired
            # publib host. The same publicly listed paths exist on publibfp.
            if result.get("http_status") == 404 and urlsplit(url).hostname == "publib.dhe.ibm.com":
                mirror = url.replace("https://publib.dhe.ibm.com/", "https://publibfp.dhe.ibm.com/", 1)
                recovered = download(dict(item, url=mirror, status="pending"), root)
                if recovered["status"] == "downloaded":
                    recovered.update(url=url, mirror_source_url=mirror,
                                     original_attempt={"url": url, "http_status": 404})
                    return recovered
    return result


def article_bodies(resources):
    """IBM Docs renders announcement bodies from this public content endpoint.

    The routes are the same ones used by IBM's public index_bundle.js client;
    download the body as well as the otherwise empty application HTML shell.
    """
    known = {item["url"] for item in resources}
    found = []
    for item in resources:
        if item.get("status") != "downloaded" or item.get("kind") != "html":
            continue
        if item.get("resource_role") == "article_body":
            continue
        parts = urlsplit(item["effective_url"])
        path = parts.path
        announcement = parse_qs(parts.query).get("announcement", [None])[0]
        if "/announcements/archive/" in path:
            announcement = path.rsplit("/", 1)[-1]
            content = "announcement_archive"
        elif "/announcements/" in path:
            announcement = path.rsplit("/", 1)[-1]
            content = announcement
        elif announcement and announcement != "all":
            content = announcement
        else:
            continue
        query = urlencode({"announcement": announcement, "parsebody": "true", "lang": "en"})
        url = f"https://www.ibm.com/docs/api/v1/content/{content}?{query}"
        if url in known:
            continue
        known.add(url)
        found.append({"url": url, "references": item["references"], "status": "pending",
                      "discovered_from": item["url"], "resource_role": "article_body"})
    return found


def attachments(resources, root):
    """Follow document attachments on linked article pages, not whole portals."""
    known = {item["url"] for item in resources}
    found = []
    for item in resources:
        if item.get("status") != "downloaded" or item.get("kind") != "html":
            continue
        if not any(part in urlsplit(item["effective_url"]).path for part in ("/support/", "/docs/")):
            continue
        soup = BeautifulSoup((root / item["path"]).read_bytes(), "lxml")
        for anchor in soup.select("article a[href]"):
            try:
                url = canonical(urljoin(item["effective_url"], anchor["href"]))
            except ValueError:
                continue
            if url in known or (not expected_type(url) and "/downloads/cas/" not in url):
                continue
            known.add(url)
            refs = [dict(ref, title=anchor.get_text(" ", strip=True) or ref["title"],
                         source_page=item["effective_url"], source_url=anchor["href"])
                    for ref in item["references"]]
            found.append({"url": url, "references": refs, "status": "pending", "discovered_from": item["url"]})
    return found


def extract_archives(resources, root):
    extracted = []
    metadata_files = []
    for item in resources:
        if item.get("status") != "downloaded" or item.get("kind") != "zip":
            continue
        ref = item["references"][0]
        with zipfile.ZipFile(root / item["path"]) as archive:
            if sum(entry.file_size for entry in archive.infolist()) > 2_000_000_000:
                raise ValueError(f"Archive exceeds extraction limit: {item['path']}")
            for entry in archive.infolist():
                if entry.is_dir() or Path(entry.filename).suffix.lower() not in DOC_EXTENSIONS - {".zip"}:
                    continue
                if entry.file_size > 268435456:
                    raise ValueError(f"Archive entry exceeds limit: {entry.filename}")
                # Flatten names, so archive paths never control local traversal.
                name = slug(Path(entry.filename).name)
                data = archive.read(entry)
                sha = digest(data)
                dest = root / "extracted" / ref["version"] / ref["language"] / f"{sha[:10]}--{name}"
                if "__MACOSX" in Path(entry.filename).parts or Path(entry.filename).name.startswith("._"):
                    # AppleDouble resource forks can have .pdf filenames but
                    # are not PDF documents. Preserve any earlier extraction
                    # separately, and keep the originals in their ZIP bundles.
                    retained = None
                    quarantine = root / "archive-metadata" / ref["version"] / ref["language"] / (dest.name + ".appledouble")
                    if dest.exists() and digest(dest.read_bytes()) == sha:
                        quarantine.parent.mkdir(parents=True, exist_ok=True)
                        if not quarantine.exists():
                            dest.rename(quarantine)
                    if quarantine.is_file() and digest(quarantine.read_bytes()) == sha:
                        retained = quarantine.relative_to(root).as_posix()
                    metadata_files.append({"archive_path": item["path"], "archive_entry": entry.filename,
                                           "sha256": sha, "bytes": len(data), "path": retained,
                                           "reason": "macOS archive metadata, not a document"})
                    continue
                if Path(entry.filename).suffix.lower() == ".pdf" and file_type(data, "") != "pdf":
                    raise ValueError(f"Non-PDF document in archive: {entry.filename}")
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    dest.write_bytes(data)
                extracted.append({"path": dest.relative_to(root).as_posix(), "archive_path": item["path"],
                                  "archive_entry": entry.filename, "source_url": item["url"],
                                  "version": ref["version"], "language": ref["language"],
                                  "bytes": len(data), "sha256": sha})
    return extracted, metadata_files


def write_manifest(root, resources, extracted=None, metadata_files=None):
    manifest = {"schema_version": 1, "library_url": LIBRARY_URL, "platform": "z/OS",
                "product": "IBM Enterprise COBOL for z/OS", "updated_at": now(),
                "scope": "All direct version-section links, public announcement bodies and document attachments on linked articles. "
                         "Online HTML landing pages are snapshots; PDF manuals supply offline book content.",
                "rights": "IBM copyright and document-specific terms retained; no training or redistribution license inferred.",
                "counts": dict(Counter(item["status"] for item in resources)),
                "resources": resources, "archive_documents": extracted or [],
                "excluded_archive_metadata": metadata_files or []}
    staging = root / "manifest.json.tmp"
    staging.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    staging.replace(root / "manifest.json")


def run_batch(resources, root, workers, all_resources):
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(download, item, root): item for item in resources}
        for index, future in enumerate(as_completed(future_map), 1):
            original = future_map[future]
            result = future.result()
            original.clear()
            original.update(result)
            if result["status"] == "failed":
                print(f"FAILED {result['url']}: {result['error'][:180]}", flush=True)
            elif index % 10 == 0 or index == len(resources):
                print(f"Downloaded/verified {index}/{len(resources)} in this batch", flush=True)
            write_manifest(root, all_resources)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    html = root / "library.html"
    if not html.exists():
        subprocess.run(["curl", "--fail", "--location", "--proto", "=https", "--proto-redir", "=https",
                        "--max-time", "60", LIBRARY_URL, "--output", str(html)], check=True)
    resources = inventory(html.read_text())
    if (root / "manifest.json").exists():
        previous = json.loads((root / "manifest.json").read_text())
        # Discard only erroneous duplicate discovery attempts from an older
        # downloader run. These are not library links and have no saved file.
        previous["resources"] = [item for item in previous["resources"] if not (
            item.get("status") == "failed" and item.get("resource_role") == "article_body" and
            "/docs/api/v1/content/" in item.get("discovered_from", ""))]
        old = {item["url"]: item for item in previous["resources"]}
        for item in resources:
            if item["url"] in old:
                item.update(old[item["url"]])
        listed = {item["url"] for item in resources}
        resources.extend(item for item in previous["resources"] if item["url"] not in listed)
    print(f"Inventory: {len(resources)} unique linked resources", flush=True)
    run_batch(list(resources), root, args.workers, resources)
    bodies = article_bodies(resources)
    if bodies:
        print(f"Retrieving {len(bodies)} public article bodies", flush=True)
        resources.extend(bodies)
        run_batch(bodies, root, args.workers, resources)
    extra = attachments(resources, root)
    if extra:
        print(f"Following {len(extra)} document attachments", flush=True)
        resources.extend(extra)
        run_batch(extra, root, args.workers, resources)
    extracted, metadata_files = extract_archives(resources, root)
    write_manifest(root, resources, extracted, metadata_files)
    print(json.dumps({"resources": dict(Counter(item["status"] for item in resources)),
                      "types": dict(Counter(item.get("kind") for item in resources if item["status"] == "downloaded")),
                      "extracted_documents": len(extracted),
                      "excluded_archive_metadata": len(metadata_files)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
