# Qwen integration and IBM i handoff

This upgrade adds a real Qwen provider to the existing Tauri application. It does not certify agentSQL for IBM production. GPU inference and IBM i interoperability require validation in the receiving environment. Existing providers, database adapters, conversation history and execution controls remain available.

## What is implemented

- The **Qwen (private server)** setting uses vLLM-compatible `/v1/models`, `/tokenize` and `/v1/chat/completions`. It requires the exact served model ID. Every generation request verifies model availability and uses the actual server tokenizer, including the chat template, before generation. Remote connections require verified HTTPS and a token; HTTP is restricted to loopback. Redirects and environment HTTP proxies are disabled. A private PEM root CA can be configured with `QWEN_CA_CERT_PATH`.
- Complete text responses are required. Different model identities, tool calls, incomplete output and unavailable services fail explicitly. There is no provider/model substitution. Plan/Chat post-processing and the existing independent SQL execution gate still apply. The model receives no execution tools.
- Schema selection retains complete column definitions for up to 32 objects by default. Selection uses lexical table/column identifiers and recent conversation terms. It is not semantic retrieval, foreign-key closure or a verified dependency graph. Large catalogs without relevant identifier matches fail with a clarification request instead of selecting arbitrary objects. Up to 25 result rows are supplied when result sharing is enabled; the context identifies the sample and original driver truncation status. Persisted results and schema are not shortened by this process. The most recent 12 history messages are eligible; additional context overflow fails rather than silently dropping more conversation text.
- A bounded JSONL evidence reader can supply up to four matching, reviewed reference excerpts. Evidence is opt-in. It is not automatically built from the unreviewed `training/` collections. The model is asked to use supplied citation markers; answers with unsupplied markers are rejected. Citation presence alone does not prove an assertion is correct.
- `deployment/qwen/gateway.py` provides a TLS/bearer boundary, concurrency limits, response-size limits, safe error responses and aggregate timing/counter metrics. It exposes only model discovery, tokenization, generation and monitoring, plus optional Ollama wire compatibility. It has no database credentials or SQL execution route.
- `tools/ibmi/connector.py` connects to a real IBM i ODBC DSN, exports actual catalog metadata and permits operator-requested reads of explicitly selected base-table columns. It accepts no caller-supplied SQL. Driver timeout requests and an outer process deadline bound client work; process termination does not establish host-side cancellation. Decimal values and integers outside JavaScript's exact range are exported as strings.
- **Import IBM i catalog snapshot** imports the export as a source profile with Db2 for i drafting instructions and its original capture time. Refresh re-reads the export file, not the IBM host. Desktop execution stays disabled for these profiles. The import validates declared provenance fields; it does not independently attest them.
- OS credential-store backends are explicitly enabled: Windows Credential Manager, macOS Keychain and Linux Secret Service with encrypted DBus transport. An unavailable/unlocked vault can cause operations to fail. Previous builds without store features used keyring's in-memory mock backend; those values cannot be recovered across process restarts and may need re-entry. Provider API tokens continue to use the application's `.env` configuration.
- Provider configuration is read per request without changing process-wide credentials. Existing file values and provider choices are retained; a blank saved token remains blank rather than reviving a previously loaded process value.

## Server prerequisites and sizing

Start the pilot with a Linux NVIDIA GPU VM, one L40S-class GPU (48 GB marketed capacity, 44 GiB listed on AWS G6e), 64 GiB host RAM, 8 vCPUs and at least 200 GB persistent model-cache space. An H100 80 GB offers more headroom. This is a starting configuration, not a measured latency/concurrency guarantee.

The Compose definition uses the official **FP8** checkpoint, rather than an unspecified third-party 4-bit quantization, with a 32,768-token total context and 2,048-token output reservation. It allows two concurrent requests initially. The actual server must demonstrate that these settings fit; reduce concurrency or context if startup or workload measurements show insufficient headroom. Full BF16 weights need more GPU memory. Fine-tuning is outside this delivery.

