"""Archive the English IBM i references relevant to agent-sql-alpha.

Run from the project root: python3 training/training_pipeline/download_ibmi.py
Uses the verified, resumable IBM downloader; does not enable model training.
"""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from download_ibm_cobol import canonical, digest, download as download_file, expected_type, now


ROOT = Path(__file__).resolve().parents[1] / "TRAINING/ibm-i-as400"
RELEASES = ("7.6", "7.5", "7.4", "7.3", "7.2", "7.1")
CATEGORIES = {
    "Database", "Programming", "Security", "Files and file systems",
    "Connecting to your system", "Systems Management", "System management",
    "Migration", "Troubleshooting", "IBM i and related software",
    "Integrated operating environments", "Availability", "About IBM i information",
}
EXTRA_TITLES = re.compile(
    r"cryptograph|certificate|identity mapping|directory server|object signing|"
    r"single sign.on|transport layer security|secure sockets|tcp/ip (setup|troubleshoot)|"
    r"socket|netserver|http server|installing.*upgrading|stored procedures.*triggers", re.I)
EXCLUDE_TITLES = re.compile(r"^AFP Utilities|^Hierarchical Storage|^Optical device|^Tape files", re.I)
SUPPLEMENTS = [
    ("https://www.ibm.com/docs/en/ssw_ibm_i_74/rzahg/linkbooks.htm", "Additional IBM i reference manuals", "Legacy references"),
    ("https://www.ibm.com/docs/en/ssw_ibm_i_74/rzahg/rzahgrpgredbooks.htm", "IBM i RPG related reference manuals", "Legacy references"),
    ("https://www.ibm.com/support/pages/ibm-i-services-sql", "IBM i Services SQL release and PTF matrix", "SQL services"),
    ("https://www.ibm.com/support/pages/db2-ibm-i", "Db2 for IBM i resources", "Database"),
    ("https://www.ibm.com/support/pages/ibm-i-tutorials-demos-and-sql-examples-0", "IBM i tutorials demos and SQL examples", "Database"),
    ("https://www.ibm.com/support/pages/ibm-i-access-client-solutions", "IBM i Access Client Solutions", "Connectivity"),
    ("https://www.ibm.com/support/pages/odbc-driver-ibm-i-access-client-solutions", "IBM i Access Client Solutions ODBC driver", "Connectivity"),
    ("https://www.ibm.com/support/pages/node/645897", "IBM i Access Linux ODBC configuration", "Connectivity"),
    ("https://www.ibm.com/support/pages/servers-ports-required-ibm-iaccess-linux%C2%AE-odbc-driver", "Ports required for IBM i Access Linux ODBC", "Connectivity"),
    ("https://www.redbooks.ibm.com/redbooks/pdfs/sg248185.pdf", "Modernizing IBM i Applications", "Modernization"),
    ("https://www.redbooks.ibm.com/redbooks/pdfs/sg245402.pdf", "Who Knew You Could Do That with RPG IV", "Modernization"),
    ("https://www.redbooks.ibm.com/redbooks/pdfs/sg246393.pdf", "Modernizing iSeries Application Data Access", "Modernization"),
    ("https://www.redbooks.ibm.com/redbooks/pdfs/sg248326.pdf", "SQL Procedures Triggers and User Defined Functions on IBM Db2 for i", "Database"),
    ("https://www.redbooks.ibm.com/docs/MD260020/MD260020.html", "IBM i application modernization guide (publisher status applies)", "Modernization"),
    ("https://bob.ibm.com/docs/ide/features/modes", "IBM Bob operational modes", "Capability benchmark"),
    ("https://bob.ibm.com/docs/ide/features/subagents", "IBM Bob subagents", "Capability benchmark"),
    ("https://bob.ibm.com/docs/ide/enterprise/on-premises/overview", "IBM Bob self-hosted deployment overview", "Capability benchmark"),
]


def clean(text):
    return " ".join(text.split())


