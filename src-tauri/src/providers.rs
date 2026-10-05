use crate::models::{AgentMode, AiConnectionTest, AiSettingsInput, QueryResult, SchemaSnapshot};
use regex::Regex;
use reqwest::Client;
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    process::{Command, Output},
};

#[derive(Clone)]
pub struct ProviderConfig {
    pub provider: String,
    pub model: String,
    pub base_url: String,
    pub api_key: Option<String>,
    pub config_path: String,
}
fn provider_defaults(provider: &str) -> (&'static str, &'static str, Option<&'static str>) {
    match provider {
        "qwen" => (
            "qwen3-coder-30b-a3b",
            "http://127.0.0.1:8000/v1",
            Some("QWEN_API_KEY"),
        ),
        "deepseek" => (
            "deepseek-flash",
            "https://api.deepseek.com",
            Some("DEEPSEEK_API_KEY"),
        ),
        "anthropic" => (
            "claude-sonnet-5",
            "https://api.anthropic.com",
            Some("ANTHROPIC_API_KEY"),
        ),
        "gemini" => (
            "gemini-3.8-flash",
            "https://generativelanguage.googleapis.com/v1beta",
            Some("GEMINI_API_KEY"),
        ),
        "ollama" => ("gemma4", "http://127.0.0.1:11434", Some("OLLAMA_API_KEY")),
        "lmstudio" => (
            "openai/gpt-oss-20b",
            "http://127.0.0.1:1234/v1",
            Some("LMSTUDIO_API_KEY"),
        ),
        _ => (
            "gpt-5.6-terra",
            "https://api.openai.com/v1",
            Some("OPENAI_API_KEY"),
        ),
    }
}
fn prefix(provider: &str) -> &'static str {
    match provider {
        "qwen" => "QWEN",
        "deepseek" => "DEEPSEEK",
        "anthropic" => "ANTHROPIC",
        "gemini" => "GEMINI",
        "ollama" => "OLLAMA",
        "lmstudio" => "LMSTUDIO",
        _ => "OPENAI",
    }
}
fn valid_provider(provider: &str) -> bool {
    matches!(
        provider,
        "openai" | "deepseek" | "anthropic" | "gemini" | "ollama" | "lmstudio" | "qwen"
    )
}
pub fn load(path: &Path) -> ProviderConfig {
    let values = config_values(path);
    let requested = config_value(&values, "AI_PROVIDER")
        .unwrap_or_else(|_| "openai".into())
        .to_lowercase();
    let provider = if valid_provider(&requested) {
        requested
    } else {
        "openai".into()
    };
    let (default_model, default_base, key_name) = provider_defaults(&provider);
    let key_prefix = prefix(&provider);
    let model = config_value(&values, &format!("{key_prefix}_MODEL"))
        .unwrap_or_else(|_| default_model.into());
    let base = config_value(&values, &format!("{key_prefix}_BASE_URL"))
        .unwrap_or_else(|_| default_base.into());
    let key = key_name
        .and_then(|name| config_value(&values, name).ok())
        .filter(|v| !v.trim().is_empty());
    ProviderConfig {
        provider,
        model,
        base_url: base.trim_end_matches('/').into(),
        api_key: key,
        config_path: path.display().to_string(),
    }
}
fn config_values(path: &Path) -> BTreeMap<String, String> {
    // Each request gets its own file values. Never change process-wide credentials.
    // Qwen's Options::load separately rejects any malformed configuration before I/O.
    dotenvy::from_path_iter(path)
        .map(|entries| entries.filter_map(Result::ok).collect())
        .unwrap_or_default()
}
fn config_value(values: &BTreeMap<String, String>, key: &str) -> Result<String, std::env::VarError> {
    values.get(key).cloned().map(Ok).unwrap_or_else(|| std::env::var(key))
}
fn validate_input(input: &AiSettingsInput) -> Result<(), String> {
    if !valid_provider(&input.provider) {
        return Err("Unsupported AI provider.".into());
    }
    if input.model.trim().is_empty() {
        return Err("Choose or enter a model name.".into());
    }
    if !input.base_url.starts_with("http://") && !input.base_url.starts_with("https://") {
        return Err("Base URL must start with http:// or https://.".into());
    }
    if [&input.provider, &input.model, &input.base_url]
        .iter()
        .any(|v| v.contains('\r') || v.contains('\n'))
        || input
            .api_key
            .as_ref()
            .is_some_and(|v| v.contains('\r') || v.contains('\n'))
    {
        return Err("AI settings cannot contain line breaks.".into());
    }
    if input.provider == "qwen" {
        crate::qwen::validate_settings(&input.base_url, &input.model)?;
        if input.base_url.contains(['\'', '"', '\\', '$', '#']) || input.base_url.chars().any(char::is_whitespace) {
            return Err("Use a Qwen URL without whitespace, quotes, backslashes, dollar signs, or #.".into());
        }
        if input.api_key.as_deref().is_some_and(|key| !key.is_ascii() || key.contains(['\'', '"', '\\', '$', '#']) || key.chars().any(char::is_whitespace)) {
            return Err("Use a Qwen API token without whitespace, quotes, backslashes, dollar signs, or #.".into());
        }
    }
    Ok(())
}
fn set_env_line(lines: &mut Vec<String>, key: &str, value: &str) {
    let marker = format!("{key}=");
    if let Some(line) = lines
        .iter_mut()
        .find(|line| line.trim_start().starts_with(&marker))
    {
        *line = format!("{key}={value}");
    } else {
        lines.push(format!("{key}={value}"));
    }
}
pub fn save(path: &Path, input: &AiSettingsInput) -> Result<ProviderConfig, String> {
    validate_input(input)?;
    let content = fs::read_to_string(path).unwrap_or_default();
    let mut lines = content.lines().map(str::to_owned).collect::<Vec<_>>();
    let provider = input.provider.to_lowercase();
    let env_prefix = prefix(&provider);
    set_env_line(&mut lines, "AI_PROVIDER", &provider);
    set_env_line(
        &mut lines,
        &format!("{env_prefix}_MODEL"),
        input.model.trim(),
    );
    set_env_line(
        &mut lines,
        &format!("{env_prefix}_BASE_URL"),
        input.base_url.trim_end_matches('/'),
    );
    if let Some(key) = input
        .api_key
        .as_deref()
        .map(str::trim)
        .filter(|v| !v.is_empty())
    {
        if let Some(key_name) = provider_defaults(&provider).2 {
            set_env_line(&mut lines, key_name, key);
        }
    }
    fs::write(path, format!("{}\n", lines.join("\n"))).map_err(|e| e.to_string())?;
    Ok(load(path))
}
fn config_for_input(path: &Path, input: &AiSettingsInput) -> Result<ProviderConfig, String> {
    validate_input(input)?;
    let values = config_values(path);
    let provider = input.provider.to_lowercase();
    let key = input
        .api_key
        .as_deref()
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .map(str::to_owned)
        .or_else(|| {
            provider_defaults(&provider)
                .2
                .and_then(|name| config_value(&values, name).ok())
                .filter(|v| !v.trim().is_empty())
        });
    Ok(ProviderConfig {
        provider,
        model: input.model.trim().into(),
        base_url: input.base_url.trim_end_matches('/').into(),
        api_key: key,
        config_path: path.display().to_string(),
    })
}
pub async fn ask(
    mut config: ProviderConfig,
    question: &str,
    schema: &SchemaSnapshot,
    history: &[(String, String)],
    result: Option<&QueryResult>,
    agent_mode: &AgentMode,
    allow_writes: bool,
) -> Result<String, String> {
    if config.provider == "qwen" {
        let options = crate::qwen::Options::load(Path::new(&config.config_path))?;
        let context = crate::qwen::context(&options, schema, question, history, result)?;
        let prompt = format!("{}\n{}", system_prompt(&context.schema, context.result.as_ref(), agent_mode, allow_writes), context.notes);
        let answer = crate::qwen::ask(&config, &options, &prompt, question, history, &context.citations).await?;
        let answer = enforce_interaction_mode(agent_mode, &answer);
        validate_source_answer(schema, &answer)?;
        return Ok(answer);
    }
    let prompt = system_prompt(schema, result, agent_mode, allow_writes);
    let client = Client::new();
    let provider = config.provider.clone();
    let answer = match provider.as_str() {
        "anthropic" => anthropic(&client, &config, &prompt, question, history).await,
        "gemini" => gemini(&client, &config, &prompt, question, history).await,
        "ollama" => ollama(&client, &config, &prompt, question, history).await,
        "lmstudio" => {
            let (_, models, base_url) = discover_lmstudio(&client, &config).await?;
            config.base_url = base_url;
            if !models.iter().any(|model| model == &config.model) {
                if let Some(model) = models.first() {
                    config.model = model.clone();
                }
            }
            local_openai_compatible(&client, &config, &prompt, question, history).await
        }
        "deepseek" => {
            openai_compatible(
                &client,
                &config,
                &prompt,
                question,
                history,
                "DEEPSEEK_API_KEY",
            )
            .await
        }
        _ => openai_responses(&client, &config, &prompt, question, history).await,
    }?;
    let answer = enforce_interaction_mode(agent_mode, &answer);
    validate_source_answer(schema, &answer)?;
    Ok(answer)
}

