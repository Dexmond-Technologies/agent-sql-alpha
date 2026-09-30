use crate::models::{DatabaseEngine, ObjectKind, SchemaColumn, SchemaSnapshot, SchemaTable};
use regex::Regex;
use rusqlite::{Connection, OpenFlags};
use std::{collections::BTreeMap, fs, path::Path};

pub struct Analysis {
    pub schema: SchemaSnapshot,
    pub scanned_files: usize,
    pub matched_files: usize,
    pub warnings: Vec<String>,
}

const SKIP_DIRS: &[&str] = &[
    ".git",
    ".svn",
    "node_modules",
    "target",
    "dist",
    "build",
    ".next",
    ".venv",
    "venv",
    "vendor",
    "coverage",
    "__pycache__",
    ".idea",
];
const MAX_FILES: usize = 2_000;
const MAX_SOURCE_FILES: usize = 1_000;
const MAX_FILE_BYTES: u64 = 1_000_000;
const MAX_TOTAL_BYTES: u64 = 16_000_000;
const MAX_TABLES: usize = 500;

pub fn analyze(folder: &Path) -> Result<Analysis, String> {
    let root = folder
        .canonicalize()
        .map_err(|e| format!("Cannot open project folder: {e}"))?;
    if !root.is_dir() {
        return Err("Choose a project folder, not a file.".into());
    }
    let mut stack = vec![(root.clone(), 0_usize)];
    let mut seen = 0_usize;
    let mut scanned = 0_usize;
    let mut matched = 0_usize;
    let mut bytes = 0_u64;
    let mut tables: BTreeMap<(String, String), SchemaTable> = BTreeMap::new();
    let mut chroma_candidates: BTreeMap<String, SchemaTable> = BTreeMap::new();
    let mut chroma_detected = false;
    let mut source_language: Option<String> = None;
    let mut catalogs = 0_usize;
    let mut warnings = Vec::new();
    while let Some((dir, depth)) = stack.pop() {
        let entries = match fs::read_dir(&dir) {
            Ok(v) => v,
            Err(_) => {
                warnings.push("Some folders could not be read.".into());
                continue;
            }
        };
        for entry in entries.flatten() {
            seen += 1;
            if seen > MAX_FILES {
                warnings.push("Project scan reached its 2,000-entry limit.".into());
                break;
            }
            let path = entry.path();
            let Ok(kind) = entry.file_type() else {
                continue;
            };
            if kind.is_symlink() {
                continue;
            }
            if !path
                .canonicalize()
                .is_ok_and(|resolved| resolved.starts_with(&root))
            {
                continue;
            }
            if kind.is_dir() {
                if depth < 10
                    && !SKIP_DIRS.contains(
                        &entry
                            .file_name()
                            .to_string_lossy()
                            .to_ascii_lowercase()
                            .as_str(),
                    )
                {
                    stack.push((path, depth + 1));
                }
                continue;
            }
            if kind.is_file()
                && entry
                    .file_name()
                    .to_string_lossy()
                    .eq_ignore_ascii_case("chroma.sqlite3")
            {
                if catalogs >= 10 {
                    warnings.push("Only the first 10 Chroma catalogs were inspected.".into());
                    continue;
                }
                catalogs += 1;
                chroma_detected = true;
                scanned += 1;
                let relative = path
                    .strip_prefix(&root)
                    .unwrap_or(&path)
                    .to_string_lossy()
                    .replace('\\', "/");
                match inspect_chroma_catalog(&path,&relative) {
                    Ok(collections) => { matched+=1; for collection in collections { chroma_candidates.insert(collection.name.clone(),collection); } },
                    Err(_) => warnings.push("Chroma storage was detected, but its collection catalog could not be read with this version/layout.".into()),
                }
                continue;
            }
            if !kind.is_file() || !supported(&path) {
                continue;
            }
            if scanned >= MAX_SOURCE_FILES {
                warnings.push("Project scan reached its 1,000-source-file limit.".into());
                break;
            }
            let Ok(meta) = entry.metadata() else { continue };
            if meta.len() > MAX_FILE_BYTES {
                warnings.push("Oversized schema files were skipped.".into());
                continue;
            }
            if bytes + meta.len() > MAX_TOTAL_BYTES {
                warnings.push("Project scan reached its 16 MB reading limit.".into());
                break;
            }
            bytes += meta.len();
            let Ok(body) = fs::read_to_string(&path) else {
                warnings.push("Non-text schema files were skipped.".into());
                continue;
            };
            scanned += 1;
            let relative = path
                .strip_prefix(&root)
                .unwrap_or(&path)
                .to_string_lossy()
                .replace('\\', "/");
            let ext = path
                .extension()
                .and_then(|s| s.to_str())
                .unwrap_or("")
                .to_ascii_lowercase();
            let found = if ext == "prisma" {
                parse_prisma(&body, &relative)
            } else if ext == "sql" {
                parse_sql(&body, &relative)
            } else {
                Vec::new()
            };
            let is_code = ["py", "ts", "tsx", "js", "jsx", "mjs", "cjs"].contains(&ext.as_str());
            let detected_here = is_code && has_chroma_marker(&body)
                || is_manifest(&path) && has_chroma_manifest(&body);
            if detected_here {
                chroma_detected = true;
                if is_code {
                    source_language.get_or_insert_with(|| {
                        if ext == "py" {
                            "python".into()
                        } else {
                            "typescript".into()
                        }
                    });
                }
            }
            if !found.is_empty() || detected_here {
                matched += 1;
            }
            if is_code {
                for collection in parse_chroma_collections(&body, &relative) {
                    chroma_candidates.insert(collection.name.clone(), collection);
                }
            }
            for table in found {
                let key = (table.schema.clone(), table.name.clone());
                if tables.len() >= MAX_TABLES && !tables.contains_key(&key) {
                    warnings.push("Project scan reached its 500-table limit.".into());
                    break;
                }
                if tables.get(&key).and_then(|old| old.source_file.as_ref())
                    <= table.source_file.as_ref()
                {
                    tables.insert(key, table);
                }
            }
        }
        if seen > MAX_FILES || scanned >= MAX_SOURCE_FILES || bytes >= MAX_TOTAL_BYTES {
            break;
        }
    }
    let sql_found = !tables.is_empty();
    if chroma_detected {
        for collection in chroma_candidates.into_values() {
            let key = (collection.schema.clone(), collection.name.clone());
            if tables.len() < MAX_TABLES {
                tables.insert(key, collection);
            }
        }
    }
    let chroma_named = tables
        .values()
        .any(|item| matches!(item.kind, ObjectKind::Collection));
    if chroma_detected && !chroma_named {
        warnings.push("Chroma was detected, but no collection names were found in source or the local catalog.".into());
    }
    if !sql_found && !chroma_detected {
        warnings.push(
            "No SQL tables, Prisma models, or Chroma usage were found in supported source files."
                .into(),
        );
    }
    let source_kind = if sql_found && chroma_detected {
        "mixed"
    } else if chroma_detected {
        "chroma"
    } else if sql_found {
        "sql"
    } else {
        "unknown"
    };
    warnings.sort();
    warnings.dedup();
    Ok(Analysis {
        schema: SchemaSnapshot {
            engine: DatabaseEngine::Source,
            tables: tables.into_values().collect(),
            captured_at: chrono::Utc::now().to_rfc3339(),
            source_kind: Some(source_kind.into()),
            source_language,
        },
        scanned_files: scanned,
        matched_files: matched,
        warnings,
    })
}

