# agentSQL Enterprise IBM i Implementation Plan

Draft for technical and commercial scoping, prepared 1 October 2026.

Evolve `agent-sql-alpha` into an on-premises development assistant for the customer's IBM i environment: Db2 for i, RPG, CL, COBOL, DDS definitions, technical documentation, and application support tickets. The first delivery should demonstrate two complete workflows: explain a real program with verifiable source references, and generate a correct query for the host's supported SQL dialect using the customer's schema and business definitions. Subsequent deliveries add coordinated agents, controlled code changes, security review, CI integration, analytics, and modernization packages.

The client has confirmed IBM i, clarifying the earlier AS/400 description. The confirmed deployment requirement is an internal company network: all customer data and inference stay on premises. The exact IBM i release and Technology Refresh/PTF levels, source locations, GPU capacity, user numbers, and delivery deadline remain unknown. Db2 for i is the target database; individual catalog, SQL service, driver, and compiler capabilities still require release-specific verification. The architecture and estimates are proposals; discovery must resolve those inputs before a fixed delivery commitment. The existing filename is retained for link compatibility.

## IBM i compatibility and native objects

Make release and capability identification the first integration task. Record hardware/partition, IBM i release and fixes, installed database/client access components, TLS support, available host services, source language variants, and a non-production test endpoint. Confirmation of IBM i does not establish a particular release or supported driver/catalog query.

| Host profile found in discovery | Planned integration path | Delivery implication |
| --- | --- | --- |
| IBM i release compatible with the chosen supported client | Verified ODBC access, release-appropriate SQL catalogs and approved source-member access | Proceed with the live connector and query pilot |
| Older IBM i release or missing required PTFs | Test a customer-approved compatible driver and available metadata/source interfaces | Scope a release-compatible adapter or agreed prerequisites; revise estimates if required catalogs or transport requirements cannot be met |
| Host access not yet available or no approved secure transport | Customer-produced source/DDL/metadata exports inside the company network | Deliver source explanation and SQL drafts against a dated snapshot; live query acceptance remains outstanding |

Model libraries, programs, physical files, logical files, record formats and file members explicitly. Import source by library/file/member identity; include common source-file conventions such as `QRPGSRC`, `QRPGLESRC`, `QCLSRC`, `QCBLSRC` and `QDDSSRC` as configurable discovery hints, never assumed customer paths. Prioritize native source-member intake alongside Git exports rather than requiring the customer to migrate its source control first.

Include RPG III/RPG/400 and RPG IV/ILE format identification in the parser feasibility work. Trace record-level I/O and indicators, not only embedded SQL, when identifying data access and business logic. Preserve DDS keys, select/omit behavior, logical-file relationships and member-specific data access. A file name alone must not silently select an unintended member or library.

Keep the AI service and model servers on separate internal infrastructure. No model installation or autonomous CL execution on IBM i is required. If a legacy connection cannot meet the agreed security policy, use approved exports while the customer resolves connectivity; do not silently weaken transport security. OS/400 and i5/OS adapters are not baseline requirements now that IBM i is confirmed; separately scope them only if additional hosts are identified.

## Delivery scope and assumptions

Treat IBM Bob as a capability benchmark. This plan describes changes to agentSQL, not an IBM product integration, license, certification, or assertion of feature parity. IBM's current documentation describes Agent, Plan, and Ask modes, while the requested agentSQL design below also includes Architect and Review. IBM also documents a self-hosted Bob deployment on OpenShift; discovery should record whether the customer expects a standalone product or interoperability with an existing licensed platform. [IBM modes](https://bob.ibm.com/docs/ide/features/modes), [IBM self-hosted deployment](https://bob.ibm.com/docs/ide/enterprise/on-premises/overview).

Proposed delivery boundaries:

- Pilot: authenticated users, enforced internal inference, Db2 for i metadata and bounded reads, explanation of agreed RPG/CL/COBOL samples, document and ticket search, citations, audit evidence, and Ask/Plan/SQL drafting workflows.
- Enterprise SDLC release: persistent coordinated agents, Code/Architect/Review workflows, isolated code changes and test runs, CLI/CI integration, shared policy, operational monitoring, and internal usage analytics.
- Modernization releases: separately accepted packages for RPG restructuring, DDS-to-SQL migration, CL changes, Java upgrades, and selected COBOL-to-Python transformations. Each package needs a supported-input matrix and behavioral tests.

Production database writes and automatic production deployment are outside the pilot. Existing alpha write functionality remains available only where the deployment policy explicitly permits it. IBM i and IBM Z are distinct platforms: COBOL source support does not imply z/OS, CICS, JCL, or VSAM integration; those require separate discovery and scope.

