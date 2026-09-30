# agentSQL Architecture

## Scope

agentSQL 0.0.1-alpha is a Tauri 2 desktop application with a React/TypeScript interface and a Rust core. SQLite, PostgreSQL, MySQL, and SQL Server are implemented behind a common live-driver boundary. Connections are read-only by default; a profile can explicitly opt into controlled data and schema changes. Project-folder analysis remains advisory and never executes inferred SQL or Chroma code.

## Application boundaries

| Layer | Responsibility |
|---|---|
| React interface (`src/`) | Profiles, schema explorer, persistent conversations, interaction modes, current query editor, output cards, result tables, settings, and Help |
| Frontend API (`src/api.ts`) | Typed boundary for Tauri commands and a localStorage-backed browser demonstration |
| Tauri command layer (`src-tauri/src/lib.rs`) | Input routing, application-data initialization, credential-vault coordination, provider calls, native export, and state locking |
| Storage (`storage.rs`) | App-private SQLite schema, migrations, normalized schema cache, chat history, query outputs, and execution history |
| Drivers (`drivers.rs`, `network.rs`) | SQLite, PostgreSQL, MySQL, and SQL Server connection, introspection, bounded reads, and confirmed changes behind the driver abstraction |
| SQL safety (`safety.rs`) | Independent one-statement classification, read-only default, elevated allow-list, external-I/O rejection, and confirmation requirement |
| Providers (`providers.rs`) | OpenAI, DeepSeek, Gemini, Anthropic, Ollama, and LM Studio configuration, request translation, mode prompts, and response gates |
| Source analysis (`source.rs`) | Bounded local inference from SQL, Prisma, supported code, and Chroma catalog metadata |

## Persistent data model

The app-private database is created in the operating system application-data directory. Foreign keys and WAL mode are enabled.

| Table | Purpose | Deletion behavior |
|---|---|---|
| `profiles` | Non-secret database and project profile metadata | Deleting a profile cascades to its schema, chats, messages, outputs, and execution history |
| `schema_cache` | Normalized schema snapshot used by the UI and provider prompt | Cascades with profile |
| `chat_sessions` | Title, profile, result-sharing choice, interaction mode, and creation time | Deleting a chat cascades to messages and outputs |
| `chat_messages` | User and assistant content plus extracted SQL marker | Cascades with chat |
| `query_outputs` | Durable generated/manual query, source message link, optional serialized result, collapse state, and timestamps | May be removed independently while its chat message remains |
| `query_history` | Minimal record of SQL that was explicitly executed | Cascades with profile |

Database credentials are not stored in these tables. They are written to the operating-system credential vault through `keyring`. Provider keys are held in the user-managed app-data `.env` file.

## Conversation lifecycle

1. Selecting a connection loads its cached schema and conversation list.
2. The last selected conversation for that profile is restored from a local UI preference; otherwise the newest conversation is opened.
3. Messages and query outputs are loaded in parallel from native storage.
4. The first user prompt becomes the durable conversation title.
5. Plan / Grill asks focused questions and suppresses executable blocks. Chat discusses the schema without query generation. Direct returns one draft when the request is sufficiently clear; the prompt policy reflects the selected profile's read-only or write-enabled state.
6. A fenced query in a Direct response is saved as a `query_outputs` record linked to the assistant message. Removing that output never mutates the message.

## Query and result lifecycle

1. A generated or selected output is loaded into the current editor.
2. The user may edit the text. Nothing executes automatically.
3. `Run current query` or `Review & execute` sends the current text to the Rust classifier.
4. The safety gate validates exactly one recognized statement. Reads may proceed; any non-read statement requires both profile opt-in and a fresh typed `EXECUTE` confirmation over the exact SQL.
5. The selected driver enforces the timeout and returns either bounded JSON-compatible rows or operation/affected-row metadata.
6. The execution is attached to the matching output. If the editor text differs from the selected saved query, a new manual output is created so the old artifact is preserved.
7. Output collapse state and result rows survive application restarts. `Copy` copies query text. `Export` writes the complete output object as JSON through a native save dialog.
8. `Close` requires confirmation and deletes the output record and retained rows only. The original conversation remains.

## SQL execution controls

- The model has no direct database execution tool.
- Every query requires an explicit user action; the model cannot call a driver.
- Exactly one statement is accepted.
- New and migrated profiles default to read-only. SELECT, safe WITH, plain EXPLAIN, and approved metadata forms are allow-listed there.
- Write-enabled profiles may execute recognized DML, DDL, procedure, permission, and maintenance categories only after a typed confirmation for that exact statement.
- Manual transaction statements, stacked statements, ATTACH/DETACH, COPY/LOAD, and external file/database operations remain blocked.
- Results are capped at 10,000 rows and marked when truncated.
- Database-side least privilege remains authoritative. Separate read and change principals are recommended.
- Plan and Chat responses are post-processed to suppress fenced executable content even if a provider ignores its prompt.

## Provider and result sharing behavior

The selected provider receives the normalized schema and conversation. The most recent selected result may also be included when result sharing is enabled for that chat. Turning result sharing off affects provider context; it does not delete locally stored output rows. Local Ollama and LM Studio adapters use loopback endpoints by default.

## Native commands

The Tauri command surface covers profile management, source import, schema load/refresh, statement assessment and confirmed execution, chat/session management, AI settings/testing, and query-output list/save/update/collapse/delete/export operations. Commands accept typed serializable models from `models.rs`; secrets are excluded from returned profile and history models.

## Browser demonstration

When Tauri is unavailable, `src/api.ts` provides a non-production browser demonstration backed by localStorage and sample results. It mirrors sessions and output-card behavior but does not connect to a real database or provider. Real credentials must never be entered into that preview.

## Verification

Frontend compilation is enforced by TypeScript before the Vite production build. Rust tests cover SQL bypass attempts, provider prompts and configuration, source inference, storage migrations and deletion, durable output independence, and live SQLite fixture behavior including the 10,000-row cap.
