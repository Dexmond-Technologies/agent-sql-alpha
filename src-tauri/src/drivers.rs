use crate::{models::*, network, safety::assess_sql};
use rusqlite::{types::ValueRef, Connection};
use serde_json::Value;
use std::{
    path::Path,
    time::{Duration, Instant},
};

/// All engine implementations satisfy this boundary. The native command layer never hands raw
/// connection strings or driver handles to the webview.
pub trait DatabaseDriver {
    fn test(&self, profile: &ProfileInput) -> Result<String, String>;
    fn introspect(
        &self,
        profile: &ConnectionProfile,
        password: Option<&str>,
    ) -> Result<SchemaSnapshot, String>;
    fn execute(
        &self,
        profile: &ConnectionProfile,
        password: Option<&str>,
        sql: &str,
        confirmed: bool,
    ) -> Result<QueryResult, String>;
}
pub struct SqliteDriver;
impl SqliteDriver {
    fn open(path: &str) -> Result<Connection, String> {
        let c = Connection::open(Path::new(path)).map_err(|e| e.to_string())?;
        c.busy_timeout(Duration::from_secs(60))
            .map_err(|e| e.to_string())?;
        Ok(c)
    }
}
impl DatabaseDriver for SqliteDriver {
    fn test(&self, p: &ProfileInput) -> Result<String, String> {
        let path = p
            .sqlite_path
            .as_deref()
            .ok_or("Choose a SQLite database file.")?;
        Self::open(path)?;
        Ok("SQLite database opened successfully.".into())
    }
    fn introspect(
        &self,
        p: &ConnectionProfile,
        _password: Option<&str>,
    ) -> Result<SchemaSnapshot, String> {
        let conn = Self::open(p.sqlite_path.as_deref().ok_or("SQLite path missing.")?)?;
        let mut found=conn.prepare("SELECT name,type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name").map_err(|e|e.to_string())?;
        let entries: Vec<(String, String)> = found
            .query_map([], |r| Ok((r.get(0)?, r.get(1)?)))
            .map_err(|e| e.to_string())?
            .collect::<Result<_, _>>()
            .map_err(|e| e.to_string())?;
        let mut tables = Vec::new();
        for (name, kind) in entries {
            let safe = name.replace('\'', "''");
            let mut stmt = conn
                .prepare(&format!("PRAGMA table_info('{safe}')"))
                .map_err(|e| e.to_string())?;
            let columns = stmt
                .query_map([], |r| {
                    Ok(SchemaColumn {
                        name: r.get(1)?,
                        data_type: r.get::<_, String>(2)?,
                        nullable: r.get::<_, i32>(3)? == 0,
                        key: if r.get::<_, i32>(5)? == 1 {
                            Some("PK".into())
                        } else {
                            None
                        },
                    })
                })
                .map_err(|e| e.to_string())?
                .collect::<Result<_, _>>()
                .map_err(|e| e.to_string())?;
            tables.push(SchemaTable {
                schema: "main".into(),
                name,
                kind: if kind == "view" {
                    ObjectKind::View
                } else {
                    ObjectKind::Table
                },
                columns,
                source_file: None,
            });
        }
        Ok(SchemaSnapshot {
            engine: DatabaseEngine::Sqlite,
            tables,
            captured_at: chrono::Utc::now().to_rfc3339(),
            source_kind: None,
            source_language: None,
        })
    }
    fn execute(
        &self,
        p: &ConnectionProfile,
        _password: Option<&str>,
        sql: &str,
        confirmed: bool,
    ) -> Result<QueryResult, String> {
        let assessment = assess_sql(sql, &DatabaseEngine::Sqlite, p.allow_writes)?;
        if assessment.requires_confirmation && !confirmed {
            return Err(
                "This statement changes data or schema and requires explicit confirmation.".into(),
            );
        }
        let begin = Instant::now();
        let conn = Self::open(p.sqlite_path.as_deref().ok_or("SQLite path missing.")?)?;
        let deadline = begin;
        conn.progress_handler(
            1_000,
            Some(move || deadline.elapsed() > Duration::from_secs(60)),
        );
        let mut stmt = conn.prepare(sql).map_err(|e| e.to_string())?;
        if stmt.column_count() == 0 {
            let affected = stmt.execute([]).map_err(|e| e.to_string())?;
            return Ok(QueryResult {
                columns: vec!["operation".into(), "affected_rows".into()],
                rows: vec![vec![
                    Value::String(assessment.label),
                    Value::from(affected as u64),
                ]],
                elapsed_ms: begin.elapsed().as_millis(),
                truncated: false,
            });
        }
        let columns = stmt.column_names().iter().map(|s| s.to_string()).collect();
        let mut rows = Vec::new();
        let mut cursor = stmt.query([]).map_err(|e| e.to_string())?;
        let mut truncated = false;
        while let Some(row) = cursor.next().map_err(|e| e.to_string())? {
            if rows.len() == 10_000 {
                truncated = true;
                break;
            }
            let mut values = Vec::new();
            for i in 0..row.as_ref().column_count() {
                values.push(match row.get_ref(i).map_err(|e| e.to_string())? {
                    ValueRef::Null => Value::Null,
                    ValueRef::Integer(v) => Value::from(v),
                    ValueRef::Real(v) => Value::from(v),
                    ValueRef::Text(v) => Value::from(String::from_utf8_lossy(v).to_string()),
                    ValueRef::Blob(v) => Value::from(format!("<{} byte blob>", v.len())),
                });
            }
            rows.push(values);
        }
        Ok(QueryResult {
            columns,
            rows,
            elapsed_ms: begin.elapsed().as_millis(),
            truncated,
        })
    }
}
pub struct NetworkDriver {
    pub engine: DatabaseEngine,
}
impl DatabaseDriver for NetworkDriver {
    fn test(&self, p: &ProfileInput) -> Result<String, String> {
        network::test(p)
    }
    fn introspect(
        &self,
        p: &ConnectionProfile,
        password: Option<&str>,
    ) -> Result<SchemaSnapshot, String> {
        network::introspect(p, password)
    }
    fn execute(
        &self,
        p: &ConnectionProfile,
        password: Option<&str>,
        sql: &str,
        confirmed: bool,
    ) -> Result<QueryResult, String> {
        let assessment = assess_sql(sql, &self.engine, p.allow_writes)?;
        if assessment.requires_confirmation && !confirmed {
            return Err(
                "This statement changes data or schema and requires explicit confirmation.".into(),
            );
        }
        network::execute(p, password, sql, assessment.read_only, &assessment.label)
    }
}
pub fn for_engine(engine: &DatabaseEngine) -> Box<dyn DatabaseDriver> {
    match engine {
        DatabaseEngine::Sqlite => Box::new(SqliteDriver),
        other => Box::new(NetworkDriver {
            engine: other.clone(),
        }),
    }
}

