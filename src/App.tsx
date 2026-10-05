import { ChangeEvent, CSSProperties, FormEvent, PointerEvent as ReactPointerEvent, useEffect, useMemo, useRef, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { api } from "./api";
import type { AgentMode, AiSettings, ChatMessage, ChatSession, ConnectionProfile, DatabaseEngine, ProfileInput, QueryAssessment, QueryOutput, QueryResult, SchemaSnapshot } from "./types";
import dexmondLogo from "./assets/brand/dexmond-favicon.png";
import { HelpModal } from "./HelpModal";
import { AiSettingsModal } from "./AiSettingsModal";
import { MessageContent } from "./MessageContent";

const engines: { value: DatabaseEngine; label: string }[] = [
  { value: "auto", label: "Auto-detect server" }, { value: "postgres", label: "PostgreSQL" },
  { value: "mysql", label: "MySQL" }, { value: "sqlserver", label: "SQL Server" }, { value: "sqlite", label: "SQLite file" }
];
const newProfile = (): ProfileInput => ({ name: "", engine: "auto", host: "localhost", database: "", username: "", allowWrites: false, tlsMode: "verifyIdentity" });
const agentModes: { value: AgentMode; label: string; short: string }[] = [
  { value: "plan", label: "Plan / Grill", short: "Refine requirements through focused questions and choices." },
  { value: "chat", label: "Chat", short: "Discuss and align without generating a query." },
  { value: "direct", label: "Direct generation", short: "Generate one query from a clear request for your review." }
];
const slashCommands = [
  { command: "/plan", description: "Switch to Plan / Grill mode" },
  { command: "/chat", description: "Switch to discussion-only mode" },
  { command: "/direct", description: "Switch to direct generation" },
  { command: "/generate", description: "Generate from the agreed plan now" },
  { command: "/remarks", description: "Add constraints or comments to the plan" },
  { command: "/help", description: "Show these commands" }
];
const clamp = (value: number, minimum: number, maximum: number) => Math.min(maximum, Math.max(minimum, value));
const savedSize = (key: string, fallback: number) => {
  const parsed = Number(window.localStorage.getItem(key));
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
};
const displayDate = (value: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));

