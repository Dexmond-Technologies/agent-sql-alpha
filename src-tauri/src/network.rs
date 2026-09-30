use crate::models::*;
use futures_util::TryStreamExt;
use serde_json::{json, Value};
use sqlx::{
    any::{install_default_drivers, AnyRow, AnyTypeInfoKind},
    AnyConnection, Column, Connection, Executor, Row, ValueRef,
};
use std::{
    collections::BTreeMap,
    future::Future,
    time::{Duration, Instant},
};
use tiberius::{AuthMethod, Client, ColumnData, Config, EncryptionLevel};
use tokio::net::TcpStream;
use tokio_util::compat::{Compat, TokioAsyncWriteCompatExt};

type SqlServerClient = Client<Compat<TcpStream>>;

pub fn test(input: &ProfileInput) -> Result<String, String> {
    let profile = ConnectionProfile {
        id: input.id.clone().unwrap_or_default(),
        name: input.name.clone(),
        engine: input.engine.clone(),
        host: input.host.clone(),
        port: input.port,
        database: input.database.clone(),
        username: input.username.clone(),
        sqlite_path: input.sqlite_path.clone(),
        source_path: input.source_path.clone(),
        allow_writes: input.allow_writes,
        tls_mode: input.tls_mode.clone(),
        created_at: String::new(),
    };
    test_connection(&profile, input.password.as_deref(), 60)
}

/// Auto mode probes only the supported engines, never executes user SQL, and
/// stores the engine that successfully completed a `SELECT 1` handshake.
pub fn detect(input: &ProfileInput) -> Result<DatabaseEngine, String> {
    let candidates = match input.port {
        Some(5432) => vec![DatabaseEngine::Postgres],
        Some(3306) => vec![DatabaseEngine::Mysql],
        Some(1433) => vec![DatabaseEngine::Sqlserver],
        Some(_) => vec![
            DatabaseEngine::Postgres,
            DatabaseEngine::Mysql,
            DatabaseEngine::Sqlserver,
        ],
        None => vec![
            DatabaseEngine::Postgres,
            DatabaseEngine::Mysql,
            DatabaseEngine::Sqlserver,
        ],
    };
    let mut failures = Vec::new();
    for engine in candidates {
        let profile = ConnectionProfile {
            id: String::new(),
            name: input.name.clone(),
            engine: engine.clone(),
            host: input.host.clone(),
            port: input.port.or(Some(default_port(&engine))),
            database: input.database.clone(),
            username: input.username.clone(),
            sqlite_path: None,
            source_path: None,
            allow_writes: input.allow_writes,
            tls_mode: input.tls_mode.clone(),
            created_at: String::new(),
        };
        match test_connection(&profile, input.password.as_deref(), 5) {
            Ok(_) => return Ok(engine),
            Err(error) => failures.push(format!("{}: {error}", engine_label(&engine))),
        }
    }
    Err(format!("Auto-detection could not verify PostgreSQL, MySQL, or SQL Server. Choose the engine explicitly for a detailed connection error. {}",failures.join(" | ")))
}

fn test_connection(
    profile: &ConnectionProfile,
    password: Option<&str>,
    timeout_seconds: u64,
) -> Result<String, String> {
    match profile.engine {
        DatabaseEngine::Sqlserver => block_on_timeout(
            async {
                let mut client = connect_sqlserver(profile, password).await?;
                client
                    .simple_query("SELECT 1")
                    .await
                    .map_err(|e| e.to_string())?
                    .into_row()
                    .await
                    .map_err(|e| e.to_string())?;
                Ok("SQL Server connection verified.".into())
            },
            timeout_seconds,
        ),
        DatabaseEngine::Postgres | DatabaseEngine::Mysql => block_on_timeout(
            async {
                let mut connection = connect_any(profile, password).await?;
                sqlx::query("SELECT 1")
                    .execute(&mut connection)
                    .await
                    .map_err(|e| e.to_string())?;
                Ok(format!(
                    "{} connection verified.",
                    engine_label(&profile.engine)
                ))
            },
            timeout_seconds,
        ),
        _ => Err("A server database engine is required.".into()),
    }
}

