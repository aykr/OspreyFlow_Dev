// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Scope = "dataset" | "case";
/**
 * @maxItems 5000
 */
export type Pairs = [unknown, unknown][];

/**
 * `POST /v1/investigations/{id}/rarity`: per dataset by default; `pairs` are the pairs to
 * explain (each two ids of the working set).
 */
export interface RarityRequest {
  scope?: Scope;
  pairs?: Pairs;
  [k: string]: unknown;
}
