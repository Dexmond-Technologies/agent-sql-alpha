use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum DatabaseEngine {
    Auto,
    Postgres,
    Mysql,
    Sqlserver,
    Sqlite,
    Source,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub enum TlsMode {
    VerifyIdentity,
    Require,
    Disable,
}
impl Default for TlsMode {
    fn default() -> Self {
        Self::VerifyIdentity
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProfileInput {
    pub id: Option<String>,
    pub name: String,
    pub engine: DatabaseEngine,
    pub host: Option<String>,
    pub port: Option<u16>,
    pub database: Option<String>,
    pub username: Option<String>,
    pub password: Option<String>,
    pub sqlite_path: Option<String>,
    pub source_path: Option<String>,
    #[serde(default)]
    pub allow_writes: bool,
    #[serde(default)]
    pub tls_mode: TlsMode,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ConnectionProfile {
    pub id: String,
    pub name: String,
    pub engine: DatabaseEngine,
    pub host: Option<String>,
    pub port: Option<u16>,
    pub database: Option<String>,
    pub username: Option<String>,
    pub sqlite_path: Option<String>,
    pub source_path: Option<String>,
    pub allow_writes: bool,
    pub tls_mode: TlsMode,
    pub created_at: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SchemaColumn {
    pub name: String,
    pub data_type: String,
    pub nullable: bool,
    pub key: Option<String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ObjectKind {
    Table,
    View,
    Collection,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SchemaTable {
    pub schema: String,
    pub name: String,
    pub kind: ObjectKind,
    pub columns: Vec<SchemaColumn>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_file: Option<String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SchemaSnapshot {
    pub engine: DatabaseEngine,
    pub tables: Vec<SchemaTable>,
    pub captured_at: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_kind: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_language: Option<String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct QueryResult {
    pub columns: Vec<String>,
    pub rows: Vec<Vec<serde_json::Value>>,
    pub elapsed_ms: u128,
    pub truncated: bool,
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum SqlOperation {
    Read,
    Insert,
    Update,
    Delete,
    Merge,
    Ddl,
    Procedure,
    Permission,
    Maintenance,
}
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct QueryAssessment {
    pub operation: SqlOperation,
    pub label: String,
    pub read_only: bool,
    pub destructive: bool,
    pub requires_confirmation: bool,
}
/// A durable query draft and its optional execution result.
///
/// Query outputs are deliberately separate from chat messages: removing an
/// output card deletes its locally stored rows but preserves the conversation
/// that produced it.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct QueryOutput {
    pub id: String,
    pub session_id: String,
    pub source_message_id: Option<String>,
    pub title: String,
    pub sql: String,
    pub result: Option<QueryResult>,
    pub collapsed: bool,
    pub created_at: String,
    pub updated_at: String,
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum AgentMode {
    Plan,
    Chat,
    Direct,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ChatSession {
    pub id: String,
    pub profile_id: String,
    pub title: String,
    pub share_results: bool,
    pub mode: AgentMode,
    pub created_at: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ChatMessage {
    pub id: String,
    pub role: String,
    pub content: String,
    pub created_at: String,
    pub sql: Option<String>,
}
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AiSettings {
    pub provider: String,
    pub model: String,
    pub base_url: String,
    pub configured: bool,
    pub config_path: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AiSettingsInput {
    pub provider: String,
    pub model: String,
    pub base_url: String,
    pub api_key: Option<String>,
}
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AiConnectionTest {
    pub provider: String,
    pub model: String,
    pub base_url: String,
    pub message: String,
    pub available_models: Vec<String>,
}
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SourceImport {
    pub profile: ConnectionProfile,
    pub schema: SchemaSnapshot,
    pub scanned_files: usize,
    pub matched_files: usize,
    pub warnings: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BundledContent {
    pub root_path: String,
    pub documentation_path: String,
    pub example_folder_path: String,
    pub example_database_path: String,
}