fn enforce_interaction_mode(mode: &AgentMode, answer: &str) -> String {
    if matches!(mode, AgentMode::Direct) {
        return answer.into();
    }
    let fenced = Regex::new(r"(?s)```.*?```").unwrap();
    if fenced.is_match(answer) {
        format!("{}\n\n> Query code was suppressed because this conversation is in {} mode. Use `/generate` or switch to Direct generation when you are ready.",fenced.replace_all(answer,"[query draft suppressed]"),if matches!(mode,AgentMode::Plan){"Plan / Grill"}else{"Chat"})
    } else {
        answer.into()
    }
}
fn validate_source_answer(schema: &SchemaSnapshot, answer: &str) -> Result<(), String> {
    if !matches!(schema.engine, crate::models::DatabaseEngine::Source)
        || !matches!(schema.source_kind.as_deref(), Some("chroma" | "mixed"))
    {
        return Ok(());
    }
    if schema.source_kind.as_deref() == Some("chroma")
        && answer.to_ascii_lowercase().contains("```sql")
    {
        return Err("The AI returned SQL for a Chroma project, so the draft was not accepted. Please ask again.".into());
    }
    let block =
        Regex::new(r"(?is)```(?:python|typescript|javascript|js|ts)\s*([\s\S]*?)```").unwrap();
    let mutation=Regex::new(r"(?i)\.\s*(?:get_or_create_collection|getOrCreateCollection|create_collection|createCollection|delete_collection|deleteCollection|add|upsert|update|delete|modify|reset)\s*\(").unwrap();
    if block
        .captures_iter(answer)
        .any(|capture| mutation.is_match(&capture[1]))
    {
        return Err("The AI returned a Chroma mutation or collection-creation call, so the draft was not accepted.".into());
    }
    Ok(())
}
fn system_prompt(
    schema: &SchemaSnapshot,
    result: Option<&QueryResult>,
    agent_mode: &AgentMode,
    allow_writes: bool,
) -> String {
    let mut safe_schema = schema.clone();
    for table in &mut safe_schema.tables {
        table.source_file = None;
    }
    let catalog = serde_json::to_string(&safe_schema).unwrap_or_default();
    let results = result
        .map(|r| serde_json::to_string(r).unwrap_or_default())
        .unwrap_or_else(|| "No result set has been executed.".into());
    let mode = if matches!(schema.engine, crate::models::DatabaseEngine::Source) {
        match schema.source_kind.as_deref() {
            Some("db2i") => "This is a dated Db2 for i catalog snapshot imported from an operator-run ODBC exporter. It is not a live connection and cannot execute inside agentSQL. Draft one read-only Db2 for i SELECT using only the supplied objects and columns. Use SQL schema.object naming and FETCH FIRST for row limits. Never use MySQL/PostgreSQL LIMIT or SQL Server TOP. The IBM i release/PTFs and available SQL Services require explicit evidence. Unknown relationships and business definitions require clarification; never invent them. Do not generate writes, DDL, CALL, transactions, locking clauses, SELECT INTO or multiple statements. Put one draft in a fenced sql block.".into(),
            Some("chroma") => { let provenance=if schema.tables.iter().any(|t|t.source_file.as_deref().is_some_and(|p|p.ends_with("chroma.sqlite3"))) {"Collection names were read from a local persisted Chroma catalog, not verified against a running server."} else {"Collection names were inferred from source code, not verified against a running Chroma instance."}; format!("This project uses Chroma, a vector database, not SQL. {provenance} Record fields shown are the generic Chroma API shape, not fixed metadata keys. Draft a READ-ONLY Chroma {} snippet using get_collection/getCollection followed by query/get/count/list only. Never use get_or_create_collection, create, add, upsert, update, delete, reset, or modify. Do not generate SQL. If collection names are unknown, ask for the name rather than inventing one. Explain that this is a draft and cannot run inside agentSQL yet. Put code in one fenced block marked python or typescript.",schema.source_language.as_deref().unwrap_or("Python")) },
            Some("mixed") => "This project contains both relational schema and Chroma vector collections. Choose SQL SELECT for relational questions or read-only Chroma query/get code for vector-search questions; do not invent joins across these systems. Ask for clarification when the target is ambiguous. Source findings are unverified drafts and cannot run inside agentSQL without a live connector. Never produce mutations or DDL. Put one draft in a fenced sql, python, or typescript block.".into(),
            Some("unknown") => "No supported database structure was found. Ask for the framework or schema location; do not invent a query.".into(),
            _ => "This SQL schema is inferred from project source files, not verified against a running database. The SQL dialect is unknown. Produce a conservative read-only SELECT draft in one sql fenced block and explain it cannot be executed until a live database is connected. Never produce writes, DDL, transactions, procedures, locking clauses, SELECT INTO, or multiple statements.".into(),
        }
    } else if allow_writes {
        "The schema was introspected from a connected SQL database. This connection's operator explicitly enabled data and schema changes. Generate exactly one SQL statement of the requested type using ONLY the supplied schema. INSERT, UPDATE, DELETE, MERGE, DDL, procedures, permissions, and maintenance statements are allowed when requested. Never claim it has run: the application will independently classify it and require a typed confirmation. Never produce multiple statements, manual transaction control, ATTACH/DETACH, COPY/LOAD, or external file/database operations. State the likely impact and assumptions before the fenced SQL block.".into()
    } else {
        "The schema was introspected from a connected SQL database. Generate one useful read-only query using ONLY the supplied schema. Explain assumptions briefly. Put SQL in exactly one sql fenced block. Never produce writes, DDL, transactions, procedures, locking clauses, SELECT INTO, or multiple statements.".into()
    };
    let interaction=match agent_mode {
        AgentMode::Plan=>"INTERACTION MODE: PLAN / GRILL. This instruction has priority over any drafting language above. Do not output SQL or executable code yet. Collaboratively refine the request by identifying ambiguity, assumptions, business definitions, filters, time ranges, grouping, ordering, and expected output. Ask no more than three high-value questions per response. For each question, give concise A/B/C choices plus an 'Other — add remarks' choice. Summarize confirmed decisions under 'Agreed so far' and unresolved items under 'Still needed'. End by telling the user they can reply with choices and remarks or use /generate when ready. Use clear headings, short paragraphs, and lists.",
        AgentMode::Chat=>"INTERACTION MODE: CHAT. This instruction has priority over any drafting language above. Discuss the schema, data meaning, terminology, trade-offs, or analytical approach. Do not generate SQL, query code, pseudo-SQL, or fenced executable blocks. If asked to create a query, explain that Direct mode or /direct is required. Use clear headings and short paragraphs.",
        AgentMode::Direct=>"INTERACTION MODE: DIRECT GENERATION. Generate the requested query immediately when the request is sufficiently clear. State assumptions and impact briefly, then provide exactly one fenced query block and a concise explanation. If a critical ambiguity makes a safe query impossible, ask one focused question instead of guessing.",
    };
    format!("You are agentSQL by Dexmond Technologies, a database analysis and SQL drafting assistant. Engine: {:?}. {mode} {interaction} Schema: {catalog}. Most recent query result (may contain sensitive data): {results}",schema.engine)
}
fn history_messages(prompt: &str, history: &[(String, String)], question: &str) -> Vec<Value> {
    let mut messages = vec![json!({"role":"system","content":prompt})];
    for (role, content) in history.iter().rev().take(12).rev() {
        messages.push(json!({"role":role,"content":content}));
    }
    messages.push(json!({"role":"user","content":question}));
    messages
}
fn conversation(history: &[(String, String)], question: &str) -> Vec<Value> {
    let mut messages = history
        .iter()
        .rev()
        .take(12)
        .rev()
        .map(|(role, content)| json!({"role":role,"content":content}))
        .collect::<Vec<_>>();
    messages.push(json!({"role":"user","content":question}));
    messages
}
async fn response_json(response: reqwest::Response) -> Result<Value, String> {
    let status = response.status();
    let body = response.text().await.map_err(|e| e.to_string())?;
    if !status.is_success() {
        let summary = body.chars().take(500).collect::<String>();
        return Err(format!("AI provider returned {status}: {summary}"));
    }
    serde_json::from_str(&body).map_err(|e| format!("AI provider returned invalid JSON: {e}"))
}
async fn openai_responses(
    client: &Client,
    c: &ProviderConfig,
    prompt: &str,
    q: &str,
    h: &[(String, String)],
) -> Result<String, String> {
    let key = c
        .api_key
        .as_ref()
        .ok_or("OPENAI_API_KEY is missing. Add it in AI provider settings.")?;
    let response = response_json(
        client
            .post(format!("{}/responses", c.base_url))
            .bearer_auth(key)
            .json(&json!({"model":c.model,"instructions":prompt,"input":conversation(h,q)}))
            .send()
            .await
            .map_err(|e| e.to_string())?,
    )
    .await?;
    if let Some(text) = response.get("output_text").and_then(Value::as_str) {
        return Ok(text.into());
    }
    response
        .get("output")
        .and_then(Value::as_array)
        .and_then(|items| {
            items.iter().find_map(|item| {
                item.get("content")?
                    .as_array()?
                    .iter()
                    .find_map(|part| part.get("text")?.as_str())
            })
        })
        .map(str::to_owned)
        .ok_or("OpenAI returned no assistant text.".into())
}
async fn openai_compatible(
    client: &Client,
    c: &ProviderConfig,
    prompt: &str,
    q: &str,
    h: &[(String, String)],
    key_name: &str,
) -> Result<String, String> {
    let key = c
        .api_key
        .as_ref()
        .ok_or_else(|| format!("{key_name} is missing from the app-data .env file."))?;
    let response = client
        .post(format!("{}/chat/completions", c.base_url))
        .bearer_auth(key)
        .json(&json!({"model":c.model,"messages":history_messages(prompt,h,q),"temperature":0.1}))
        .send()
        .await
        .map_err(|e| e.to_string())?
        .error_for_status()
        .map_err(|e| e.to_string())?
        .json::<Value>()
        .await
        .map_err(|e| e.to_string())?;
    response
        .pointer("/choices/0/message/content")
        .and_then(Value::as_str)
        .map(str::to_owned)
        .ok_or("The AI provider returned no assistant text.".into())
}
async fn local_openai_compatible(
    client: &Client,
    c: &ProviderConfig,
    prompt: &str,
    q: &str,
    h: &[(String, String)],
) -> Result<String, String> {
    let mut request = client
        .post(format!("{}/chat/completions", c.base_url))
        .json(&json!({"model":c.model,"messages":history_messages(prompt,h,q),"temperature":0.1}));
    if let Some(key) = c.api_key.as_ref() {
        request = request.bearer_auth(key);
    }
    let response = request
        .send()
        .await
        .map_err(|e| format!("Could not reach LM Studio: {e}"))?
        .error_for_status()
        .map_err(|e| e.to_string())?
        .json::<Value>()
        .await
        .map_err(|e| e.to_string())?;
    response
        .pointer("/choices/0/message/content")
        .and_then(Value::as_str)
        .map(str::to_owned)
        .ok_or("LM Studio returned no assistant text.".into())
}
async fn anthropic(
    client: &Client,
    c: &ProviderConfig,
    prompt: &str,
    q: &str,
    h: &[(String, String)],
) -> Result<String, String> {
    let key = c
        .api_key
        .as_ref()
        .ok_or("ANTHROPIC_API_KEY is missing from the app-data .env file.")?;
    let mut messages: Vec<Value> = h
        .iter()
        .map(|(r, t)| json!({"role":r,"content":t}))
        .collect();
    messages.push(json!({"role":"user","content":q}));
    let response = client
        .post(format!("{}/v1/messages", c.base_url))
        .header("x-api-key", key)
        .header("anthropic-version", "2023-06-01")
        .json(&json!({"model":c.model,"max_tokens":1800,"system":prompt,"messages":messages}))
        .send()
        .await
        .map_err(|e| e.to_string())?
        .error_for_status()
        .map_err(|e| e.to_string())?
        .json::<Value>()
        .await
        .map_err(|e| e.to_string())?;
    response
        .pointer("/content/0/text")
        .and_then(Value::as_str)
        .map(str::to_owned)
        .ok_or("Anthropic returned no assistant text.".into())
}
async fn gemini(
    client: &Client,
    c: &ProviderConfig,
    prompt: &str,
    q: &str,
    h: &[(String, String)],
) -> Result<String, String> {
    let key = c
        .api_key
        .as_ref()
        .ok_or("GEMINI_API_KEY is missing. Add it in AI provider settings.")?;
    let mut contents=h.iter().rev().take(12).rev().map(|(role,text)|json!({"role":if role=="assistant"{"model"}else{"user"},"parts":[{"text":text}]})).collect::<Vec<_>>();
    contents.push(json!({"role":"user","parts":[{"text":q}]}));
    let response=response_json(client.post(format!("{}/models/{}:generateContent",c.base_url,c.model)).query(&[("key",key)]).json(&json!({"systemInstruction":{"parts":[{"text":prompt}]},"contents":contents,"generationConfig":{"temperature":0.1,"maxOutputTokens":1800}})).send().await.map_err(|e|e.to_string())?).await?;
    response
        .pointer("/candidates/0/content/parts/0/text")
        .and_then(Value::as_str)
        .map(str::to_owned)
        .ok_or("Gemini returned no assistant text.".into())
}
async fn ollama(
    client: &Client,
    c: &ProviderConfig,
    prompt: &str,
    q: &str,
    h: &[(String, String)],
) -> Result<String, String> {
    let mut request = client
        .post(format!("{}/api/chat", c.base_url))
        .json(&json!({"model":c.model,"stream":false,"messages":history_messages(prompt,h,q)}));
    if let Some(key) = c.api_key.as_ref() { request = request.bearer_auth(key); }
    let response = request.send()
        .await
        .map_err(|e| e.to_string())?
        .error_for_status()
        .map_err(|e| e.to_string())?
        .json::<Value>()
        .await
        .map_err(|e| e.to_string())?;
    response
        .pointer("/message/content")
        .and_then(Value::as_str)
        .map(str::to_owned)
        .ok_or("Ollama returned no assistant text.".into())
}

