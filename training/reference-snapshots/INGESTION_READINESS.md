# IBM i corpus: pre-ingestion readiness

Review date: 2026-10-01. Customer platform: **IBM i**, exact release/TR/PTFs unknown. Customer data and inference must stay on premises on the internal network. This report accompanies the [implementation plan](../../docs/AS400_ENTERPRISE_IMPLEMENTATION_PLAN.md).

## Decision

The public-reference collection covers the principal documentation categories needed to design an IBM i ingestion pilot. **Ingestion and model training have not started.** This is not yet a complete customer knowledge base or an approved production corpus. More indiscriminate downloading cannot supply customer releases, business definitions, permissions, or actual programs.

Use the manifests and [verification report](IBM_COLLECTION_VERIFICATION.json) for exact counts, checksums, unavailable URLs and placeholders. File counts include notices, landing pages, examples and different editions, not just unique manuals. Original archives and extracted copies must not both become duplicate inputs.

Current verification: **4,263 manifest file records, 4,256 distinct local paths, and 4,082 distinct content hashes** across six collections. All recorded size/hash checks and 1,000 PDF-file-record parsing checks passed, with zero integrity errors. Repeated URLs/editions and identical content remain separately traceable; deduplication must preserve their provenance. Seven offline downloader regression tests also passed.

Core-manual checks found SQL reference, ILE RPG language/programming, ILE COBOL language/programming, CL concepts, DDS, and security-reference PDFs for each of the six IBM i catalog releases. This is 48 category/release coverage checks, not proof that every native API, command, PTF or product option is covered.

## Known public-source gaps

Thirteen IBM source URLs remain unavailable after retries and same-document IBM archive recovery:

| Group | Unavailable URLs | Treatment |
| --- | --- | --- |
| IBM i 7.2 Toolbox, Navigator Web tasks, job scheduler, performance, software maintenance | 9, including duplicate old/new URL forms | Keep failed links explicit; other editions and JTOpen references do not silently replace release-specific evidence |
| IBM i 7.6 catalog terms link | 1 | Retain document notices and available terms, but require rights review; older terms are not assumed equivalent |
| Legacy Power performance-capabilities reference | 1 | Revisit only if the actual hardware/performance scope requires it |
| Legacy Power system migration and partitioning PDFs | 2 | Record as unresolved; do not infer compatibility from another hardware release |

Eleven IBM landing snapshots have no downloadable manual link (including Web Query, geospatial, console and memo pages). Their retained HTML is not a claim of complete offline product documentation. Two unixODBC manual URLs are publisher placeholders and explicitly excluded from ingestion.

Legacy BookManager files are preserved but need a reviewed converter or corresponding PDF before use. Thirty-six macOS archive-metadata entries are not PDFs: earlier extracted copies were moved recoverably to the z/OS collection's `archive-metadata/`, and original ZIPs remain intact. None belong in document ingestion.

## Coverage and evidence boundaries

| Need | Public references | Gate before use |
| --- | --- | --- |
| Db2 for i SQL, catalogs, services, embedded SQL | [IBM i manuals](ibm-i-as400/README.md), SQL/PTF support matrix, IBM examples | Match release/TR/PTFs, schema, naming and business definitions |
| RPG, CL, DDS, ILE COBOL, IFS, native APIs | IBM i 7.1–7.6 catalog selections; selected CL/API HTML; RPG/400 and COBOL/400 references | Identify compiler/dialect, CCSID, source format, copy members and library context |
| Connectivity and OSS operations | [IBM OSS hub collection](ibm-i-open-source/README.md), ACS ODBC, JTOpen, Rust ODBC, PASE/toolkits | Test driver/server combination, TLS, identity and least privilege |
| Workflows and testing | [Community/tooling collection](ibm-i-community/README.md), TOBi, Code for IBM i, RPG grammar fixtures, iRPGUnit | Validate parser/compiler coverage; independent customer acceptance tests |
| Document extraction | [Engineering references](enterprise-engineering-reference/README.md): Docling, pypdf; Unicode | Local artifacts, bounded parsing, page/table fidelity tests |
| Retrieval and grounded answers | FTS5, PostgreSQL search/permissions/RLS, pgvector, sentence-transformers | Choose architecture; ACL filters, exact member search and citation tests |
| On-premises inference | Ollama, vLLM, llama.cpp, offline/security pages | Select hardware/model/license; disable external services and deny public egress |
| Agents, tools, security review | MCP, OWASP, Semgrep | Approvals, isolation, authorization, injection tests and honest scanner coverage |
| Identity, audit, analytics, delivery | [Web/standards collection](enterprise-web-reference/README.md): OIDC/OAuth, OpenTelemetry, NIST, SLSA, SPDX | Apply customer identity/retention policy; validate controls, not just collect guidance |
| Separately requested mainframe COBOL | [z/OS library](ibm-enterprise-cobol-zos/README.md), releases 3.1–6.5 | Exclude from IBM i default evidence: z/OS is not ILE COBOL on IBM i |

