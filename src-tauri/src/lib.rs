mod drivers;
mod ibmi_snapshot;
mod models;
mod network;
mod providers;
mod qwen;
mod safety;
mod source;
mod storage;
use keyring::Entry;
use models::*;
use std::{
    fs,
    path::{Path, PathBuf},
    sync::Mutex,
};
use storage::Storage;
use tauri::{Manager, State};
use tauri_plugin_dialog::DialogExt;

pub struct AppState {
    storage: Mutex<Storage>,
    env_path: PathBuf,
}
fn fail<E: ToString>(e: E) -> String {
    e.to_string()
}
const CREDENTIAL_SERVICE: &str = "com.dexmond.agentsql";
const LEGACY_CREDENTIAL_SERVICE: &str = "com.querycraft.desktop";
fn service_vault(service: &str, id: &str) -> Result<Entry, String> {
    Entry::new(service, &format!("profile-{id}")).map_err(fail)
}
fn vault(id: &str) -> Result<Entry, String> {
    service_vault(CREDENTIAL_SERVICE, id)
}
fn saved_password(id: &str) -> Result<Option<String>, String> {
    match vault(id)?.get_password() {
        Ok(value) => Ok(Some(value)),
        Err(keyring::Error::NoEntry) => {
            match service_vault(LEGACY_CREDENTIAL_SERVICE, id)?.get_password() {
                Ok(value) => {
                    vault(id)?.set_password(&value).map_err(fail)?;
                    Ok(Some(value))
                }
                Err(keyring::Error::NoEntry) => Ok(None),
                Err(error) => Err(error.to_string()),
            }
        }
        Err(error) => Err(error.to_string()),
    }
}
fn migrate_legacy_app_data(dir: &Path) -> std::io::Result<()> {
    let Some(parent) = dir.parent() else {
        return Ok(());
    };
    let legacy = parent.join(LEGACY_CREDENTIAL_SERVICE);
    if !legacy.is_dir() {
        return Ok(());
    }
    let legacy_env = legacy.join(".env");
    let current_env = dir.join(".env");
    if legacy_env.is_file() && !current_env.exists() {
        fs::copy(legacy_env, current_env)?;
    }
    let legacy_database = legacy.join("querycraft.sqlite");
    let current_database = dir.join("agentsql.sqlite");
    if legacy_database.is_file() && !current_database.exists() {
        let temporary_database = dir.join("agentsql.sqlite.migrating");
        if temporary_database.exists() {
            fs::remove_file(&temporary_database)?;
        }
        let migration = (|| -> std::io::Result<()> {
            let source =
                rusqlite::Connection::open(legacy_database).map_err(std::io::Error::other)?;
            let mut destination =
                rusqlite::Connection::open(&temporary_database).map_err(std::io::Error::other)?;
            {
                let backup = rusqlite::backup::Backup::new(&source, &mut destination)
                    .map_err(std::io::Error::other)?;
                backup
                    .run_to_completion(100, std::time::Duration::from_millis(10), None)
                    .map_err(std::io::Error::other)?;
            }
            drop(destination);
            fs::rename(&temporary_database, &current_database)
        })();
        if let Err(error) = migration {
            let _ = fs::remove_file(temporary_database);
            return Err(error);
        }
    }
    Ok(())
}
fn profile_for(state: &AppState, id: &str) -> Result<ConnectionProfile, String> {
    state.storage.lock().map_err(fail)?.profile(id)
}
fn effective_engine(input: &ProfileInput) -> Result<DatabaseEngine, String> {
    if input.engine == DatabaseEngine::Auto {
        if input.sqlite_path.as_ref().is_some_and(|p| !p.is_empty()) {
            Ok(DatabaseEngine::Sqlite)
        } else {
            network::detect(input)
        }
    } else {
        Ok(input.engine.clone())
    }
}

