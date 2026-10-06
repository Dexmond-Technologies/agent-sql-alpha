# Training catalog

Original SQL collections were downloaded on 2026-09-22; IBM i and enterprise
additions below were collected on 2026-10-01. Sparse selections contain only the
listed material. Pinned reference snapshots are not automatically ingested.

Before ingestion, read [INGESTION_READINESS.md](INGESTION_READINESS.md) and the
[six-collection integrity report](IBM_COLLECTION_VERIFICATION.json).

## General and course material

### SQL 101

- Local: `SQL-101/`
- Source: <https://github.com/s-shemmee/SQL-101>
- Revision: `05ec3bf9dfb137c4c2c4c3e348c93ca8c7a23974`
- Focus: beginner concepts, examples, exercises, and two PDF note sets.
- Dialect: broadly portable SQL, with introductory setup notes for several
  database systems.

### SQL Ultimate Course

- Local: `sql-ultimate-course/`
- Source: <https://github.com/DataWithBaraa/sql-ultimate-course>
- Revision: `7896d4a34c620ab8b73a7c607d86975cd7945642`
- Focus: course PDFs, SQL scripts, CSV datasets, optimization, analytics, and
  projects.
- Dialect: primarily Microsoft SQL Server/T-SQL.

## Official PostgreSQL documentation

- Local: `postgresql-docs/doc/src/sgml/`
- Source: <https://github.com/postgres/postgres/tree/master/doc/src/sgml>
- Revision: `77f54eb07488341025073a370f6e381a6ee05e04`
- Scope: complete official PostgreSQL manual source, including tutorial, SQL
  language, administration, indexes, performance, replication, PL/pgSQL, and
  bundled extensions.
- Format: DocBook SGML source.
- Suggested entry: `postgresql-docs/doc/src/sgml/tutorial.sgml`.

## Official Microsoft material

### Transact-SQL reference

- Local: `microsoft-sql-docs/language-reference.md`
- Source: <https://github.com/MicrosoftDocs/sql-docs/blob/live/docs/t-sql/language-reference.md>
- Focus: entry point for the Microsoft T-SQL reference.

### ODBC SQL overview

- Local source: `microsoft-learn-odbc-sql/sql.md`
- Local rendered snapshot: `microsoft-learn-odbc-sql/sql.html`
- Source: <https://learn.microsoft.com/en-us/cpp/data/odbc/sql?view=msvc-170>
- Focus: SQL use through Microsoft C++ ODBC.

### SQL Server samples

- Local: `sql-server-samples/samples/`
- Source: <https://github.com/microsoft/sql-server-samples>
- Revision: `beaab06ef72831089ca80e5355d65e661fd19b26`
- Included: `databases/`, `features/`, `tutorials/`, and `demos/`.
- Focus: official sample databases and applied SQL Server/Azure SQL examples.

## Official MariaDB documentation

- Local: `mariadb-docs/server/`
- Source: <https://github.com/mariadb-corporation/mariadb-docs>
- Revision: `1a89bd3d6cf9678ae16dd73d84bfa26024d9e24d`
- Included: quick-start guides, data types, SQL functions, SQL statements, SQL
  structure, basics, stored routines, triggers/events, and views.
- Format: Markdown.

## Official DuckDB documentation

- Local: `duckdb-docs/docs/current/`
- Source: <https://github.com/duckdb/duckdb-web>
- Revision: `6d978b5fb075d31c66d02b88f2f3984dfbc49a40`
- Included: current documentation, especially `docs/current/sql/`.
- Focus: analytical SQL, data ingestion, functions, and DuckDB-specific syntax.
- Format: Markdown and supporting documentation assets.

## IBM Enterprise COBOL for z/OS

