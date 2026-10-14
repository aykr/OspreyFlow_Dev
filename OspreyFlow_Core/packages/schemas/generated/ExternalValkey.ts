// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * The managed cache's address
 */
export type Host = string;
/**
 * Its port
 */
export type Port = number;
/**
 * Whether it is reached over TLS
 */
export type Tls = boolean;

/**
 * A cloud's managed Valkey or Redis (`05_DEPLOYMENT.md` §3b: ElastiCache, Azure Cache for
 * Redis); a cluster's replicas share it. Its password, if any, arrives as `VALKEY_PASSWORD`.
 */
export interface ExternalValkey {
  host: Host;
  port?: Port;
  tls?: Tls;
}