fn supported(path: &Path) -> bool {
    let name = path
        .file_name()
        .unwrap_or_default()
        .to_string_lossy()
        .to_ascii_lowercase();
    if name.starts_with('.')
        || name.contains("secret")
        || name.contains("credential")
        || name.contains("password")
    {
        return false;
    }
    path.extension().is_some_and(|e| {
        [
            "sql", "prisma", "py", "ts", "tsx", "js", "jsx", "mjs", "cjs",
        ]
        .iter()
        .any(|x| e.eq_ignore_ascii_case(x))
    }) || is_manifest(path)
}

fn is_manifest(path: &Path) -> bool {
    path.file_name().is_some_and(|s| {
        ["package.json", "requirements.txt", "pyproject.toml"]
            .iter()
            .any(|name| s.eq_ignore_ascii_case(name))
    })
}
fn has_chroma_manifest(body: &str) -> bool {
    Regex::new(r#"(?i)(?:\bchromadb\b|\blangchain.chroma\b|@langchain/chroma)"#)
        .unwrap()
        .is_match(body)
}
fn has_chroma_marker(body: &str) -> bool {
    Regex::new(r#"(?i)(?:\bchromadb\b|\blangchain_chroma\b|@langchain/chroma|/vectorstores/chroma|\bChromaClient\b|\bPersistentClient\b)"#).unwrap().is_match(body)
}

fn parse_chroma_collections(body: &str, source: &str) -> Vec<SchemaTable> {
    let patterns = [
        r#"(?i)\b(?:get_or_create_collection|create_collection|get_collection)\s*\(\s*(?:name\s*=\s*)?["']([A-Za-z0-9_.-]{3,80})["']"#,
        r#"(?i)\b(?:getOrCreateCollection|createCollection|getCollection)\s*\(\s*\{[^}]{0,500}?\bname\s*:\s*["']([A-Za-z0-9_.-]{3,80})["']"#,
        r#"(?i)\b(?:collection_name\s*=|collectionName\s*:)\s*["']([A-Za-z0-9_.-]{3,80})["']"#,
    ];
    let mut names = BTreeMap::new();
    for pattern in patterns {
        let re = Regex::new(pattern).unwrap();
        for c in re.captures_iter(body) {
            names.insert(c[1].to_string(), ());
        }
    }
    names
        .into_keys()
        .map(|name| SchemaTable {
            schema: "chroma".into(),
            name,
            kind: ObjectKind::Collection,
            columns: chroma_fields(),
            source_file: Some(source.into()),
        })
        .collect()
}
fn chroma_fields() -> Vec<SchemaColumn> {
    [
        ("id", "string", false),
        ("document", "text", true),
        ("metadata", "object", true),
        ("embedding", "vector", true),
        ("uri", "string", true),
    ]
    .into_iter()
    .map(|(name, data_type, nullable)| SchemaColumn {
        name: name.into(),
        data_type: data_type.into(),
        nullable,
        key: None,
    })
    .collect()
}

fn inspect_chroma_catalog(path: &Path, source: &str) -> Result<Vec<SchemaTable>, String> {
    let conn = Connection::open_with_flags(
        path,
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )
    .map_err(|e| e.to_string())?;
    conn.execute_batch("PRAGMA query_only=ON;")
        .map_err(|e| e.to_string())?;
    let columns = conn
        .prepare("PRAGMA table_info(collections)")
        .map_err(|e| e.to_string())?
        .query_map([], |r| r.get::<_, String>(1))
        .map_err(|e| e.to_string())?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| e.to_string())?;
    if !columns.iter().any(|c| c == "name") {
        return Err("Unsupported Chroma catalog layout".into());
    }
    let has_dimension = columns.iter().any(|c| c == "dimension");
    let query = if has_dimension {
        "SELECT name,dimension FROM collections LIMIT 500"
    } else {
        "SELECT name,NULL FROM collections LIMIT 500"
    };
    let result = conn
        .prepare(query)
        .map_err(|e| e.to_string())?
        .query_map([], |r| {
            Ok((r.get::<_, String>(0)?, r.get::<_, Option<i64>>(1)?))
        })
        .map_err(|e| e.to_string())?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| e.to_string())?;
    Ok(result
        .into_iter()
        .filter(|(name, _)| valid_collection_name(name))
        .map(|(name, dimension)| {
            let mut fields = chroma_fields();
            if let Some(size) = dimension.filter(|n| *n > 0 && *n < 1_000_000) {
                fields[3].data_type = format!("vector({size})");
            }
            SchemaTable {
                schema: "chroma".into(),
                name,
                kind: ObjectKind::Collection,
                columns: fields,
                source_file: Some(source.into()),
            }
        })
        .collect())
}
fn valid_collection_name(s: &str) -> bool {
    s.len() >= 3
        && s.len() <= 512
        && s.chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '.' || c == '_' || c == '-')
}