export default function App() {
  const [theme, setTheme] = useState<"light" | "dark">(() => window.localStorage.getItem("agentsql.theme") === "dark" ? "dark" : "light");
  const [profiles, setProfiles] = useState<ConnectionProfile[]>([]);
  const [profile, setProfile] = useState<ConnectionProfile>();
  const [schema, setSchema] = useState<SchemaSnapshot>();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [session, setSession] = useState<ChatSession>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("SELECT *\nFROM ");
  const [result, setResult] = useState<QueryResult>();
  const [outputs, setOutputs] = useState<QueryOutput[]>([]);
  const [activeOutputId, setActiveOutputId] = useState<string>();
  const [closeOutput, setCloseOutput] = useState<QueryOutput>();
  const [executionConfirm, setExecutionConfirm] = useState<{ assessment: QueryAssessment; sql: string }>();
  const [settings, setSettings] = useState<AiSettings>();
  const [form, setForm] = useState<ProfileInput>();
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [helpOpen, setHelpOpen] = useState(false);
  const [aiSettingsOpen, setAiSettingsOpen] = useState(false);
  const [commandsOpen, setCommandsOpen] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(() => savedSize("querycraft.sidebarWidth", 252));
  const [schemaWidth, setSchemaWidth] = useState(() => savedSize("querycraft.schemaWidth", 235));
  const [chatWidth, setChatWidth] = useState(() => savedSize("querycraft.chatWidth", 390));
  const browserFolder = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const available = await refreshProfiles();
        const remembered = window.localStorage.getItem("agentsql.activeProfile");
        const initial = available.find(item => item.id === remembered) || available[0];
        if (initial) await selectProfile(initial);
      } catch (e) { showError(e); }
    })();
    void api.settings().then(setSettings).catch(showError);
  }, []);
  useEffect(() => { document.documentElement.dataset.theme = theme; window.localStorage.setItem("agentsql.theme", theme); }, [theme]);
  useEffect(() => { window.localStorage.setItem("querycraft.sidebarWidth", String(sidebarWidth)); }, [sidebarWidth]);
  useEffect(() => { window.localStorage.setItem("querycraft.schemaWidth", String(schemaWidth)); }, [schemaWidth]);
  useEffect(() => { window.localStorage.setItem("querycraft.chatWidth", String(chatWidth)); }, [chatWidth]);
  async function refreshProfiles() { try { const available = await api.profiles(); setProfiles(available); return available; } catch (e) { showError(e); return []; } }
  function showError(e: unknown) { setNotice(e instanceof Error ? e.message : String(e)); }
  async function loadBundledExample() {
    if (!api.nativeApp) return; setBusy("example");
    try {
      const content=await api.bundledContent();const available=await api.profiles();
      let saved=available.find(item=>item.engine==="sqlite"&&item.sqlitePath===content.exampleDatabasePath);
      if(!saved)saved=await api.saveProfile({name:"Synthetic Core Banking",engine:"sqlite",sqlitePath:content.exampleDatabasePath,allowWrites:false,tlsMode:"verifyIdentity"});
      await refreshProfiles();await selectProfile(saved);setSchema(await api.refreshSchema(saved.id));
      setNotice("Bundled core-banking example loaded. It is synthetic and ready for local querying.");
    }catch(e){showError(e);}finally{setBusy(undefined);}
  }
  async function openBundledContent(){try{await api.openBundledContent();setNotice("Opened the installed examples and documentation folder.");}catch(e){showError(e);}}

  async function selectProfile(next: ConnectionProfile) {
    window.localStorage.setItem("agentsql.activeProfile",next.id);
    setProfile(next); setResult(undefined); setSchema(undefined); setSessions([]); setSession(undefined); setMessages([]); setOutputs([]); setActiveOutputId(undefined); setDraft(next.engine === "source" ? "" : "SELECT *\nFROM ");
    try { const cached = await api.schema(next.id); setSchema(cached); if (next.engine === "source" && api.nativeApp && !cached.sourceKind) setSchema(await api.refreshSchema(next.id)); } catch { /* no cached schema is expected for a new profile */ }
    try { const available = await api.sessions(next.id); setSessions(available); const remembered = window.localStorage.getItem(`agentsql.activeSession.${next.id}`); const initial = available.find(item => item.id === remembered) || available[0]; if (initial) await selectSession(initial,next); } catch (e) { showError(e); }
  }
  async function selectSession(next: ChatSession, owner=profile) {
    setSession(next); window.localStorage.setItem(`agentsql.activeSession.${next.profileId}`,next.id);
    try {
      const [savedMessages,savedOutputs]=await Promise.all([api.messages(next.id),api.queryOutputs(next.id)]);
      setMessages(savedMessages);setOutputs(savedOutputs);
      const first=savedOutputs[0];setActiveOutputId(first?.id);setDraft(first?.sql || (owner?.engine === "source" ? "" : "SELECT *\nFROM "));setResult(first?.result);
    } catch (e) { showError(e); }
  }
  async function createSession() { if (!profile) return; try { const created=await api.newSession(profile.id);setSessions(current=>[created,...current]);await selectSession(created); } catch (e) { showError(e); } }
  async function toggleSharing() { if (!session) return; const next = !session.shareResults; try { await api.setSessionSharing(session.id, next); setSession({ ...session, shareResults: next }); } catch (e) { showError(e); } }
  async function changeMode(mode: AgentMode) { if (!session) return; try { await api.setSessionMode(session.id, mode); setSession(current => current ? { ...current, mode } : current); setCommandsOpen(false); setNotice(`${agentModes.find(item => item.value === mode)?.label} mode selected.`); } catch (e) { showError(e); } }
  async function eraseChat() { if (!session || !profile) return; try { await api.deleteSession(session.id); const remaining=await api.sessions(profile.id);setSessions(remaining);setSession(undefined);setMessages([]);setOutputs([]);setActiveOutputId(undefined);setResult(undefined);if(remaining[0])await selectSession(remaining[0]);setNotice("The local conversation and its saved output cards were deleted."); } catch (e) { showError(e); } }
  async function refreshSchema() {
    if (!profile) return; setBusy("schema");
    if (profile.engine === "source" && !api.nativeApp) { setBusy(undefined); setNotice("Choose the folder again to update the browser preview."); return; }
    try { setSchema(await api.refreshSchema(profile.id)); setNotice(profile.engine === "source" ? "Project schema re-analyzed locally." : "Schema refreshed locally."); } catch (e) { showError(e); } finally { setBusy(undefined); }
  }
  async function openProjectFolder() {
    if (!api.nativeApp) { browserFolder.current?.click(); return; }
    try {
      const path = await open({ directory: true, multiple: false, title: "Choose a project source folder" });
      if (!path || typeof path !== "string") return;
      setBusy("import"); const imported = await api.importSourceProject(path);
      await refreshProfiles(); await selectProfile(imported.profile); setSchema(imported.schema);
      setNotice(`Found ${imported.schema.tables.length} database objects in ${imported.matchedFiles} files. ${imported.warnings.join(" ")}`);
    } catch (e) { showError(e); } finally { setBusy(undefined); }
  }
  async function onBrowserFolder(event: ChangeEvent<HTMLInputElement>) {
    const files = event.target.files; if (!files?.length) return; setBusy("import");
    try { const imported = await api.importBrowserProject(files); await refreshProfiles(); await selectProfile(imported.profile); setSchema(imported.schema); setNotice(`Found ${imported.schema.tables.length} database objects. ${imported.warnings.join(" ")}`); }
    catch (e) { showError(e); } finally { setBusy(undefined); event.target.value = ""; }
  }
  async function importIbmiCatalog() {
    if (!api.nativeApp) return;
    try {
      const path = await open({ directory: false, multiple: false, title: "Import an IBM i catalog snapshot", filters: [{ name: "IBM i catalog export", extensions: ["json"] }] });
      if (!path || typeof path !== "string") return;
      setBusy("import");
      const imported = await api.importSourceProject(path);
      await refreshProfiles(); await selectProfile(imported.profile); setSchema(imported.schema);
      setNotice(`Imported ${imported.schema.tables.length} catalog objects. ${imported.warnings.join(" ")}`);
    } catch (e) { showError(e); } finally { setBusy(undefined); }
  }
  async function removeSource() {
    if (!profile || profile.engine !== "source" || !window.confirm(`Remove the local project analysis for ${profile.name}? Your source files will not be deleted.`)) return;
    try { await api.deleteProfile(profile.id); setProfile(undefined); setSchema(undefined); setSessions([]); setSession(undefined); setMessages([]);setOutputs([]);setActiveOutputId(undefined); await refreshProfiles(); setNotice("Project analysis and its local chats were removed. Source files were untouched."); } catch (e) { showError(e); }
  }
  async function saveExecution(next: QueryResult, assessment: QueryAssessment, sql: string) {
    if (!profile) return;
    let workingSession=session;
    if(!workingSession){workingSession=await api.newSession(profile.id);setSessions(current=>[workingSession!,...current]);setSession(workingSession);}
    let output=outputs.find(item=>item.id===activeOutputId && item.sql.trim()===sql.trim());
    if(!output)output=await api.saveQueryOutput(workingSession.id,undefined,assessment.label,sql);
    const updated=await api.updateQueryOutput(output.id,sql,next);
    setOutputs(current=>[updated,...current.filter(item=>item.id!==updated.id)]);setActiveOutputId(updated.id);setResult(next);
    setNotice(next.truncated ? "Result saved and capped at 10,000 rows." : assessment.readOnly ? "Read query completed and saved." : `${assessment.label} completed and saved to local history.`);
  }
  async function executeAssessed(assessment: QueryAssessment, sql: string, confirmed: boolean) {
    if (!profile) return; setBusy("query");
    try {
      const next=await api.executeQuery(profile.id,sql,confirmed);await saveExecution(next,assessment,sql);setExecutionConfirm(undefined);
    } catch (e) { showError(e); } finally { setBusy(undefined); }
  }
  async function runQuery() {
    if (!profile || !draft.trim()) return; setBusy("review");
    try { const assessment=await api.assessQuery(profile.id,draft);if(assessment.requiresConfirmation){setExecutionConfirm({assessment,sql:draft});setBusy(undefined);return;}await executeAssessed(assessment,draft,false); }
    catch(e){showError(e);setBusy(undefined);}
  }
  function selectOutput(output:QueryOutput){setActiveOutputId(output.id);setDraft(output.sql);setResult(output.result);}
  async function toggleOutput(output:QueryOutput){const collapsed=!output.collapsed;setOutputs(current=>current.map(item=>item.id===output.id?{...item,collapsed}:item));try{await api.setQueryOutputCollapsed(output.id,collapsed);}catch(e){showError(e);}}
  async function copyOutput(output:QueryOutput){try{await navigator.clipboard.writeText(output.sql);setNotice("Query copied to the clipboard.");}catch(e){showError(e);}}
  async function exportOutput(output:QueryOutput){try{const destination=await api.exportQueryOutput(output);if(destination)setNotice(`Output exported to ${destination}`);}catch(e){showError(e);}}
  async function confirmCloseOutput(){if(!closeOutput)return;try{await api.deleteQueryOutput(closeOutput.id);const remaining=outputs.filter(item=>item.id!==closeOutput.id);setOutputs(remaining);if(activeOutputId===closeOutput.id){const next=remaining[0];setActiveOutputId(next?.id);setDraft(next?.sql || (profile?.engine==="source"?"":"SELECT *\nFROM "));setResult(next?.result);}setCloseOutput(undefined);setNotice("Output removed. Its original chat message is still in the conversation.");}catch(e){showError(e);}}
  async function sendPrompt(event: FormEvent) {
    event.preventDefault(); if (!session || !prompt.trim()) return;
    const raw = prompt.trim(); let text = raw; let activeMode = session.mode;
    if (raw.startsWith("/")) {
      const [command, ...parts] = raw.split(/\s+/); const remainder = parts.join(" ").trim();
      if (command === "/help") { setCommandsOpen(true); setPrompt(""); return; }
      if (command === "/plan" || command === "/chat" || command === "/direct") {
        activeMode = command.slice(1) as AgentMode; await changeMode(activeMode); setPrompt("");
        if (!remainder) return; text = remainder;
      } else if (command === "/generate") {
        activeMode = "direct"; await changeMode(activeMode); text = remainder || "Generate the final query using the decisions agreed in this conversation.";
      } else if (command === "/remarks") {
        if (!remainder) { setCommandsOpen(true); setNotice("Add your notes after /remarks."); return; }
        activeMode = "plan"; await changeMode(activeMode); text = `Additional remarks: ${remainder}`;
      } else { setCommandsOpen(true); setNotice(`Unknown command: ${command}`); return; }
    }
    setBusy("chat"); setPrompt(""); setCommandsOpen(false); setMessages(current => [...current, { id: "pending", role: "user", content: text, createdAt: new Date().toISOString() }]);
    try {
      const answer = await api.ask(session.id, text, session.shareResults ? result : undefined);
      setMessages(await api.messages(session.id));
      if(profile){const available=await api.sessions(profile.id);setSessions(available);const refreshed=available.find(item=>item.id===session.id);if(refreshed)setSession(refreshed);}
      if (activeMode === "direct") {
        const codePattern = profile?.engine === "source" ? /```(?:sql|python|typescript|javascript|ts|js)\s*([\s\S]*?)```/i : /```sql\s*([\s\S]*?)```/i; const foundDraft = answer.content.match(codePattern)?.[1];
        if (foundDraft) { const sql=foundDraft.trim();const output=await api.saveQueryOutput(session.id,answer.id,profile?.engine==="source"?"Generated draft":"Generated SQL",sql);setDraft(sql);setResult(output.result);setActiveOutputId(output.id);setOutputs(current=>[output,...current.filter(item=>item.id!==output.id)]); }
      }
    } catch (e) { showError(e); setMessages(current => current.filter(m => m.id !== "pending")); } finally { setBusy(undefined); }
  }
  async function saveProfile(event: FormEvent) {
    event.preventDefault(); if (!form) return; setBusy("profile");
    try { const saved = await api.saveProfile(form); await refreshProfiles(); setForm(undefined); await selectProfile(saved); setNotice(api.nativeApp ? "Profile saved. Credentials are stored in your operating system's secure vault." : "Browser demo profile saved locally. Do not enter real credentials here."); } catch (e) { showError(e); } finally { setBusy(undefined); }
  }
  async function testProfile() { if (!form) return; setBusy("test"); try { const tested = await api.testProfile(form); setNotice(`${tested.engine}: ${tested.message}`); } catch (e) { showError(e); } finally { setBusy(undefined); } }
  const tables = useMemo(() => schema?.tables ?? [], [schema]);
  const sourceKind = profile?.engine === "source" ? schema?.sourceKind : undefined;
  const isChroma = sourceKind === "chroma";
  const hasChromaCatalog = tables.some(table => table.kind === "collection" && table.sourceFile?.endsWith("chroma.sqlite3"));
  const currentMode = agentModes.find(item => item.value === session?.mode) || agentModes[0];

  const shellStyle = { "--sidebar-width": `${sidebarWidth}px` } as CSSProperties;
  const contentStyle = { "--schema-width": `${schemaWidth}px`, "--chat-width": `${chatWidth}px` } as CSSProperties;

  return <main className="app-shell" style={shellStyle}>
    <aside className="sidebar"><div className="brand"><img src={dexmondLogo} alt="Dexmond Technologies" /><div><strong>agentSQL</strong><small>by Dexmond Technologies</small></div></div>
      <button className="primary wide" onClick={() => setForm(newProfile())}>+ New connection</button>
      <button className="wide source-button" onClick={() => void openProjectFolder()} disabled={busy === "import"}>{busy === "import" ? "Analyzing folder…" : "⌁ Open project folder"}</button>
      {api.nativeApp && <button className="wide source-button" onClick={() => void importIbmiCatalog()} disabled={busy === "import"}>Import IBM i catalog snapshot</button>}
      <input ref={el => { browserFolder.current = el; el?.setAttribute("webkitdirectory", ""); }} type="file" multiple className="hidden-file" onChange={onBrowserFolder} aria-label="Choose a project folder" />
      <p className="section-label">CONNECTIONS & PROJECTS</p>
      <nav>{profiles.map(item => <button key={item.id} className={profile?.id === item.id ? "connection active" : "connection"} onClick={() => void selectProfile(item)}><span className="engine-dot">{item.engine.slice(0, 1).toUpperCase()}</span><span>{item.name}<small>{item.engine}</small></span></button>)}</nav>
      <div className="sidebar-tools"><button onClick={() => setAiSettingsOpen(true)}><span>⌁</span>AI provider</button><button onClick={() => setHelpOpen(true)}><span>?</span>Help & tutorials</button>{api.nativeApp&&<button onClick={()=>void openBundledContent()}><span>▣</span>Examples & documents</button>}</div>
      <button className="theme-toggle wide" onClick={() => setTheme(current => current === "light" ? "dark" : "light")} aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}><span>{theme === "light" ? "☾" : "☼"}</span>{theme === "light" ? "Dark mode" : "Light mode"}</button>
      <div className="sidebar-foot"><span className={settings?.configured ? "status ready" : "status"}></span>{settings?.configured ? `${settings.provider} · ${settings.model}` : "Add an API key to .env"}</div>
    </aside>
    <ResizeHandle label="Resize navigation" className="app-resize-handle" onResize={delta => setSidebarWidth(current => clamp(current + delta, 208, 380))} />
    <section className="workspace">
      {!api.nativeApp && <div className="source-banner" role="status">Browser demonstration: chat replies and query results use synthetic examples. Database connections and Qwen inference require the installed desktop application.</div>}
      {!profile ? <Welcome logo={dexmondLogo} onNew={() => setForm(newProfile())} onProject={() => void openProjectFolder()} onExample={api.nativeApp?()=>void loadBundledExample():undefined} exampleBusy={busy==="example"} configPath={settings?.configPath} /> : <>
        <header><div><p className="eyebrow">{profile.engine === "source" ? `PROJECT SOURCE · ${profile.sourcePath}` : `${profile.engine} · ${profile.database || profile.sqlitePath} · ${profile.allowWrites ? "WRITE ENABLED" : "READ ONLY"}`}</p><h1>{profile.name}</h1></div><div className="header-actions"><button onClick={() => void refreshSchema()} disabled={busy === "schema"}>{busy === "schema" ? "Refreshing…" : profile.engine === "source" ? sourceKind === "db2i" ? "Reload catalog file" : api.nativeApp ? "Re-analyze folder" : "Refresh help" : "Refresh schema"}</button>{profile.engine !== "source" && <button onClick={() => setForm({...profile,password:undefined})}>Edit connection</button>}{profile.engine === "source" && <button className="danger" onClick={() => void removeSource()}>Remove project</button>}<button className="primary" onClick={() => void createSession()}>New chat</button></div></header>
        {profile.engine === "source" && <div className="source-banner">{sourceKind === "db2i" ? `Db2 for i catalog snapshot captured ${schema?.capturedAt}. Importing it does not establish a live connection or verify its declared provenance.` : isChroma ? `Chroma vector database detected. Collection names ${hasChromaCatalog ? "were read from its local catalog" : "are inferred from code"}; record fields are Chroma's generic API shape, not verified metadata keys. No SQL is generated for this mode.` : sourceKind === "mixed" ? "Relational and Chroma structures detected. Drafts depend on which system you ask about; cross-database joins are not assumed." : "Relational schema inferred from SQL migrations or Prisma models."} Source files stay local; {api.nativeApp ? `normalized metadata is sent to ${settings?.provider || "your AI provider"} when you chat` : "browser preview chat uses sample replies"}. Drafts cannot run without a live connector.</div>}
        <div className="content-grid" style={contentStyle}>
          <section className="schema-pane panel"><div className="panel-title"><h2>{sourceKind === "db2i" ? "Catalog snapshot" : isChroma ? "Collections" : profile.engine === "source" ? "Inferred structure" : "Schema"}</h2><span>{tables.length} objects</span></div>{tables.length ? <div className="schema-list">{tables.map(table => <details key={`${table.schema}.${table.name}`}><summary><span>{table.kind === "view" ? "◫" : table.kind === "collection" ? "◎" : "▦"}</span>{table.schema}.{table.name}</summary>{table.sourceFile && <div className="source-file">{table.sourceFile}</div>}{table.columns.map(col => <div className="column" key={col.name}><span>{col.name}</span><small>{col.dataType}{col.key ? ` · ${col.key}` : ""}</small></div>)}</details>)}</div> : <Empty label={isChroma ? api.nativeApp ? "Chroma was found, but no collection names could be read. Re-analyze or inspect the project source." : "Chroma was found. Open this folder in the desktop app to read its collection catalog." : profile.engine === "source" ? "No supported database structure was found in this folder." : "Connect, then refresh the schema to begin."} />}</section>
          <ResizeHandle label="Resize schema panel" onResize={delta => setSchemaWidth(current => clamp(current + delta, 190, 430))} />
          <section className="chat-pane panel"><div className="panel-title chat-title"><div><h2>Ask about your data</h2><span>{profile.engine === "source" ? "Inferred structure and chat may be sent to your AI provider" : session?.shareResults ? "Results may be sent to your AI provider" : "Only schema and chat are shared"}</span></div>{session && <div className="chat-actions"><select className="session-select" value={session.id} onChange={event=>{const selected=sessions.find(item=>item.id===event.target.value);if(selected)void selectSession(selected);}} aria-label="Conversation history">{sessions.map(item=><option key={item.id} value={item.id}>{item.title}</option>)}</select><select className={`mode-select ${session.mode}`} value={session.mode} onChange={event => void changeMode(event.target.value as AgentMode)} aria-label="Agent interaction mode">{agentModes.map(mode => <option value={mode.value} key={mode.value}>{mode.label}</option>)}</select><button className="ghost command-button" onClick={() => setCommandsOpen(current => !current)} title="Slash commands">/</button>{profile.engine !== "source" && <button className="ghost" onClick={() => void toggleSharing()}>{session.shareResults ? "Stop sharing" : "Share results"}</button>}<button className="ghost danger" onClick={() => void eraseChat()}>Delete</button></div>}</div>
            {session && <div className={`mode-banner ${session.mode}`}><strong>{currentMode.label}</strong><span>{currentMode.short}</span></div>}
            <div className="messages">{!session ? <Empty label="Start a chat to work with your data." /> : messages.map(message => <article className={`message ${message.role}`} key={message.id}><span>{message.role === "assistant" ? "AI" : "YOU"}</span><MessageContent content={message.content} /></article>)}</div>
            {commandsOpen && session && <div className="command-menu"><div><strong>Slash commands</strong><button className="icon" onClick={() => setCommandsOpen(false)} aria-label="Close commands">×</button></div>{slashCommands.map(item => <button key={item.command} onClick={() => { setPrompt(`${item.command} `); setCommandsOpen(false); }}><code>{item.command}</code><span>{item.description}</span></button>)}</div>}
            <form className="prompt" onSubmit={sendPrompt}><textarea value={prompt} onChange={e => { setPrompt(e.target.value); if (e.target.value === "/") setCommandsOpen(true); }} placeholder={session?.mode === "plan" ? "Describe the goal, constraints, and any remarks…" : session?.mode === "chat" ? "Ask about the schema, meaning, or approach…" : isChroma ? "Describe the read-only Chroma request…" : "Describe the query to generate…"} rows={3} disabled={!session || busy === "chat"} /><div className="prompt-actions"><button type="button" className="slash-trigger" onClick={() => setCommandsOpen(current => !current)} disabled={!session}>/ commands</button><button className="primary" disabled={!session || busy === "chat"}>{busy === "chat" ? "Thinking…" : "Send"}</button></div></form>
          </section>
          <ResizeHandle label="Resize chat panel" onResize={delta => setChatWidth(current => clamp(current + delta, 300, 720))} />
          <section className="query-pane panel"><div className="panel-title"><div><h2>Query outputs</h2><span>{outputs.length} saved · {profile.engine === "source" ? "drafts cannot execute" : profile.allowWrites ? "writes require confirmation" : "read operations only"}</span></div><button className="primary" onClick={() => void runQuery()} disabled={busy === "query" || busy === "review" || profile.engine === "source" || !draft.trim()}>{busy === "query" ? "Running…" : busy === "review" ? "Reviewing…" : profile.allowWrites ? "Review & execute" : "Run current query"}</button></div>
            <div className="current-draft"><label>{isChroma ? "Current Chroma draft" : "Current SQL draft"}<small>{activeOutputId ? "Selected from saved outputs" : "Not saved until generated or run"}</small></label><textarea className="sql-editor" value={draft} onChange={e => setDraft(e.target.value)} spellCheck={false} placeholder={isChroma ? "A read-only Chroma query draft will appear here." : undefined} /></div>
            <div className="output-list" aria-label="Saved query outputs">
              {busy==="chat"&&session?.mode==="direct"&&<div className="output-pending"><span className="status ready"/>Generating a new query output…</div>}
              {!outputs.length&&busy!=="chat"?<Empty label="Generated queries and executed results will remain here until you close them."/>:outputs.map(output=><QueryOutputCard key={output.id} output={output} active={output.id===activeOutputId} onSelect={()=>selectOutput(output)} onToggle={()=>void toggleOutput(output)} onCopy={()=>void copyOutput(output)} onExport={()=>void exportOutput(output)} onClose={()=>setCloseOutput(output)}/>)}
            </div>
          </section>
        </div></>}
    </section>
    {form && <ProfileDialog form={form} setForm={setForm} onClose={() => setForm(undefined)} onSave={saveProfile} onTest={testProfile} busy={busy} />}
    {helpOpen && <HelpModal onClose={() => setHelpOpen(false)} />}
    {aiSettingsOpen && settings && <AiSettingsModal settings={settings} onClose={() => setAiSettingsOpen(false)} onSaved={next => { setSettings(next); setNotice(`${next.provider} · ${next.model} saved.`); }} />}
    {closeOutput&&<ConfirmDialog title="Remove this output?" message="The saved query card and any locally stored result rows will be removed from the output list. The original agent response will remain in the chat history." confirmLabel="Remove output" onCancel={()=>setCloseOutput(undefined)} onConfirm={()=>void confirmCloseOutput()}/>} 
    {executionConfirm&&<ExecutionConfirm assessment={executionConfirm.assessment} sql={executionConfirm.sql} busy={busy==="query"} onCancel={()=>setExecutionConfirm(undefined)} onConfirm={()=>void executeAssessed(executionConfirm.assessment,executionConfirm.sql,true)}/>} 
    {notice && <div className="notice" onClick={() => setNotice(undefined)}>{notice}<span>×</span></div>}
  </main>;
}

