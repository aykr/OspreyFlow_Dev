// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "files" | "sql" | "api" | "json";
export type Name = string;
export type Settings = (SqlConnectionSettings | ApiConnectionSettings | JsonConnectionSettings) | null;
export type Kind1 = "sql";
export type Host = string;
export type Port = number;
export type Database = string;
export type User = string;
export type Secret = string;
export type Tls = "require" | "verify-full";
export type CaCertificate = string | null;
/**
 * @minItems 1
 */
export type Schemas = [string, ...string[]];
export type Kind2 = "api";
export type BaseUrl = string;
export type Auth = "none" | "bearer";
export type Secret1 = string | null;
export type Pagination = "none" | "page" | "next_link";
export type PageParam = string;
export type NextAt = string | null;
export type CaCertificate1 = string | null;
export type Kind3 = "json";
export type Datasets = string[];

export interface ConnectionInput {
  kind?: Kind;
  name: Name;
  settings?: Settings;
  datasets?: Datasets;
  [k: string]: unknown;
}
/**
 * A SQL database read through a **read-only** login over TLS (the redesign's phase 9). The
 * login is checked read-only by *Test connection* and again before every read.
 */
export interface SqlConnectionSettings {
  kind?: Kind1;
  host: Host;
  port?: Port;
  database: Database;
  user: User;
  secret: Secret;
  tls?: Tls;
  ca_certificate?: CaCertificate;
  schemas?: Schemas;
}
/**
 * An HTTP API: its base URL (HTTPS only), how it is signed in to, and how it pages. Its host
 * must be on the deployment's egress allow-list (`OSPREY_CONNECTOR_EGRESS`), which only an
 * operator changes: a host not on it is refused in words that say whom to ask.
 */
export interface ApiConnectionSettings {
  kind?: Kind2;
  base_url: BaseUrl;
  auth?: Auth;
  secret?: Secret1;
  pagination?: Pagination;
  page_param?: PageParam;
  next_at?: NextAt;
  ca_certificate?: CaCertificate1;
}
/**
 * JSON files in the ingest root: a source names its file pattern and where its records are.
 */
export interface JsonConnectionSettings {
  kind?: Kind3;
}