fn parse_sql(body: &str, source: &str) -> Vec<SchemaTable> {
    let clean = strip_comments(body);
    let re = Regex::new(r#"(?i)\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?((?:[A-Za-z_][A-Za-z0-9_$]*|"[A-Za-z_][A-Za-z0-9_$]*"|`[A-Za-z_][A-Za-z0-9_$]*`|\[[A-Za-z_][A-Za-z0-9_$]*\])(?:\s*\.\s*(?:[A-Za-z_][A-Za-z0-9_$]*|"[A-Za-z_][A-Za-z0-9_$]*"|`[A-Za-z_][A-Za-z0-9_$]*`|\[[A-Za-z_][A-Za-z0-9_$]*\]))?)\s*\("#).unwrap();
    let column_re = Regex::new(r#"^\s*(?:"([A-Za-z_][A-Za-z0-9_$]*)"|`([A-Za-z_][A-Za-z0-9_$]*)`|\[([A-Za-z_][A-Za-z0-9_$]*)\]|([A-Za-z_][A-Za-z0-9_$]*))\s+(.+)$"#).unwrap();
    let mut out = Vec::new();
    for capture in re.captures_iter(&clean) {
        let Some(name_match) = capture.get(1) else {
            continue;
        };
        let Some(full_match) = capture.get(0) else {
            continue;
        };
        let raw = name_match.as_str().replace(['"', '`', '[', ']', ' '], "");
        let (schema, name) = raw
            .split_once('.')
            .map(|(a, b)| (a.to_owned(), b.to_owned()))
            .unwrap_or(("inferred".into(), raw));
        let Some((body, _)) = enclosed(&clean, full_match.end() - 1, '(', ')') else {
            continue;
        };
        let mut columns = Vec::new();
        for definition in split_top_level(body) {
            let Some(c) = column_re.captures(definition) else {
                continue;
            };
            let column_name = (1..=4)
                .find_map(|i| c.get(i).map(|v| v.as_str()))
                .unwrap_or("");
            if [
                "CONSTRAINT",
                "PRIMARY",
                "FOREIGN",
                "UNIQUE",
                "CHECK",
                "KEY",
                "INDEX",
            ]
            .contains(&column_name.to_ascii_uppercase().as_str())
            {
                continue;
            }
            let rest = c.get(5).map(|v| v.as_str()).unwrap_or("");
            let data_type = rest
                .split_whitespace()
                .take_while(|w| {
                    ![
                        "PRIMARY",
                        "NOT",
                        "NULL",
                        "DEFAULT",
                        "REFERENCES",
                        "UNIQUE",
                        "CHECK",
                        "CONSTRAINT",
                        "COLLATE",
                        "GENERATED",
                        "IDENTITY",
                        "AUTO_INCREMENT",
                    ]
                    .contains(&w.to_ascii_uppercase().as_str())
                })
                .collect::<Vec<_>>()
                .join(" ");
            if data_type.is_empty() || data_type.len() > 80 {
                continue;
            }
            let upper = rest.to_ascii_uppercase();
            if columns.len() < 100 {
                columns.push(SchemaColumn {
                    name: column_name.into(),
                    data_type,
                    nullable: !upper.contains("NOT NULL") && !upper.contains("PRIMARY KEY"),
                    key: upper.contains("PRIMARY KEY").then(|| "PK".into()),
                });
            }
        }
        if !columns.is_empty() {
            out.push(SchemaTable {
                schema,
                name,
                kind: ObjectKind::Table,
                columns,
                source_file: Some(source.into()),
            });
        }
    }
    out
}

fn parse_prisma(body: &str, source: &str) -> Vec<SchemaTable> {
    let re = Regex::new(r"(?m)^\s*model\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{").unwrap();
    let field_re =
        Regex::new(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+([A-Za-z_][A-Za-z0-9_]*)(\??)(\[\])?").unwrap();
    let mut out = Vec::new();
    for c in re.captures_iter(body) {
        let Some(m) = c.get(0) else { continue };
        let Some((block, _)) = enclosed(body, m.end() - 1, '{', '}') else {
            continue;
        };
        let mut columns = Vec::new();
        let mut mapped_name = c[1].to_owned();
        for line in block.lines() {
            let trim = line.trim();
            if let Some(mapped) = trim
                .strip_prefix("@@map(")
                .and_then(|s| s.split('"').nth(1))
            {
                if valid_ident(mapped) {
                    mapped_name = mapped.into();
                }
            }
            if trim.starts_with("//") || trim.starts_with("@@") {
                continue;
            }
            let Some(field) = field_re.captures(trim) else {
                continue;
            };
            let ty = &field[2];
            if ![
                "String", "Int", "BigInt", "Float", "Decimal", "Boolean", "DateTime", "Bytes",
                "Json",
            ]
            .contains(&ty)
            {
                continue;
            }
            let mapped = trim
                .split("@map(\"")
                .nth(1)
                .and_then(|s| s.split('"').next())
                .filter(|s| valid_ident(s));
            if columns.len() < 100 {
                columns.push(SchemaColumn {
                    name: mapped.unwrap_or(&field[1]).into(),
                    data_type: prisma_type(ty).into(),
                    nullable: field.get(3).is_some_and(|m| !m.as_str().is_empty()),
                    key: trim.contains("@id").then(|| "PK".into()),
                });
            }
        }
        if !columns.is_empty() {
            out.push(SchemaTable {
                schema: "inferred".into(),
                name: mapped_name,
                kind: ObjectKind::Table,
                columns,
                source_file: Some(source.into()),
            });
        }
    }
    out
}

fn prisma_type(t: &str) -> &'static str {
    match t {
        "String" => "TEXT",
        "Int" => "INTEGER",
        "BigInt" => "BIGINT",
        "Float" => "DOUBLE",
        "Decimal" => "DECIMAL",
        "Boolean" => "BOOLEAN",
        "DateTime" => "TIMESTAMP",
        "Bytes" => "BLOB",
        "Json" => "JSON",
        _ => "UNKNOWN",
    }
}
fn valid_ident(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 80
        && s.chars()
            .next()
            .is_some_and(|c| c.is_ascii_alphabetic() || c == '_')
        && s.chars().all(|c| c.is_ascii_alphanumeric() || c == '_')
}

fn enclosed(text: &str, open: usize, left: char, right: char) -> Option<(&str, usize)> {
    let mut depth = 0;
    let mut quote = None;
    let mut escaped = false;
    for (offset, ch) in text[open..].char_indices() {
        if let Some(q) = quote {
            if escaped {
                escaped = false;
                continue;
            }
            if ch == '\\' {
                escaped = true;
                continue;
            }
            if ch == q {
                quote = None;
            }
            continue;
        }
        if ch == '\'' || ch == '"' || ch == '`' {
            quote = Some(ch);
            continue;
        }
        if ch == left {
            depth += 1;
        }
        if ch == right {
            depth -= 1;
            if depth == 0 {
                return Some((&text[open + 1..open + offset], open + offset + 1));
            }
        }
    }
    None
}
fn split_top_level(body: &str) -> Vec<&str> {
    let mut parts = Vec::new();
    let (mut depth, mut start, mut quote) = (0_i32, 0_usize, None);
    for (i, ch) in body.char_indices() {
        if let Some(q) = quote {
            if ch == q {
                quote = None;
            }
            continue;
        }
        if ch == '\'' || ch == '"' || ch == '`' {
            quote = Some(ch);
        } else if ch == '(' {
            depth += 1;
        } else if ch == ')' {
            depth -= 1;
        } else if ch == ',' && depth == 0 {
            parts.push(&body[start..i]);
            start = i + 1;
        }
    }
    parts.push(&body[start..]);
    parts
}
fn strip_comments(body: &str) -> String {
    let chars: Vec<char> = body.chars().collect();
    let mut out = String::with_capacity(body.len());
    let (mut i, mut quote) = (0_usize, None);
    while i < chars.len() {
        let c = chars[i];
        let next = chars.get(i + 1).copied();
        if let Some(q) = quote {
            out.push(c);
            if c == q {
                quote = None;
            }
            i += 1;
            continue;
        }
        if c == '\'' || c == '"' || c == '`' {
            quote = Some(c);
            out.push(c);
            i += 1;
            continue;
        }
        if c == '-' && next == Some('-') {
            while i < chars.len() && chars[i] != '\n' {
                i += 1;
            }
            continue;
        }
        if c == '/' && next == Some('*') {
            i += 2;
            while i + 1 < chars.len() && !(chars[i] == '*' && chars[i + 1] == '/') {
                i += 1;
            }
            i = (i + 2).min(chars.len());
            out.push(' ');
            continue;
        }
        out.push(c);
        i += 1;
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn sql_schema_is_structured_only() {
        let found=parse_sql("-- CREATE TABLE fake (x INT);\nCREATE TABLE IF NOT EXISTS public.orders (id BIGINT PRIMARY KEY, price DECIMAL(10,2) NOT NULL, CONSTRAINT x CHECK(price > 0)); INSERT INTO orders VALUES (1, 9);", "migrations/001.sql");
        assert_eq!(found.len(), 1);
        assert_eq!(found[0].name, "orders");
        assert_eq!(found[0].columns.len(), 2);
        assert_eq!(found[0].columns[1].data_type, "DECIMAL(10,2)");
    }
    #[test]
    fn prisma_maps_fields() {
        let found=parse_prisma("model User {\n id Int @id\n email String? @map(\"email_address\")\n posts Post[]\n @@map(\"users\")\n}","schema.prisma");
        assert_eq!(found[0].name, "users");
        assert_eq!(found[0].columns.len(), 2);
        assert_eq!(found[0].columns[1].name, "email_address");
        assert!(found[0].columns[1].nullable);
    }
    #[test]
    fn scan_ignores_env_and_dependencies() {
        let root =
            std::env::temp_dir().join(format!("querycraft-source-test-{}", uuid::Uuid::new_v4()));
        fs::create_dir_all(root.join("node_modules")).unwrap();
        fs::write(root.join(".env.sql"), "CREATE TABLE secrets (key TEXT);").unwrap();
        fs::write(
            root.join("node_modules/ignored.sql"),
            "CREATE TABLE ignored (id INT);",
        )
        .unwrap();
        fs::write(
            root.join("schema.prisma"),
            "model Account {\n id Int @id\n}",
        )
        .unwrap();
        let result = analyze(&root).unwrap();
        assert_eq!(result.schema.tables.len(), 1);
        assert_eq!(result.schema.tables[0].name, "Account");
        fs::remove_dir_all(&root).unwrap();
    }
    #[test]
    fn finds_python_chroma_collection_without_secrets() {
        let root =
            std::env::temp_dir().join(format!("querycraft-chroma-test-{}", uuid::Uuid::new_v4()));
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("vector_store.py"),"import chromadb\nclient = chromadb.PersistentClient(path='./data')\ncollection = client.get_or_create_collection(name='research_docs')\ncollection.add(ids=['private'], documents=['secret text'])").unwrap();
        fs::write(root.join(".env"), "CHROMA_API_KEY=secret").unwrap();
        let result = analyze(&root).unwrap();
        assert_eq!(result.schema.source_kind.as_deref(), Some("chroma"));
        assert_eq!(result.schema.source_language.as_deref(), Some("python"));
        assert_eq!(result.schema.tables.len(), 1);
        assert_eq!(result.schema.tables[0].name, "research_docs");
        assert!(matches!(
            result.schema.tables[0].kind,
            ObjectKind::Collection
        ));
        assert!(!serde_json::to_string(&result.schema)
            .unwrap()
            .contains("secret text"));
        fs::remove_dir_all(&root).unwrap();
    }
    #[test]
    fn finds_typescript_chroma_collection() {
        let body="import { ChromaClient } from 'chromadb';\nconst collection = await client.getCollection({ name: 'customer_vectors' });";
        assert!(has_chroma_marker(body));
        let found = parse_chroma_collections(body, "src/vector.ts");
        assert_eq!(found.len(), 1);
        assert_eq!(found[0].name, "customer_vectors");
    }
    #[test]
    fn dynamic_collection_is_detected_without_fabricated_name() {
        let root = std::env::temp_dir().join(format!(
            "querycraft-chroma-dynamic-test-{}",
            uuid::Uuid::new_v4()
        ));
        fs::create_dir_all(&root).unwrap();
        fs::write(
            root.join("db.py"),
            "import chromadb\ncollection = client.get_collection(name=config.collection)",
        )
        .unwrap();
        let result = analyze(&root).unwrap();
        assert_eq!(result.schema.source_kind.as_deref(), Some("chroma"));
        assert!(result.schema.tables.is_empty());
        assert!(result
            .warnings
            .iter()
            .any(|w| w.contains("no collection names")));
        fs::remove_dir_all(&root).unwrap();
    }
    #[test]
    fn reads_persisted_chroma_catalog_without_records() {
        let root = std::env::temp_dir().join(format!(
            "querycraft-chroma-catalog-test-{}",
            uuid::Uuid::new_v4()
        ));
        fs::create_dir_all(&root).unwrap();
        let db = root.join("chroma.sqlite3");
        let conn = Connection::open(&db).unwrap();
        conn.execute_batch("CREATE TABLE collections(id TEXT, name TEXT, dimension INTEGER); INSERT INTO collections VALUES('x','research_vectors',768);").unwrap();
        drop(conn);
        let result = analyze(&root).unwrap();
        assert_eq!(result.schema.source_kind.as_deref(), Some("chroma"));
        assert_eq!(result.schema.tables[0].name, "research_vectors");
        assert_eq!(result.schema.tables[0].columns[3].data_type, "vector(768)");
        fs::remove_dir_all(&root).unwrap();
    }
}