## Existing code and required changes

| Area | Evidence in the current workspace | Required extension |
| --- | --- | --- |
| Desktop and query workflow | React/Tauri UI, durable conversations, query cards, explicit execution | Enterprise workspace navigation, evidence viewer, jobs, approvals, and modes |
| Database adapters | `DatabaseDriver` supports SQLite, PostgreSQL, MySQL, and SQL Server | Separate Db2 for i adapter and release capability detection |
| SQL controls | Token-based classification, row/time caps, profile write opt-in, boolean confirmation | Db2-aware validation, routine restrictions, database authority enforcement, centrally authorized execution |
| Model access | Local and cloud adapters; provider URL validation accepts HTTP/HTTPS | Mandatory internal inference gateway, endpoint policy, no cloud fallback, authenticated internal TLS |
| Source analysis | SQL/Prisma inference and Chroma recognition; bounded local scans | RPG/CL/COBOL/DDS parsing, source-member import, dependency extraction, provenance |
| Knowledge search | Python preparation pipeline and SQLite full-text search in `training/` | Runtime integration, customer corpus, access filtering, IBM i references, semantic retrieval and citations |
| Identity and storage | Desktop OS credential vault and local SQLite; provider keys in `.env` | Enterprise identity, role/resource authorization, managed secrets, protected shared storage and retention |
| Audit and operations | Local history, no central enterprise audit/agent runtime | Durable job records, security audit, monitoring, recovery, and contribution/cost metrics |
| Testing and packaging | Prior scan: 30 Rust tests passed; app frontend tests and build passed | Isolate vendored tests, establish reproducible CI, compatibility tests and signed enterprise delivery |

The previous scan also found that the full `npm test` command picks up a vendored training test requiring `q`, and reported five development dependency audit findings. Recheck these against the actual release baseline. The desktop configuration currently has no content security policy. These are initial engineering backlog items, not evidence that the application has completed a security assessment.

Source references: [architecture](ARCHITECTURE.md), [data handling](DATA_HANDLING.md), [models](../src-tauri/src/models.rs), [drivers](../src-tauri/src/drivers.rs), [SQL gate](../src-tauri/src/safety.rs), [providers](../src-tauri/src/providers.rs), [source scanner](../src-tauri/src/source.rs), [training search](../training/training_pipeline/search.py), [desktop configuration](../src-tauri/tauri.conf.json).

## Proposed architecture

Keep the React/Tauri client and extract reusable Rust application logic into a core library consumed by the desktop adapter, an internal service, and a CLI. Use a modular service initially, with separate worker processes for ingestion, model jobs, and code execution. This supports central identity and policy without requiring a large microservice deployment.

| Component | Responsibility | Proposed location |
| --- | --- | --- |
| Desktop client | Conversations, schema explorer, evidence, drafts, job progress, review | Existing `src/` and thin `src-tauri/` adapter |
| Core library | Typed contracts, policies, SQL assessment, application workflows | New `crates/agentsql-core/` |
| Internal API service | Authenticate requests, authorize resources/actions, coordinate jobs and approvals | New `crates/agentsql-server/` |
| IBM i connector worker | Driver ownership, metadata, source import, bounded query execution | New `crates/agentsql-connectors/` |
| Ingestion and retrieval workers | Parse source/documents/tickets, preserve access metadata, retrieve evidence | New `services/knowledge/`, reusing appropriate Python pipeline code |
| Inference gateway | Route generation, embeddings and reranking to approved internal model servers | Internal service endpoint with centrally managed model policy |
| Agent workers | Execute scoped tasks with isolated contexts, workspaces and resource limits | New `crates/agentsql-orchestrator/` and approved worker images |
| CLI | Submit jobs, inspect evidence, export reports and integrate with internal CI | New `crates/agentsql-cli/` |
| Shared stores | Metadata, job state, permissions, searchable chunks, protected artifacts and audit | Customer-managed database and storage on premises |

The primary path is client or CLI → authenticated internal service → authorization and policy → retrieval/model/tool work → validation → cited answer or reviewable artifact. A separate authorized action executes a SQL draft or applies a code patch. Model output cannot directly invoke privileged adapters.

Start the pilot with an internal Linux service and worker deployment, a shared relational store, and the existing desktop client. A proposed default is PostgreSQL for metadata and full-text search, with vector search added after evaluating an approved extension. Keep a retrieval interface so the customer's existing search platform can be used. Do not make Chroma mandatory: current Chroma support is source recognition, not an enterprise retrieval service.

Select VM/container hosting or OpenShift/Kubernetes in discovery based on customer operations. IBM i remains the database and source-system host; GPU inference is expected to run on separate internal infrastructure unless the customer establishes another supported deployment. No particular GPU, model size, cluster, or concurrent-user capacity is assumed.

