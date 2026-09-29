// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
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
