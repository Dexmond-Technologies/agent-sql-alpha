# agentSQL 0.0.1 Alpha

This is the first public test build of agentSQL by Dexmond Technologies for Windows and Linux.

## Qwen integration upgrade

- Dedicated Qwen3-Coder-30B-A3B provider with exact model verification, real server-side token budgeting, bounded schema/result context, optional reviewed evidence, and rejection of incomplete responses.
- Pinned FP8 model/vLLM deployment, authenticated TLS gateway, and a script that records real endpoint timings/token usage without inventing measurements.
- Operator-run IBM i ODBC catalog export and bounded base-table reads, plus desktop import as a dated Db2 for i source snapshot. This is not a live IBM i desktop execution adapter.
- Explicit Windows/macOS/Linux credential-store features; previous builds without them used keyring's in-memory mock backend.
- Qwen browser connection/testing requests fail explicitly. Existing browser examples remain available and are labelled synthetic.
- Existing database/provider features, profiles, conversations and SQL execution controls are preserved. GPU/IBM i production acceptance and installer signing still require the recipient's environment and credentials.

## Included

- SQLite connection profiles and live schema introspection.
- Natural-language SQL drafting with configurable AI providers.
- Plan / Grill, Chat, and Direct generation interaction modes with slash commands.
- In-app provider setup and connection testing for OpenAI, DeepSeek, Google Gemini, Anthropic Claude, Ollama, and LM Studio models.
- Searchable Help centre with guided connection, querying, privacy, and troubleshooting tutorials.
- Project-folder analysis for source-derived database structures.
- Live SQLite, PostgreSQL, MySQL, and SQL Server connection, schema-introspection, read, and controlled-change adapters.
- Safe auto-detection for server profiles through a `SELECT 1` handshake.
- Read-only-by-default profiles plus opt-in INSERT, UPDATE, DELETE, MERGE, DDL, procedure, permission, and maintenance execution.
- Exact one-statement classification and a typed `EXECUTE` confirmation for every non-read operation.
- Configurable TLS verification modes, a 60-second timeout, and a 10,000-row result cap.
- Persistent conversation history with a selector for reopening prior chats and automatic restoration of the last workspace.
- Collapsible query-output cards with durable execution rows, clipboard copy, native JSON export, and confirmed card removal that preserves chat messages.
- Local chat and query history with operating-system credential storage.
- Synthetic core-banking database fixture for live testing.
- Offline Windows setup with the WebView2 runtime installer, complete documentation, third-party inventory, and curated core-banking example files included.
- Start-screen action to load the packaged banking database and a navigation action to open installed examples and documents.
- Versioned architecture, data-handling, and complete locked-dependency/license documentation.

## Packages

- Windows: MSI installer.
- Linux: Debian package and AppImage.

## Alpha limitations

- Server adapters are alpha-quality and require integration verification against the organization's supported PostgreSQL, MySQL, and SQL Server versions before production use.
- Rich catalog metadata beyond tables, views, columns, nullability, and primary-key markers is not yet normalized for server engines.
- Packages remain unsigned until Dexmond Technologies supplies an organization code-signing certificate and private key. Setting a publisher label alone cannot establish a trusted Windows signature.
- Query results retained in output cards are stored in the local SQLite history database, which is not yet application-level encrypted at rest.

Use synthetic/non-production data and least-privilege database accounts while evaluating this alpha. Write-enable a profile only when the connected account, backups, and change-approval process are appropriate.
