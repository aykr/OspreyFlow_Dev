// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type SourceId = string;
export type SourceLabel = string;
export type SourceLocation = string | null;
export type LoadId = string;
export type RecipeId = string;
export type RecipeVersion = number;
export type RowsRead = number;
export type RowsDeduplicated = number;
export type RowsAlreadyLoaded = number;
export type NodesCreated = number;
export type NodesReferenced = number;
export type EdgesCreated = number;
export type RowIndex = number;
export type Reason = string;
export type Sample = string;
export type Rejections = RejectionRecord[];
export type KeptRowKeys = string[];
export type RowKeyFingerprint = string | null;
export type NodeId = string;
export type CreatedNodeIds = NodeId[];
export type EdgeId = string;
export type TouchedEdgeIds = EdgeId[];
export type CreatedEdgeIds = EdgeId[];
export type MergedEdgeIds = EdgeId[];
export type MergedNodeIds = NodeId[];
export type RuleNodeIds = NodeId[];
export type RuleCreatedEdgeIds = EdgeId[];
export type RuleMergedEdgeIds = EdgeId[];
export type RowsHeld = number;
export type RuleNotes = string[];

/**
 * One source branch's run: which source node fed it, where it read from, and the branch's
 * own `LoadReport`. Each branch has its own `load_id`, so a branch remains independently
 * revertible (`09_INGEST_STUDIO.md` §9.1).
 */
export interface BranchRunReport {
  source_id: SourceId;
  source_label: SourceLabel;
  source_location?: SourceLocation;
  report: LoadReport;
  [k: string]: unknown;
}
export interface LoadReport {
  load_id: LoadId;
  recipe_id: RecipeId;
  recipe_version: RecipeVersion;
  rows_read?: RowsRead;
  rows_deduplicated?: RowsDeduplicated;
  rows_already_loaded?: RowsAlreadyLoaded;
  nodes_created?: NodesCreated;
  nodes_referenced?: NodesReferenced;
  edges_created?: EdgesCreated;
  rejections?: Rejections;
  kept_row_keys?: KeptRowKeys;
  row_key_fingerprint?: RowKeyFingerprint;
  created_node_ids?: CreatedNodeIds;
  touched_edge_ids?: TouchedEdgeIds;
  created_edge_ids?: CreatedEdgeIds;
  merged_edge_ids?: MergedEdgeIds;
  merged_node_ids?: MergedNodeIds;
  rule_node_ids?: RuleNodeIds;
  rule_created_edge_ids?: RuleCreatedEdgeIds;
  rule_merged_edge_ids?: RuleMergedEdgeIds;
  rows_held?: RowsHeld;
  rule_notes?: RuleNotes;
  [k: string]: unknown;
}
/**
 * One rejected row, grouped by cause in the load report — never a
 * silent coercion (`01_DOMAIN_MODEL.md` §7).
 */
export interface RejectionRecord {
  row_index: RowIndex;
  reason: Reason;
  sample: Sample;
  [k: string]: unknown;
}