pub fn introspect(
    profile: &ConnectionProfile,
    password: Option<&str>,
) -> Result<SchemaSnapshot, String> {
    let captured_at = chrono::Utc::now().to_rfc3339();
    let result = match profile.engine {
        DatabaseEngine::Postgres => block_on(async {
            let mut connection = connect_any(profile, password).await?;
            read_any(&mut connection, POSTGRES_CATALOG).await
        }),
        DatabaseEngine::Mysql => block_on(async {
            let mut connection = connect_any(profile, password).await?;
            read_any(&mut connection, MYSQL_CATALOG).await
        }),
        DatabaseEngine::Sqlserver => block_on(async {
            let mut client = connect_sqlserver(profile, password).await?;
            read_sqlserver(&mut client, SQLSERVER_CATALOG).await
        }),
        _ => return Err("A server database engine is required.".into()),
    }?;
    let mut objects: BTreeMap<(String, String), (ObjectKind, Vec<SchemaColumn>)> = BTreeMap::new();
    for row in result.rows {
        if row.len() < 7 {
            continue;
        }
        let schema = text(&row[0]);
        let name = text(&row[1]);
        let kind = if text(&row[2]).to_ascii_uppercase().contains("VIEW") {
            ObjectKind::View
        } else {
            ObjectKind::Table
        };
        let column = SchemaColumn {
            name: text(&row[3]),
            data_type: text(&row[4]),
            nullable: text(&row[5]).eq_ignore_ascii_case("YES") || row[5].as_bool() == Some(true),
            key: if text(&row[6]).eq_ignore_ascii_case("PK") {
                Some("PK".into())
            } else {
                None
            },
        };
        objects
            .entry((schema, name))
            .or_insert_with(|| (kind, Vec::new()))
            .1
            .push(column);
    }
    let tables = objects
        .into_iter()
        .map(|((schema, name), (kind, columns))| SchemaTable {
            schema,
            name,
            kind,
            columns,
            source_file: None,
        })
        .collect();
    Ok(SchemaSnapshot {
        engine: profile.engine.clone(),
        tables,
        captured_at,
        source_kind: None,
        source_language: None,
    })
}

pub fn execute(
    profile: &ConnectionProfile,
    password: Option<&str>,
    sql: &str,
    read_only: bool,
    label: &str,
) -> Result<QueryResult, String> {
    let begin = Instant::now();
    match profile.engine {
        DatabaseEngine::Postgres | DatabaseEngine::Mysql => block_on(async {
            let mut connection = connect_any(profile, password).await?;
            if read_only {
                let mut result = read_any(&mut connection, sql).await?;
                result.elapsed_ms = begin.elapsed().as_millis();
                Ok(result)
            } else {
                let affected = sqlx::query(sql)
                    .execute(&mut connection)
                    .await
                    .map_err(|e| e.to_string())?
                    .rows_affected();
                Ok(execution_result(
                    label,
                    affected,
                    begin.elapsed().as_millis(),
                ))
            }
        }),
        DatabaseEngine::Sqlserver => block_on(async {
            let mut client = connect_sqlserver(profile, password).await?;
            if read_only {
                let mut result = read_sqlserver(&mut client, sql).await?;
                result.elapsed_ms = begin.elapsed().as_millis();
                Ok(result)
            } else {
                let affected = client
                    .execute(sql, &[])
                    .await
                    .map_err(|e| e.to_string())?
                    .total();
                Ok(execution_result(
                    label,
                    affected,
                    begin.elapsed().as_millis(),
                ))
            }
        }),
        _ => Err("A server database engine is required.".into()),
    }
}

fn block_on<T, F>(future: F) -> Result<T, String>
where
    F: Future<Output = Result<T, String>>,
{
    block_on_timeout(future, 60)
}
fn block_on_timeout<T, F>(future: F, seconds: u64) -> Result<T, String>
where
    F: Future<Output = Result<T, String>>,
{
    tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .map_err(|e| e.to_string())?
        .block_on(async {
            tokio::time::timeout(Duration::from_secs(seconds), future)
                .await
                .map_err(|_| format!("Database operation timed out after {seconds} seconds."))?
        })
}
fn default_port(engine: &DatabaseEngine) -> u16 {
    match engine {
        DatabaseEngine::Postgres => 5432,
        DatabaseEngine::Mysql => 3306,
        DatabaseEngine::Sqlserver => 1433,
        _ => 0,
    }
}

async fn connect_any(
    profile: &ConnectionProfile,
    password: Option<&str>,
) -> Result<AnyConnection, String> {
    install_default_drivers();
    let url = connection_url(profile, password)?;
    AnyConnection::connect(&url)
        .await
        .map_err(|e| format!("{} connection failed: {e}", engine_label(&profile.engine)))
}