fn lms_candidates() -> Vec<PathBuf> {
    let executable = if cfg!(windows) { "lms.exe" } else { "lms" };
    let mut paths = vec![PathBuf::from(executable)];
    if let Some(home) = std::env::var_os(if cfg!(windows) { "USERPROFILE" } else { "HOME" }) {
        paths.push(
            PathBuf::from(home)
                .join(".lmstudio")
                .join("bin")
                .join(executable),
        );
    }
    paths
}

fn run_lms(path: &Path, args: &[&str]) -> std::io::Result<Output> {
    let mut command = Command::new(path);
    command.args(args);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    command.output()
}

fn ensure_lmstudio_server() -> Result<String, String> {
    let mut found = false;
    let mut failures = Vec::new();
    for executable in lms_candidates() {
        match run_lms(&executable, &["server", "status", "--json", "--quiet"]) {
            Ok(output) => {
                found = true;
                if let Ok(status) = serde_json::from_slice::<Value>(&output.stdout) {
                    if status.get("running").and_then(Value::as_bool) == Some(true) {
                        if let Some(port) = status.get("port").and_then(Value::as_u64) {
                            return Ok(format!("http://127.0.0.1:{port}/v1"));
                        }
                    }
                }
                match run_lms(
                    &executable,
                    &["server", "start", "--port", "1234", "--bind", "127.0.0.1"],
                ) {
                    Ok(started) if started.status.success() => {
                        return Ok("http://127.0.0.1:1234/v1".into())
                    }
                    Ok(started) => {
                        failures.push(String::from_utf8_lossy(&started.stderr).trim().to_owned())
                    }
                    Err(error) => failures.push(error.to_string()),
                }
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => failures.push(error.to_string()),
        }
    }
    if found {
        Err(format!(
            "LM Studio is installed, but its local server could not be started. {}",
            failures.join(" | ")
        ))
    } else {
        Err("LM Studio's local helper was not found. Open LM Studio once so its bundled lms helper is installed.".into())
    }
}

async fn probe_lmstudio(
    client: &Client,
    c: &ProviderConfig,
    base_url: &str,
) -> Result<(Value, Vec<String>, String), String> {
    let mut request = client
        .get(format!("{base_url}/models"))
        .timeout(std::time::Duration::from_secs(2));
    if let Some(key) = c.api_key.as_ref() {
        request = request.bearer_auth(key);
    }
    let value = response_json(request.send().await.map_err(|error| error.to_string())?).await?;
    let models = value
        .get("data")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item.get("id").and_then(Value::as_str).map(str::to_owned))
                .collect()
        })
        .unwrap_or_default();
    Ok((value, models, base_url.into()))
}

