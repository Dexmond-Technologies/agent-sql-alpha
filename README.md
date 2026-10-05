# agentSQL

agentSQL is a Dexmond Technologies cross-platform desktop workspace for asking questions about SQL databases in natural language, reviewing generated SQL, and explicitly executing approved statements. Every connection starts read-only; authorized users can opt a profile into controlled DML, DDL, procedure, permission, and maintenance execution.

## What is included

- A Tauri + React desktop interface for connection profiles, schema exploration, persistent conversation history, SQL review, and tabular results.
- Three interaction modes: Plan / Grill for requirements discovery, Chat for discussion without query generation, and Direct generation for unambiguous requests. The same modes are available through `/plan`, `/chat`, `/direct`, `/generate`, and `/remarks` commands.
- A persistent query-output workspace. Every generated query can be selected, collapsed, copied, exported as JSON, executed, and retained with its result metadata and rows. Closing an output requires confirmation and does not delete the originating chat message.
- A native persistence store in the operating-system application-data folder. Database passwords are stored separately in the OS credential vault; the local SQLite history store never contains them.
- A provider boundary with OpenAI, DeepSeek, Anthropic, Gemini, Ollama, and LM Studio requests. On first run the app writes a `.env` template to its application-data directory. Copy the values from [`.env.example`](.env.example) and configure the selected provider there.
- A model-independent SQL gate. Read-only profiles permit one `SELECT`/safe `WITH`, plain `EXPLAIN`, or approved metadata statement. Write-enabled profiles also classify DML, DDL, procedures, permission changes, and maintenance, then require a typed `EXECUTE` confirmation for every statement. Stacked statements, manual transaction control, and external file/database operations remain blocked.
- Functional SQLite, PostgreSQL, MySQL, and SQL Server drivers for connection testing, schema discovery, execution, a 10,000-row cap, 60-second timeout, and durable result history. Auto mode probes the three server engines with a safe `SELECT 1` handshake.
- A project-folder mode that infers relational structure from `.sql` migrations and Prisma `.prisma` models, recognizes Chroma collections referenced in Python and JavaScript/TypeScript source, and reads collection names from a local `chroma.sqlite3` catalog in read-only mode. It stores only normalized object metadata and relative source-file names locally. Source files and `.env` files are never sent to the AI provider. The inferred structure is shared when you chat.

## Run locally

Install Node.js 20+ and Rust (via `rustup`), then:

```powershell
npm install
npm run tauri dev
```

For a distributable build, use `npm run tauri build`. Tauri produces the platform-appropriate installer; release signing requires the relevant Windows/macOS/Linux signing credentials.

## Windows installer contents

The MSI is built as an offline evaluation package. It embeds the Microsoft WebView2 offline installer, so the user interface does not need to download that runtime during setup. Rust, the database drivers, SQLite, and the application libraries are compiled into the agentSQL executable.

The installation also includes a curated `documentation` folder and `examples/core-banking` folder. The example contains the ready-to-use 12,000-entry SQLite database, schema, generator, verifier, prompts, golden catalogs, and safe/blocked query examples. The reproducible 250,000-entry generated database and Python cache files are deliberately excluded to keep the MSI manageable.

Use **Load banking example** on the start screen to copy the packaged SQLite fixture into the user's private application-data directory and connect it. Use **Examples & documents** in the navigation to open all installed supporting files.

## Conversations and query outputs

Chat sessions, messages, interaction mode, sharing preference, generated-query cards, collapse state, and executed result rows are stored in the app-private SQLite database. The conversation selector reopens older chats, and agentSQL restores the most recently selected connection and conversation on launch.

Generated queries never execute automatically. Selecting an output card loads its query into the current editor. `Run current query` or `Review & execute` passes the current text—not the model's original text—through the independent SQL gate. Any non-read statement requires a second modal review and the exact phrase `EXECUTE`. If edited text differs from the selected saved query, execution creates a new manual output so the earlier artifact is preserved.

`Copy` copies query text to the system clipboard. `Export` opens a native save dialog and writes a JSON document containing the query, timestamps, status, and any stored rows. `Close` removes only that output and its retained rows after confirmation; the assistant response remains in chat. Deleting the whole chat removes its messages and all attached outputs.

## Database support status

The application exposes a common `DatabaseDriver` boundary for PostgreSQL, MySQL, SQL Server, and SQLite. All four are connected end to end in the alpha. PostgreSQL and MySQL use SQLx with Rustls; SQL Server uses Tiberius with Rustls. The normalized alpha catalog currently covers tables, views, columns, nullability, and primary-key markers; richer foreign-key, index, trigger, generated-column, and view-definition metadata remains on the roadmap.