fn connection_url(profile: &ConnectionProfile, password: Option<&str>) -> Result<String, String> {
    let host = host_value(profile)?;
    let host = if host.contains(':') && !host.starts_with('[') {
        format!("[{host}]")
    } else {
        host.into()
    };
    let user = profile
        .username
        .as_deref()
        .filter(|value| !value.is_empty())
        .ok_or("Username is required.")?;
    let database = profile
        .database
        .as_deref()
        .filter(|value| !value.is_empty())
        .ok_or("Database is required.")?;
    let password = password.unwrap_or_default();
    let user = urlencoding::encode(user);
    let password = urlencoding::encode(password);
    let database = urlencoding::encode(database);
    match profile.engine {
        DatabaseEngine::Postgres => {
            let mode = match profile.tls_mode {
                TlsMode::VerifyIdentity => "verify-full",
                TlsMode::Require => "require",
                TlsMode::Disable => "disable",
            };
            Ok(format!(
                "postgres://{user}:{password}@{host}:{}/{database}?sslmode={mode}",
                profile.port.unwrap_or(5432)
            ))
        }
        DatabaseEngine::Mysql => {
            let mode = match profile.tls_mode {
                TlsMode::VerifyIdentity => "VERIFY_IDENTITY",
                TlsMode::Require => "REQUIRED",
                TlsMode::Disable => "DISABLED",
            };
            Ok(format!(
                "mysql://{user}:{password}@{host}:{}/{database}?ssl-mode={mode}",
                profile.port.unwrap_or(3306)
            ))
        }
        _ => Err("Unsupported SQLx engine.".into()),
    }
}

async fn connect_sqlserver(
    profile: &ConnectionProfile,
    password: Option<&str>,
) -> Result<SqlServerClient, String> {
    let mut config = Config::new();
    config.host(host_value(profile)?);
    config.port(profile.port.unwrap_or(1433));
    config.database(
        profile
            .database
            .as_deref()
            .filter(|value| !value.is_empty())
            .ok_or("Database is required.")?,
    );
    config.application_name("agentSQL");
    let user = profile
        .username
        .as_deref()
        .filter(|value| !value.is_empty())
        .ok_or("Username is required for SQL Server authentication in this alpha.")?;
    config.authentication(AuthMethod::sql_server(user, password.unwrap_or_default()));
    match profile.tls_mode {
        TlsMode::VerifyIdentity => config.encryption(EncryptionLevel::Required),
        TlsMode::Require => {
            config.encryption(EncryptionLevel::Required);
            config.trust_cert();
        }
        TlsMode::Disable => config.encryption(EncryptionLevel::Off),
    }
    let tcp = TcpStream::connect(config.get_addr())
        .await
        .map_err(|e| format!("SQL Server TCP connection failed: {e}"))?;
    tcp.set_nodelay(true).map_err(|e| e.to_string())?;
    Client::connect(config, tcp.compat_write())
        .await
        .map_err(|e| format!("SQL Server login failed: {e}"))
}

async fn read_any(connection: &mut AnyConnection, sql: &str) -> Result<QueryResult, String> {
    let columns = connection
        .describe(sql)
        .await
        .map_err(|e| e.to_string())?
        .columns()
        .iter()
        .map(|column| column.name().to_string())
        .collect::<Vec<_>>();
    let mut rows = Vec::new();
    let mut truncated = false;
    let mut stream = sqlx::query(sql).fetch(connection);
    while let Some(row) = stream.try_next().await.map_err(|e| e.to_string())? {
        if rows.len() == 10_000 {
            truncated = true;
            break;
        }
        rows.push((0..row.len()).map(|index| any_value(&row, index)).collect());
    }
    Ok(QueryResult {
        columns,
        rows,
        elapsed_ms: 0,
        truncated,
    })
}

