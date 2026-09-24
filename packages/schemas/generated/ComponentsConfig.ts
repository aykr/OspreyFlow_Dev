// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * Default: arcadedb
 */
export type GraphStore = "arcadedb" | "janusgraph";
/**
 * Default: duckdb
 */
export type AnalyticsEngine = "duckdb" | "clickhouse";
/**
 * Default: opensearch. postgres-fulltext is §3's reduced variant.
 */
export type SearchBackend = "opensearch" | "postgres-fulltext";
/**
 * Default: /var/lib/osprey/data
 */
export type Data = string;
/**
 * Default: /var/lib/osprey/staging
 */
export type Staging = string;
/**
 * Default: /var/lib/osprey/backups
 */
export type Backups = string;

/**
 * `05_DEPLOYMENT.md` §2.1's Components screen. Defaults are the `local-lite` row of §1's own
 * profile table, because that is the profile this repository is demonstrable on today.
 */
export interface ComponentsConfig {
  graph_store?: GraphStore;
  analytics_engine?: AnalyticsEngine;
  search?: SearchBackend;
  storage?: StorageRoots;
}
/**
 * `05_DEPLOYMENT.md` §2.1's Components screen: "the storage roots for data, staging and
 * backups". Paths on the deployment host, not in this repository.
 */
export interface StorageRoots {
  data?: Data;
  staging?: Staging;
  backups?: Backups;
}
