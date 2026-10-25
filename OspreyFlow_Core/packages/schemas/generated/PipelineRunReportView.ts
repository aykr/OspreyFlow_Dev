// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type LoadId = string;
export type RecipeId = string;
export type RecipeVersion = number;
export type SourceId = string;
export type SourceLabel = string;
export type SourceLocation = string | null;
export type LoadId1 = string;
export type RecipeId1 = string;
export type RecipeVersion1 = number;
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
export type Branches = BranchRunReportView[];
export type NodeId = string;
export type Library = string;
export type Output = string;
export type DocumentsRead = number;
export type CandidatesQueued = number;
export type NodesWrittenInferred = number;
export type HandlingOverridden = number;
export type OverrideReason = string | null;
export type Refusals = string[];
export type Extracts = ExtractStageReport[];
export type NodeId1 = string;
export type Geocoder = string;
export type LocationsConsidered = number;
export type MatchedLocal = number;
export type MatchedOnline = number;
export type Unmatched = number;
export type Refusals1 = string[];
export type Enriches = EnrichStageReport[];
export type RowsRead1 = number;
export type NodesCreated1 = number;
export type NodesReferenced1 = number;
export type EdgesCreated1 = number;
export type Rejections1 = RejectionRecord[];
export type RowsHeld1 = number;
export type RuleNotes1 = string[];

/**
 * `PipelineRunReport` as a route answers it: counts and words, no id lists, each branch a
 * `LoadReportView` (see `LoadReportView`).
 */
export interface PipelineRunReportView {
  load_id: LoadId;
  recipe_id: RecipeId;
  recipe_version: RecipeVersion;
  branches?: Branches;
  extracts?: Extracts;
  enriches?: Enriches;
  rows_read?: RowsRead1;
  nodes_created?: NodesCreated1;
  nodes_referenced?: NodesReferenced1;
  edges_created?: EdgesCreated1;
  rejections?: Rejections1;
  rows_held?: RowsHeld1;
  rule_notes?: RuleNotes1;
  [k: string]: unknown;
}
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
  load_id: LoadId1;
  recipe_id: RecipeId1;
  recipe_version: RecipeVersion1;
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
/**
 * One extract node's run, loud about everything it did and refused (rules 2 and 5): how many
 * documents it read, where its findings went, how many carried an overridden handling, and every
 * refusal in words — a stage that could not run says so here, never silently does nothing.
 */
export interface ExtractStageReport {
  node_id: NodeId;
  library: Library;
  output: Output;
  documents_read?: DocumentsRead;
  candidates_queued?: CandidatesQueued;
  nodes_written_inferred?: NodesWrittenInferred;
  handling_overridden?: HandlingOverridden;
  override_reason?: OverrideReason;
  refusals?: Refusals;
  [k: string]: unknown;
}
/**
 * One enrich node's run (ruling Q5: local gazetteers first, online only via the deployment's
 * configured allow-list, disclosed per run). A `SAME_AS` match is `inferred`, never a merge.
 */
export interface EnrichStageReport {
  node_id: NodeId1;
  geocoder: Geocoder;
  locations_considered?: LocationsConsidered;
  matched_local?: MatchedLocal;
  matched_online?: MatchedOnline;
  unmatched?: Unmatched;
  refusals?: Refusals1;
  [k: string]: unknown;
}
