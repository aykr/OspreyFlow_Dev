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
 * Default: /var/lib/osprey/ingest
 */
export type Ingest = string;
/**
 * Default: /var/lib/osprey/tiles
 */
export type Tiles = string;
/**
 * Default: none — the owned services (workspace, api, ingest) are PULLED, by the digest recorded in versions.lock, from the registry reference harness/render.py's own service_images names. This is the operator path: the harness image itself carries no services/ or apps/workspace source, and round 05's own finding was that the documented one-command bootstrap could not Launch without it — a clean laptop has no checkout. Set to a checkout root containing services/api/Dockerfile, services/ingest/Dockerfile and apps/workspace/Dockerfile (this repository's own root, for a developer/CI run) to BUILD owned images from source instead. Declared and the Dockerfiles absent is refused by name (harness.render.MissingDockerfileError) — never silently treated as the pull path.
 */
export type SourcePath = string | null;

/**
 * `05_DEPLOYMENT.md` §2.1's Components screen. Defaults are the `local-lite` row of §1's own
 * profile table, because that is the profile this repository is demonstrable on today.
 */
export interface ComponentsConfig {
  graph_store?: GraphStore;
  analytics_engine?: AnalyticsEngine;
  search?: SearchBackend;
  storage?: StorageRoots;
  source_path?: SourcePath;
}
/**
 * `05_DEPLOYMENT.md` §2.1's Components screen: "the storage roots for data, staging and
 * backups", plus `ingest` (owner ruling R6, 27 September 2026). Paths on the deployment host,
 * not in this repository.
 */
export interface StorageRoots {
  data?: Data;
  staging?: Staging;
  backups?: Backups;
  ingest?: Ingest;
  tiles?: Tiles;
}
