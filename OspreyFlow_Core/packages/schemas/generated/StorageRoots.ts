// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
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
