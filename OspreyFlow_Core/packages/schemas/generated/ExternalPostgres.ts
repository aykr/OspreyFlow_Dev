// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * The managed server's address
 */
export type Host = string;
/**
 * Its port
 */
export type Port = number;
/**
 * The deployment's database on it
 */
export type Database = string;
/**
 * The login, which needs CREATEROLE and CREATEDB there
 */
export type User = string;
/**
 * Default: require. A managed server is reached over TLS.
 */
export type Sslmode = "require" | "verify-ca" | "verify-full";

/**
 * A cloud's managed PostgreSQL (`05_DEPLOYMENT.md` §3a). The password is never here: it arrives
 * at apply as `OSPREY_POSTGRES_PASSWORD`, from the cloud's secret store.
 */
export interface ExternalPostgres {
  host: Host;
  port?: Port;
  database?: Database;
  user?: User;
  sslmode?: Sslmode;
}
