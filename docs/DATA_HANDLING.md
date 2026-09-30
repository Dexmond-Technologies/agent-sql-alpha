# agentSQL Data Handling and Retention

## Purpose

This document describes the 0.0.1-alpha implementation. It is an engineering record, not a certification or a substitute for a bank's data-protection, outsourcing, operational-resilience, or cryptographic-control assessment.

## Data categories and locations

| Data | Local location | Sent to an AI provider? |
|---|---|---|
| Connection name, engine, host, database, user name, TLS mode, write-enable policy, and paths | App-private SQLite database | Relevant normalized schema identifiers may be included in prompts |
| Database password | Operating-system credential vault | No |
| AI API key | App-data `.env` file | Used as request authentication; not added to prompts or history |
| Normalized schema and inferred collection metadata | App-private SQLite database | Yes, when chatting |
| Raw project source and `.env` files | Read locally within scanner bounds; not persisted as raw source | No |
| Chat messages | App-private SQLite database | Yes, as conversation context |
| Generated query text | Chat message and query-output record | Yes, as conversation context |
| Executed result rows | Query-output record in app-private SQLite | Only when per-chat result sharing is enabled and a later prompt includes the current result |
| Minimal execution history | App-private SQLite database | No direct provider transmission |
| Theme, panel sizes, last profile/session | WebView localStorage | No |

## Retention and deletion semantics

- History is retained until the user removes it; there is no automatic expiry in this alpha.
- Closing an output card deletes that output's query copy and serialized result rows after confirmation. The assistant message that originally contained the query remains in chat.
- Deleting a conversation cascades to all messages and output cards for that conversation.
- Deleting a profile cascades to its schema cache, conversations, outputs, and execution history, and requests deletion of its credential-vault entry.
- SQLite deletion does not guarantee immediate physical erasure from database pages, WAL files, filesystem snapshots, backups, or endpoint telemetry. Production policy must define secure-erasure and backup-retention controls.
- Export creates a user-selected JSON file outside agentSQL's managed history. agentSQL cannot revoke or delete that copy automatically.

## Provider controls

Result sharing is enabled per conversation by default in the current alpha and can be disabled from the chat header. The control determines whether the current result is included in subsequent provider requests; it does not alter local persistence. Schema names and conversation text are still sent to the configured provider. Provider terms, regional processing, retention, training controls, and subprocessors must be reviewed before use with bank data.

Ollama and LM Studio are intended for local inference through loopback interfaces. Their own model files, logs, extensions, authentication, and remote-access settings remain outside agentSQL's control and must be secured separately.

## Current alpha gaps for banking production

- The local history SQLite database is not application-level encrypted at rest.
- There is no enterprise identity, role-based access control, maker/checker approval, centralized policy, immutable audit export, rollback orchestration, or retention scheduler.
- Exported files are not automatically encrypted, signed, watermarked, or classified.
- Provider requests do not yet include configurable redaction, tokenization, field-level policies, or data-loss-prevention approval.
- Installer signing and a formal secure software-development lifecycle evidence pack are not complete.
- PostgreSQL, MySQL, and SQL Server live adapters are alpha-quality and have not completed the target bank's compatibility, failover, TLS/PKI, and production-hardening matrix.

Before deployment, use managed full-disk encryption, endpoint access control, OS account separation, restrictive file permissions, separate least-privilege read/change database principals, database-native auditing and change approval, outbound network allow-listing, approved model/provider tenancy, centralized audit collection, tested backup/rollback/deletion policy, signed installers, SBOM/vulnerability scanning, and the organization's required Italian/EU regulatory review.

## Incident and support evidence

Do not send production database files, API keys, passwords, or unredacted query results in support tickets. Collect application version, operating system, database engine, sanitized query shape, error text, and reproducible synthetic data instead. The bundled core-banking fixture is intended for this purpose.
