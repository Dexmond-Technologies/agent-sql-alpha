# Primary engineering documentation and standards

Collected on 2026-10-01: 34 publisher snapshots, comprising 29 HTML pages and five PDFs. Two HTML pages are unfinished publisher placeholders and must be excluded from ingestion. These references inform engineering decisions; they do not establish regulatory compliance or certification.

## Coverage

- Connectivity: unixODBC user manual and Rust ODBC guide.
- Retrieval/permissions: SQLite FTS5; PostgreSQL full-text search, ranking, privileges and row security.
- Text fidelity: Unicode normalization; preserve original source bytes and identifiers.
- Local operation: Docling offline artifacts/remote-service controls, Ollama local/cloud controls, vLLM security/usage statistics.
- Security scanning: Semgrep language coverage, CE deployment, CLI and telemetry.
- Identity: OpenID Connect Core and OAuth security best current practice, RFC 9700.
- Governance: NIST AI RMF, Generative AI Profile, SSDF and generative-AI secure-development practices.
- Internal analytics: OpenTelemetry security, sensitive-data handling and collector configuration.
- Supply chain: selected SLSA 1.2 pages and the SPDX 3.0.1 specification.

[INDEX.tsv](INDEX.tsv) lists titles/paths. [manifest.json](manifest.json) records source/effective URLs, timestamps, hashes, byte counts, categories, status and exclusions. `/current/` and `/latest/` URLs are dated snapshots, not compatibility guarantees for the eventual deployment.

## Gaps and safety boundaries

The unixODBC administrator/programmer manual pages state that they are unfinished. Their snapshots document that gap; they are not substantive manuals. The user manual, Rust guide and IBM ODBC references are available in the combined corpus.

The [Semgrep language matrix](https://docs.semgrep.dev/supported-languages) does not establish native RPG/CL/COBOL coverage. Generic matching is not equivalent to a language-aware analyzer. Report unsupported languages as unscanned until an alternative is validated.

HTML retains external scripts/assets: extract or sanitize it in an isolated process instead of rendering it directly in the application. Privacy/security settings described here have not been configured by this download task. Retained publisher notices require rights review for ingestion, redistribution or training. No ingestion or fine-tuning has started.

## Reproduce and verify

```sh
python3 training/training_pipeline/download_engineering_pages.py
python3 training/training_pipeline/verify_ibm_collections.py
```

Run from the project root. Successful snapshots are reused by checksum; conflicting replacements are not silently overwritten. Downloads do not install the described products.
