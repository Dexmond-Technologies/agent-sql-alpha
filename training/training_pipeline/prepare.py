"""Prepare the downloaded SQL corpus without executing downloaded code.

Run from the workspace root: python3 -m training_pipeline.prepare
Only the Python standard library and Poppler's pdftotext are required.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import fnmatch
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path(__file__).with_name("sources.json")
EXCLUDED_PARTS = {".git", ".github", ".claude", "node_modules", "wwwroot",
                  "vendor", "bin", "obj", "packages", "public"}
EXCLUDED_NAMES = {"agents.md", "claude.md", "contributing.md", "summary.md",
                  "code_of_conduct.md", "security.md"}
SECRET_PATTERNS = [r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
                   r"\bAKIA[0-9A-Z]{16}\b", r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"]
FENCES = re.compile(r"(```[^\n]*\n[\s\S]*?```|~~~[^\n]*\n[\s\S]*?~~~)")


def digest(value):
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def jsonl(path, records):
    with path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def git(directory, *args):
    result = subprocess.run(["git", "-C", str(directory), *args],
                            capture_output=True, text=True, check=True)
    return result.stdout.strip()


def decode(data):
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "utf-16"
    if b"\x00" in data:
        raise ValueError("binary or unmarked UTF-16 content")
    try:
        return data.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("cp1252"), "cp1252"


def tidy(text):
    # Do not collapse SQL literals, change case, or apply Unicode compatibility
    # normalization: all can change the meaning of a SQL example.
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


class DocBookText(HTMLParser):
    """A non-expanding, offline SGML text reader with code preservation."""

    blocks = {"para", "simpara", "chapter", "sect1", "sect2", "sect3", "sect4",
              "refsect1", "refsect2", "refsect3", "listitem", "row", "entry",
              "refpurpose", "term", "warning", "note"}
    code_tags = {"programlisting", "screen", "synopsis", "literallayout"}
    ignored = {"indexterm", "script", "style"}

    def __init__(self, version="unknown"):
        super().__init__(convert_charrefs=False)
        self.parts = []
        self.ignore_depth = 0
        self.code_depth = 0
        self.title_depth = 0
        self.unresolved = set()
        self.version = version

    def handle_starttag(self, tag, attrs):
        if self.ignore_depth:
            self.ignore_depth += 1
            return
        if tag in self.ignored:
            self.ignore_depth = 1
        elif tag in self.code_tags:
            self.parts.append("\n\n```\n")
            self.code_depth += 1
        elif tag in {"title", "refentrytitle"}:
            self.parts.append("\n\n## ")
            self.title_depth += 1
        elif tag in self.blocks:
            self.parts.append("\n\n")
        elif tag == "xref":
            target = dict(attrs).get("linkend", "unknown")
            self.parts.append(f"[reference: {target}]")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag != "xref":
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.ignore_depth:
            self.ignore_depth -= 1
        elif tag in self.code_tags:
            self.code_depth = max(0, self.code_depth - 1)
            self.parts.append("\n```\n\n")
        elif tag in {"title", "refentrytitle"}:
            self.title_depth = max(0, self.title_depth - 1)
            self.parts.append("\n\n")
        elif tag in self.blocks:
            self.parts.append("\n\n")

    def handle_data(self, data):
        if not self.ignore_depth:
            self.parts.append(data if self.code_depth else re.sub(r"\s+", " ", data))

    def handle_entityref(self, name):
        known = {"version": self.version, "majorversion": self.version.split(".")[0],
                 "nbsp": " ", "mdash": "—", "ndash": "–", "hellip": "…",
                 "copy": "©", "ge": "≥", "le": "≤"}
        value = known.get(name, html.unescape(f"&{name};"))
        if value == f"&{name};":
            self.unresolved.add(name)
        self.handle_data(value)

    def handle_charref(self, name):
        self.handle_data(html.unescape(f"&#{name};"))

    def text(self):
        return tidy("".join(self.parts))


def markdown(text):
    flags = []
    title = None
    front = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.S)
    if front:
        found = re.search(r"^title:\s*[\"']?(.*?)[\"']?\s*$", front[1], re.M)
        title = found[1] if found else None
        text = text[front.end():]

    def prose(part):
        part = re.sub(r"<!--[\s\S]*?-->", "", part)
        part = re.sub(r"\{%\s*link\s+([^%]+?)\s*%\}", r"\1", part)
        if re.search(r"\{%\s*include\b|\{\{", part):
            flags.append("unresolved_template_or_include")
        part = re.sub(r"\{%\s*tab\s+title=[\"']([^\"']+)[\"']\s*%\}", r"\n### \1\n", part)
        part = re.sub(r"\{%\s*(?:end)?(?:hint|tabs|tab|code|columns|column|content-ref)\b.*?%\}", "", part)
        part = re.sub(r"</?(?:div|span|sub|sup|details|summary|figure|figcaption|p)\b[^>]*>", "", part)
        return part

    text = "".join(part if i % 2 else prose(part) for i, part in enumerate(FENCES.split(text)))
    if title and not re.match(r"\s*# ", text):
        text = f"# {title}\n\n{text}"
    return tidy(text), sorted(set(flags))


def extract(path, version):
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        result = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],
                                capture_output=True, timeout=120, check=True)
        text = result.stdout.decode("utf-8")
        # Page boundaries survive as blank lines. PDF text/reading order is
        # approximate; images are not OCR'd.
        return tidy(text.replace("\f", "\n\n")), "pdftotext-layout", ["pdf_layout_needs_review"], ""
    raw, encoding = decode(path.read_bytes())
    raw = tidy(raw)
    if suffix == ".sgml":
        reader = DocBookText(version)
        reader.feed(raw)
        reader.close()
        flags = ["unresolved_sgml_entities"] if reader.unresolved else []
        return reader.text(), "docbook-text-v1", flags, raw
    if suffix == ".md":
        text, flags = markdown(raw)
        if encoding != "utf-8":
            flags.append("legacy_encoding")
        return text, f"markdown-{encoding}", flags, raw
    return raw, f"sql-{encoding}", [], raw


def classify_license(source, raw):
    page = re.search(r"This page is licensed:\s*([^<\n]+)", raw, re.I)
    declared = re.sub(r"[_*]", "", page[1]).strip() if page else source["license"]
    # This is an explicit curation policy, not a legal determination.
    eligible = bool(source.get("notice")) and declared in {"MIT", "PostgreSQL"}
    if re.search(r"adapted from|copied.{0,30}(?:from|permission)|originally from", raw, re.I):
        eligible = False
    return declared, "notice-recorded" if eligible else "review-required"


def windows(text, limit, overlap):
    if limit < 100 or not 0 <= overlap < limit // 2:
        raise ValueError("chunk limit must be >=100 and overlap < half the limit")
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + limit // 2, end)
            if boundary < 0:
                boundary = text.rfind(" ", start + limit // 2, end)
            if boundary >= 0:
                end = boundary + 1
        yield start, end, text[start:end]
        if end == len(text):
            break
        start = max(start + 1, end - overlap)


class Groups:
    def __init__(self, ids):
        self.parent = {item: item for item in ids}

    def find(self, item):
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


def near_groups(documents, groups):
    """Conservative sampled-shingle grouping; never deletes a near duplicate.

    Candidate pairs share a bottom hash; Jaccard over 128 bottom hashes is a
    heuristic, not exhaustive semantic deduplication.
    """
    buckets = defaultdict(list)
    signatures = {}
    matches = []
    for doc in documents:
        tokens = doc["text"].split()
        hashes = {hashlib.blake2b(" ".join(tokens[i:i + 5]).encode(), digest_size=8).digest()
                  for i in range(max(0, len(tokens) - 4))}
        signature = set(sorted(hashes)[:128])
        if len(signature) < 32:
            continue
        candidates = set()
        for item in sorted(signature)[:8]:
            candidates.update(buckets[item])
        for other in sorted(candidates):
            previous = signatures[other]
            score = len(signature & previous) / len(signature | previous)
            if score >= 0.85:
                groups.union(doc["id"], other)
                matches.append({"a": doc["id"], "b": other, "sampled_jaccard": round(score, 4)})
        signatures[doc["id"]] = signature
        for item in sorted(signature)[:8]:
            buckets[item].append(doc["id"])
    return matches


def partition(group, seed):
    value = int(digest(seed + ":" + group)[:8], 16) % 100
    return "test" if value < 5 else "validation" if value < 10 else "train"


def make_chunks(documents, config):
    groups = Groups(doc["id"] for doc in documents)
    near = near_groups(documents, groups)
    unique = {}
    for doc in documents:
        for index, (start, end, text) in enumerate(windows(doc["text"], config["chunk_chars"], config["overlap_chars"])):
            if not text.strip():
                continue
            identity = digest(text)
            span = {"document_id": doc["id"], "start_char": start, "end_char": end, "index": index}
            if identity in unique:
                groups.union(unique[identity]["spans"][0]["document_id"], doc["id"])
                unique[identity]["spans"].append(span)
            else:
                unique[identity] = {"id": identity, "text": text, "spans": [span]}
    lookup = {doc["id"]: doc for doc in documents}
    for doc in documents:
        doc["group_id"] = groups.find(doc["id"])
        doc["split"] = partition(doc["group_id"], config["split_seed"])
    for chunk in unique.values():
        docs = [lookup[span["document_id"]] for span in chunk["spans"]]
        chunk.update({"group_id": docs[0]["group_id"], "split": docs[0]["split"],
                      "dialects": sorted({p["dialect"] for doc in docs for p in doc["provenance"]}),
                      "source_ids": sorted({p["source_id"] for doc in docs for p in doc["provenance"]}),
                      "source_urls": sorted({p["source_url"] for doc in docs for p in doc["provenance"]}),
                      "training_eligible": all(doc["training_eligible"] for doc in docs),
                      "quality_flags": sorted({flag for doc in docs for flag in doc["quality_flags"]})})
    return sorted(unique.values(), key=lambda item: item["id"]), near


def prepare_sources(training, config):
    sources = []
    for original in config["sources"]:
        source = dict(original)
        directory = training / source["directory"]
        if not directory.is_dir():
            raise ValueError(f"missing source directory: {directory}")
        source["revision"] = git(directory, "rev-parse", "HEAD") if source.get("repository") else None
        source["working_tree_clean"] = not git(directory, "status", "--porcelain") if source.get("repository") else None
        if source["version"] == "detect-postgresql":
            configure = (directory / "configure.ac").read_text()
            source["version"] = re.search(r"AC_INIT\(\[PostgreSQL\], \[([^]]+)\]", configure)[1]
        notice = directory / source["notice"] if source["notice"] else None
        if notice and not notice.is_file():
            raise ValueError(f"missing declared license notice: {notice}")
        source["notice_sha256"] = digest(notice.read_bytes()) if notice else None
        sources.append(source)
    return sources


def inventory(training, sources, config):
    documents, audit, errors = {}, [], []
    for source in sources:
        directory = training / source["directory"]
        paths = sorted(directory.rglob("*"))
        for path in paths:
            relative = path.relative_to(directory)
            if any(part in EXCLUDED_PARTS or part.startswith(".") for part in relative.parts):
                continue
            if not path.is_file():
                continue
            record = {"source_id": source["id"], "path": str(path.relative_to(training))}
            def skip(reason):
                audit.append({**record, "status": "skipped", "reason": reason})
            if path.is_symlink():
                skip("symlink")
                continue
            if path.name.lower() in EXCLUDED_NAMES or not any(fnmatch.fnmatch(relative.as_posix(), p) for p in source["include"]):
                skip("outside content allowlist")
                continue
            size = path.stat().st_size
            limit = config["maximum_pdf_bytes"] if path.suffix.lower() == ".pdf" else config["maximum_file_bytes"]
            if size > limit or size == 0:
                skip("oversize" if size else "empty")
                continue
            raw_hash = digest(path.read_bytes())
            try:
                text, extractor, flags, raw = extract(path, source["version"])
            except (ValueError, UnicodeError, OSError, subprocess.SubprocessError) as exc:
                errors.append({**record, "error": str(exc)[:500]})
                audit.append({**record, "status": "extraction-error"})
                continue
            if len(text) < config["minimum_chars"]:
                skip("too little extracted text")
                continue
            if "\ufffd" in text or "\x00" in text:
                flags.append("invalid_text_characters")
            if any(re.search(pattern, text) for pattern in SECRET_PATTERNS):
                # Do not emit matching secrets into any generated text export.
                skip("credential_pattern_requires_review")
                continue
            license_name, license_status = classify_license(source, raw)
            if license_status == "review-required":
                flags.append("license_review_required")
            if source["working_tree_clean"] is False:
                flags.append("modified_source_checkout")
            source_url = source.get("url") or (source["repository"] + "/blob/" + source["revision"] + "/" + quote(relative.as_posix()))
            provenance = {"source_id": source["id"], "path": record["path"],
                          "source_url": source_url, "revision": source["revision"],
                          "raw_sha256": raw_hash, "dialect": source["dialect"],
                          "version": source["version"], "license": license_name,
                          "license_status": license_status,
                          "notice_path": f"notices/{source['id']}.txt" if source["notice"] else None,
                          "extractor": extractor}
            identity = digest(text)
            if identity in documents:
                documents[identity]["provenance"].append(provenance)
                documents[identity]["quality_flags"] = sorted(set(documents[identity]["quality_flags"] + flags))
                status = "exact-document-duplicate"
            else:
                title = re.search(r"^#{1,6}\s+(.+)$", text, re.M)
                documents[identity] = {"id": identity, "title": title[1].strip() if title else path.stem,
                                       "text": text, "provenance": [provenance], "quality_flags": sorted(set(flags))}
                status = "included"
            audit.append({**record, "status": status, "document_id": identity, "raw_sha256": raw_hash})
        print(f"Prepared {source['id']}: {len(documents)} unique documents so far", flush=True)
    for doc in documents.values():
        doc["training_eligible"] = not doc["quality_flags"]
    return sorted(documents.values(), key=lambda doc: doc["id"]), audit, errors


def index_chunks(path, chunks):
    with sqlite3.connect(path) as db:
        db.execute("CREATE VIRTUAL TABLE chunks USING fts5(id UNINDEXED, text, dialects UNINDEXED, source_urls UNINDEXED, split UNINDEXED, training_eligible UNINDEXED, tokenize='unicode61')")
        db.executemany("INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
                       ((c["id"], c["text"], json.dumps(c["dialects"]), json.dumps(c["source_urls"]), c["split"], int(c["training_eligible"])) for c in chunks))


def validate(documents, chunks, config):
    failures = []
    lookup = {doc["id"]: doc for doc in documents}
    seen = set()
    groups = defaultdict(set)
    for doc in documents:
        if doc["id"] != digest(doc["text"]) or not doc["provenance"]:
            failures.append("document identity or provenance failure")
        groups[doc["group_id"]].add(doc["split"])
    for chunk in chunks:
        if chunk["id"] in seen or chunk["id"] != digest(chunk["text"]):
            failures.append("duplicate or invalid chunk identity")
        seen.add(chunk["id"])
        if not 0 < len(chunk["text"]) <= config["chunk_chars"]:
            failures.append("invalid chunk length")
        for span in chunk["spans"]:
            doc = lookup[span["document_id"]]
            if doc["text"][span["start_char"]:span["end_char"]] != chunk["text"]:
                failures.append("chunk does not match document span")
            if doc["split"] != chunk["split"] or doc["group_id"] != chunk["group_id"]:
                failures.append("split leakage")
        if chunk["training_eligible"] and chunk["quality_flags"]:
            failures.append("review flag in training export")
    if any(len(splits) != 1 for splits in groups.values()):
        failures.append("group appears in multiple splits")
    if not documents or not chunks:
        failures.append("empty dataset")
    return sorted(set(failures))


def build(training, output, config_path=CONFIG):
    config = json.loads(config_path.read_text())
    if output.exists():
        raise ValueError(f"output already exists; choose a new --output directory: {output}")
    if not shutil.which("pdftotext"):
        raise ValueError("pdftotext is required (install poppler-utils)")
    sources = prepare_sources(training, config)
    documents, audit, errors = inventory(training, sources, config)
    chunks, near = make_chunks(documents, config)
    failures = validate(documents, chunks, config)
    if failures:
        raise ValueError("validation failed: " + "; ".join(failures))
    output.parent.mkdir(parents=True, exist_ok=True)
    # Publish the complete build atomically; partial output is never presented
    # as a finished corpus. A new output path is required for every rebuild.
    with tempfile.TemporaryDirectory(prefix="sql-build-", dir=output.parent) as temporary:
        stage = Path(temporary) / "dataset"
        stage.mkdir()
        (stage / "notices").mkdir()
        for source in sources:
            if source["notice"]:
                shutil.copy2(training / source["directory"] / source["notice"], stage / "notices" / f"{source['id']}.txt")
        jsonl(stage / "documents.jsonl", documents)
        jsonl(stage / "chunks.jsonl", chunks)
        jsonl(stage / "inventory.jsonl", audit)
        jsonl(stage / "near_duplicates.jsonl", near)
        jsonl(stage / "review.jsonl", ({"document_id": d["id"], "flags": d["quality_flags"], "provenance": d["provenance"]} for d in documents if not d["training_eligible"]))
        for split in ("train", "validation", "test"):
            jsonl(stage / f"{split}.jsonl", (c for c in chunks if c["training_eligible"] and c["split"] == split))
        index_chunks(stage / "search.sqlite", chunks)
        report = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                  "pipeline_sha256": digest(Path(__file__).read_bytes()),
                  "config_sha256": digest(config_path.read_bytes()), "config": config,
                  "sources": sources, "documents": len(documents), "chunks": len(chunks),
                  "characters": sum(len(d["text"]) for d in documents),
                  "documents_by_source": dict(Counter(p["source_id"] for d in documents for p in d["provenance"])),
                  "chunks_by_dialect": dict(Counter(x for c in chunks for x in c["dialects"])),
                  "training_split_chunks": dict(Counter(c["split"] for c in chunks if c["training_eligible"])),
                  "review_documents": sum(not d["training_eligible"] for d in documents),
                  "quality_flags": dict(Counter(flag for d in documents for flag in d["quality_flags"])),
                  "inventory_status": dict(Counter(a["status"] for a in audit)),
                  "skip_reasons": dict(Counter(a["reason"] for a in audit if "reason" in a)),
                  "near_duplicate_pairs_grouped": len(near),
                  "largest_document_group": max(Counter(d["group_id"] for d in documents).values()),
                  "validation_failures": failures, "extraction_errors": errors,
                  "readiness": "prepared-with-review-items" if errors or any(d["quality_flags"] for d in documents) else "prepared",
                  "limitations": ["Raw text corpus, not instruction-response fine-tuning examples.",
                                  "Character-based chunks require target-model tokenization before training.",
                                  "PDFs have no OCR; figures and reading order require review.",
                                  "Sparse-source includes and external references are not recursively downloaded.",
                                  "Near-duplicate grouping is heuristic; semantic or paraphrase leakage is not measured.",
                                  "License labels record notices and curation policy, not legal clearance.",
                                  "PostgreSQL master may document unreleased features; consult per-source version metadata.",
                                  "Corpus splits measure held-out text, not SQL execution correctness."]}
        report["artifact_sha256"] = {p.name: digest(p.read_bytes()) for p in sorted(stage.iterdir()) if p.is_file()}
        (stage / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        (stage / "READINESS.md").write_text(
            "# Prepared SQL corpus\n\n"
            f"Documents: {len(documents):,}. Unique chunks: {len(chunks):,}. "
            f"Documents awaiting review: {report['review_documents']:,}.\n\n"
            "Validation: passed identity, provenance, span, chunk-size and group/split checks.\n\n"
            f"Eligible text chunks by split: `{report['training_split_chunks']}`.\n\n"
            f"Extraction errors: {len(errors)}. See `report.json` and `inventory.jsonl`.\n\n"
            "The retrieval index contains all extracted documents, including flagged material. "
            "The training splits contain only documents that pass the configured curation policy.\n\n"
            + "\n".join("- " + item for item in report["limitations"]) + "\n",
            encoding="utf-8")
        stage.rename(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training", type=Path, default=ROOT / "TRAINING")
    parser.add_argument("--output", type=Path, default=ROOT / "TRAINING" / "prepared")
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()
    try:
        report = build(args.training.resolve(), args.output.resolve(), args.config.resolve())
    except (ValueError, OSError, subprocess.SubprocessError, sqlite3.Error) as exc:
        parser.exit(1, f"Preparation failed: {exc}\n")
    print(json.dumps({key: report[key] for key in ["documents", "chunks", "training_split_chunks", "review_documents", "readiness"]}, indent=2))
    if report["extraction_errors"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