def download(item, root):
    # IBM's 7.2 catalog accidentally publishes authoring-system FileNet paths.
    # The same referenced topic exists in the normal public product namespace.
    original = item["url"]
    normalized = re.sub(r"(/ssw_ibm_i_\d\d)/FileNet/Work/Current/IDCMS1/STG/IBMi/v\dr\dm\df/", r"\1/", original)
    if normalized != original and item.get("status") != "downloaded":
        result = download_file(dict(item, url=normalized, status="pending"), root)
        result.update(url=original, mirror_source_url=normalized,
                      original_attempt={"url": original, "repair": "Removed published FileNet authoring path"})
    else:
        result = download_file(item, root)
    if result["status"] != "failed":
        return result
    replacement = None
    if original.endswith("/books/sc191030.pdf"):
        # The 7.6 catalog publishes this same InfoSphere 9.7 book here.
        replacement = "https://public.dhe.ibm.com/systems/power/docs/systemi/v6r1/en_US/sc191030.pdf"
    elif original.startswith("https://publib.boulder.ibm.com/infocenter/iseries/v6r1m0/topic/"):
        # The IBM v6r1 PDF download list publishes these exact book numbers.
        book = original.rsplit("/", 1)[-1]
        if book in {"sc415210.pdf", "sc415703.pdf", "sc415212.pdf", "sc237691.pdf", "sh126720.pdf"}:
            replacement = "https://public.dhe.ibm.com/systems/power/docs/systemi/v6r1/en_US/" + book
    elif original == "https://www.ibm.com/pdf/rbafzpdf.pdf":
        parent = item.get("discovered_from", "")
        if parent == "https://www.ibm.com/docs/en/ssw_ibm_i_74/rzahg/rzatdprintable.htm":
            replacement = "https://www.ibm.com/docs/en/ssw_ibm_i_74/pdf/rbafzpdf.pdf"
    elif original == "https://www.ibm.com/common/ssi/rep_ca/9/897/ENUS200-179/ENUS200-179.PDF":
        # IBM retired the PDF link but still supplies its full announcement.
        replacement = "https://www.ibm.com/docs/api/v1/content/announcement_archive?announcement=ENUS200-179&parsebody=true&lang=en"
    if replacement:
        recovered = download_file(dict(item, url=replacement, status="pending"), root)
        if recovered["status"] == "downloaded":
            recovered.update(url=original, mirror_source_url=replacement,
                             original_attempt={"url": original, "error": result.get("error")})
            if recovered["kind"] == "html":
                recovered["format_substitution"] = "Original announcement PDF unavailable; full IBM archive HTML body retained"
            return recovered
    return result


def namespace(version):
    return "ssw_ibm_i_" + version.replace(".", "")


def ref(version, title, subject, source):
    return {"version": version, "language": "en", "title": clean(title),
            "subject": clean(subject), "source_page": source}


def add(resources, url, references, role="document", **metadata):
    try:
        url = canonical(url)
    except ValueError:
        return None
    if url in resources:
        item = resources[url]
        for reference in references:
            if reference not in item["references"]:
                item["references"].append(reference)
    else:
        item = {"url": url, "references": references, "status": "pending", "resource_role": role}
        resources[url] = item
    item.update(metadata)
    # A catalog can legitimately link a manual originally published for an
    # older release. Keep the publisher's URL release separate from references.
    match = re.search(r"ssw_ibm_i_(\d)(\d)|/systemi/(v\dr\d)/", url)
    if match:
        item["publisher_release_from_url"] = (f"{match[1]}.{match[2]}" if match[1] else match[3])
    return item


def save(root, resources, omitted):
    items = list(resources.values())
    manifest = {
        "schema_version": 1, "updated_at": now(), "platform": "IBM i",
        "customer_release": "unknown", "catalog_releases": list(RELEASES), "language": "en",
        "scope": "English IBM i 7.1–7.6 manuals selected from IBM's PDF catalogs for database, "
                 "programming, security, connectivity, filesystem, operations, availability and migration; "
                 "support references and modernization Redbooks. Not a mirror of all ibm.com.",
        "rights": "Original IBM notices retained; no redistribution or model-training license inferred.",
        "counts": dict(Counter(i["status"] for i in items)),
        "types": dict(Counter(i.get("kind") for i in items if i["status"] == "downloaded")),
        "resources": items, "excluded_catalog_entries": omitted,
    }
    staging = root / "manifest.json.tmp"
    staging.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    staging.replace(root / "manifest.json")


