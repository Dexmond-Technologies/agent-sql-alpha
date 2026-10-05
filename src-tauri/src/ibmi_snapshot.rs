//! Import an explicitly identified IBM i catalog export without pretending it is a live driver.
use crate::models::{DatabaseEngine, ObjectKind, SchemaSnapshot, SchemaTable};
use crate::source::Analysis;
use serde::Deserialize;
use std::{collections::BTreeSet, fs::File, io::Read, path::Path};

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Catalog {
    format: String,
    captured_at: String,
    server_information: ServerInformation,
    transport_verification: String,
    read_only_requested: bool,
    schemas: Vec<String>,
    tables: Vec<SchemaTable>,
    warnings: Vec<String>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct ServerInformation {
    dbms_name: String,
    dbms_version: String,
    driver_name: String,
    driver_version: String,
}

pub fn analyze(path: &Path) -> Result<Analysis, String> {
    let file = File::open(path).map_err(|_| "Cannot open the IBM i catalog export.")?;
    let mut bytes = Vec::new();
    file.take(8 * 1024 * 1024 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "Cannot read the IBM i catalog export.")?;
    if bytes.len() > 8 * 1024 * 1024 {
        return Err("IBM i catalog exports are limited to 8 MiB.".into());
    }
    let export: Catalog = serde_json::from_slice(&bytes).map_err(|_| "Invalid IBM i catalog export. Use tools/ibmi/connector.py catalog; arbitrary JSON is not a catalog snapshot.")?;
    if export.format != "agentsql-ibmi-catalog-v1"
        || !export.read_only_requested
        || chrono::DateTime::parse_from_rfc3339(&export.captured_at).is_err()
        || export.transport_verification != "not-verified-by-exporter"
        || export.server_information.dbms_name.is_empty()
        || export.server_information.dbms_version.is_empty()
        || export.server_information.driver_name.is_empty()
        || export.server_information.driver_version.is_empty()
        || export.schemas.is_empty()
        || export.schemas.len() > 100
    {
        return Err("The IBM i export has missing or unsupported provenance fields.".into());
    }
    let dbms = export.server_information.dbms_name.to_uppercase();
    if !["AS/400", "DB2/400", "DB2 FOR I", "ISERIES"]
        .iter()
        .any(|identity| dbms.contains(identity))
    {
        return Err("The export does not declare a recognized Db2 for i database identity.".into());
    }
    let scopes: BTreeSet<_> = export.schemas.iter().collect();
    let mut seen = BTreeSet::new();
    if export.tables.is_empty() || export.tables.len() > 500 {
        return Err("The IBM i export must contain between 1 and 500 tables/views; export a narrower schema scope.".into());
    }
    for table in &export.tables {
        if !scopes.contains(&table.schema)
            || table.name.is_empty()
            || table.name.len() > 128
            || table.schema.len() > 128
            || matches!(table.kind, ObjectKind::Collection)
            || table.columns.is_empty()
            || table.columns.len() > 2000
            || table.source_file.is_some()
            || !seen.insert((&table.schema, &table.name))
        {
            return Err("The IBM i export has invalid, duplicate or out-of-scope objects.".into());
        }
        let mut names = BTreeSet::new();
        for column in &table.columns {
            if column.name.is_empty()
                || column.name.len() > 128
                || column.data_type.is_empty()
                || column.data_type.len() > 256
                || column.key.as_deref().is_some_and(|key| key != "PK")
                || !names.insert(&column.name)
            {
                return Err("The IBM i export has invalid or duplicate column metadata.".into());
            }
        }
    }
    let mut warnings = export.warnings;
    warnings.push(format!("Imported catalog captured at {}. This is not a live IBM i connection. Export provenance is declared by the file, not independently attested.", export.captured_at));
    warnings.push("The exporter requested encrypted read-only ODBC access; transport/certificate verification requires validation on the actual host and driver.".into());
    Ok(Analysis {
        schema: SchemaSnapshot {
            engine: DatabaseEngine::Source,
            tables: export.tables,
            captured_at: export.captured_at,
            source_kind: Some("db2i".into()),
            source_language: None,
        },
        scanned_files: 1,
        matched_files: 1,
        warnings,
    })
}