## On-premises policy and enterprise foundation

Establish this boundary before importing confidential customer material.

1. Add an administrator-managed `enterprise_on_prem` deployment policy. Apply it in backend services and native commands, including connection tests and model discovery. Desktop settings, environment overrides and CLI flags must not bypass it. Enterprise clients use the central service; direct desktop database/provider access is disabled under this policy.
2. Allow only registered internal endpoints. Validate destinations, redirects, resolved addresses and proxy behavior; require authenticated TLS and approved internal certificate authorities. A private-looking hostname or a provider named "local" is insufficient. Combine application checks with workload-level network rules that block public egress.
3. Keep generation, embeddings, reranking, OCR, vector storage, prompts, caches, diagnostic logs, analytics and backups internal. Disable external telemetry, crash uploads, remote model downloads and cloud fallbacks. Show an actionable internal-service failure if inference is unavailable.
4. Use a separate controlled update path to mirror approved packages, scanner rules, models and vulnerability databases. Updates are pinned and verified; application workers have no direct update-related internet access or customer-data upload path.
5. Integrate the customer's identity provider through an agreed standard, preferably OIDC where supported. Define workspace roles such as reader, query executor, developer, reviewer, administrator and auditor; also authorize each library, repository, document and ticket resource.
6. Move enterprise credentials into an internal secret manager or equivalent managed store. Services receive only required credentials. Protect databases, indexes, artifacts, backups and any desktop caches with managed encryption and keys; define rotation and recovery procedures.
7. Disable automatic query-result inclusion in model context by default. Allow only policy-approved fields and bounded samples when needed. Reauthorize every request, resource retrieval, export and execution; do not rely on UI controls.
8. Separate deletable chat history from the security audit. Record identity, resource/version references, policy decisions, tool calls, approvals, model/version and outcomes without storing raw sensitive content in generic logs. Use access-controlled append-only retention with tamper evidence and an independent audit destination.
9. Introduce a restrictive desktop content security policy and minimize native command permissions. Evidence rendering must not load external images, scripts or other remote content from imported documents or model responses.

Pass criteria: ordinary users cannot enable an external provider; external calls fail at both application and network boundaries; document ingestion and model/scanner work function with internet access denied; audit records remain available after a chat is deleted.

## Db2 for i integration

Implement `Db2i` as a distinct engine. Do not map it to an existing SQL Server/MySQL driver or assume that Db2 LUW and Db2 for i catalog behavior is interchangeable.