def batch(root, resources, items, workers, omitted):
    if not items:
        return
    print(f"Fetching/verifying {len(items)} references", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(download, i, root): i for i in items}
        for count, future in enumerate(as_completed(futures), 1):
            original = futures[future]
            result = future.result()
            original.clear()
            original.update(result)
            if result["status"] == "failed":
                print(f"FAILED {result['url']}: {result.get('error', '')[:140]}", flush=True)
            elif count % 20 == 0 or count == len(items):
                print(f"Verified {count}/{len(items)}", flush=True)
            save(root, resources, omitted)


def soup_for(item, root):
    return BeautifulSoup((root / item["path"]).read_bytes(), "lxml")


def parse_catalog(item, root, resources, omitted):
    version = item["references"][0]["version"]
    base = f"https://www.ibm.com/docs/en/{namespace(version)}/rzahg/catalog.htm"
    soup = soup_for(item, root)
    rows = soup.select("tr")
    if len(rows) < 100:
        item["discovery_error"] = "Catalog does not contain the expected manual table"
        return
    item.pop("discovery_error", None)
    selected = 0
    for row in rows:
        cells = row.find_all("td", recursive=False)
        if len(cells) < 3:
            continue
        title, category = [clean(c.get_text(" ", strip=True)) for c in cells[:2]]
        categories = {part.strip() for part in category.split(";")}
        include = (bool(categories & CATEGORIES) or EXTRA_TITLES.search(title)) and not EXCLUDE_TITLES.search(title)
        for anchor in cells[0].select("a[href]"):
            href = anchor["href"]
            if href.startswith("#"):
                continue
            url = urljoin(base, href)
            if not include:
                entry = {"catalog_release": version, "title": title, "category": category,
                         "url": url, "reason": "Outside the selected IBM i assistant documentation scope"}
                if entry not in omitted:
                    omitted.append(entry)
                continue
            reference = ref(version, title, category, item["url"])
            reference["source_url"] = href
            add(resources, url, [reference], "manual" if expected_type(url) else "print_landing")
            selected += 1
    item["selected_entries"] = selected
    # Preserve the publisher's terms alongside the references.
    for anchor in soup.select("a[href]"):
        if "terms and conditions" in anchor.get_text(" ", strip=True).lower():
            add(resources, urljoin(base, anchor["href"]),
                [ref(version, "IBM documentation terms and conditions", "Rights", item["url"])], "terms")