Keep ordinary analysis profiles read-only and use server-side read-only accounts. If a change profile is required, use a separate least-privilege account constrained to the intended schemas and operations. The application gate and typed confirmation are workflow controls, not substitutes for database authorization, backups, change approval, or maker/checker controls.

TLS defaults to server identity verification. “Require encryption, trust certificate” is intended for controlled test environments with private/self-signed certificates; disabling TLS is for isolated local testing only.

## Core banking test fixture

[`fixtures/core-banking`](fixtures/core-banking/README.md) contains a deterministic synthetic banking database for exercising live SQLite introspection, project-source inference, complex read queries, SQL blocking, and the 10,000-row result cap. A ready-to-open 12,000-entry database is included, and the same generator can create a 250,000-entry local profile.

## Privacy

Schema data and chat messages are sent to the selected AI provider to formulate an answer. Query results are also sent by default for the active chat; the `Stop sharing results` control persists per chat. History is local-only and can be deleted from the chat header. Query results retained in output cards are stored in the local history database so they survive restarts. This alpha does not encrypt that SQLite history file at rest; banking deployments must apply endpoint encryption, access control, retention policy, and secure deletion requirements before production use.

Project analysis reads supported `.sql`, `.prisma`, Python, JavaScript/TypeScript, and dependency-manifest text files. It skips common dependency/build directories, hidden/secret files, and symlinks, and is bounded to 1,000 files / 16 MB. Inferred structure can be incomplete or stale; re-analyze after source changes. Chroma collection names may be dynamic, and record metadata is not a fixed SQL schema.

Chroma support currently means source recognition and **read-only query drafts**, not a live Chroma connection or execution. agentSQL never runs generated Chroma code. The `Run current query` action remains disabled for all project-source profiles. Chroma's documented read APIs are `query` and `get`; collection creation and record mutation are outside this version's scope. See [Chroma's query documentation](https://docs.trychroma.com/docs/querying-collections/query-and-get).

## DeepSeek configuration

Set `AI_PROVIDER=deepseek`, then add `DEEPSEEK_API_KEY` to the app-data `.env` file generated by agentSQL. The default model is `deepseek-flash` and the default endpoint is `https://api.deepseek.com`; both can be overridden with `DEEPSEEK_MODEL` and `DEEPSEEK_BASE_URL`. Do not place the key in the browser-demo page or commit it to the repository.

## LM Studio configuration

Choose **LM Studio (local)** in agentSQL and select **Connect LM Studio**. agentSQL first detects an existing server and its configured port through LM Studio's bundled `lms` helper. If the server is stopped, agentSQL starts it bound to `127.0.0.1`, waits for it to become ready, discovers available models, and selects one. LM Link computer names do not need to be entered. No token is required by default; if authentication is enabled in LM Studio, paste its API token or set `LMSTUDIO_API_KEY` in the app-data `.env` file.

## Technical and compliance documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) describes the application boundaries, persistence model, query lifecycle, providers, and safety controls.
- [`docs/DATA_HANDLING.md`](docs/DATA_HANDLING.md) documents local and provider data flows, deletion semantics, and banking deployment considerations.
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) inventories all locked JavaScript and Rust dependencies plus bundled third-party assets, with license and version status.
- [`docs/WINDOWS_SIGNING.md`](docs/WINDOWS_SIGNING.md) describes the organization-validated MSI signing workflow and certificate prerequisite.

## Private Qwen and IBM i catalog snapshots

Choose **Qwen (private server)** to use a real vLLM endpoint serving Qwen3-Coder-30B-A3B. The dedicated adapter verifies the exact model, counts tokens using the server's tokenizer, bounds schema/result context, and rejects incomplete answers. Remote servers require authenticated HTTPS; there is no alternate-provider fallback. The browser demonstration cannot test or use Qwen and remains explicitly labelled as synthetic.

[`deployment/qwen`](deployment/qwen/compose.yaml) contains the pinned FP8 model/runtime configuration and a TLS gateway. [`tools/ibmi`](tools/ibmi/connector.py) supplies a real operator-run ODBC catalog exporter and bounded base-table reads. **Import IBM i catalog snapshot** enables Db2 for i drafting against the dated export. It does not add a live IBM i desktop driver; execution remains disabled for imported snapshots.

See [`docs/QWEN_DEPLOYMENT.md`](docs/QWEN_DEPLOYMENT.md) for setup, prerequisites, actual endpoint measurement, evidence handling and unresolved production acceptance requirements. OS credential-store backends are now explicitly enabled; vault access still needs validation on each delivery platform. GPU performance, IBM i interoperability and IBM certification are not established by this repository upgrade.
