use crate::models::{DatabaseEngine, QueryAssessment, SqlOperation};

/// Classifies one SQL statement and enforces the profile's execution policy.
/// Read-only remains the default. Write-enabled profiles may run common DML,
/// DDL, procedure, permission, and maintenance statements only after a second
/// explicit confirmation in the UI.
pub fn assess_sql(
    sql: &str,
    engine: &DatabaseEngine,
    allow_writes: bool,
) -> Result<QueryAssessment, String> {
    let tokens = tokenize(sql)?;
    let words = single_statement_words(&tokens)?;
    if contains_external_or_host_operation(&words) {
        return Err("External file, database attachment, extension loading, and host-command operations remain blocked in this alpha.".into());
    }
    if validate_read_only(sql, engine).is_ok() {
        return Ok(QueryAssessment {
            operation: SqlOperation::Read,
            label: "Read query".into(),
            read_only: true,
            destructive: false,
            requires_confirmation: false,
        });
    }
    if !allow_writes {
        return Err("This connection is read-only. Edit the connection and explicitly enable data and schema changes before running this statement.".into());
    }
    if words
        .iter()
        .any(|word| matches!(*word, "ATTACH" | "DETACH" | "COPY" | "LOAD"))
    {
        return Err(
            "External file and database attachment operations remain blocked in this alpha.".into(),
        );
    }
    if words
        .iter()
        .any(|word| matches!(*word, "BEGIN" | "COMMIT" | "ROLLBACK" | "SAVEPOINT"))
    {
        return Err("Manual transaction-control statements are not supported because each approved statement runs in an isolated execution.".into());
    }
    let first = words[0];
    let operation = if first == "INSERT"
        || words.first() == Some(&"WITH") && words.contains(&"INSERT")
    {
        SqlOperation::Insert
    } else if first == "UPDATE" || words.first() == Some(&"WITH") && words.contains(&"UPDATE") {
        SqlOperation::Update
    } else if first == "DELETE" || words.first() == Some(&"WITH") && words.contains(&"DELETE") {
        SqlOperation::Delete
    } else if matches!(first, "MERGE" | "UPSERT" | "REPLACE") {
        SqlOperation::Merge
    } else if matches!(first, "CREATE" | "ALTER" | "DROP" | "TRUNCATE")
        || first == "SELECT" && words.contains(&"INTO")
    {
        SqlOperation::Ddl
    } else if matches!(first, "CALL" | "EXEC" | "EXECUTE" | "DO") {
        SqlOperation::Procedure
    } else if matches!(first, "GRANT" | "REVOKE") {
        SqlOperation::Permission
    } else if matches!(first, "VACUUM" | "ANALYZE" | "SET" | "PRAGMA") || contains_lock(&words) {
        SqlOperation::Maintenance
    } else {
        return Err(
            "The statement type is not recognized by the elevated SQL gate and remains blocked."
                .into(),
        );
    };
    let destructive = matches!(
        operation,
        SqlOperation::Delete
            | SqlOperation::Ddl
            | SqlOperation::Procedure
            | SqlOperation::Permission
            | SqlOperation::Maintenance
    );
    let label = match operation {
        SqlOperation::Read => "Read query",
        SqlOperation::Insert => "Insert rows",
        SqlOperation::Update => "Update rows",
        SqlOperation::Delete => "Delete rows",
        SqlOperation::Merge => "Merge or replace rows",
        SqlOperation::Ddl => "Schema change",
        SqlOperation::Procedure => "Procedure execution",
        SqlOperation::Permission => "Permission change",
        SqlOperation::Maintenance => "Database maintenance",
    }
    .into();
    Ok(QueryAssessment {
        operation,
        label,
        read_only: false,
        destructive,
        requires_confirmation: true,
    })
}

