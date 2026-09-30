import { invoke } from "@tauri-apps/api/core";
import type { AgentMode, AiConnectionTest, AiSettings, AiSettingsInput, BundledContent, ChatMessage, ChatSession, ConnectionProfile, ProfileInput, QueryAssessment, QueryOutput, QueryResult, SchemaSnapshot, SourceImport } from "./types";
import { assessBrowserQuery } from "./queryAssessment";

const nativeApp = "__TAURI_INTERNALS__" in window;
const now = () => new Date().toISOString(); const id = () => crypto.randomUUID();
const schema: SchemaSnapshot = { engine: "sqlite", capturedAt: now(), tables: [
  { schema: "main", name: "customers", kind: "table", columns: [{ name: "id", dataType: "INTEGER", nullable: false, key: "PK" }, { name: "name", dataType: "TEXT", nullable: false }, { name: "created_at", dataType: "DATETIME", nullable: false }] },
  { schema: "main", name: "orders", kind: "table", columns: [{ name: "id", dataType: "INTEGER", nullable: false, key: "PK" }, { name: "customer_id", dataType: "INTEGER", nullable: false }, { name: "total", dataType: "DECIMAL", nullable: false }, { name: "created_at", dataType: "DATETIME", nullable: false }] }
] };
type Store = { profiles: ConnectionProfile[]; sessions: ChatSession[]; messages: Record<string, ChatMessage[]>; schemas: Record<string, SchemaSnapshot>; outputs: Record<string, QueryOutput[]> };
const storageKey = "querycraft-browser-demo";
const store = (): Store => { const value = JSON.parse(localStorage.getItem(storageKey) || '{"profiles":[],"sessions":[],"messages":{},"schemas":{},"outputs":{}}'); return { ...value, profiles: (value.profiles || []).map((profile: ConnectionProfile) => ({ ...profile, allowWrites: profile.allowWrites || false, tlsMode: profile.tlsMode || "verifyIdentity" })), sessions: (value.sessions || []).map((session: ChatSession) => ({ ...session, mode: session.mode || "plan" })), schemas: value.schemas || {}, outputs: value.outputs || {} }; };
const persist = (next: Store) => localStorage.setItem(storageKey, JSON.stringify(next));
const call = <T>(command: string, args?: Record<string, unknown>) => invoke<T>(command, args);
const demoResult: QueryResult = { columns: ["customer", "orders", "total_revenue"], rows: [["Ada Lovelace", 12, 1430.5], ["Grace Hopper", 9, 1098], ["Margaret Hamilton", 7, 846.25]], elapsedMs: 18, truncated: false };
export const api = {
  nativeApp,
  bundledContent: async (): Promise<BundledContent> => {
    if (!nativeApp) throw new Error("Bundled examples are available in the installed desktop application.");
    return call<BundledContent>("bundled_content");
  },
  openBundledContent: async () => {
    if (!nativeApp) throw new Error("Bundled examples are available in the installed desktop application.");
    return call<void>("open_bundled_content");
  },
  profiles: async () => nativeApp ? call<ConnectionProfile[]>("list_profiles") : store().profiles,
  saveProfile: async (profile: ProfileInput) => {
    if (nativeApp) return call<ConnectionProfile>("save_profile", { profile }); const state = store(); const old = state.profiles.find(p => p.id === profile.id);
    const saved: ConnectionProfile = { id: old?.id || id(), name: profile.name, engine: profile.engine, host: profile.host, port: profile.port, database: profile.database, username: profile.username, sqlitePath: profile.sqlitePath, allowWrites: profile.allowWrites, tlsMode: profile.tlsMode, createdAt: old?.createdAt || now() };
    state.profiles = [...state.profiles.filter(p => p.id !== saved.id), saved]; persist(state); return saved;
  },
  deleteProfile: async (profileId: string) => { if (nativeApp) return call<void>("delete_profile", { id: profileId }); const state = store(); const sessionIds = state.sessions.filter(s => s.profileId === profileId).map(s => s.id); state.profiles = state.profiles.filter(p => p.id !== profileId); state.sessions = state.sessions.filter(s => s.profileId !== profileId); sessionIds.forEach(sessionId => { delete state.messages[sessionId]; delete state.outputs[sessionId]; }); delete state.schemas[profileId]; persist(state); },
  importSourceProject: async (path: string): Promise<SourceImport> => call<SourceImport>("import_source_project", { path }),
  importBrowserProject: async (files: FileList): Promise<SourceImport> => {
    const state = store(); const selected = Array.from(files).filter(file => (/\.(sql|prisma|py|ts|tsx|js|jsx|mjs|cjs)$/i.test(file.name) || /^(package\.json|requirements\.txt|pyproject\.toml|chroma\.sqlite3)$/i.test(file.name)) && !file.name.startsWith(".") && !/(secret|credential|password)/i.test(file.name) && (file.name === "chroma.sqlite3" || file.size <= 1_000_000) && !/(^|\/)(node_modules|\.git|target|vendor|dist|build)\//i.test(file.webkitRelativePath)).slice(0, 1000);
    let total = 0; const tables: SchemaSnapshot["tables"] = []; const chromaCandidates: SchemaSnapshot["tables"] = []; let matched = 0; let chromaDetected = false; let sourceLanguage: SchemaSnapshot["sourceLanguage"];
    for (const file of selected) {
      if (file.name === "chroma.sqlite3") { chromaDetected = true; matched++; continue; }
      if (total + file.size > 16_000_000) break; total += file.size;
      const body = await file.text(); const sourceFile = file.webkitRelativePath;
      const found: SchemaSnapshot["tables"] = [];
      const isCode = /\.(py|ts|tsx|js|jsx|mjs|cjs)$/i.test(file.name);
      const hasChroma = /\bchromadb\b|\blangchain_chroma\b|@langchain\/chroma|\/vectorstores\/chroma|\bChromaClient\b|\bPersistentClient\b/i.test(body);
      if (hasChroma) { chromaDetected = true; if (isCode && !sourceLanguage) sourceLanguage = /\.py$/i.test(file.name) ? "python" : "typescript"; }
      if (isCode) {
        const names = new Set<string>();
        for (const match of body.matchAll(/\b(?:get_or_create_collection|create_collection|get_collection)\s*\(\s*(?:name\s*=\s*)?["']([A-Za-z0-9_.-]{3,80})["']/gi)) names.add(match[1]);
        for (const match of body.matchAll(/\b(?:getOrCreateCollection|createCollection|getCollection)\s*\(\s*\{[^}]{0,500}?\bname\s*:\s*["']([A-Za-z0-9_.-]{3,80})["']/gi)) names.add(match[1]);
        for (const match of body.matchAll(/\b(?:collection_name\s*=|collectionName\s*:)\s*["']([A-Za-z0-9_.-]{3,80})["']/gi)) names.add(match[1]);
        for (const name of names) chromaCandidates.push({ schema: "chroma", name, kind: "collection", columns: [{ name: "id", dataType: "string", nullable: false }, { name: "document", dataType: "text", nullable: true }, { name: "metadata", dataType: "object", nullable: true }, { name: "embedding", dataType: "vector", nullable: true }, { name: "uri", dataType: "string", nullable: true }], sourceFile });
      }
      if (/\.prisma$/i.test(file.name)) {
        for (const match of body.matchAll(/\bmodel\s+([A-Za-z_]\w*)\s*\{([^}]*)\}/g)) {
          const columns = Array.from(match[2].matchAll(/^\s*([A-Za-z_]\w*)\s+(String|Int|BigInt|Float|Decimal|Boolean|DateTime|Bytes|Json)(\?)?(?=\s|\[|$)([^\n]*)/gm)).map(f => ({ name: f[1], dataType: f[2], nullable: !!f[3], key: f[4].includes("@id") ? "PK" : undefined }));
          if (columns.length) found.push({ schema: "inferred", name: match[1], kind: "table", columns, sourceFile });
        }
      } else {
        const withoutComments = body.replace(/--[^\n]*|\/\*[\s\S]*?\*\//g, " ");
        for (const match of withoutComments.matchAll(/\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*\(([\s\S]*?)\)\s*;/gi)) {
          const parts = match[1].split("."); const columns = Array.from(match[2].matchAll(/(?:^|,)\s*([A-Za-z_]\w*)\s+([A-Za-z_]\w*(?:\([^)]*\))?)([^,]*)/gi)).filter(c => !/^(CONSTRAINT|PRIMARY|FOREIGN|UNIQUE|CHECK|KEY)$/i.test(c[1])).map(c => ({ name: c[1], dataType: c[2], nullable: !/NOT\s+NULL|PRIMARY\s+KEY/i.test(c[3]), key: /PRIMARY\s+KEY/i.test(c[3]) ? "PK" : undefined }));
          if (columns.length) found.push({ schema: parts.length === 2 ? parts[0] : "inferred", name: parts[parts.length - 1], kind: "table", columns, sourceFile });
        }
      }
      if (found.length || hasChroma) matched++;
      tables.push(...found);
    }
    if (chromaDetected) tables.push(...chromaCandidates.filter((candidate, index) => chromaCandidates.findIndex(other => other.name === candidate.name) === index));
    const sourceKind: SchemaSnapshot["sourceKind"] = chromaDetected ? tables.some(table => table.kind === "table") ? "mixed" : "chroma" : tables.length ? "sql" : "unknown";
    const profile: ConnectionProfile = { id: id(), name: files[0]?.webkitRelativePath.split("/")[0] || "Project source", engine: "source", sourcePath: "Browser-selected folder", allowWrites: false, tlsMode: "verifyIdentity", createdAt: now() };
    const snapshot: SchemaSnapshot = { engine: "source", tables, capturedAt: now(), sourceKind, sourceLanguage };
    state.profiles.push(profile); state.schemas[profile.id] = snapshot; persist(state);
    return { profile, schema: snapshot, scannedFiles: selected.length, matchedFiles: matched, warnings: ["Browser preview uses a simplified parser. Open the desktop app for fuller local analysis.", ...(sourceKind === "unknown" ? ["No supported SQL, Prisma, or Chroma structure was found."] : []), ...(sourceKind === "chroma" && !chromaCandidates.length ? ["Chroma was detected, but the browser preview cannot read its collection catalog. Use the desktop app."] : [])] };
  },
  testProfile: async (profile: ProfileInput) => nativeApp ? call<{ engine: string; message: string }>("test_profile", { profile }) : ({ engine: profile.engine, message: "Browser demo connection verified." }),
  schema: async (profileId: string) => nativeApp ? call<SchemaSnapshot>("load_schema", { profileId }) : store().schemas[profileId] || schema,
  refreshSchema: async (profileId: string) => nativeApp ? call<SchemaSnapshot>("refresh_schema", { profileId }) : (store().schemas[profileId] || { ...schema, capturedAt: now() }),
  assessQuery: async (profileId: string, sql: string) => {
    if (nativeApp) return call<QueryAssessment>("assess_query", { profileId, sql });
    const profile = store().profiles.find(item => item.id === profileId);
    if (!profile || profile.engine === "source") throw new Error("Project source is not a live database. Connect a database to run SQL.");
    return assessBrowserQuery(sql, profile.allowWrites);
  },
  executeQuery: async (profileId: string, sql: string, confirmed = false) => {
    if (nativeApp) return call<QueryResult>("execute_query", { profileId, sql, confirmed });
    const profile = store().profiles.find(item => item.id === profileId);
    if (!profile || profile.engine === "source") throw new Error("Project source is not a live database. Connect a database to run SQL.");
    const assessment = assessBrowserQuery(sql, profile.allowWrites);
    if (assessment.requiresConfirmation && !confirmed) throw new Error("This statement requires explicit confirmation.");
    return assessment.readOnly ? demoResult : { columns: ["operation", "affected_rows"], rows: [[assessment.label, 1]], elapsedMs: 12, truncated: false };
  },
  sessions: async (profileId: string) => nativeApp ? call<ChatSession[]>("list_sessions", { profileId }) : store().sessions.filter(s => s.profileId === profileId),
  newSession: async (profileId: string, shareResults = true) => { if (nativeApp) return call<ChatSession>("create_session", { profileId, shareResults }); const state = store(); const session: ChatSession = { id: id(), profileId, title: "New chat", shareResults, mode: "plan", createdAt: now() }; state.sessions.unshift(session); state.messages[session.id] = []; persist(state); return session; },
  setSessionSharing: async (sessionId: string, shareResults: boolean) => { if (nativeApp) return call<void>("set_session_sharing", { sessionId, shareResults }); const state = store(); state.sessions = state.sessions.map(s => s.id === sessionId ? { ...s, shareResults } : s); persist(state); },
  setSessionMode: async (sessionId: string, mode: AgentMode) => { if (nativeApp) return call<void>("set_session_mode", { sessionId, mode }); const state = store(); state.sessions = state.sessions.map(s => s.id === sessionId ? { ...s, mode } : s); persist(state); },
  messages: async (sessionId: string) => nativeApp ? call<ChatMessage[]>("list_messages", { sessionId }) : store().messages[sessionId] || [],
  queryOutputs: async (sessionId: string) => nativeApp ? call<QueryOutput[]>("list_query_outputs", { sessionId }) : store().outputs[sessionId] || [],
  saveQueryOutput: async (sessionId: string, sourceMessageId: string | undefined, title: string, sql: string) => {
    if (nativeApp) return call<QueryOutput>("save_query_output", { sessionId, sourceMessageId, title, sql });
    const state = store(); const existing = sourceMessageId ? (state.outputs[sessionId] || []).find(output => output.sourceMessageId === sourceMessageId) : undefined;
    if (existing) return existing;
    const createdAt = now(); const output: QueryOutput = { id: id(), sessionId, sourceMessageId, title, sql, collapsed: false, createdAt, updatedAt: createdAt };
    state.outputs[sessionId] = [output, ...(state.outputs[sessionId] || [])]; persist(state); return output;
  },
  updateQueryOutput: async (outputId: string, sql: string, result?: QueryResult) => {
    if (nativeApp) return call<QueryOutput>("update_query_output", { outputId, sql, result });
    const state = store(); let updated: QueryOutput | undefined;
    for (const sessionId of Object.keys(state.outputs)) state.outputs[sessionId] = state.outputs[sessionId].map(output => output.id === outputId ? (updated = { ...output, sql, result, updatedAt: now() }) : output);
    if (!updated) throw new Error("Query output was not found."); persist(state); return updated;
  },
  setQueryOutputCollapsed: async (outputId: string, collapsed: boolean) => {
    if (nativeApp) return call<void>("set_query_output_collapsed", { outputId, collapsed });
    const state = store(); for (const sessionId of Object.keys(state.outputs)) state.outputs[sessionId] = state.outputs[sessionId].map(output => output.id === outputId ? { ...output, collapsed, updatedAt: now() } : output); persist(state);
  },
  deleteQueryOutput: async (outputId: string) => {
    if (nativeApp) return call<void>("delete_query_output", { outputId });
    const state = store(); for (const sessionId of Object.keys(state.outputs)) state.outputs[sessionId] = state.outputs[sessionId].filter(output => output.id !== outputId); persist(state);
  },
  exportQueryOutput: async (output: QueryOutput) => {
    if (nativeApp) return call<string | null>("export_query_output", { outputId: output.id });
    const blob = new Blob([JSON.stringify(output, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const link = document.createElement("a");
    link.href = url; link.download = `agentsql-output-${output.id.slice(0, 8)}.json`; link.click(); URL.revokeObjectURL(url); return link.download;
  },
  ask: async (sessionId: string, message: string, result?: QueryResult) => {
    if (nativeApp) return call<ChatMessage>("ask_agent", { sessionId, message, result }); const state = store(); const user: ChatMessage = { id: id(), role: "user", content: message, createdAt: now() };
    const currentSession = state.sessions.find(s => s.id === sessionId); const currentProfile = state.profiles.find(p => p.id === currentSession?.profileId);
    const currentSchema = currentProfile?.engine === "source" ? state.schemas[currentProfile.id] : undefined;
    const firstTable = currentSchema?.tables.find(table => table.kind === "table");
    const firstCollection = currentSchema?.tables.find(table => table.kind === "collection");
    let content = currentSession?.mode === "plan" ? "## Let’s shape the query\n\n### 1. Which time range should apply?\n\n- **A.** Current month\n- **B.** Current year\n- **C.** All available data\n- **Other — add remarks**\n\n### 2. How should results be grouped?\n\n- **A.** Customer\n- **B.** Month\n- **C.** Customer and month\n- **Other — add remarks**\n\n### Agreed so far\n\n- Use the available customer and order schema.\n\nReply with your choices and any remarks, or use `/generate` when ready." : currentSession?.mode === "chat" ? "## Schema alignment\n\nThe available schema contains `customers` and `orders`, connected through the customer identifier. We can discuss business definitions, suitable metrics, joins, and data-quality concerns here.\n\nChat mode does not generate SQL. Switch to **Direct** or use `/direct` when you want a query." : "I used the available `customers` and `orders` schema. Review this read-only query before running it:\n\n```sql\nSELECT c.name AS customer, COUNT(o.id) AS orders, SUM(o.total) AS total_revenue\nFROM customers c JOIN orders o ON o.customer_id = c.id\nGROUP BY c.id, c.name ORDER BY total_revenue DESC LIMIT 100;\n```";
    if (currentSession?.mode === "direct" && currentSchema?.sourceKind === "chroma") content = firstCollection ? currentSchema.sourceLanguage === "typescript" ? `Browser preview only: Chroma collection ${firstCollection.name} was inferred from source. This is a read-only draft, not executed.\n\n\`\`\`typescript\nconst collection = await client.getCollection({ name: "${firstCollection.name}" });\nconst results = await collection.query({ queryTexts: [${JSON.stringify(message)}], nResults: 10 });\n\`\`\`` : `Browser preview only: Chroma collection ${firstCollection.name} was inferred from source. This is a read-only draft, not executed.\n\n\`\`\`python\ncollection = client.get_collection(name="${firstCollection.name}")\nresults = collection.query(query_texts=[${JSON.stringify(message)}], n_results=10)\n\`\`\`` : "Chroma use was detected, but the collection name is set dynamically. Tell me the collection name before drafting a read-only query.";
    else if (currentSession?.mode === "direct" && currentSchema) content = firstTable ? `Browser preview only: I found ${firstTable.schema}.${firstTable.name} in the selected source. This inferred schema may differ from a live database. Review this draft; it cannot run until you connect a database.\n\n\`\`\`sql\nSELECT * FROM ${firstTable.name} LIMIT 100;\n\`\`\`` : "No supported structure was inferred. Try the desktop app with SQL migrations, Prisma, or Chroma source files.";
    const assistant: ChatMessage = { id: id(), role: "assistant", content, createdAt: now() };
    state.messages[sessionId] = [...(state.messages[sessionId] || []), user, assistant];
    state.sessions = state.sessions.map(item => item.id === sessionId && item.title === "New chat" ? { ...item, title: message.replace(/\s+/g, " ").trim().slice(0, 64) } : item);
    persist(state); return assistant;
  },
  settings: async (): Promise<AiSettings> => nativeApp ? call<AiSettings>("ai_settings") : ({ provider: "openai", model: "browser demo responses", baseUrl: "https://api.openai.com/v1", configured: true, configPath: "Browser demo — desktop app uses its .env file" }),
  saveAiSettings: async (settings: AiSettingsInput): Promise<AiSettings> => nativeApp ? call<AiSettings>("save_ai_settings", { settings }) : ({ provider: settings.provider, model: settings.model, baseUrl: settings.baseUrl, configured: settings.provider === "ollama" || settings.provider === "lmstudio" || !!settings.apiKey, configPath: "Browser demo — settings are not sent anywhere" }),
  testAiProvider: async (settings: AiSettingsInput): Promise<AiConnectionTest> => nativeApp ? call<AiConnectionTest>("test_ai_provider", { settings }) : ({ provider: settings.provider, model: settings.model, baseUrl: settings.baseUrl, message: "Browser demo settings are valid. Use the desktop app to test a real provider.", availableModels: [settings.model] }),
  deleteSession: async (sessionId: string) => { if (nativeApp) return call<void>("delete_session", { sessionId }); const state = store(); state.sessions = state.sessions.filter(s => s.id !== sessionId); delete state.messages[sessionId]; delete state.outputs[sessionId]; persist(state); }
};