- Local: `ibm-enterprise-cobol-zos/`
- Source: [Enterprise COBOL for z/OS documentation library](https://www.ibm.com/support/pages/enterprise-cobol-zos-documentation-library).
- Download date: 2026-10-01.
- Scope: all listed releases from 3.1 through 6.5, English and Japanese manuals, original ZIP bundles, legacy BookManager files, and linked supporting documents.
- Platform: z/OS; keep distinct from AS/400 and IBM i compiler/runtime documentation.
- Inventory and download status: `ibm-enterprise-cobol-zos/manifest.json` records each source URL, file hash, release/language context, and any unavailable resource.
- Entry point and resume instructions: `ibm-enterprise-cobol-zos/README.md`.
- Rights: IBM copyright and document-specific terms; not automatically eligible for fine-tuning.

## IBM i technical manuals

- Local: `ibm-i-as400/` (IBM i is the confirmed customer platform; release unknown).
- Sources: IBM i 7.1–7.6 PDF catalogs, IBM support references, and IBM Redbooks.
- Scope: English Db2 for i, SQL, RPG, CL, ILE COBOL, DDS, native APIs, IFS, connectivity, security, operations, and modernization references; selected IBM Bob benchmark pages.
- Provenance, download status, exclusions and warnings: `ibm-i-as400/manifest.json`.
- Usage and resume instructions: `ibm-i-as400/README.md`.
- Rights: original IBM terms retained; not automatically eligible for fine-tuning or external redistribution.

## IBM i open source documentation and examples

- Local: `ibm-i-open-source/`.
- Starting point: [IBM i Open Source Resources](https://ibm.github.io/ibmi-oss-resources/).
- Scope: 11 repositories with 644 checked-out files, plus 92 documentation HTML snapshots; PASE, internal RPM mirrors, SSH/TLS, ODBC, Python/Node.js, SQLAlchemy, XMLSERVICE, deployment and selected integration examples.
- Repository commits, per-file hashes, notices, URLs and outcomes: `ibm-i-open-source/manifest.json`.
- Usage and resume instructions: `ibm-i-open-source/README.md`.
- No downloaded code was installed or executed; sources are not automatically indexed or included in fine-tuning.

## IBM i community and development tooling

- Local: [ibm-i-community](ibm-i-community/README.md).
- Discovery: 42 repositories on the requested topic listing; 11 selected plus three build/editor supplements.
- Downloaded: 14 reference sets, 290 files including licenses/examples.
- Coverage: local retrieval, Db2/source/5250 tool designs, ILE COBOL, traceability, SQL services, native builds, editor workflows and security-assessment references.
- Provenance: pinned commits, hashes, source links, selections/exclusions and notices in `manifest.json`; browse `INDEX.tsv`.
- Community claims remain unverified; no tools installed or connected to IBM i.

## Enterprise implementation references

- Local: [enterprise-engineering-reference](enterprise-engineering-reference/README.md).
- Downloaded: 14 project-maintained reference sets, 1,473 files including licenses and selected public test/parser fixtures.
- Coverage: JTOpen/Rust ODBC, RPG parsing/testing, Docling/pypdf, local inference, embeddings/reranking, pgvector, MCP and OWASP.
- Engineering options, not a selected stack or IBM i dialect authority.
- Commits, selection scope, hashes and notices: `manifest.json`; browse `INDEX.tsv`.

## Primary engineering web documentation and standards

- Local: [enterprise-web-reference](enterprise-web-reference/README.md).
- Downloaded: 34 snapshots including five PDFs; two unfinished unixODBC placeholders marked for exclusion.
- Coverage: ODBC, FTS5/PostgreSQL search/permissions, Unicode, offline/telemetry controls, Semgrep, OIDC/OAuth, NIST, OpenTelemetry, SLSA and SPDX.
- Source URLs and outcomes: `manifest.json` and `INDEX.tsv`.
- Reference standards do not establish certification; rights/applicability require review.

## Updating

Review changes before updating the older course/general SQL clones. New collections
use manifests and scripts documented in their READMEs. Preserve pinned commits and
hashes; upstream revision updates are separate reviews, not automatic ingestion.
