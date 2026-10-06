# IBM i technical reference collection

The client has confirmed IBM i; the exact release and PTF levels remain unknown. This collection gathers English IBM documentation for the proposed agentSQL integration and keeps IBM i 7.1 through 7.6 references distinct. The existing folder name retains the earlier AS/400 terminology, but the target platform is IBM i.

## Scope

Manuals are selected from IBM's release-specific PDF catalogs for Db2 for i, SQL, embedded SQL, RPG, ILE COBOL, CL, DDS, native APIs, IFS, connectivity, security, operations, availability, and migration. The collection also includes relevant IBM support references, modernization Redbooks, older RPG/400 and COBOL/400 references, and a small set of IBM Bob capability-benchmark pages. It is not a mirror of all IBM websites.

- `documents/<catalog-release>/en/`: downloaded manuals and attachments.
- `pages/<catalog-release>/en/`: catalog, print-link, support, native API, CL command, and other HTML snapshots.
- `sources/`: original catalog snapshots used during discovery.
- `manifest.json`: URLs, titles, subjects, catalog-release references, publisher release where identifiable from the URL, hashes, download status, exclusions, and discovery warnings.

Use the manifest for the current download counts and any unavailable links. A catalog can refer to an older manual, and a shared manual can appear in several release catalogs. The directory is the first catalog reference, not proof of the manual's publication release. Check `publisher_release_from_url`, all `references`, and the document itself before selecting evidence.

The 2026-10-01 snapshot has 1,350 downloaded resource records (730 PDF and 620 HTML) and 13 unavailable source URLs. Shared mirror targets produce 1,343 distinct local paths. All downloaded records passed checksum/size verification and PDF parsing where applicable. Browse [INDEX.tsv](INDEX.tsv); see [pre-ingestion readiness](../INGESTION_READINESS.md) for unresolved subjects and customer-input gates. Eleven landing pages retain HTML only, with no downloadable-manual link found.

IBM's current API and CL PDFs cover overview/concept material, not every individual API or command. Selected native source/object APIs and build-related CL commands are therefore also saved as HTML. HTML pages are content snapshots, not complete offline mirrors of interactive IBM portals.

Snapshots can retain publisher scripts and external asset links. Extract or sanitize their content before displaying it inside an internal application; do not treat downloaded HTML or code examples as trusted instructions.

## Platform and usage boundaries

Use this collection for IBM i. Keep the separately requested `../ibm-enterprise-cobol-zos/` collection tagged as z/OS; its compiler/runtime and operating-system guidance is not a substitute for ILE COBOL on IBM i. Treat IBM Bob pages as a capability benchmark, not an implementation dependency or evidence of product parity.

Original IBM copyright and document-specific terms are retained. Downloading the documents does not establish permission to distribute them outside the enterprise or use them for model fine-tuning. This collection is not automatically added to the existing training preparation or search pipeline.

## Resume and verify

From `agent-sql-alpha`, run `python3 training/training_pipeline/download_ibmi.py`. Requirements are Python 3, curl, BeautifulSoup, and lxml. The downloader resumes existing files, validates PDF signatures, records SHA-256 hashes, and retains failed links explicitly. Do not start two instances against the same collection simultaneously.

Companion open-source documentation and reference examples are in `../ibm-i-open-source/`, with their own commits, hashes, and licenses.
