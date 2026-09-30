export type DatabaseEngine = "auto" | "postgres" | "mysql" | "sqlserver" | "sqlite" | "source";
export type ProviderName = "openai" | "deepseek" | "anthropic" | "gemini" | "ollama" | "lmstudio";
export type AgentMode = "plan" | "chat" | "direct";
export type TlsMode = "verifyIdentity" | "require" | "disable";
export type SqlOperation = "read" | "insert" | "update" | "delete" | "merge" | "ddl" | "procedure" | "permission" | "maintenance";

export interface ConnectionProfile {
  id: string;
  name: string;
  engine: DatabaseEngine;
  host?: string;
  port?: number;
  database?: string;
  username?: string;
  sqlitePath?: string;
  sourcePath?: string;
  allowWrites: boolean;
  tlsMode: TlsMode;
  createdAt: string;
}

export interface ProfileInput {
  id?: string;
  name: string;
  engine: DatabaseEngine;
  host?: string;
  port?: number;
  database?: string;
  username?: string;
  password?: string;
  sqlitePath?: string;
  sourcePath?: string;
  allowWrites: boolean;
  tlsMode: TlsMode;
}

export interface SchemaTable { schema: string; name: string; kind: "table" | "view" | "collection"; columns: SchemaColumn[]; sourceFile?: string }
export interface SchemaColumn { name: string; dataType: string; nullable: boolean; key?: string }
export interface SchemaSnapshot { engine: DatabaseEngine; tables: SchemaTable[]; capturedAt: string; sourceKind?: "sql" | "chroma" | "mixed" | "unknown"; sourceLanguage?: "python" | "typescript" }
export interface QueryResult { columns: string[]; rows: unknown[][]; elapsedMs: number; truncated: boolean; }
export interface QueryAssessment { operation: SqlOperation; label: string; readOnly: boolean; destructive: boolean; requiresConfirmation: boolean; }
export interface QueryOutput { id: string; sessionId: string; sourceMessageId?: string; title: string; sql: string; result?: QueryResult; collapsed: boolean; createdAt: string; updatedAt: string; }
export interface ChatMessage { id: string; role: "user" | "assistant"; content: string; createdAt: string; sql?: string; }
export interface ChatSession { id: string; profileId: string; title: string; shareResults: boolean; mode: AgentMode; createdAt: string; }
export interface AiSettings { provider: ProviderName; model: string; baseUrl: string; configured: boolean; configPath: string; }
export interface AiSettingsInput { provider: ProviderName; model: string; baseUrl: string; apiKey?: string; }
export interface AiConnectionTest { provider: string; model: string; baseUrl: string; message: string; availableModels: string[]; }
export interface SourceImport { profile: ConnectionProfile; schema: SchemaSnapshot; scannedFiles: number; matchedFiles: number; warnings: string[] }
export interface BundledContent { rootPath: string; documentationPath: string; exampleFolderPath: string; exampleDatabasePath: string; }