#[cfg(test)]
mod fixture_tests {
    use super::*;
    use serde_json::Value;
    use std::{fs, path::PathBuf};

    fn fixture_dir() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("fixtures")
            .join("core-banking")
    }
    fn fixture_profile() -> ConnectionProfile {
        let path = fixture_dir().join("banking-small.sqlite");
        ConnectionProfile {
            id: "fixture".into(),
            name: "Synthetic Core Banking".into(),
            engine: DatabaseEngine::Sqlite,
            host: None,
            port: None,
            database: None,
            username: None,
            sqlite_path: Some(path.to_string_lossy().to_string()),
            source_path: None,
            allow_writes: false,
            tls_mode: TlsMode::VerifyIdentity,
            created_at: "fixture".into(),
        }
    }
    fn normalized(mut value: Value) -> Value {
        if let Some(object) = value.as_object_mut() {
            object.insert("capturedAt".into(), Value::String("<dynamic>".into()));
        }
        value
    }
    fn expected(name: &str) -> Value {
        serde_json::from_str(
            &fs::read_to_string(fixture_dir().join("expected").join(name)).unwrap(),
        )
        .unwrap()
    }
    fn assert_json(actual: Value, expected: Value) {
        fn mismatch(path: &str, a: &Value, e: &Value) -> Option<String> {
            match (a, e) {
                (Value::Object(ao), Value::Object(eo)) => {
                    for key in ao.keys().chain(eo.keys()) {
                        if ao.get(key) != eo.get(key) {
                            return mismatch(
                                &format!("{path}.{key}"),
                                ao.get(key).unwrap_or(&Value::Null),
                                eo.get(key).unwrap_or(&Value::Null),
                            )
                            .or_else(|| {
                                Some(format!(
                                    "{path}.{key}: actual={:?} expected={:?}",
                                    ao.get(key),
                                    eo.get(key)
                                ))
                            });
                        }
                    }
                    None
                }
                (Value::Array(aa), Value::Array(ea)) => {
                    if aa.len() != ea.len() {
                        return Some(format!(
                            "{path}: array lengths {} != {}",
                            aa.len(),
                            ea.len()
                        ));
                    }
                    for (i, (av, ev)) in aa.iter().zip(ea).enumerate() {
                        if av != ev {
                            return mismatch(&format!("{path}[{i}]"), av, ev);
                        }
                    }
                    None
                }
                _ => Some(format!("{path}: actual={a:?} expected={e:?}")),
            }
        }
        if actual != expected {
            panic!(
                "{}",
                mismatch("$", &actual, &expected).unwrap_or_else(|| "JSON differs".into())
            );
        }
    }

    #[test]
    fn banking_live_introspection_matches_golden() {
        let schema = SqliteDriver.introspect(&fixture_profile(), None).unwrap();
        assert_json(
            normalized(serde_json::to_value(schema).unwrap()),
            expected("querycraft-live-v1.json"),
        );
    }

    #[test]
    fn banking_source_analysis_matches_golden() {
        let analysis = crate::source::analyze(&fixture_dir()).unwrap();
        assert_json(
            normalized(serde_json::to_value(analysis.schema).unwrap()),
            expected("querycraft-source-v1.json"),
        );
    }

    #[test]
    fn banking_queries_cover_views_ctes_and_windows() {
        let profile = fixture_profile();
        let view=SqliteDriver.execute(&profile,None,"SELECT branch_id, SUM(arrears_minor) AS arrears FROM v_loan_arrears GROUP BY branch_id ORDER BY arrears DESC LIMIT 5",false).unwrap();
        assert!(!view.rows.is_empty());
        let cte=SqliteDriver.execute(&profile,None,"WITH ranked AS (SELECT account_id, posting_month, net_flow_minor, ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY posting_month DESC) AS rn FROM v_monthly_cash_flow) SELECT account_id, posting_month, net_flow_minor FROM ranked WHERE rn = 1 LIMIT 20",false).unwrap();
        assert!(!cte.rows.is_empty());
    }

    #[test]
    fn banking_large_read_is_capped() {
        let result = SqliteDriver
            .execute(
                &fixture_profile(),
                None,
                "SELECT * FROM ledger_entries ORDER BY entry_id",
                false,
            )
            .unwrap();
        assert_eq!(result.rows.len(), 10_000);
        assert!(result.truncated);
    }

    #[test]
    fn banking_blocked_examples_never_execute() {
        let cases: Value = serde_json::from_str(
            &fs::read_to_string(fixture_dir().join("queries").join("blocked.json")).unwrap(),
        )
        .unwrap();
        for case in cases.as_array().unwrap() {
            let sql = case["sql"].as_str().unwrap();
            assert!(
                SqliteDriver
                    .execute(&fixture_profile(), None, sql, false)
                    .is_err(),
                "blocked example was accepted: {}",
                case["name"]
            );
        }
    }

    #[test]
    fn sqlite_changes_require_profile_opt_in_and_confirmation() {
        let path = std::env::temp_dir().join(format!(
            "agentsql-write-test-{}.sqlite",
            uuid::Uuid::new_v4()
        ));
        Connection::open(&path)
            .unwrap()
            .execute_batch("CREATE TABLE items(id INTEGER PRIMARY KEY, name TEXT NOT NULL);")
            .unwrap();
        let mut profile = ConnectionProfile {
            id: "write-test".into(),
            name: "Write test".into(),
            engine: DatabaseEngine::Sqlite,
            host: None,
            port: None,
            database: None,
            username: None,
            sqlite_path: Some(path.to_string_lossy().to_string()),
            source_path: None,
            allow_writes: false,
            tls_mode: TlsMode::VerifyIdentity,
            created_at: "test".into(),
        };
        assert!(SqliteDriver
            .execute(
                &profile,
                None,
                "INSERT INTO items(name) VALUES ('alpha')",
                true
            )
            .is_err());
        profile.allow_writes = true;
        assert!(SqliteDriver
            .execute(
                &profile,
                None,
                "INSERT INTO items(name) VALUES ('alpha')",
                false
            )
            .is_err());
        let inserted = SqliteDriver
            .execute(
                &profile,
                None,
                "INSERT INTO items(name) VALUES ('alpha')",
                true,
            )
            .unwrap();
        assert_eq!(inserted.rows[0][1], Value::from(1));
        SqliteDriver
            .execute(
                &profile,
                None,
                "UPDATE items SET name='beta' WHERE id=1",
                true,
            )
            .unwrap();
        SqliteDriver
            .execute(
                &profile,
                None,
                "CREATE TABLE audit_events(id INTEGER PRIMARY KEY)",
                true,
            )
            .unwrap();
        let read = SqliteDriver
            .execute(&profile, None, "SELECT name FROM items", false)
            .unwrap();
        assert_eq!(read.rows[0][0], Value::String("beta".into()));
        drop(read);
        fs::remove_file(path).unwrap();
    }
}
