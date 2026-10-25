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
export type NodesCreated = number;
export type NodesReferenced = number;
export type EdgesCreated = number;
export type RowIndex = number;
export type Reason = string;
export type Sample = string;
export type Rejections = RejectionRecord[];
export type RowsHeld = number;
export type RuleNotes = string[];

/**
 * `BranchRunReport` as a route answers it: the branch's `LoadReportView`.
 */
export interface BranchRunReportView {
  source_id: SourceId;
  source_label: SourceLabel;
  source_location?: SourceLocation;
  report: LoadReportView;
  [k: string]: unknown;
}
/**
 * What a route answers for a load: the counts and the words, never the id lists. `LoadReport`
 * keeps `created_node_ids`, `created_edge_ids`, `merged_edge_ids` and the rest for the load's own
 * record; handed to the loader, `merged_edge_ids` would say a link pre-existed whether or not
 * they may read it (rules 3 and 7, ADR-127 decision 6).
 */
export interface LoadReportView {
  load_id: LoadId;
  recipe_id: RecipeId;
  recipe_version: RecipeVersion;
  rows_read?: RowsRead;
  rows_deduplicated?: RowsDeduplicated;
  nodes_created?: NodesCreated;
  nodes_referenced?: NodesReferenced;
  edges_created?: EdgesCreated;
  rejections?: Rejections;
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
