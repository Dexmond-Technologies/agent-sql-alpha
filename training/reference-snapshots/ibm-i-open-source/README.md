# IBM i open source reference collection

This collection supplements the IBM i manuals with documentation and examples selected from [IBM's IBM i Open Source Resources directory](https://ibm.github.io/ibmi-oss-resources/). It supports the proposed on-premises agentSQL connector, source analysis, and deployment work. It is reference material, not an installed product dependency or a trained model.

## What is included

The snapshot contains 11 repositories, 644 checked-out files, and 92 HTML documentation snapshots. `manifest.json` records source URLs, exact Git commits, file hashes, license locations, download status, and documentation redirects. Multiple URLs can point to equivalent documentation; these counts are not unique manuals.

| Local repository under `repositories/` | Main use |
| --- | --- |
| `IBM--ibmi-oss-resources` | Original resource directory |
| `IBM--ibmi-oss-docs` | PASE, RPM installation and internal mirrors, SSH, TLS, ODBC, Python, Node.js, Java, troubleshooting, and service deployment |
| `IBM--ibmi-oss-examples` | Selected Python, Node.js, ODBC, Java, Nginx, and PostgreSQL reference examples |
| `IBM--python-itoolkit` | Python program calls, CL calls, transport and marshaling |
| `IBM--nodejs-itoolkit` | Node.js program calls, command calls and migration documentation |
| `IBM--xmlservice` | Program-call interfaces, CCSIDs, library lists, connections and diagnostics |
| `IBM--sqlalchemy-ibmi` | Db2 for i dialect, naming, library lists, transactions and connection options |
| `IBM--node-odbc` | ODBC connections, parameters, pooling and diagnostics |
| `IBM--nodejs-idb-connector` | Native IBM i Node.js Db2 connector |
| `IBM--nodejs-idb-pconnector` | Native IBM i Node.js connection pooling |
| `IBM--ibmichroot` | IBM i chroot setup reference |

The directory's old `markdirish/node-odbc` link now resolves to `IBM/node-odbc`; the latter is the recorded repository. HTML snapshots cover the five linked Read the Docs projects, the LoopBack Db2 for i connector, IBM's SQL tutorial directory, and the original resource page. They preserve document content, not a self-contained rendering of every website asset.

## How to use this safely

- Start with `IBM--ibmi-oss-docs/odbc/`, `tls/`, `user_setup/`, and `yum/`. The internal repository mirror documentation is relevant to controlled updates; examples that use public services are not approved deployment designs.
- Keep inference on the separate internal servers described in the implementation plan. IBM i-hosted Node.js connectors and chroot examples do not require moving inference onto IBM i. Chroot alone is not the agent execution security boundary.
- Treat sample SQL, program calls, CL commands, installation scripts, save files, and Dockerfiles as untrusted reference inputs. Some examples write data, run commands, contain demonstration credentials, or call external services. Nothing was installed, built, restored, or executed during collection.
- HTML snapshots retain publisher scripts and external asset links. Extract or sanitize their content before using them in an internal UI; do not serve the original active HTML as trusted application content.
- Match documentation to the actual IBM i release, PTF level, driver, and library version. Some pages describe deprecated APIs, historical runtimes, or development versions.
- Preserve each repository's LICENSE and any nested notices. Keep IBM product documentation rights separate from open-source licenses. No blanket redistribution or fine-tuning permission is assumed.
- Social channels, marketing, videos, customer stories, and broad third-party blog collections were not mirrored. This is the selected engineering corpus, not every outbound link on the directory.

## Resume and verify

From the `agent-sql-alpha` directory, run `python3 training/training_pipeline/download_ibmi_oss.py`. Requirements are Git, Python 3, requests, BeautifulSoup, and lxml. The downloader hashes checked-out files, preserves existing Git revisions and local changes, and retries missing pages. Updating a repository revision is a separate explicit action.

These sources have not been added to `training_pipeline/sources.json`, indexed into the existing search database, or used for fine-tuning. That next step needs source selection, version/platform metadata, license review, and filtering of unsafe or external-service examples.
