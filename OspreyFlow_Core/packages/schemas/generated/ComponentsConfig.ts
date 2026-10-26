// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * Default: arcadedb. The graph store.
 */
export type GraphStore = "arcadedb" | "janusgraph";
/**
 * Default: duckdb. Where events are counted: DuckDB inside the Conduit, or ClickHouse shared by several.
 */
export type AnalyticsEngine = "duckdb" | "clickhouse";
/**
 * Default: true. Whether a load queues entity resolution afterwards (`OSPREY_POST_INGEST_RESOLUTION`). False for a demonstration whose people must not gain automatic `SAME_AS` links; an analyst's own Resolve now still works.
 */
export type PostIngestResolution = boolean;
/**
 * Default: opensearch. Search; postgres-fulltext is the lighter variant.
 */
export type SearchBackend = "opensearch" | "postgres-fulltext";
/**
 * Default: /var/lib/osprey/data. Where the deployment keeps its data inside the containers.
 */
export type Data = string;
/**
 * Default: /var/lib/osprey/staging. Where loads stage their rows before they reach the graph.
 */
export type Staging = string;
/**
 * Default: /var/lib/osprey/backups. Where backups are written.
 */
export type Backups = string;
/**
 * Default: /var/lib/osprey/ingest. The host folder of source files the Ingest Studio lists (read-only to it; uploads go to its uploaded/ folder).
 */
export type Ingest = string;
/**
 * Default: /var/lib/osprey/tiles. The host folder a built basemap lives in.
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
  post_ingest_resolution?: PostIngestResolution;
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