fn bundled_content_paths(app: &tauri::AppHandle) -> Result<BundledContent, String> {
    let root = app.path().resource_dir().map_err(fail)?;
    let documentation = root.join("documentation");
    let example_folder = root.join("examples").join("core-banking");
    let bundled_database = example_folder.join("banking-small.sqlite");
    if !bundled_database.is_file() {
        return Err("The bundled banking example is missing from this installation.".into());
    }
    let local_example_folder = app
        .path()
        .app_data_dir()
        .map_err(fail)?
        .join("examples")
        .join("core-banking");
    fs::create_dir_all(&local_example_folder).map_err(fail)?;
    let local_database = local_example_folder.join("banking-small.sqlite");
    if !local_database.exists() {
        fs::copy(&bundled_database, &local_database).map_err(fail)?;
    }
    Ok(BundledContent {
        root_path: root.to_string_lossy().into_owned(),
        documentation_path: documentation.to_string_lossy().into_owned(),
        example_folder_path: example_folder.to_string_lossy().into_owned(),
        example_database_path: local_database.to_string_lossy().into_owned(),
    })
}

#[tauri::command]
fn bundled_content(app: tauri::AppHandle) -> Result<BundledContent, String> {
    bundled_content_paths(&app)
}

#[tauri::command]
fn open_bundled_content(app: tauri::AppHandle) -> Result<(), String> {
    let content = bundled_content_paths(&app)?;
    #[cfg(target_os = "windows")]
    let mut command = std::process::Command::new("explorer.exe");
    #[cfg(target_os = "macos")]
    let mut command = std::process::Command::new("open");
    #[cfg(target_os = "linux")]
    let mut command = std::process::Command::new("xdg-open");
    command.arg(content.root_path).spawn().map_err(fail)?;
    Ok(())
}