fn any_value(row: &AnyRow, index: usize) -> Value {
    let Ok(raw) = row.try_get_raw(index) else {
        return Value::Null;
    };
    if raw.is_null() {
        return Value::Null;
    }
    match raw.type_info().kind() {
        AnyTypeInfoKind::Null => Value::Null,
        AnyTypeInfoKind::Bool => row
            .try_get::<bool, _>(index)
            .map(Value::Bool)
            .unwrap_or(Value::Null),
        AnyTypeInfoKind::SmallInt => row
            .try_get::<i16, _>(index)
            .map(|value| json!(value))
            .unwrap_or(Value::Null),
        AnyTypeInfoKind::Integer => row
            .try_get::<i32, _>(index)
            .map(|value| json!(value))
            .unwrap_or(Value::Null),
        AnyTypeInfoKind::BigInt => row
            .try_get::<i64, _>(index)
            .map(|value| json!(value))
            .unwrap_or(Value::Null),
        AnyTypeInfoKind::Real => row
            .try_get::<f32, _>(index)
            .ok()
            .and_then(|value| serde_json::Number::from_f64(value as f64))
            .map(Value::Number)
            .unwrap_or(Value::Null),
        AnyTypeInfoKind::Double => row
            .try_get::<f64, _>(index)
            .ok()
            .and_then(serde_json::Number::from_f64)
            .map(Value::Number)
            .unwrap_or(Value::Null),
        AnyTypeInfoKind::Text => row
            .try_get::<String, _>(index)
            .map(Value::String)
            .unwrap_or(Value::Null),
        AnyTypeInfoKind::Blob => row
            .try_get::<Vec<u8>, _>(index)
            .map(|value| Value::String(format!("<{} byte blob>", value.len())))
            .unwrap_or(Value::Null),
    }
}

async fn read_sqlserver(client: &mut SqlServerClient, sql: &str) -> Result<QueryResult, String> {
    let mut stream = client
        .simple_query(sql)
        .await
        .map_err(|e| e.to_string())?
        .into_row_stream();
    let mut columns = Vec::new();
    let mut rows = Vec::new();
    let mut truncated = false;
    while let Some(row) = stream.try_next().await.map_err(|e| e.to_string())? {
        if columns.is_empty() {
            columns = row
                .columns()
                .iter()
                .map(|column| column.name().to_string())
                .collect()
        }
        if rows.len() == 10_000 {
            truncated = true;
            break;
        }
        rows.push(row.into_iter().map(sqlserver_value).collect());
    }
    Ok(QueryResult {
        columns,
        rows,
        elapsed_ms: 0,
        truncated,
    })
}

fn sqlserver_value(value: ColumnData<'static>) -> Value {
    match value {
        ColumnData::U8(value) => value.map(|item| json!(item)).unwrap_or(Value::Null),
        ColumnData::I16(value) => value.map(|item| json!(item)).unwrap_or(Value::Null),
        ColumnData::I32(value) => value.map(|item| json!(item)).unwrap_or(Value::Null),
        ColumnData::I64(value) => value.map(|item| json!(item)).unwrap_or(Value::Null),
        ColumnData::F32(value) => value
            .and_then(|item| serde_json::Number::from_f64(item as f64))
            .map(Value::Number)
            .unwrap_or(Value::Null),
        ColumnData::F64(value) => value
            .and_then(serde_json::Number::from_f64)
            .map(Value::Number)
            .unwrap_or(Value::Null),
        ColumnData::Bit(value) => value.map(Value::Bool).unwrap_or(Value::Null),
        ColumnData::String(value) => value
            .map(|item| Value::String(item.into_owned()))
            .unwrap_or(Value::Null),
        ColumnData::Guid(value) => value
            .map(|item| Value::String(item.to_string()))
            .unwrap_or(Value::Null),
        ColumnData::Binary(value) => value
            .map(|item| Value::String(format!("<{} byte blob>", item.len())))
            .unwrap_or(Value::Null),
        ColumnData::Numeric(value) => value
            .map(|item| Value::String(item.to_string()))
            .unwrap_or(Value::Null),
        other => {
            if format!("{other:?}").contains("None") {
                Value::Null
            } else {
                Value::String(format!("{other:?}"))
            }
        }
    }
}

fn execution_result(label: &str, affected: u64, elapsed_ms: u128) -> QueryResult {
    QueryResult {
        columns: vec!["operation".into(), "affected_rows".into()],
        rows: vec![vec![json!(label), json!(affected)]],
        elapsed_ms,
        truncated: false,
    }
}
fn host_value(profile: &ConnectionProfile) -> Result<&str, String> {
    let host = profile
        .host
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or("Host is required.")?;
    if !host.chars().all(|character| {
        character.is_ascii_alphanumeric() || matches!(character, '.' | '-' | '_' | ':' | '[' | ']')
    }) {
        return Err("Host contains unsupported characters.".into());
    }
    Ok(host)
}
fn text(value: &Value) -> String {
    value
        .as_str()
        .map(str::to_owned)
        .unwrap_or_else(|| value.to_string().trim_matches('"').to_string())
}
fn engine_label(engine: &DatabaseEngine) -> &'static str {
    match engine {
        DatabaseEngine::Postgres => "PostgreSQL",
        DatabaseEngine::Mysql => "MySQL",
        DatabaseEngine::Sqlserver => "SQL Server",
        _ => "Database",
    }
}

