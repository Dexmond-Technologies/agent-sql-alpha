import type { QueryAssessment } from "./types";

const mapping: Record<string, Pick<QueryAssessment, "operation" | "label" | "destructive">> = {
  SELECT: { operation: "read", label: "Read query", destructive: false },
  WITH: { operation: "read", label: "Query", destructive: false },
  EXPLAIN: { operation: "read", label: "Explain", destructive: false },
  SHOW: { operation: "read", label: "Metadata query", destructive: false },
  DESCRIBE: { operation: "read", label: "Metadata query", destructive: false },
  INSERT: { operation: "insert", label: "Insert rows", destructive: false },
  UPDATE: { operation: "update", label: "Update rows", destructive: true },
  DELETE: { operation: "delete", label: "Delete rows", destructive: true },
  MERGE: { operation: "merge", label: "Merge rows", destructive: true },
  REPLACE: { operation: "merge", label: "Replace rows", destructive: true },
  UPSERT: { operation: "merge", label: "Upsert rows", destructive: true },
  CREATE: { operation: "ddl", label: "Create database object", destructive: true },
  ALTER: { operation: "ddl", label: "Alter database object", destructive: true },
  DROP: { operation: "ddl", label: "Drop database object", destructive: true },
  TRUNCATE: { operation: "ddl", label: "Truncate data", destructive: true },
  CALL: { operation: "procedure", label: "Call procedure", destructive: true },
  EXEC: { operation: "procedure", label: "Execute procedure", destructive: true },
  EXECUTE: { operation: "procedure", label: "Execute procedure", destructive: true },
  GRANT: { operation: "permission", label: "Grant permissions", destructive: true },
  REVOKE: { operation: "permission", label: "Revoke permissions", destructive: true },
  VACUUM: { operation: "maintenance", label: "Database maintenance", destructive: false },
  ANALYZE: { operation: "maintenance", label: "Database maintenance", destructive: false },
  SET: { operation: "maintenance", label: "Change session setting", destructive: false },
  PRAGMA: { operation: "maintenance", label: "SQLite maintenance", destructive: false }
};

/** A preview-only classifier. Native execution always uses the stricter Rust gate. */
export function assessBrowserQuery(sql: string, allowWrites: boolean): QueryAssessment {
  const trimmed = sql.replace(/^\s*(?:--[^\n]*(?:\n|$)|\/\*[\s\S]*?\*\/\s*)*/g, "").trim();
  const statements = trimmed.split(";").filter(part => part.trim());
  if (statements.length !== 1) throw new Error("Enter exactly one SQL statement.");
  const words = statements[0].replace(/'(?:''|[^'])*'|"(?:""|[^"])*"/g, " ").match(/[A-Za-z_][A-Za-z0-9_]*/g)?.map(word => word.toUpperCase()) || [];
  let keyword = words[0] || "";
  if (keyword === "WITH") keyword = ["INSERT", "UPDATE", "DELETE", "MERGE"].find(word => words.includes(word)) || "WITH";
  const found = mapping[keyword];
  if (!found) throw new Error("This SQL command is not recognized by the execution gate.");
  if (found.operation !== "read" && !allowWrites) throw new Error("This connection is read-only. Edit the connection and explicitly enable data and schema changes first.");
  const readOnly = found.operation === "read";
  return { ...found, readOnly, requiresConfirmation: !readOnly };
}
