// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "sql";
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

/**
 * A SQL database read through a **read-only** login over TLS (the redesign's phase 9). The
 * login is checked read-only by *Test connection* and again before every read.
 */
export interface SqlConnectionSettings {
  kind?: Kind;
  host: Host;
  port?: Port;
  database: Database;
  user: User;
  secret: Secret;
  tls?: Tls;
  ca_certificate?: CaCertificate;
  schemas?: Schemas;
}
