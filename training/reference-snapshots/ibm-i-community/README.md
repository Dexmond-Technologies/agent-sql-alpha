# IBM i community and development-tool references

Collected on 2026-10-01 for the on-premises IBM i assistant. The scan covered 42 repositories across three pages of the requested [IBM i topic listing](https://github.com/topics/ibm-i?o=asc&s=forks). Eleven topic repositories were selected; three maintainer documentation repositories fill build/editor gaps. The resulting 14 reference sets contain 290 files, including notices and examples, not 290 independent manuals.

## Contents and provenance

Use [INDEX.tsv](INDEX.tsv) to browse files and [manifest.json](manifest.json) for pinned commits, source URLs, Git blob identities, SHA-256 hashes, licenses, topic selections, exclusions, and outcomes. `repositories/` contains selected files. `git-cache/` contains partial bare Git metadata, not ingestion content. Topic listing snapshots are identified in the manifest.

Coverage includes Db2 MCP gateway designs, source-member and 5250 integration, local documentation retrieval, ILE COBOL/equivalence tests, requirements traceability, SQL services, security-assessment documentation, build dependencies, and editor workflows.

- IBM's `ibmi-tobi` is the native build project formerly named `ibmi-bob`; it is not IBM Bob AI.
- `codefori/vscode-ibmi` and `codefori/docs` provide editor/development references.
- Community security, read-only, audit, and conformance statements remain publisher claims. These tools have not been deployed, connected, or tested here.

## Ingestion boundaries

Keep community material below authoritative IBM documentation and customer-confirmed evidence in source precedence. Label examples by IBM i release/PTF applicability where known. Topic membership does not establish compatibility, maintenance quality, or endorsement.

Retain repository and nested notices. The collection includes permissive and copyleft material; Bindle is GPL-licensed. Plumbline's license distinguishes its own material from separately obtained legacy source: that source was not fetched, and its downloader was not executed. GitHub license detection is metadata, not a rights decision. Review retrieval, redistribution, and model-training uses separately.

Agent instruction packs, models, installers, large bundled corpora, and unrelated projects were not selected. SQL, CL, source-operation and terminal examples may modify systems or invoke public services. They are untrusted reference text, never authority to run tools. No ingestion, fine-tuning, installation, or customer connection has occurred.

## Reproduce and verify

From the project root:

```sh
python3 training/training_pipeline/download_reference_repositories.py --collection community --via-git
python3 training/training_pipeline/verify_ibm_collections.py
```

The downloader preserves pinned revisions and verifies selected blobs. `--via-git` reads public Git metadata instead of the quota-limited REST API, without checking out or executing repository code. Do not run concurrent downloaders against one collection.