The proposed first transport is IBM i Access ODBC in a connector process. IBM provides platform-specific ODBC packages, including Linux/macOS packages using unixODBC. Confirm deployment-platform compatibility, package entitlement, redistribution terms, authentication and TLS with the customer before packaging it. Use a JDBC/IBM Toolbox alternative only if a concrete discovery constraint warrants the additional runtime. [IBM ODBC packages](https://www.ibm.com/support/pages/odbc-driver-ibm-i-access-client-solutions).

Implementation work:

- Extend Rust/TypeScript engine and connection contracts with host, approved credential reference, default library/schema, library list, naming convention, encoding information and detected capabilities. Keep system names alongside SQL names.
- Introspect approved libraries through version-appropriate catalog queries. Capture tables, views, physical/logical files, columns, labels/comments, keys, indexes and relationships where available. IBM documents both SQL and system names in `SYSTABLES` and related catalogs in `QSYS2`. [SYSTABLES](https://www.ibm.com/docs/en/i/7.5.0?topic=views-systables), [IBM i catalogs](https://www.ibm.com/docs/en/i/7.5.0?topic=views-i-catalog-tables).
- Probe catalog/service capabilities instead of assuming every IBM i release/fix level supports the same features. Preserve unsupported and incomplete metadata as explicit status. Use only SQL services available at the customer's release and PTF level, with approved alternatives where needed.
- Handle CCSID/encoding conversion, fixed-width strings, nullable fields, decimal precision, timestamps, qualified names and member identity. Represent exact financial decimal values without silently converting them into binary floating point or lossy JavaScript numbers.
- Separate metadata access, source import and interactive query identities. Enforce each caller's authorized libraries and objects; a broad ingestion account must not grant broad user access. Map application identity to approved IBM i authority or a customer-approved delegation model.
- Add parameterized query contracts and Db2-specific SQL validation. Use a parser verified against the supported dialect, with unsupported syntax blocked or limited to vetted templates. Validate resolved objects and routines as well as statement shape: a `SELECT` may call a function with side effects. Reject unauthorized routines, system-command services and cross-system access.
- Preserve explicit execution, row limits, result-byte limits, timeouts and cancellation. Test that timeout/cancellation stops work on IBM i, not merely the client wait. Capture SQLSTATE and sanitized diagnostics.
- Bind any future elevated approval to the exact SQL and parameters, connection, actor, policy version, expiry and single use. Revalidate at execution; a frontend boolean is not enterprise authorization.

Read-only database authorities are a separate control from SQL classification. Any DBA provisioning, including aliases needed for particular member access, is a documented setup operation outside the model's tools.

Deliver synthetic fixtures early, then certify the connector against a customer-provided non-production IBM i system. SQLite fixtures cannot demonstrate Db2 for i compatibility.

## Legacy source and knowledge ingestion

Provide two intake paths: approved Git/exported source files and an IBM i source-member/IFS connector. Discovery selects the initial path; design the common document contract so both are possible. Record library, source file, member, source type, sequence/line mapping, encoding, revision/hash and extraction timestamp. Never identify a program by basename alone when several libraries contain the same name.

| Input | Initial processing | Required evidence |
| --- | --- | --- |
| RPG and SQLRPGLE | RPG/400 versus ILE identification, fixed/free format, procedure boundaries, native file I/O, indicators, calls, copy members, embedded SQL | Original source spans, symbol/dependency links, unresolved constructs |
| CL and CLLE | Commands, parameters, program calls, overrides, error handling and library context | Command spans and explicit uncertainty for runtime-dependent behavior |
| COBOL | Divisions, paragraphs, file definitions, copybooks, data layouts, calls and embedded SQL | Original/expanded-source mapping and dialect assumptions |
| DDS and SQL definitions | Files, record formats, fields, keys, access paths and relationships | Link between source definitions, runtime catalog and consuming programs |
| Documentation | Markdown/text/PDF/DOCX extraction; local OCR when required | Document revision, heading/page references and classification |
| Support tickets | Approved exports first; read-only internal API adapter when identified | Ticket ID, timestamps, attachment/source references and ticket visibility |

Use deterministic parsers or language-aware extractors where feasible, with a documented coverage matrix. Text-only fallback can support cited explanation but must report reduced structural confidence. Compiled objects without source do not justify an invented explanation. Dynamic calls, overrides, missing copybooks, and source/deployed-object mismatches remain visible limitations.

Build a dependency graph for program → procedure → called program → file/table and ticket → affected component. Distinguish statically observed, customer-confirmed and model-suggested relationships. Large programs require structured summaries of routines and dependency expansion; simple fixed-size chunks are insufficient for end-to-end explanation.

Index incrementally using content hashes and checkpoints. Respect source exclusions, resolve paths within approved roots, bound parsing work, isolate document converters, and avoid running macros or imported code. Source is untrusted data even when it comes from an internal repository.

The existing `training/` corpus is reference material and preparation code; its presence does not mean the LLM has been trained on it. Reuse licensing/provenance and extraction work after review. Add approved IBM i/Db2 for i material matched to the target release. Keep generic SQL lessons separate from authoritative customer schema and business definitions. Fine-tuning is a later option only if evaluation demonstrates a need and data/model rights permit it.

Local reference collections now have separate manifests and usage notes: [IBM i manuals](../training/TRAINING/ibm-i-as400/README.md), [IBM i open-source documentation and examples](../training/TRAINING/ibm-i-open-source/README.md), and the separately requested [z/OS COBOL library](../training/TRAINING/ibm-enterprise-cobol-zos/README.md). Preserve platform, release, PTF applicability, source revision, and rights when indexing them. IBM's open-source documentation adds internal RPM mirror, SSH/PASE, TLS, ODBC, Python/Node.js, and XMLSERVICE references. These downloads are not yet indexed or enabled as model-training inputs.

Keep the proposed remote ODBC connector distinct from native Node.js connectors that run on IBM i. Evaluate XMLSERVICE or toolkit-based program calls only if a source-access use case requires them; their ability to run CL or shell commands does not authorize unrestricted agent execution. Treat public-service integrations and write-capable examples as reference code, not approved on-premises deployment patterns. [IBM i open-source resources](https://ibm.github.io/ibmi-oss-resources/), [IBM i native Node.js connector](https://github.com/IBM/nodejs-idb-connector).

## Retrieval and grounded answers

Before any corpus intake, complete the [pre-ingestion readiness gates](../training/TRAINING/INGESTION_READINESS.md). The public-reference expansion adds pinned IBM i community/tooling examples, local extraction/inference/retrieval documentation, and primary security/identity/analytics/standards references. Their presence does not approve dependencies, customer permissions, training rights or platform compatibility. The readiness report separates public reference coverage from the customer evidence still required.

Implement retrieval-augmented generation: search authorized source and documentation, then give selected evidence to an internal model to answer the question.

- Combine exact symbol/member searches and keyword search with local embeddings and reranking. Exact identifiers such as `ABC123` must work independently of semantic similarity.
- Apply access-control filters before retrieving/ranking content and before expanding dependency links. Recheck at artifact fetch and answer delivery. Chunk indexes, vector entries, summaries, caches, citations and prior-session reuse must preserve authorization scope.
- Treat missing or stale authorization metadata as a denial. Carry source deletion and permission revocation through chunks, vectors, cached answers and generated summaries within a tested policy-defined interval. Restrict exported or previously generated artifacts according to the customer's retention policy.
- Include stable source IDs, revision/hash and source locations in answers. Validate that cited spans exist in the referenced snapshot. Separate observed behavior from inferred intent and surface conflicting or stale sources.
- Add a customer-maintained business glossary: for example, which statuses mean "open order," whether cancelled/held/partially shipped orders count, and which date or company scope applies. Ask for clarification or report missing evidence when these definitions are absent.
- Treat text in tickets, documents and source comments as evidence, never as authority to change mode, tool permissions, network destinations or policy. Test adversarial instructions embedded in each source type.

For "Explain the RPG program ABC123," the answer should identify the exact program version, purpose, inputs/outputs, important branches, tables read/written, calls, error handling, related tickets and unresolved dependencies, with navigable source references.

For "Generate an SQL query to find open orders," the app should retrieve the permitted schema and approved business definition, generate parameterized SQL validated for the detected Db2/host release, explain its filters and assumptions, and present a draft. Execution requires the user's separate action and current authorization.

## Modes and coordinated agents

Modes must change enforced capabilities, not just prompts. Persist the selected mode and validate every tool request against the effective policy. A requested mode switch cannot silently grant additional authority.

| Mode | Allowed work | Result |
| --- | --- | --- |
| Ask | Search permitted knowledge and explain it | Cited answer; SQL draft when explicitly requested, with separate execution action |
| Plan | Inspect requirements and dependencies; propose work | Reviewable plan, scope, risks and acceptance criteria |
| Architect | Compare designs and analyze impact | Architecture decisions, dependency diagrams and migration design |
| Code | Produce scoped changes in an isolated workspace; run approved development tools | Patch, tests and implementation notes |
| Review | Analyze a selected revision/diff and run approved scanners | Findings with locations, severity, evidence and remediation |

Migrate existing `chat` to Ask and `plan` to Plan while preserving history. Migrate `direct` sessions to an explicit SQL-drafting workflow; do not automatically grant Code permissions. Keep SQL generation and database execution as distinct actions in every mode.

Add a durable task graph with planner/coordinator, IBM i analyst, SQL specialist, implementer, tester, reviewer and documentation worker roles. Parallelize independent tasks; schedule dependent work only after its prerequisites are accepted. A documentation or pipeline worker can prepare proposed changes alongside tests, but publishing and deployment remain explicit authorized operations.

Each worker gets a bounded task description, minimum evidence, isolated context, scoped tools, inherited user identity, resource/time/token limits and an output schema. Child permissions are a subset of the parent's effective permissions. Use one approved internal model initially; add model routing only after measured need.

Persist job/task states such as queued, running, waiting for review, failed, cancelled and completed. Support retries, resumable work, cancellation and idempotency. A failed agent must not leave the overall job marked complete. Reserve budgets for validation, and cap recursion and concurrency.

Code workers use separate worktrees or sandbox copies. Assign file ownership or reconcile conflicting patches before integration. Tools run without production credentials, with approved network access and CPU/memory/time limits. Display diffs and test results, then recheck the target revision before applying an approved patch. Commands come from validated tool schemas and policies, not unrestricted model-generated shell strings.

## Security review and compliance evidence

Run approved static analysis, secret detection, dependency/license checks, and relevant language/compiler checks locally. Use local pinned Semgrep rules with metrics disabled and public networking blocked. Semgrep documents local-rule operation and `--metrics off`; its published language matrix does not establish native RPG/CL/COBOL support, so legacy-language coverage needs separate analyzers or custom rules with tested limitations. An unsupported language must be reported as unscanned. [Semgrep telemetry](https://docs.semgrep.dev/metrics), [language coverage](https://docs.semgrep.dev/supported-languages).

Map deterministic findings to code locations and rule versions. AI triage can explain and prioritize evidence, but cannot silently dismiss findings or turn incomplete scans into a pass. Record reviewer dispositions and re-open findings when relevant code or rules change. Export machine-readable reports, such as SARIF for supported findings, and an internal review summary.

Define the customer's required control set during discovery. Maintain a trace from requirement → implemented control → test → evidence → owner. Include identity/access review, network isolation, model/artifact provenance, retention, release integrity and incident procedures. Passing these engineering checks is not a claim of regulatory certification.

## CLI integration and internal analytics

Provide an `agentsql` CLI using the same core contracts, policy and internal service as the desktop. Proposed commands cover `ask`, `plan`, `query draft`, `review`, `job status`, and `report`. CI uses short-lived service identities with explicit workspace permissions, predictable exit codes, JSON/SARIF outputs and cancellation. CI jobs that require an unavailable human approval return a pending/blocked result rather than bypassing the policy.

Start with one customer-selected internal Git/CI system. Add a reference pipeline for checks, review artifacts and proposed documentation changes. Store all source, artifacts, runner logs and job results internally. External ticket systems or SaaS CI are not assumed to be allowed by the deployment requirement.

Introduce analytics events from the first service release, then add dashboards: active users, task completion, accepted/reverted patches, review findings, token counts, inference latency, queue time, GPU usage and tool execution duration. Attribute contributions to a task and reviewed artifact. Calculate on-premises cost from an agreed infrastructure allocation model, with explicit assumptions. Measure productivity using a baseline and observed task cycle time; token counts and generated lines are not proof of business value. Restrict dashboard visibility and exclude raw source, prompts and results from default metrics.

## Modernization packages

Implement versioned packages containing prerequisites, supported constructs, analysis, transformation steps, tests and rollback instructions. Each package executes through the same orchestrator and authorization controls.

| Package | First bounded capability | Acceptance evidence |
| --- | --- | --- |
| RPG modernization | Refactor an agreed fixed-format procedure into free-format RPG supported by the agreed target compiler | Compilation on the target release, representative tests, call/data behavior comparison; a host/compiler upgrade is a separate dependency if needed |
| DDS to SQL | Generate a migration design and candidate DDL for selected physical/logical files | Review keys, record formats, field attributes and dependent programs; reconcile data in a test library |
| CL maintenance | Explain and propose scoped changes to an agreed job/control flow | Review command effects, library/override behavior and error paths in a test environment |
| Java upgrades | Upgrade one agreed application/JDK/framework combination | Build, compatibility, security and application regression results |
| COBOL to Python | Translate one selected business routine with defined interfaces | Characterization tests and differential results for decimal arithmetic, rounding, encodings, layouts and error behavior |

Preserve working legacy behavior through characterization tests before changing it. Account for I/O, database transactions, locking, job behavior and operational dependencies; generated code that compiles is not sufficient evidence of equivalence. Where the target runtime cannot preserve a behavior, require an explicit design decision. Whole-application conversion and new host-platform integrations require fresh estimates after the initial package is validated.

## Code change map

Paths below describe planned work and do not imply those modules already exist.

| Existing area | Planned change |
| --- | --- |
| `src-tauri/src/models.rs`, `src/types.ts` | Db2i profiles/capabilities, evidence references, workspace identity, policies, modes, tasks, artifacts and approval contracts |
| `src-tauri/src/lib.rs`, `src/api.ts` | Extract application services; keep thin desktop commands; add authenticated internal API transport and job progress |
| `src-tauri/src/providers.rs` | Split provider transport from prompt construction and policy; require internal gateway in enterprise mode; report model usage |
| `src-tauri/src/drivers.rs`, `network.rs`, `safety.rs` | Reusable driver contracts, IBM i worker adapter, dialect-aware validation, authorization and execution controls |
| `src-tauri/src/source.rs` | Retain lightweight project inference; add structured intake contracts for legacy parsers and member imports |
| `training/training_pipeline/` | Reuse reviewed extraction/provenance code in runtime ingestion; introduce IBM i sources and customer ACL metadata |
| `src-tauri/src/storage.rs` | Versioned migrations, session compatibility, protected cache policy; shared persistence adapter for enterprise service |
| `src/App.tsx`, settings and message components | Workspace/mode UI, policy status, citations/source viewer, task tree, diffs, approvals and review results |
| `src-tauri/tauri.conf.json`, capability files | Content security policy, reduced native privileges and enterprise packaging configuration |
| `docs/`, `fixtures/`, new `evals/` and `deploy/` | Revised data-flow documentation, IBM i fixtures, evaluation cases, installation and operational runbooks |

Keep interfaces versioned across client/service releases. Preserve existing local profiles and conversations through an explicit migration path. Do not silently upload old desktop histories into the shared service. In enterprise mode, the data-handling documentation must explicitly explain that authorized source excerpts can now reach an internal inference service; the alpha's claim that raw source is never sent to a provider would no longer describe that workflow.

## Delivery sequence and ownership

Indicative schedule assumes approximately eight full-time equivalents, an available customer AS/400 specialist, and timely access to sample source, a compatible test host and internal hosting. Weeks are elapsed from kickoff, with overlapping workstreams. These are planning ranges, not a contracted deadline; infrastructure delays, legacy connector work and unsupported language dialects can extend them. An export-only prototype does not satisfy the live database pilot milestone.

| Phase | Indicative weeks | Accountable lead | Deliverables and exit criteria |
| --- | --- | --- | --- |
| 0 Discovery and baseline | 1–2 | Technical lead + customer AS/400 owner | Exact host OS/release and driver feasibility, environment/support matrix, sample corpus, business glossary owner, data-flow boundary, deployment/model benchmark plan, corrected test discovery and reproducible baseline |
| 1 Enterprise foundation | 3–6 | Backend/security + platform | Reusable core/internal service, identity and authorization, internal model gateway, secret/storage policy, audit, denied public egress; internal-only end-to-end smoke test |
| 2 IBM i and ingestion | 5–10 | IBM i integration + knowledge lead | Db2i connector on a real test system, agreed source formats, document/ticket intake, provenance and permissions, basic cited explanations |
| 3 Grounded workflows | 9–12 | Knowledge lead + frontend | Hybrid retrieval, evidence viewer, Ask/Plan/SQL drafts, validated business terms, repeatable quality evaluation |
| 4 Customer pilot | 13–16 | QA/security + customer sponsor | Both example workflows accepted, authorization/egress tests passed, load/model sizing measured, recovery/retention exercised, operating runbooks |
| 5 Coordinated development | 17–22 | Orchestration + frontend | Architect/Code/Review, durable task graph, parallel isolated workers, scoped tools, cancellation, patch review and tests |
| 6 Enterprise SDLC delivery | 23–28 | Platform/security + product | Internal CLI/CI, scanner coverage, dashboards, signed releases, upgrade/rollback/backup exercises, service objectives validated |
| 7 Initial modernization packages | 29–36+ | IBM i/modernization lead | Selected transformations with characterization/differential tests and customer acceptance; estimates refreshed per package |

Suggested staffing: one technical lead; two backend/integration engineers; one frontend engineer; one retrieval/ML engineer; one IBM i/RPG/COBOL specialist; one QA/security engineer; and approximately one equivalent split between platform operations and product/delivery. Customer domain reviewers and infrastructure owners are additional dependencies. A smaller team needs a narrower initial scope or a longer schedule.

Critical dependencies: enforce internal policy before using confidential material; prove live IBM i access and source fidelity before claiming grounded IBM i answers; establish authorization/provenance before shared retrieval; complete isolated execution and durable audit before Code agents; establish behavioral baselines before transformations.

Overlapping connector and parser work uses synthetic or approved non-confidential fixtures until the enterprise foundation gate passes. A snapshot-based answer must be labeled as such; it cannot establish the behavior of a deployed program without verified source/object correspondence.

## Principal delivery risks

| Risk | Owner | Mitigation and decision point |
| --- | --- | --- |
| Old host lacks compatible secure connectivity or expected SQL catalogs | AS/400 integration lead | Prove compatibility in discovery; use approved exports for early source work and separately estimate any legacy adapter |
| Missing source, copybooks, record definitions or business glossary | Customer application owner | Inventory dependencies and define supported explanation cases; make missing evidence visible and exclude unsupported cases from correctness claims |
| Internal model quality or capacity is insufficient | Retrieval/ML lead | Benchmark representative tasks and concurrent load before selecting models/hardware; narrow pilot scope or revise capacity explicitly |
| Ticket/source permissions cannot be mapped reliably | Identity/security lead | Deny shared indexing/retrieval for unmapped resources; agree a verifiable workspace access model with source-system owners |
| Parser or scanner has incomplete legacy-language coverage | IBM i specialist + QA | Publish a tested coverage matrix; distinguish text explanation, structural analysis, scanning and executable transformation support |
| A proposed modernization changes business behavior | Modernization lead + customer reviewer | Require characterization tests, differential checks and a test-host rollout; keep production promotion under existing change control |
| Required infrastructure or customer review access arrives late | Delivery lead | Track prerequisites separately from engineering progress and reforecast the affected acceptance milestone |

## Acceptance and evaluation

The following are proposed acceptance gates to confirm in discovery. They describe how success will be measured; no accuracy or performance result is claimed today.

| Capability | Proposed gate |
| --- | --- |
| Residency | All pilot workflows complete with public egress blocked; network and endpoint tests detect and deny attempted external calls, including redirects and worker/tool traffic |
| Authorization | All defined cross-user/resource denial tests pass, including search, dependency expansion, citations, cache reuse, exports and permission revocation |
| Program explanation | Customer experts accept at least 90% of the agreed representative cases with no critical business-logic misstatement in accepted answers; every code-specific assertion has evidence or is marked inference |
| SQL drafting | At least 90% semantic correctness against reviewed expected results for supported benchmark questions; 100% of the defined unauthorized/write/side-effect cases blocked in pilot mode |
| Citation integrity | All emitted citations resolve to the referenced authorized snapshot and source span; missing dependencies and source/version conflicts are surfaced |
| Retrieval | Required evidence appears in the top ten results for at least 90% of a held-out, access-filtered question set; assess exact identifiers separately |
| Agent operation | Cancellation, restart, exhausted budget, duplicate retry, stale patch and conflicting-change scenarios complete safely with accurate job state and audit |
| Modernization | Selected packages compile/run on target systems and pass agreed characterization and differential tests before any production promotion |
| Operations | Customer-approved backup restoration, rollback, key rotation, retention and audit access exercises pass on the deployment topology |

An initial proposed quality set contains 120 cases: 40 program explanations across agreed languages/formats, 40 SQL questions, 20 document/ticket questions and 20 ambiguous/missing-evidence questions. Add a separate adversarial suite for prompt injection, source ACLs, SQL routines, network destinations, parser inputs and agent tool misuse. Keep evaluation questions and expected answers out of tuning/development sets. Version source snapshots, model weights, prompts, parsers and tool rules so comparisons remain reproducible.

Benchmark two or three approved internal model candidates using the real tasks. Record accuracy, context capacity, time to first output, total latency, peak memory and throughput under single-user and concurrent load. Set the latency and concurrency service objectives after this benchmark; do not buy hardware or promise a model size from an unmeasured assumption. Embedding, reranking and generation models each require licensing and capacity review.

## Initial engineering backlog

Start with these implementation tickets after the plan is accepted for delivery:

1. Establish the application repository/release baseline; isolate app tests from vendored training suites; triage reported dependency findings and add reproducible checks.
2. Document deployment policy, threat/data-flow model, resource authorization contract and audit schema; define the discovery questionnaire and sample-data contract.
3. Extract a thin reusable application core and service skeleton, preserving current desktop behavior through regression tests.
4. Implement mandatory internal provider routing with destination validation, authenticated TLS, no fallback and egress-denial tests.
5. Add enterprise identity and effective resource/tool authorization; enforce the same policy in desktop, API and CLI paths.
6. Create the Db2i connection/capability model and an ODBC feasibility spike. Demonstrate verified TLS, metadata access, exact-value handling and cancellation on a real test system before committing to the adapter.
7. Add a versioned source/evidence contract and representative synthetic RPG/CL/COBOL/DDS fixtures; evaluate parser coverage and original-line preservation.
8. Connect the existing preparation/search work to an ACL-aware internal retrieval prototype and implement navigable citations.
9. Build the two customer example workflows end to end and establish the held-out evaluation harness.
10. Use pilot measurements to finalize the orchestrator, infrastructure sizing and modernization package scope.

## Outstanding discovery decisions

| Decision | Information needed | Default until resolved |
| --- | --- | --- |
| IBM i compatibility | IBM i is confirmed; obtain hardware/partition, exact release, Technology Refresh/PTF levels, libraries, authentication, driver/TLS availability, test host | Capability-driven design; individual driver/catalog/service support and release certification remain unconfirmed |
| Source access | Git/IFS/source members, language dialects, copybooks, compiled/source mapping | Export-based fixtures for development; connector choice remains open |
| Business meaning | Definitions of open orders, entity ownership, company/date scope | Require evidence or clarification; never invent status-code mappings |
| Documents and tickets | Systems, access metadata, attachments, internal API/export options | Controlled imports preserving source permissions |
| Inference and capacity | Available GPUs, model rights, user concurrency, latency targets | Internal model gateway plus benchmark; no hardware commitment |
| Identity and deployment | Identity provider, certificate authority, internal platform and secret store | Standard identity/API boundaries; platform chosen during discovery |
| Operations and controls | Retention, audit ownership, recovery targets, required control framework | Explicit policies and evidence; avoid jurisdiction assumptions |
| Delivery and ownership | Budget, deadline, support SLA, code/IP rights, vendor dependencies, IBM interoperability | Phased estimates above; scope and commercial obligations unresolved |

The next delivery decision is the Phase 0 scope and staffing. Completion of that phase should produce a measured, customer-specific pilot commitment and a prioritized enterprise backlog.
