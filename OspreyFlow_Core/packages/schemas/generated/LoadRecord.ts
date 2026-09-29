// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type LoadId = string;
export type RecipeId = string;
export type RecipeVersion = number;
export type Source = string;
export type StartedAt = string;
export type CompletedAt = string | null;
export type PrincipalId = string;
export type NodeId = string;
export type CreatedNodeIds = NodeId[];
export type EdgeId = string;
export type TouchedEdgeIds = EdgeId[];
export type RejectedCount = number;
export type SupersededAt = string | null;

/**
 * One execution of a recipe against a source — the persisted form of
 * a `LoadReport`. `created_node_ids` is only the nodes this load
 * created, never one it merely referenced; `touched_edge_ids` is every
 * edge it wrote to, created or merged into. This asymmetry is what makes
 * `revert_load` safe: reverting a node this load created can never
 * affect another load, but an edge is shared the moment two loads touch
 * the same pair, which is why `GraphArcadeDBAdapter.revert_elements`
 * only ever sets a flag rather than deleting — the audit trail (and any
 * other load's claim on the same edge) stays intact regardless. Every
 * element also carries `load_id` on its own `AuditStub`, so filtering
 * the graph directly by load or recipe version never needs this ledger
 * at all; the ledger is for load-level operations (revert, history) a
 * per-element stamp cannot answer by itself.
 */
export interface LoadRecord {
  load_id: LoadId;
  recipe_id: RecipeId;
  recipe_version: RecipeVersion;
  source: Source;
  started_at: StartedAt;
  completed_at?: CompletedAt;
  created_by: PrincipalId;
  created_node_ids?: CreatedNodeIds;
  touched_edge_ids?: TouchedEdgeIds;
  rejected_count?: RejectedCount;
  superseded_at?: SupersededAt;
  superseded_by?: PrincipalId | null;
  [k: string]: unknown;
}