#[tauri::command]
fn list_profiles(state: State<'_, AppState>) -> Result<Vec<ConnectionProfile>, String> {
    state.storage.lock().map_err(fail)?.list_profiles()
}
#[tauri::command]
async fn save_profile(
    state: State<'_, AppState>,
    mut profile: ProfileInput,
) -> Result<ConnectionProfile, String> {
    let probe = profile.clone();
    profile.engine = tauri::async_runtime::spawn_blocking(move || effective_engine(&probe))
        .await
        .map_err(fail)??;
    let password = profile.password.take();
    let saved = state.storage.lock().map_err(fail)?.save_profile(profile)?;
    if let Some(secret) = password.filter(|p| !p.is_empty()) {
        vault(&saved.id)?.set_password(&secret).map_err(fail)?;
    }
    Ok(saved)
}
#[tauri::command]
fn delete_profile(state: State<'_, AppState>, id: String) -> Result<(), String> {
    state.storage.lock().map_err(fail)?.delete_profile(&id)?;
    let _ = vault(&id).and_then(|e| e.delete_credential().map_err(fail));
    let _ = service_vault(LEGACY_CREDENTIAL_SERVICE, &id)
        .and_then(|e| e.delete_credential().map_err(fail));
    Ok(())
}
#[tauri::command]
async fn test_profile(mut profile: ProfileInput) -> Result<serde_json::Value, String> {
    if profile.password.as_deref().is_none_or(str::is_empty) {
        if let Some(id) = profile.id.as_deref() {
            profile.password = saved_password(id)?;
        }
    }
    tauri::async_runtime::spawn_blocking(move || {
        profile.engine = effective_engine(&profile)?;
        let message = drivers::for_engine(&profile.engine).test(&profile)?;
        Ok(serde_json::json!({"engine":format!("{:?}",profile.engine),"message":message}))
    })
    .await
    .map_err(fail)?
}
#[tauri::command]
fn import_source_project(state: State<'_, AppState>, path: String) -> Result<SourceImport, String> {
    let folder = PathBuf::from(&path).canonicalize().map_err(fail)?;
    let analysis = source::analyze(&folder)?;
    let name = folder
        .file_name()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_else(|| "Project source".into());
    let source_path = folder.to_string_lossy().to_string();
    let store = state.storage.lock().map_err(fail)?;
    let id = store.source_profile_at(&source_path)?.map(|p| p.id);
    let input = ProfileInput {
        id,
        name,
        engine: DatabaseEngine::Source,
        host: None,
        port: None,
        database: None,
        username: None,
        password: None,
        sqlite_path: None,
        source_path: Some(source_path),
        allow_writes: false,
        tls_mode: TlsMode::VerifyIdentity,
    };
    let profile = store.save_profile(input)?;
    store.save_schema(&profile.id, &analysis.schema)?;
    Ok(SourceImport {
        profile,
        schema: analysis.schema,
        scanned_files: analysis.scanned_files,
        matched_files: analysis.matched_files,
        warnings: analysis.warnings,
    })
}
#[tauri::command]
fn load_schema(state: State<'_, AppState>, profile_id: String) -> Result<SchemaSnapshot, String> {
    state.storage.lock().map_err(fail)?.schema(&profile_id)
}
#[tauri::command]
async fn refresh_schema(
    state: State<'_, AppState>,
    profile_id: String,
) -> Result<SchemaSnapshot, String> {
    let profile = profile_for(&state, &profile_id)?;
    let password = saved_password(&profile.id)?;
    let schema = tauri::async_runtime::spawn_blocking(move || {
        if profile.engine == DatabaseEngine::Source {
            Ok(source::analyze(&PathBuf::from(
                profile
                    .source_path
                    .as_deref()
                    .ok_or("Project folder missing.")?,
            ))?
            .schema)
        } else {
            drivers::for_engine(&profile.engine).introspect(&profile, password.as_deref())
        }
    })
    .await
    .map_err(fail)??;
    state
        .storage
        .lock()
        .map_err(fail)?
        .save_schema(&profile_id, &schema)?;
    Ok(schema)
}
#[tauri::command]
fn assess_query(
    state: State<'_, AppState>,
    profile_id: String,
    sql: String,
) -> Result<QueryAssessment, String> {
    let profile = profile_for(&state, &profile_id)?;
    safety::assess_sql(&sql, &profile.engine, profile.allow_writes)
}
#[tauri::command]
async fn execute_query(
    state: State<'_, AppState>,
    profile_id: String,
    sql: String,
    confirmed: bool,
) -> Result<QueryResult, String> {
    let profile = profile_for(&state, &profile_id)?;
    if profile.engine == DatabaseEngine::Source {
        return Err("Project source is not a live database. Connect a database to run SQL.".into());
    }
    let password = saved_password(&profile.id)?;
    let executed_sql = sql.clone();
    let result = tauri::async_runtime::spawn_blocking(move || {
        drivers::for_engine(&profile.engine).execute(
            &profile,
            password.as_deref(),
            &executed_sql,
            confirmed,
        )
    })
    .await
    .map_err(fail)??;
    state
        .storage
        .lock()
        .map_err(fail)?
        .add_query(&profile_id, &sql)?;
    Ok(result)
}
#[tauri::command]
fn list_sessions(
    state: State<'_, AppState>,
    profile_id: String,
) -> Result<Vec<ChatSession>, String> {
    state.storage.lock().map_err(fail)?.sessions(&profile_id)
}
#[tauri::command]
fn create_session(
    state: State<'_, AppState>,
    profile_id: String,
    share_results: bool,
) -> Result<ChatSession, String> {
    state
        .storage
        .lock()
        .map_err(fail)?
        .create_session(&profile_id, share_results)
}
#[tauri::command]
fn list_messages(
    state: State<'_, AppState>,
    session_id: String,
) -> Result<Vec<ChatMessage>, String> {
    state.storage.lock().map_err(fail)?.messages(&session_id)
}
#[tauri::command]
fn delete_session(state: State<'_, AppState>, session_id: String) -> Result<(), String> {
    state
        .storage
        .lock()
        .map_err(fail)?
        .delete_session(&session_id)
}
#[tauri::command]
fn set_session_sharing(
    state: State<'_, AppState>,
    session_id: String,
    share_results: bool,
) -> Result<(), String> {
    state
        .storage
        .lock()
        .map_err(fail)?
        .set_session_sharing(&session_id, share_results)
}
#[tauri::command]
fn set_session_mode(
    state: State<'_, AppState>,
    session_id: String,
    mode: AgentMode,
) -> Result<(), String> {
    state
        .storage
        .lock()
        .map_err(fail)?
        .set_session_mode(&session_id, &mode)
}
#[tauri::command]
fn list_query_outputs(
    state: State<'_, AppState>,
    session_id: String,
) -> Result<Vec<QueryOutput>, String> {
    state
        .storage
        .lock()
        .map_err(fail)?
        .query_outputs(&session_id)
}
#[tauri::command]
fn save_query_output(
    state: State<'_, AppState>,
    session_id: String,
    source_message_id: Option<String>,
    title: String,
    sql: String,
) -> Result<QueryOutput, String> {
    state.storage.lock().map_err(fail)?.save_query_output(
        &session_id,
        source_message_id.as_deref(),
        &title,
        &sql,
    )
}
#[tauri::command]
fn update_query_output(
    state: State<'_, AppState>,
    output_id: String,
    sql: String,
    result: Option<QueryResult>,
) -> Result<QueryOutput, String> {
    state
        .storage
        .lock()
        .map_err(fail)?
        .update_query_output(&output_id, &sql, result.as_ref())
}
#[tauri::command]
fn set_query_output_collapsed(
    state: State<'_, AppState>,
    output_id: String,
    collapsed: bool,
) -> Result<(), String> {
    state
        .storage
        .lock()
        .map_err(fail)?
        .set_query_output_collapsed(&output_id, collapsed)
}
#[tauri::command]
fn delete_query_output(state: State<'_, AppState>, output_id: String) -> Result<(), String> {
    state
        .storage
        .lock()
        .map_err(fail)?
        .delete_query_output(&output_id)
}
#[tauri::command]
async fn export_query_output(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    output_id: String,
) -> Result<Option<String>, String> {
    let output = state
        .storage
        .lock()
        .map_err(fail)?
        .query_output(&output_id)?;
    let file_name = format!(
        "agentsql-output-{}.json",
        &output.id[..8.min(output.id.len())]
    );
    let Some(destination) = app
        .dialog()
        .file()
        .add_filter("JSON output", &["json"])
        .set_file_name(&file_name)
        .blocking_save_file()
    else {
        return Ok(None);
    };
    let path = destination.into_path().map_err(fail)?;
    fs::write(&path, serde_json::to_string_pretty(&output).map_err(fail)?).map_err(fail)?;
    Ok(Some(path.to_string_lossy().to_string()))
}
#[tauri::command]
async fn ask_agent(
    state: State<'_, AppState>,
    session_id: String,
    message: String,
    result: Option<QueryResult>,
) -> Result<ChatMessage, String> {
    let (session, schema, history, allow_writes) = {
        let store = state.storage.lock().map_err(fail)?;
        let session = store.session(&session_id)?;
        let schema = store.schema(&session.profile_id)?;
        let allow_writes = store.profile(&session.profile_id)?.allow_writes;
        let history = store
            .messages(&session_id)?
            .into_iter()
            .map(|m| (m.role, m.content))
            .collect::<Vec<_>>();
        (session, schema, history, allow_writes)
    };
    {
        let store = state.storage.lock().map_err(fail)?;
        store.set_session_title_from_message(&session_id, &message)?;
        store.add_message(&session_id, "user", &message)?;
    }
    let config = providers::load(&state.env_path);
    let shared = if session.share_results {
        result.as_ref()
    } else {
        None
    };
    let answer = providers::ask(
        config,
        &message,
        &schema,
        &history,
        shared,
        &session.mode,
        allow_writes,
    )
    .await?;
    let store = state.storage.lock().map_err(fail)?;
    let response = store.add_message(&session_id, "assistant", &answer)?;
    if let Some(sql) = response.sql.as_deref() {
        store.save_query_output(&session_id, Some(&response.id), "Generated SQL", sql)?;
    }
    Ok(response)
}
fn public_ai_settings(config: providers::ProviderConfig) -> AiSettings {
    let configured = if config.provider == "qwen" {
        qwen::configured(&config)
    } else {
        matches!(config.provider.as_str(), "ollama" | "lmstudio") || config.api_key.is_some()
    };
    AiSettings {
        provider: config.provider,
        model: config.model,
        base_url: config.base_url,
        configured,
        config_path: config.config_path,
    }
}
#[tauri::command]
fn ai_settings(state: State<'_, AppState>) -> AiSettings {
    public_ai_settings(providers::load(&state.env_path))
}
#[tauri::command]
fn save_ai_settings(
    state: State<'_, AppState>,
    settings: AiSettingsInput,
) -> Result<AiSettings, String> {
    Ok(public_ai_settings(providers::save(
        &state.env_path,
        &settings,
    )?))
}
#[tauri::command]
async fn test_ai_provider(
    state: State<'_, AppState>,
    settings: AiSettingsInput,
) -> Result<AiConnectionTest, String> {
    providers::test(&state.env_path, &settings).await
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let dir = app.path().app_data_dir()?;
            fs::create_dir_all(&dir)?;
            migrate_legacy_app_data(&dir)?;
            let env_path = dir.join(".env");
            if !env_path.exists() {
                fs::write(&env_path, include_str!("../../.env.example"))?;
            }
            let storage =
                Storage::open(&dir.join("agentsql.sqlite")).map_err(std::io::Error::other)?;
            app.manage(AppState {
                storage: Mutex::new(storage),
                env_path,
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            bundled_content,
            open_bundled_content,
            list_profiles,
            save_profile,
            delete_profile,
            test_profile,
            import_source_project,
            load_schema,
            refresh_schema,
            assess_query,
            execute_query,
            list_sessions,
            create_session,
            list_messages,
            delete_session,
            set_session_sharing,
            set_session_mode,
            list_query_outputs,
            save_query_output,
            update_query_output,
            set_query_output_collapsed,
            delete_query_output,
            export_query_output,
            ask_agent,
            ai_settings,
            save_ai_settings,
            test_ai_provider
        ])
        .run(tauri::generate_context!())
        .expect("agentSQL failed to launch");
}