Required host components: Docker Engine, Compose with GPU reservations, a compatible NVIDIA driver and NVIDIA Container Toolkit. Follow [NVIDIA's installation guidance](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html). The model and server pins were resolved from the publishers; a pin is not a vulnerability review:

- `Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8`, revision `dcaee4d4dfc5ee71ad501f01f530e5652438fde0`.
- `vllm/vllm-openai:v0.30.0`, digest `sha256:8a69ffad015f138d7170c4ddc429e230a3bc1c1719f67e14324749df200a4b90`.

See the [Qwen model card](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8), [vLLM release](https://github.com/vllm-project/vllm/releases/tag/v0.30.0) and [serving APIs](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html). The gateway uses Python's standard library in the pinned runtime image and installs no additional dependencies. The separate ODBC tool pins `pyodbc==5.3.0`; the IBM driver is supplied/licensed by the recipient, not bundled.

## Deploy and connect

1. On the GPU host, copy `deployment/qwen/.env.example` to `deployment/qwen/.env`. Supply an actual random token of at least 32 ASCII characters, absolute model-cache and TLS-directory paths, and the real private VM interface address. Restrict access to this file. Generate the token in your secret manager; do not paste it into issue descriptions or logs.
2. Provision the dedicated cache directory so container UID/GID `10001:10001` can write it. Supply `server-chain.pem` and `server-key.pem` issued for the real server hostname. Give UID 10001 read access to the key while denying unrelated users access. Do not commit either file. The first model start downloads the pinned checkpoint from Hugging Face; controlled installations can pre-stage the same revision and restrict subsequent egress. GPU hardware and model downloads are not included in the desktop installer.
3. Validate and start the stack:

   ```bash
   docker compose --env-file deployment/qwen/.env -f deployment/qwen/compose.yaml config --quiet
   docker compose --env-file deployment/qwen/.env -f deployment/qwen/compose.yaml up -d
   ```

   The defaults publish TLS only on loopback. Change `QWEN_HOST_BIND` to the actual private interface for VPN/client access, and permit access only from approved client networks. The model's port is not published. Avoid plain `docker compose config`: it can display interpolated credentials. This stack is a single VM service, not high availability.
4. In the installed application, choose **Qwen (private server)**, enter the real `https://hostname:8443/v1` endpoint, model ID `qwen3-coder-30b-a3b`, and the server token. Use **Test connection**. This performs real discovery, tokenization and a small generation request. It is not a SQL correctness test.
5. Existing installations do not overwrite their `.env` on upgrade. Add the optional limits from the repository `.env.example` when needed. The default Qwen sampling parameters match the model card: temperature 0.7, top_p 0.8, top_k 20 and repetition_penalty 1.05. SQL-specific alternatives need measured evaluation. The shorter output limit is an application resource policy; it differs from Qwen's general coding recommendation. Length-limited responses are rejected.

The preferred integration is the dedicated Qwen provider. For Ollama compatibility, configure the existing Ollama provider with the gateway origin, its exact model ID and `OLLAMA_API_KEY` in the app-data `.env`. The existing Ollama adapter now supports an optional bearer token. This compatibility path uses the gateway's limits but does not apply the dedicated native Qwen schema/evidence selection.

## IBM i metadata and bounded reads

Install a recipient-approved IBM i Access ODBC driver, configure a real DSN for the target release/architecture, and validate trust/hostname checking through that driver's supported configuration. The tool sets `CONNTYPE=2`, `ALLOWPROCCALLS=0`, `XDYNAMIC=0`, `NAM=0`, `SSL=1` and `QUERYTIMEOUT=1`, and requests ODBC read-only access. IBM documents connection properties and platform distinctions in [its driver keyword reference](https://www.ibm.com/docs/en/i/7.6.0?topic=details-connection-string-keywords) and [Linux configuration guidance](https://www.ibm.com/support/pages/ibm-iaccess-linux-odbc-configuration). TLS keywords/support differ by platform and driver; this code does not prove encryption or certificate validation. Exported transport verification is explicitly `not-verified-by-exporter`.

Use a host account restricted to the intended objects and operations. Provide `IBMI_DSN`, `IBMI_USER` and `IBMI_PASSWORD` through the operator's secret environment; the tool has no default host, user, password or fabricated data. Install the Python dependency in a dedicated environment, then use the actual authorized schema/table identifiers:

```bash
python3 -m venv .venv-ibmi
.venv-ibmi/bin/pip install -r tools/ibmi/requirements.txt
.venv-ibmi/bin/python tools/ibmi/connector.py catalog --schema "$IBMI_SCHEMA" --output "$IBMI_NEW_CATALOG_PATH"
.venv-ibmi/bin/python tools/ibmi/connector.py read-table --schema "$IBMI_SCHEMA" --table "$IBMI_TABLE" --column "$IBMI_COLUMN" --limit 100 --output "$IBMI_NEW_RESULT_PATH"
```

The schema/path variables above must be populated by the operator. Existing output files are never overwritten. Outputs are published after successful completion, with owner-only permissions where the OS supports them. An ODBC metadata error does not generate example objects. Unsupported primary-key metadata is explicitly marked unknown; unknown column types/nullability cause failure. This version does not export foreign keys, indexes, routines, view definitions or IBM i record-format/file-member semantics. SQL Services availability and compiler/RPG/COBOL behavior remain unvalidated.

Import the resulting catalog JSON using the desktop button. To supply release-specific drafting context, set `QWEN_IBMI_RELEASE` to the confirmed release/TR/PTF description. For ordinary SQL project imports intended for IBM i, additionally set `QWEN_SOURCE_DIALECT=db2i`; this does not relabel SQLite/PostgreSQL/MySQL/SQL Server connections.

## Reviewed evidence

`QWEN_KNOWLEDGE_PATH` identifies one operator-approved UTF-8 JSONL file. Every nonblank record must contain exactly `id`, `version`, `dialect`, `title`, `text` and `source`. Use real source excerpts and source/version identifiers. IDs/versions accept letters, digits, `.`, `_` and `-`. Dialects are `db2i`, `postgresql`, `mysql`, `tsql`, `sqlite` or `generic`. Matching uses the actual profile dialect, so an IBM-specific reference is not selected for SQLite.

The limit is 8 MiB, 2,000 records and 12,000 text bytes per record. Select only material that the current operator is permitted to access. There is no enterprise ACL engine or automatic document ingestion in this implementation. Referenced text is sent to the configured model endpoint; this is separate from the existing source scanner's metadata-only behavior. No document, example question or business definition is pre-populated in production.

## Verification and acceptance

Run the actual endpoint measurement after deployment, supplying `QWEN_API_KEY` through the secret environment:

```bash
python3 tools/qwen/verify_endpoint.py --base-url "$QWEN_ACTUAL_BASE_URL" --runs 3 --concurrency 1 --report "$QWEN_NEW_REPORT_PATH"
```

For a private CA, add `--ca-certificate` with the real PEM path. For an actual workload, add `--prompt-file` with a reviewed question. Reports contain actual token usage, response durations and prompt/answer hashes; they exclude prompt/answer text. The default small prompt tests connectivity only. Aggregate completion tokens per wall-second includes prompt processing and network time; it is not decode-only speed or first-token latency. Failed checks produce a failed report and nonzero exit status, without substitute measurements.

The gateway's `/healthz` reports process liveness; `/readyz` checks exact model listing and explicitly does not establish generation. Authenticated `/metrics` returns aggregate counters and durations, with no user/row/prompt values. Native unit/regression checks and isolated gateway failure checks do not establish that the actual model/ODBC driver works.

### Local development results — 2026-10-05

| Check | Observed result | Scope |
|---|---|---|
| `npm run build` | Passed | TypeScript compilation and Vite frontend bundle |
| `cargo test --locked --lib` in `src-tauri` | 34 passed | Native unit/regression checks; includes existing explicitly synthetic SQLite fixtures and four Qwen transformation/rejection checks |
| `npm run test -- src/queryAssessment.test.ts` | 3 passed | Existing query assessment checks |
| `python3 -m unittest discover -s tools/tests -v` | 8 passed | Actual local gateway authentication/failure handling against an unavailable backend; pure serialization/escaping checks; failed endpoint report |
| Python AST parsing | Passed | Syntax of gateway, endpoint verifier and IBM i connector |
| `docker compose ... config --quiet` | Passed | Compose configuration only, using temporary real directories and an ephemeral generated token; no containers or model were started |
| `git diff --check` | Passed | Whitespace checks for tracked edits |

No successful model response, IBM i metadata/result, GPU latency measurement or cross-platform credential-store runtime validation is reported here. Unit inputs and existing fixtures are synthetic checks, not client data or proof of model accuracy. Installer packaging, signing and target-machine acceptance remain required.

Before IBM/client production acceptance, record the actual IBM i release/TR/PTFs, driver/platform, certificate and hostname validation, least-privilege account behavior, approved schemas, exact decimal/date/CCSID handling, timeout/cancellation behavior, model/runtime pins, held-out SQL expected results, concurrency/latency targets and recovery/rollback exercises. No real IBM i system or GPU model server was supplied in this development session, so those checks cannot be reported as passed.

Existing alpha limitations still apply: unencrypted local SQLite history, provider tokens in `.env`, no enterprise identity/resource ACL engine, no immutable audit trail, and unsigned release packages without organization signing credentials. See [DATA_HANDLING.md](DATA_HANDLING.md). This upgrade supplies integration code and reproducible deployment inputs, not IBM certification or a completed production approval.

For rollback, retain the previous application installer, Compose file, image/model pins and reviewed evidence versions. Stop the new stack and restore the previously validated configuration. Changing provider settings does not require deleting existing profiles or conversations. Back up the app-data SQLite store with an approved consistent SQLite backup procedure; do not copy only the main file while WAL writes are active. Protect and restore secrets through the configured vault/secret manager.
