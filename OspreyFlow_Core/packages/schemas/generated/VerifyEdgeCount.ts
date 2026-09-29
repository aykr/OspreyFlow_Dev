// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Created = number;

/**
 * An edge has no `match_on`/`on_match` of its own (`RecipeEdge` never
 * declares one) — every edge the dry run resolves is "created" in the
 * sense of "this recipe would write it"; same-pair edges within the
 * sample still merge into one, occurrence-counted, the way a real load's
 * `GraphArcadeDBAdapter.upsert_edges` merges them.
 */
export interface VerifyEdgeCount {
  created?: Created;
  [k: string]: unknown;
}