async fn discover_lmstudio(
    client: &Client,
    c: &ProviderConfig,
) -> Result<(Value, Vec<String>, String), String> {
    let mut candidates = vec![
        c.base_url.trim_end_matches('/').to_owned(),
        "http://127.0.0.1:1234/v1".into(),
        "http://localhost:1234/v1".into(),
    ];
    candidates.dedup();
    let mut failures = Vec::new();
    for base_url in &candidates {
        match probe_lmstudio(client, c, base_url).await {
            Ok(found) => return Ok(found),
            Err(error) => failures.push(format!("{base_url}: {error}")),
        }
    }
    let managed_url = ensure_lmstudio_server().map_err(|error| {
        format!("LM Studio was not reachable and automatic startup failed: {error}")
    })?;
    for _ in 0..5 {
        match probe_lmstudio(client, c, &managed_url).await {
            Ok(found) => return Ok(found),
            Err(error) => failures.push(format!("{managed_url}: {error}")),
        }
        tokio::time::sleep(std::time::Duration::from_millis(250)).await;
    }
    Err(format!(
        "LM Studio was started, but its local API did not become ready. {}",
        failures.join(" | ")
    ))
}

pub async fn test(path: &Path, input: &AiSettingsInput) -> Result<AiConnectionTest, String> {
    let c = config_for_input(path, input)?;
    if c.provider == "qwen" {
        return crate::qwen::test(&c, &crate::qwen::Options::load(path)?).await;
    }
    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(20))
        .build()
        .map_err(|e| e.to_string())?;
    let mut detected_base_url = c.base_url.clone();
    let (value, mut models) = match c.provider.as_str() {
        "ollama" => {
            let mut request = client.get(format!("{}/api/tags", c.base_url));
            if let Some(key) = c.api_key.as_ref() { request = request.bearer_auth(key); }
            let value = response_json(
                request.send()
                    .await
                    .map_err(|e| format!("Could not reach Ollama: {e}"))?,
            )
            .await?;
            let models: Vec<String> = value
                .get("models")
                .and_then(Value::as_array)
                .map(|items| {
                    items
                        .iter()
                        .filter_map(|item| {
                            item.get("name")
                                .or_else(|| item.get("model"))
                                .and_then(Value::as_str)
                                .map(str::to_owned)
                        })
                        .collect()
                })
                .unwrap_or_default();
            (value, models)
        }
        "lmstudio" => {
            let (value, models, base_url) = discover_lmstudio(&client, &c).await?;
            detected_base_url = base_url;
            (value, models)
        }
        "gemini" => {
            let key = c
                .api_key
                .as_ref()
                .ok_or("GEMINI_API_KEY is missing. Paste a key before testing.")?;
            let value = response_json(
                client
                    .get(format!("{}/models", c.base_url))
                    .query(&[("key", key)])
                    .send()
                    .await
                    .map_err(|e| e.to_string())?,
            )
            .await?;
            let models = value
                .get("models")
                .and_then(Value::as_array)
                .map(|items| {
                    items
                        .iter()
                        .filter_map(|item| {
                            item.get("name")
                                .and_then(Value::as_str)
                                .map(|name| name.trim_start_matches("models/").to_owned())
                        })
                        .collect()
                })
                .unwrap_or_default();
            (value, models)
        }
        "anthropic" => {
            let key = c
                .api_key
                .as_ref()
                .ok_or("ANTHROPIC_API_KEY is missing. Paste a key before testing.")?;
            let value = response_json(
                client
                    .get(format!("{}/v1/models", c.base_url))
                    .header("x-api-key", key)
                    .header("anthropic-version", "2023-06-01")
                    .send()
                    .await
                    .map_err(|e| e.to_string())?,
            )
            .await?;
            let models = value
                .get("data")
                .and_then(Value::as_array)
                .map(|items| {
                    items
                        .iter()
                        .filter_map(|item| {
                            item.get("id").and_then(Value::as_str).map(str::to_owned)
                        })
                        .collect()
                })
                .unwrap_or_default();
            (value, models)
        }
        _ => {
            let key = c.api_key.as_ref().ok_or_else(|| {
                format!(
                    "{}_API_KEY is missing. Paste a key before testing.",
                    prefix(&c.provider)
                )
            })?;
            let value = response_json(
                client
                    .get(format!("{}/models", c.base_url))
                    .bearer_auth(key)
                    .send()
                    .await
                    .map_err(|e| e.to_string())?,
            )
            .await?;
            let models = value
                .get("data")
                .and_then(Value::as_array)
                .map(|items| {
                    items
                        .iter()
                        .filter_map(|item| {
                            item.get("id").and_then(Value::as_str).map(str::to_owned)
                        })
                        .collect()
                })
                .unwrap_or_default();
            (value, models)
        }
    };
    let _ = value;
    models.sort();
    models.dedup();
    let present = models
        .iter()
        .any(|model| model == &c.model || model.split(':').next() == Some(c.model.as_str()));
    let model = if c.provider == "lmstudio" && !present {
        models.first().cloned().unwrap_or_else(|| c.model.clone())
    } else {
        c.model.clone()
    };
    let message = if c.provider == "lmstudio" {
        if models.is_empty() {
            format!("LM Studio detected at {detected_base_url}, but it reported no available models. Load a model in LM Studio.")
        } else {
            format!(
                "LM Studio detected at {detected_base_url}. {} model(s) available; '{}' selected.",
                models.len(),
                model
            )
        }
    } else if models.is_empty() {
        format!(
            "Connected to {}. The provider did not return a model list.",
            c.provider
        )
    } else if present {
        format!("Connected to {} and found the selected model.", c.provider)
    } else {
        format!(
            "Connected to {}, but '{}' was not listed for this account or local server.",
            c.provider, c.model
        )
    };
    Ok(AiConnectionTest {
        provider: c.provider,
        model,
        base_url: detected_base_url,
        message,
        available_models: models,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::*;
    #[test]
    fn source_prompt_excludes_local_paths() {
        let schema = SchemaSnapshot {
            engine: DatabaseEngine::Source,
            tables: vec![SchemaTable {
                schema: "inferred".into(),
                name: "users".into(),
                kind: ObjectKind::Table,
                columns: vec![],
                source_file: Some("private/migrations/001.sql".into()),
            }],
            captured_at: "now".into(),
            source_kind: Some("sql".into()),
            source_language: None,
        };
        let prompt = system_prompt(&schema, None, &AgentMode::Direct, false);
        assert!(prompt.contains("inferred from project source"));
        assert!(prompt.contains("users"));
        assert!(!prompt.contains("private/migrations"));
    }
    #[test]
    fn chroma_prompt_never_requests_sql() {
        let schema = SchemaSnapshot {
            engine: DatabaseEngine::Source,
            tables: vec![],
            captured_at: "now".into(),
            source_kind: Some("chroma".into()),
            source_language: Some("python".into()),
        };
        let prompt = system_prompt(&schema, None, &AgentMode::Direct, false);
        assert!(prompt.contains("Do not generate SQL"));
        assert!(prompt.contains("Never use get_or_create_collection"));
    }
    #[test]
    fn interaction_modes_have_distinct_query_rules() {
        let schema = SchemaSnapshot {
            engine: DatabaseEngine::Sqlite,
            tables: vec![],
            captured_at: "now".into(),
            source_kind: None,
            source_language: None,
        };
        let plan = system_prompt(&schema, None, &AgentMode::Plan, false);
        let chat = system_prompt(&schema, None, &AgentMode::Chat, false);
        let direct = system_prompt(&schema, None, &AgentMode::Direct, false);
        assert!(plan.contains("Do not output SQL"));
        assert!(plan.contains("Other — add remarks"));
        assert!(chat.contains("Do not generate SQL"));
        assert!(direct.contains("Generate the requested query immediately"));
    }
    #[test]
    fn write_enabled_prompt_allows_dml_and_requires_confirmation() {
        let schema = SchemaSnapshot {
            engine: DatabaseEngine::Postgres,
            tables: vec![],
            captured_at: "now".into(),
            source_kind: None,
            source_language: None,
        };
        let prompt = system_prompt(&schema, None, &AgentMode::Direct, true);
        assert!(prompt.contains("INSERT, UPDATE, DELETE"));
        assert!(prompt.contains("typed confirmation"));
        assert!(prompt.contains("Never produce multiple statements"));
    }
    #[test]
    fn non_generation_modes_suppress_fenced_queries() {
        let answer = "Explanation\n```sql\nSELECT 1\n```";
        assert!(!enforce_interaction_mode(&AgentMode::Chat, answer).contains("SELECT 1"));
        assert!(enforce_interaction_mode(&AgentMode::Direct, answer).contains("SELECT 1"));
    }
    #[test]
    fn chroma_answer_gate_rejects_sql_and_mutations() {
        let schema = SchemaSnapshot {
            engine: DatabaseEngine::Source,
            tables: vec![],
            captured_at: "now".into(),
            source_kind: Some("chroma".into()),
            source_language: Some("python".into()),
        };
        assert!(validate_source_answer(&schema, "```sql\nSELECT * FROM docs\n```").is_err());
        assert!(
            validate_source_answer(&schema, "```python\ncollection.add(ids=['x'])\n```").is_err()
        );
        assert!(validate_source_answer(
            &schema,
            "```python\ncollection.query(query_texts=['x'])\n```"
        )
        .is_ok());
    }
    #[test]
    fn lmstudio_defaults_to_local_openai_compatibility_without_a_required_key() {
        let (default_model, base_url, key_name) = provider_defaults("lmstudio");
        assert_eq!(default_model, "openai/gpt-oss-20b");
        assert_eq!(base_url, "http://127.0.0.1:1234/v1");
        assert_eq!(key_name, Some("LMSTUDIO_API_KEY"));
        assert!(valid_provider("lmstudio"));
    }
    #[test]
    fn settings_save_preserves_an_existing_key_when_blank() {
        let path =
            std::env::temp_dir().join(format!("agentsql-provider-{}.env", uuid::Uuid::new_v4()));
        std::fs::write(&path,"AI_PROVIDER=deepseek\nDEEPSEEK_API_KEY=test-secret\nDEEPSEEK_MODEL=old\nDEEPSEEK_BASE_URL=https://api.deepseek.com\n").unwrap();
        let input = AiSettingsInput {
            provider: "deepseek".into(),
            model: "deepseek-flash".into(),
            base_url: "https://api.deepseek.com".into(),
            api_key: Some(String::new()),
        };
        let config = save(&path, &input).unwrap();
        let saved = std::fs::read_to_string(&path).unwrap();
        assert_eq!(config.model, "deepseek-flash");
        assert!(config.api_key.is_some());
        assert!(saved.contains("DEEPSEEK_API_KEY=test-secret"));
        std::fs::remove_file(path).unwrap();
    }
}