const POSTGRES_CATALOG:&str="SELECT c.table_schema,c.table_name,t.table_type,c.column_name,c.data_type,c.is_nullable,CASE WHEN EXISTS (SELECT 1 FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema WHERE tc.constraint_type='PRIMARY KEY' AND tc.table_schema=c.table_schema AND tc.table_name=c.table_name AND kcu.column_name=c.column_name) THEN 'PK' ELSE '' END AS key_type FROM information_schema.columns c JOIN information_schema.tables t ON t.table_schema=c.table_schema AND t.table_name=c.table_name WHERE c.table_schema NOT IN ('pg_catalog','information_schema') ORDER BY c.table_schema,c.table_name,c.ordinal_position";
const MYSQL_CATALOG:&str="SELECT c.TABLE_SCHEMA,c.TABLE_NAME,t.TABLE_TYPE,c.COLUMN_NAME,c.COLUMN_TYPE,c.IS_NULLABLE,CASE WHEN c.COLUMN_KEY='PRI' THEN 'PK' ELSE '' END AS key_type FROM information_schema.COLUMNS c JOIN information_schema.TABLES t ON t.TABLE_SCHEMA=c.TABLE_SCHEMA AND t.TABLE_NAME=c.TABLE_NAME WHERE c.TABLE_SCHEMA=DATABASE() ORDER BY c.TABLE_SCHEMA,c.TABLE_NAME,c.ORDINAL_POSITION";
const SQLSERVER_CATALOG:&str="SELECT c.TABLE_SCHEMA,c.TABLE_NAME,t.TABLE_TYPE,c.COLUMN_NAME,c.DATA_TYPE,c.IS_NULLABLE,CASE WHEN EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu ON tc.CONSTRAINT_NAME=kcu.CONSTRAINT_NAME AND tc.TABLE_SCHEMA=kcu.TABLE_SCHEMA WHERE tc.CONSTRAINT_TYPE='PRIMARY KEY' AND tc.TABLE_SCHEMA=c.TABLE_SCHEMA AND tc.TABLE_NAME=c.TABLE_NAME AND kcu.COLUMN_NAME=c.COLUMN_NAME) THEN 'PK' ELSE '' END AS key_type FROM INFORMATION_SCHEMA.COLUMNS c JOIN INFORMATION_SCHEMA.TABLES t ON t.TABLE_SCHEMA=c.TABLE_SCHEMA AND t.TABLE_NAME=c.TABLE_NAME ORDER BY c.TABLE_SCHEMA,c.TABLE_NAME,c.ORDINAL_POSITION";

#[cfg(test)]
mod tests {
    use super::*;
    fn profile(engine: DatabaseEngine, tls_mode: TlsMode) -> ConnectionProfile {
        ConnectionProfile {
            id: "test".into(),
            name: "test".into(),
            engine,
            host: Some("db.example.invalid".into()),
            port: None,
            database: Some("banking/reporting".into()),
            username: Some("agent@bank".into()),
            sqlite_path: None,
            source_path: None,
            allow_writes: false,
            tls_mode,
            created_at: "test".into(),
        }
    }
    #[test]
    fn connection_urls_encode_credentials_and_require_verified_tls_by_default() {
        let postgres = connection_url(
            &profile(DatabaseEngine::Postgres, TlsMode::VerifyIdentity),
            Some("p:ss word"),
        )
        .unwrap();
        assert!(postgres
            .contains("agent%40bank:p%3Ass%20word@db.example.invalid:5432/banking%2Freporting"));
        assert!(postgres.ends_with("sslmode=verify-full"));
        let mysql = connection_url(
            &profile(DatabaseEngine::Mysql, TlsMode::Require),
            Some("secret"),
        )
        .unwrap();
        assert!(mysql.ends_with("ssl-mode=REQUIRED"));
    }
    #[test]
    fn connection_urls_reject_host_parameter_injection() {
        let mut value = profile(DatabaseEngine::Postgres, TlsMode::VerifyIdentity);
        value.host = Some("db.example.invalid?sslmode=disable".into());
        assert!(connection_url(&value, None).is_err());
    }
}