#[cfg(test)]
mod migration_tests {
    use super::*;

    #[test]
    fn legacy_app_data_is_copied_without_overwriting_new_files() {
        let root =
            std::env::temp_dir().join(format!("agentsql-migration-{}", uuid::Uuid::new_v4()));
        let legacy = root.join(LEGACY_CREDENTIAL_SERVICE);
        let current = root.join(CREDENTIAL_SERVICE);
        fs::create_dir_all(&legacy).unwrap();
        fs::create_dir_all(&current).unwrap();
        fs::write(legacy.join(".env"), "AI_PROVIDER=deepseek\n").unwrap();
        let legacy_database = rusqlite::Connection::open(legacy.join("querycraft.sqlite")).unwrap();
        legacy_database
            .execute_batch("CREATE TABLE settings(value TEXT NOT NULL); INSERT INTO settings(value) VALUES ('legacy-db');")
            .unwrap();
        drop(legacy_database);
        fs::write(current.join(".env"), "AI_PROVIDER=ollama\n").unwrap();
        migrate_legacy_app_data(&current).unwrap();
        assert_eq!(
            fs::read_to_string(current.join(".env")).unwrap(),
            "AI_PROVIDER=ollama\n"
        );
        let migrated = rusqlite::Connection::open(current.join("agentsql.sqlite")).unwrap();
        let value: String = migrated
            .query_row("SELECT value FROM settings", [], |row| row.get(0))
            .unwrap();
        assert_eq!(value, "legacy-db");
        drop(migrated);
        fs::remove_dir_all(root).unwrap();
    }
}