/// The gate runs on every query, including text manually edited after the agent responds.
pub fn validate_read_only(sql: &str, engine: &DatabaseEngine) -> Result<(), String> {
    let tokens = tokenize(sql)?;
    let words = single_statement_words(&tokens)?;
    let forbidden = [
        "INSERT",
        "UPDATE",
        "DELETE",
        "MERGE",
        "UPSERT",
        "REPLACE",
        "CREATE",
        "ALTER",
        "DROP",
        "TRUNCATE",
        "GRANT",
        "REVOKE",
        "CALL",
        "EXEC",
        "EXECUTE",
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "SAVEPOINT",
        "SET",
        "ATTACH",
        "DETACH",
        "VACUUM",
        "ANALYZE",
        "INTO",
        "COPY",
        "LOAD",
        "DO",
        "HANDLER",
    ];
    if words.iter().any(|word| forbidden.contains(word)) {
        return Err("That statement contains a write, DDL, transaction, or procedure operation and is blocked.".into());
    }
    let first = words[0];
    let allowed = match first {
        "SELECT" => !contains_lock(&words),
        "WITH" => words.contains(&"SELECT") && !contains_lock(&words),
        "EXPLAIN" => {
            words
                .iter()
                .skip(1)
                .any(|word| *word == "SELECT" || *word == "WITH")
                && !contains_lock(&words)
        }
        "SHOW" | "DESCRIBE" | "DESC" => !matches!(engine, DatabaseEngine::Sqlite),
        "PRAGMA" => {
            matches!(engine, DatabaseEngine::Sqlite)
                && sqlite_read_pragma(words.get(1).copied())
                && !tokens.iter().any(|t| t == "=")
        }
        _ => false,
    };
    if allowed {
        Ok(())
    } else {
        Err("Only SELECT/WITH, plain EXPLAIN, and approved metadata commands are allowed.".into())
    }
}
fn single_statement_words(tokens: &[String]) -> Result<Vec<&str>, String> {
    if tokens.is_empty() {
        return Err("Enter a SQL statement first.".into());
    }
    let semis: Vec<_> = tokens
        .iter()
        .enumerate()
        .filter(|(_, token)| token.as_str() == ";")
        .collect();
    if semis.len() > 1
        || semis
            .first()
            .is_some_and(|(index, _)| *index + 1 != tokens.len())
    {
        return Err("Only one statement is allowed.".into());
    }
    let words: Vec<_> = tokens
        .iter()
        .filter(|token| token.as_str() != ";")
        .map(String::as_str)
        .collect();
    if words.is_empty() {
        Err("Enter a SQL statement first.".into())
    } else {
        Ok(words)
    }
}
fn contains_lock(words: &[&str]) -> bool {
    words.contains(&"LOCK")
        || words.iter().position(|w| *w == "FOR").is_some_and(|at| {
            words
                .iter()
                .skip(at + 1)
                .any(|w| *w == "UPDATE" || *w == "SHARE")
        })
}
fn contains_external_or_host_operation(words: &[&str]) -> bool {
    words.iter().any(|word| {
        matches!(
            *word,
            "ATTACH"
                | "DETACH"
                | "COPY"
                | "LOAD"
                | "LOAD_EXTENSION"
                | "PG_READ_FILE"
                | "PG_READ_BINARY_FILE"
                | "PG_STAT_FILE"
                | "PG_LS_DIR"
                | "PG_WRITE_FILE"
                | "PG_WRITE_BINARY_FILE"
                | "LO_IMPORT"
                | "LO_EXPORT"
                | "DBLINK_EXEC"
                | "XP_CMDSHELL"
                | "OPENROWSET"
                | "OPENDATASOURCE"
                | "LOAD_FILE"
        )
    }) || words
        .windows(2)
        .any(|pair| pair == ["INTO", "OUTFILE"] || pair == ["INTO", "DUMPFILE"])
}
fn sqlite_read_pragma(name: Option<&str>) -> bool {
    matches!(
        name,
        Some(
            "TABLE_INFO"
                | "TABLE_XINFO"
                | "INDEX_LIST"
                | "INDEX_INFO"
                | "INDEX_XINFO"
                | "DATABASE_LIST"
                | "COMPILE_OPTIONS"
                | "FOREIGN_KEY_LIST"
        )
    )
}
fn tokenize(input: &str) -> Result<Vec<String>, String> {
    let mut tokens = Vec::new();
    let chars: Vec<char> = input.chars().collect();
    let mut i = 0;
    while i < chars.len() {
        match chars[i] {
            '-' if chars.get(i + 1) == Some(&'-') => {
                i += 2;
                while i < chars.len() && chars[i] != '\n' {
                    i += 1;
                }
            }
            '#' => {
                i += 1;
                while i < chars.len() && chars[i] != '\n' {
                    i += 1;
                }
            }
            '/' if chars.get(i + 1) == Some(&'*') => {
                i += 2;
                while i + 1 < chars.len() && !(chars[i] == '*' && chars[i + 1] == '/') {
                    i += 1;
                }
                if i + 1 >= chars.len() {
                    return Err("Unterminated SQL comment.".into());
                }
                i += 2;
            }
            '\'' | '"' | '`' | '[' => {
                let quote = chars[i];
                let end = if quote == '[' { ']' } else { quote };
                i += 1;
                let mut closed = false;
                while i < chars.len() {
                    if chars[i] == end {
                        if chars.get(i + 1) == Some(&end) {
                            i += 2;
                            continue;
                        }
                        i += 1;
                        closed = true;
                        break;
                    }
                    i += 1;
                }
                if !closed {
                    return Err("Unterminated quoted SQL value or identifier.".into());
                }
            }
            '$' => {
                let start = i;
                i += 1;
                while i < chars.len() && (chars[i].is_ascii_alphanumeric() || chars[i] == '_') {
                    i += 1
                }
                if chars.get(i) == Some(&'$') {
                    let delimiter = chars[start..=i].iter().collect::<String>();
                    i += 1;
                    let remaining = chars[i..].iter().collect::<String>();
                    let Some(offset) = remaining.find(&delimiter) else {
                        return Err("Unterminated PostgreSQL dollar-quoted body.".into());
                    };
                    i += remaining[..offset].chars().count() + delimiter.chars().count();
                } else {
                    i = start + 1
                }
            }
            c if c.is_ascii_alphabetic() || c == '_' => {
                let mut word = String::new();
                while i < chars.len()
                    && (chars[i].is_ascii_alphanumeric() || chars[i] == '_' || chars[i] == '$')
                {
                    word.push(chars[i]);
                    i += 1;
                }
                tokens.push(word.to_ascii_uppercase());
            }
            ';' | '=' => {
                tokens.push(chars[i].to_string());
                i += 1;
            }
            _ => i += 1,
        }
    }
    Ok(tokens)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::DatabaseEngine::*;
    #[test]
    fn allows_reads_and_metadata() {
        assert!(validate_read_only("WITH x AS (SELECT 1) SELECT * FROM x", &Postgres).is_ok());
        assert!(validate_read_only("PRAGMA table_info('users')", &Sqlite).is_ok());
    }
    #[test]
    fn rejects_bypasses() {
        for sql in [
            "SELECT 1; DELETE FROM users",
            "WITH x AS (DELETE FROM users RETURNING *) SELECT * FROM x",
            "SELECT * FROM users FOR UPDATE",
            "EXPLAIN ANALYZE SELECT 1",
            "SELECT * INTO copy FROM users",
        ] {
            assert!(validate_read_only(sql, &Postgres).is_err(), "{sql}");
        }
    }
    #[test]
    fn ignores_delimiters_inside_literals_comments_and_dollar_bodies() {
        assert!(validate_read_only("SELECT '; DELETE' AS text -- ; DROP\n", &Postgres).is_ok());
        assert_eq!(
            assess_sql(
                "CREATE FUNCTION f() RETURNS void AS $$ BEGIN PERFORM 1; END $$ LANGUAGE plpgsql",
                &Postgres,
                true
            )
            .unwrap()
            .operation,
            SqlOperation::Ddl
        );
        assert!(assess_sql("SELECT 'unterminated", &Postgres, true).is_err());
    }
    #[test]
    fn elevated_gate_classifies_writes_and_keeps_external_io_blocked() {
        assert_eq!(
            assess_sql(
                "INSERT INTO audit_log(message) VALUES ('ok')",
                &Postgres,
                true
            )
            .unwrap()
            .operation,
            SqlOperation::Insert
        );
        assert_eq!(
            assess_sql("DROP TABLE old_data", &Postgres, true)
                .unwrap()
                .operation,
            SqlOperation::Ddl
        );
        assert!(assess_sql("DELETE FROM accounts", &Postgres, false).is_err());
        assert!(assess_sql("COPY customers TO '/tmp/customers.csv'", &Postgres, true).is_err());
        assert!(assess_sql("SELECT pg_read_file('/etc/passwd')", &Postgres, false).is_err());
        assert!(assess_sql("SELECT load_extension('unsafe')", &Sqlite, true).is_err());
        assert!(assess_sql("DELETE FROM a; DROP TABLE a", &Postgres, true).is_err());
    }
}