The topic scan covered 42 listed projects; 14 selected topic/gap-filling repository sets were downloaded. Another 14 engineering repository sets and 34 primary web/standards snapshots extend the IBM collections. These are bounded selections, not complete mirrors of every linked website.

## Findings that affect ingestion design

1. **Partition evidence.** Distinguish IBM i, customer-controlled evidence, z/OS, community projects, engineering docs, and existing PostgreSQL/T-SQL/MariaDB/DuckDB lessons. Carry platform, release, PTF applicability, language, revision, rights and authority metadata. Do not assume the newest downloaded edition matches the customer.
2. **Preserve provenance and fidelity.** Retain original bytes/hash, source/effective URL, title, fetch date, Git commit where relevant, page/heading or member/line spans, and extraction version. For IBM i source preserve library/file/member identity, source type, CCSID, fixed columns, sequence fields and copybook relationships. Converted text must map back to the original.
3. **Treat content as untrusted data.** Exclude Git internals, active agent packs, installers, binaries/save files, macOS resource forks, duplicate archive members, navigation-only pages and publisher placeholders. Never execute examples, macros, repository hooks, or embedded instructions. Sanitize HTML and block external asset fetches.
4. **Keep all processing local.** OCR, conversion, embeddings, reranking, inference, evaluation and scanners need approved internal artifacts/endpoints. Docling documents automatic model fetching and optional remote services; installation alone does not establish offline operation. Test with public egress denied, including error paths and telemetry. [Docling offline/remote options](https://docling-project.github.io/docling/usage/advanced_options/).
5. **Do not overstate scanner coverage.** Semgrep's matrix does not establish native RPG/CL/COBOL support. Track unsupported languages until separate analysis/compiler checks are validated; generic patterns do not prove semantic coverage. [Semgrep language list](https://docs.semgrep.dev/supported-languages).
6. **Decide rights explicitly.** Preserve publisher and nested repository notices. IBM publication terms, GPL/LGPL, permissive licenses and document-specific terms differ. Downloads and detected license labels do not authorize every retrieval, redistribution or fine-tuning use. Record approval per intended use; unreviewed sources stay outside the ingestion allowlist.
7. **Preserve permissions through derived content.** Propagate customer source/ticket ACLs to chunks, vectors, summaries, dependencies, caches, citations and exports. Missing/stale ACLs must deny access. Test separation, revocation/deletion and privileged roles that bypass database policies. Collecting security guidance does not implement these controls.

## What the internet cannot supply

| Customer input | Why it is required |
| --- | --- |
| IBM i release, Technology Refresh, PTF groups, compilers | Select applicable syntax, services and language behavior |
| Approved schema/catalog export and data dictionary | Generate queries without inventing tables or joins |
| “Open order” definitions, status/date conventions, ownership, library lists | Translate business intent into correct SQL |
| Representative RPG/CL/COBOL/DDS, copybooks, build options, dependencies | Explain real programs and test extraction/build assumptions |
| Technical docs/tickets with revision, classification, ownership and ACLs | Establish reliable, permission-aware knowledge |
| Identity, security, retention, redistribution and data-use approvals | Define permitted content and access boundaries |
| Inference hardware, model/license, internal artifact/update process | Establish capacity and genuinely on-premises operation |
| Reviewed questions, expected SQL/results, independent holdout programs | Measure correctness, citations, refusals and leakage |

## Gates for a controlled ingestion pilot

- [ ] Owner approves an explicit document allowlist and intended uses; restricted/unreviewed material stays excluded.
- [ ] Target release/PTFs and language variants are recorded; incompatible platforms/editions are filtered.
- [ ] Customer intake is authorized, secrets/PII handling agreed, ACL metadata complete.
- [ ] Isolated extraction is tested on PDFs, tables, fixed/free source, CCSIDs and copybooks; failed/empty results are quarantined.
- [ ] Provenance, deduplication, incremental updates, citations, deletion and permission revocation are tested.
- [ ] OCR/embedding/model/scanner artifacts and licenses are approved and internal; public egress and remote asset loading fail closed in tests.
- [ ] Retrieval passes independent customer holdouts, unauthorized-user probes, version conflicts and prompt-injection fixtures.
- [ ] Remaining unavailable links are reviewed against pilot scope; none are silently treated as ingested.

Passing these gates supports a bounded pilot under customer approval, not unrestricted production ingestion or fine-tuning. Begin with a small approved IBM i subset and customer fixtures, then expand based on measured gaps.

## Recheck the snapshot

From the project root run `python3 training/training_pipeline/verify_ibm_collections.py`. It checks recorded bytes/SHA-256, selected Git blob identities, IBM OSS checkout commits and PDF parsing with Poppler. It creates manual browsing indexes and `IBM_COLLECTION_VERIFICATION.json` for six new collections. This is integrity verification, not malware scanning, semantic extraction validation or a legal/compliance assessment. Older general SQL collections are outside this run.
