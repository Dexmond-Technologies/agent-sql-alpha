# Enterprise engineering references

Collected on 2026-10-01. Fourteen project-maintained reference sets contain 1,473 selected files, including licenses, examples, and specifications. This is a bounded selection, not a complete mirror or an approved dependency stack.

## Coverage

| Area | Projects | Intended use |
| --- | --- | --- |
| Connectivity | IBM JTOpen, Rust `odbc-api` | JDBC/native access and Rust ODBC; validate the actual driver/server combination |
| IBM i language/testing | rpgleparser, Code for IBM i RPG extension, iRPGUnit | Fixed/free RPG parsing, editing, and native testing |
| Extraction | Docling, pypdf | Local document/table extraction, parser limits, page evidence, offline artifacts |
| Local inference | vLLM, Ollama, llama.cpp | Internal serving options; model weights not included |
| Retrieval | sentence-transformers, pgvector | Embeddings, reranking, evaluation, vector indexing |
| Tool integration | Model Context Protocol | Versioned transport, identity, tool and security specifications |
| Security | OWASP Cheat Sheet Series | RAG, prompt injection, MCP, SQL/command injection, uploads, secrets, authorization, logging, deployment |

[INDEX.tsv](INDEX.tsv) lists files. [manifest.json](manifest.json) records commits, Git blob hashes, SHA-256, purposes, notices, and outcomes. Do not index `git-cache/`.

## Limits

These are implementation references, not authority for Db2 for i syntax or customer business logic. Public parser fixtures are development fixtures, not independent customer acceptance tests. Measure language coverage against actual fixed/free RPG, embedded SQL, copybooks, and compiler options.

Examples may describe cloud services, online model downloads, telemetry, or remote OCR. They are not approved deployment patterns. Stage reviewed dependencies and model artifacts internally, then test with public egress denied. No packages, models, containers, or downloaded examples were installed or executed.

Every selected repository retains license material, including iRPGUnit's nested LGPL/copyright files. `review-retained-license` means automated license identification was not used, not that rights are absent or approved. Review document-specific and nested terms separately. Public availability is not a blanket fine-tuning or redistribution license.

Agent instruction packs, model binaries, and oversized example datasets are excluded. No collection is automatically added to training or retrieval.

## Reproduce and verify

```sh
python3 training/training_pipeline/download_reference_repositories.py --collection engineering --via-git
python3 training/training_pipeline/verify_ibm_collections.py
```

Run from the project root. Successful snapshots preserve pinned commits; refreshing to a newer upstream revision is a separate reviewed update.