function ResizeHandle({ label, onResize, className = "" }: { label: string; onResize: (delta: number) => void; className?: string }) {
  const dragging = useRef(false);
  const previousX = useRef(0);
  function start(event: ReactPointerEvent<HTMLDivElement>) {
    dragging.current = true;
    previousX.current = event.clientX;
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function move(event: ReactPointerEvent<HTMLDivElement>) {
    if (!dragging.current) return;
    const delta = event.clientX - previousX.current;
    previousX.current = event.clientX;
    onResize(delta);
  }
  function stop() { dragging.current = false; }
  return <div className={`resize-handle ${className}`} role="separator" aria-orientation="vertical" aria-label={label} tabIndex={0} onPointerDown={start} onPointerMove={move} onPointerUp={stop} onLostPointerCapture={stop} onKeyDown={event => {
    if (event.key === "ArrowLeft") onResize(-16);
    if (event.key === "ArrowRight") onResize(16);
  }}><span /></div>;
}

function Welcome({ logo, onNew, onProject, onExample, exampleBusy, configPath }: { logo: string; onNew: () => void; onProject: () => void; onExample?: () => void; exampleBusy?: boolean; configPath?: string }) { return <section className="welcome"><div className="hero-logo"><img src={logo} alt="Dexmond Technologies" /></div><p className="eyebrow">DEXMOND TECHNOLOGIES · agentSQL</p><h1>Ask your database,<br />in plain language.</h1><p>Connect securely or inspect a project's SQL, Prisma, or Chroma structure. Review every draft before use.</p><div className="welcome-actions"><button className="primary" onClick={onNew}>Create your first connection</button><button onClick={onProject}>Open project folder</button>{onExample&&<button onClick={onExample} disabled={exampleBusy}>{exampleBusy?"Loading example…":"Load banking example"}</button>}</div><small>AI settings: {configPath || "loading…"}</small></section>; }
function Empty({ label }: { label: string }) { return <div className="empty">{label}</div>; }
function Results({ result }: { result?: QueryResult }) { if (!result) return <div className="results empty">Results will appear here after you explicitly run an approved statement.</div>; return <div className="results"><div className="result-meta">{result.rows.length.toLocaleString()} rows · {result.elapsedMs} ms {result.truncated ? "· limited to 10,000 rows" : ""}</div><div className="result-scroll"><table><thead><tr>{result.columns.map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>{result.rows.map((row, i) => <tr key={i}>{row.map((value, j) => <td key={j}>{typeof value === "object" ? JSON.stringify(value) : String(value ?? "NULL")}</td>)}</tr>)}</tbody></table></div></div>; }
function QueryOutputCard({output,active,onSelect,onToggle,onCopy,onExport,onClose}:{output:QueryOutput;active:boolean;onSelect:()=>void;onToggle:()=>void;onCopy:()=>void;onExport:()=>void;onClose:()=>void}){
  return <article className={`output-card ${active?"active":""}`}>
    <div className="output-card-header"><button className="output-collapse" onClick={onToggle} aria-expanded={!output.collapsed} aria-label={output.collapsed?"Expand output":"Collapse output"}><span>{output.collapsed?"▸":"▾"}</span><span><strong>{output.title}</strong><small>{output.result?`${output.result.rows.length.toLocaleString()} rows · ${output.result.elapsedMs} ms`:"Generated · not executed"} · {displayDate(output.createdAt)}</small></span></button><div className="output-actions"><button onClick={onCopy} title="Copy query to clipboard">Copy</button><button onClick={onExport} title="Export query and result metadata as JSON">Export</button><button className="danger" onClick={onClose} title="Remove this output">Close</button></div></div>
    {!output.collapsed&&<div className="output-card-body" onClick={onSelect}><pre><code>{output.sql}</code></pre>{output.result?<Results result={output.result}/>:<div className="result-awaiting">Not executed. Select this card to load it into the editor.</div>}</div>}
  </article>;
}
function ConfirmDialog({title,message,confirmLabel,onCancel,onConfirm}:{title:string;message:string;confirmLabel:string;onCancel:()=>void;onConfirm:()=>void}){return <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="confirm-title"><section className="modal confirm-modal"><div className="modal-header"><div><p className="eyebrow">CONFIRM REMOVAL</p><h2 id="confirm-title">{title}</h2></div><button className="icon" onClick={onCancel} aria-label="Cancel">×</button></div><p>{message}</p><div className="modal-actions"><button onClick={onCancel}>Cancel</button><button className="danger confirm-danger" onClick={onConfirm}>{confirmLabel}</button></div></section></div>;}
function ExecutionConfirm({assessment,sql,busy,onCancel,onConfirm}:{assessment:QueryAssessment;sql:string;busy:boolean;onCancel:()=>void;onConfirm:()=>void}){const[phrase,setPhrase]=useState("");return <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="execute-title"><section className="modal execution-modal"><div className="modal-header"><div><p className="eyebrow">DATABASE CHANGE · {assessment.operation.toUpperCase()}</p><h2 id="execute-title">Confirm {assessment.label.toLowerCase()}</h2></div><button className="icon" onClick={onCancel} aria-label="Cancel">×</button></div><p className="safety-note danger-note">This statement can change data, schema, permissions, or server state. Database-side privileges remain the final control. Review the exact SQL before continuing.</p><pre className="confirm-sql"><code>{sql}</code></pre><label>Type <strong>EXECUTE</strong> to confirm<input autoFocus value={phrase} onChange={event=>setPhrase(event.target.value)} autoComplete="off" /></label><div className="modal-actions"><button onClick={onCancel}>Cancel</button><button className="danger confirm-danger" disabled={phrase!=="EXECUTE"||busy} onClick={onConfirm}>{busy?"Executing…":"Execute statement"}</button></div></section></div>;}
function ProfileDialog({ form, setForm, onClose, onSave, onTest, busy }: { form: ProfileInput; setForm: (value: ProfileInput) => void; onClose: () => void; onSave: (e: FormEvent) => void; onTest: () => void; busy?: string }) {
  const set = (key: keyof ProfileInput, value: string | number | boolean) => setForm({ ...form, [key]: value } as ProfileInput); const isFile = form.engine === "sqlite";
  return <div className="modal-backdrop"><form className="modal" onSubmit={onSave}><div className="modal-header"><div><p className="eyebrow">SECURE CONNECTION</p><h2>{form.id?"Edit connection":"New connection"}</h2></div><button type="button" className="icon" onClick={onClose}>×</button></div>
    <label>Name<input required value={form.name} onChange={e => set("name", e.target.value)} placeholder="Production reporting" /></label><label>Database type<select value={form.engine} onChange={e => set("engine", e.target.value)}>{engines.map(engine => <option value={engine.value} key={engine.value}>{engine.label}</option>)}</select></label>
    {isFile ? <label>SQLite file path<input required value={form.sqlitePath || ""} onChange={e => set("sqlitePath", e.target.value)} placeholder="C:\\data\\reporting.db" /></label> : <div className="form-grid"><label>Host<input required value={form.host || ""} onChange={e => set("host", e.target.value)} /></label><label>Port<input type="number" value={form.port || ""} onChange={e => set("port", Number(e.target.value))} placeholder="Optional" /></label><label>Database<input required value={form.database || ""} onChange={e => set("database", e.target.value)} /></label><label>Username<input value={form.username || ""} onChange={e => set("username", e.target.value)} /></label></div>}
    {!isFile && <><label>Password <small>{form.id?"leave blank to keep the saved credential":"stored only in the OS secure vault"}</small><input type="password" value={form.password || ""} onChange={e => set("password", e.target.value)} autoComplete="new-password" /></label><label>TLS security<select value={form.tlsMode} onChange={e=>set("tlsMode",e.target.value)}><option value="verifyIdentity">Verify server identity (recommended)</option><option value="require">Require encryption, trust certificate</option><option value="disable">Disable TLS (local testing only)</option></select></label></>}
    <label className="permission-toggle"><input type="checkbox" checked={form.allowWrites} onChange={e=>set("allowWrites",e.target.checked)}/><span><strong>Enable data and schema changes</strong><small>Allows INSERT, UPDATE, DELETE, MERGE, DDL, procedures, permissions and maintenance after a typed confirmation for every statement.</small></span></label>
    <p className="safety-note">{form.allowWrites?"Use a least-privilege database account. agentSQL still rejects multiple statements, manual transactions, and external file/database operations; every accepted change requires a separate EXECUTE confirmation.":"Read-only is the default. Use a database account with server-side read-only permissions as the final defense."}</p><div className="modal-actions"><button type="button" onClick={onTest} disabled={busy === "test"}>{busy === "test" ? "Testing…" : "Test connection"}</button><button className="primary" disabled={busy === "profile"}>{busy === "profile" ? "Saving…" : "Save connection"}</button></div>
  </form></div>;
}