def discover_documents(item, root, resources):
    if item.get("kind") != "html" or item.get("status") != "downloaded":
        return
    role = item.get("resource_role")
    if role not in ("print_landing", "support", "supplement", "additional_index"):
        return
    soup = soup_for(item, root)
    section = soup.select_one("article") or soup.select_one("main") or soup.body or soup
    base = item.get("effective_url", item["url"])
    # Classic topic URLs contain the directory needed for ../pdf references.
    if "/ssw_ibm_i_" in item["url"]:
        base = item.get("mirror_source_url", item["url"])
    found = 0
    for anchor in section.select("a[href]"):
        href = anchor["href"]
        if href.startswith("#"):
            continue
        url = urljoin(base, href)
        kind = expected_type(url)
        # Documentation only: no executables, drivers, installation archives,
        # unbounded crawling, or downloads requiring an IBM entitlement.
        if kind not in ("pdf", "txt", "doc", "docx"):
            continue
        references = [dict(r, title=clean(anchor.get_text(" ", strip=True)) or r["title"],
                           source_page=item["url"], source_url=href,
                           parent_title=r["title"]) for r in item["references"]]
        if add(resources, url, references, "manual", discovered_from=item["url"]):
            found += 1
    item["linked_document_count"] = found
    # Do not silently call an interactive shell an offline manual.
    if role == "print_landing" and found == 0:
        item["discovery_warning"] = "No downloadable document link found; retained HTML snapshot only"
    else:
        item.pop("discovery_warning", None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    resources, omitted = {}, []
    if (root / "manifest.json").exists():
        previous = json.loads((root / "manifest.json").read_text())
        resources = {i["url"]: i for i in previous["resources"]}
        omitted = previous.get("excluded_catalog_entries", [])
    for version in RELEASES:
        section = "documentation" if version in ("7.6", "7.5") else "information"
        url = f"https://www.ibm.com/docs/en/i/{version}.0?topic={section}-pdf-files-manuals"
        if version == "7.3":
            # The product alias returns a navigation index, not this catalog.
            # Its published navigation points to the classic topic URL below.
            if url in resources:
                resources[url]["resource_role"] = "navigation_snapshot"
                resources[url].pop("discovery_error", None)
            url = "https://www.ibm.com/docs/en/ssw_ibm_i_73/pdftable/pdftable.htm"
        add(resources, url, [ref(version, f"IBM i {version} PDF files and manuals", "Catalog", url)], "catalog")
    for url, title, category in SUPPLEMENTS:
        add(resources, url, [ref("cross-release", title, category, url)],
            "support" if "/support/" in url else "supplement")
    # IBM no longer supplies PDFs for individual CL commands and APIs. These
    # source/object inspection and controlled build references are kept as HTML.
    native_topics = {
        "apis/qbnlpgmi.htm": "List ILE Program Information QBNLPGMI",
        "apis/qbnlspgm.htm": "List Service Program Information QBNLSPGM",
        "apis/qbnrmodi.htm": "Retrieve Module Information QBNRMODI",
        "apis/qclrpgmi.htm": "Retrieve Program Information QCLRPGMI",
        "apis/qdbrtvfd.htm": "Retrieve Database File Description QDBRTVFD",
        "apis/quslmbr.htm": "List Database File Members QUSLMBR",
        "apis/quslobj.htm": "List Objects QUSLOBJ",
        "apis/quslrcd.htm": "List Record Formats QUSLRCD",
        "apis/qusrmbrd.htm": "Retrieve Member Description QUSRMBRD",
        "apis/quscrtus.htm": "Create User Space QUSCRTUS",
        "apis/qusrtvus.htm": "Retrieve User Space QUSRTVUS",
        "cl/cpytoStmf.htm": "Copy To Stream File CPYTOSTMF",
        "cl/cpyfrmstmf.htm": "Copy From Stream File CPYFRMSTMF",
        "cl/crtrpgmod.htm": "Create RPG Module CRTRPGMOD",
        "cl/crtbndrpg.htm": "Create Bound RPG Program CRTBNDRPG",
        "cl/crtcblmod.htm": "Create COBOL Module CRTCBLMOD",
        "cl/crtbndcbl.htm": "Create Bound COBOL Program CRTBNDCBL",
        "cl/crtclmod.htm": "Create CL Module CRTCLMOD",
        "cl/crtbndcl.htm": "Create Bound CL Program CRTBNDCL",
        "cl/crtpgm.htm": "Create Program CRTPGM",
        "cl/crtsrvpgm.htm": "Create Service Program CRTSRVPGM",
        "cl/crtpf.htm": "Create Physical File CRTPF",
        "cl/crtlf.htm": "Create Logical File CRTLF",
        "cl/runsqlstm.htm": "Run SQL Statements RUNSQLSTM",
    }
    for version in ("7.6", "7.5", "7.4"):
        for topic, title in native_topics.items():
            url = f"https://www.ibm.com/docs/en/{namespace(version)}/{topic.lower()}"
            add(resources, url, [ref(version, title, "Native APIs and CL commands", url)], "native_topic")
    catalogs = [i for i in resources.values() if i["resource_role"] == "catalog"]
    batch(root, resources, catalogs, args.workers, omitted)
    for item in catalogs:
        if item["status"] == "downloaded":
            parse_catalog(item, root, resources, omitted)
    # Each print landing can expose several manuals (e.g. CL reference parts).
    # Two bounded passes capture all those documents without crawling websites.
    for unused in range(2):
        pending = [i for i in resources.values() if i["resource_role"] != "catalog" and
                   (i.get("status") != "downloaded" or not (root / i.get("path", "missing")).is_file())]
        batch(root, resources, pending, args.workers, omitted)
        for item in list(resources.values()):
            discover_documents(item, root, resources)
        save(root, resources, omitted)
    # Verify every saved resource's checksum, including resumed runs.
    for item in resources.values():
        if item.get("status") == "downloaded":
            path = root / item["path"]
            if not path.is_file() or digest(path.read_bytes()) != item["sha256"]:
                item.update(status="failed", error="Local checksum verification failed")
    save(root, resources, omitted)
    print(json.dumps({"status": dict(Counter(i["status"] for i in resources.values())),
                      "types": dict(Counter(i.get("kind") for i in resources.values() if i["status"] == "downloaded")),
                      "catalogs": [{"release": i["references"][0]["version"],
                                    "selected": i.get("selected_entries"), "error": i.get("discovery_error")}
                                   for i in catalogs]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
