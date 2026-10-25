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
export type InvestigationId = string | null;
export type CreatedEdgeIds = EdgeId[];
export type MergedEdgeIds = EdgeId[];
export type MergedNodeIds = NodeId[];
export type CreatedGeometryRefs = string[];
export type UncoveredWrites = boolean;
export type ReleasedFrom = string | null;
export type EventsStamped = boolean;
export type RevertedAt = string | null;

/**
 * One execution of a recipe against a source — the persisted form of
 * a `LoadReport`. `created_node_ids` is only the nodes this load
 * created, never one it merely referenced; `touched_edge_ids` is every
 * edge it wrote to, created or merged into. The revert
 * (`services/ingest/load_revert.py`) reads the created lists only and refuses a load that
 * merged: an element a load created can be taken back without affecting another load, but
 * one it merged into is shared, and `GraphArcadeDBAdapter.revert_elements` only ever sets a
 * flag rather than deleting, so the audit trail stays intact regardless. Every
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
  investigation_id?: InvestigationId;
  created_edge_ids?: CreatedEdgeIds;
  merged_edge_ids?: MergedEdgeIds;
  merged_node_ids?: MergedNodeIds;
  created_geometry_refs?: CreatedGeometryRefs;
  uncovered_writes?: UncoveredWrites;
  released_from?: ReleasedFrom;
  events_stamped?: EventsStamped;
  superseded_by?: PrincipalId | null;
  reverted_at?: RevertedAt;
  reverted_by?: PrincipalId | null;
  [k: string]: unknown;
}
