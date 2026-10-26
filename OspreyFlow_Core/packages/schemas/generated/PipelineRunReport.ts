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
export type ReferencedNodeIds = NodeId[];
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
export type Branches = BranchRunReport[];
export type NodeId1 = string;
export type Library = string;
export type Output = string;
export type DocumentsRead = number;
export type CandidatesQueued = number;
export type NodesWrittenInferred = number;
export type HandlingOverridden = number;
export type OverrideReason = string | null;
export type Refusals = string[];
export type Extracts = ExtractStageReport[];
export type NodeId2 = string;
export type Geocoder = string;
export type LocationsConsidered = number;
export type MatchedLocal = number;
export type MatchedOnline = number;
export type Unmatched = number;
export type Refusals1 = string[];
export type Enriches = EnrichStageReport[];
export type RowsRead1 = number;
export type RowsAlreadyLoaded1 = number;
export type NodesCreated1 = number;
export type NodesReferenced1 = number;
export type EdgesCreated1 = number;
export type Rejections1 = RejectionRecord[];
export type CreatedNodeIds1 = NodeId[];
export type ReferencedNodeIds1 = NodeId[];
export type TouchedEdgeIds1 = EdgeId[];
export type RowsHeld1 = number;
export type RuleNotes1 = string[];

/**
 * A whole pipeline's run (ADR-108 phase C): every branch's `LoadReport`, every extract and
 * enrich stage's own account, and the aggregates the post-run machinery (resolution trigger,
 * change stream, audit) reads uniformly with a plain `LoadReport`.
 */
export interface PipelineRunReport {
  load_id: LoadId;
  recipe_id: RecipeId;
  recipe_version: RecipeVersion;
  branches?: Branches;
  extracts?: Extracts;
  enriches?: Enriches;
  rows_read?: RowsRead1;
  rows_already_loaded?: RowsAlreadyLoaded1;
  nodes_created?: NodesCreated1;
  nodes_referenced?: NodesReferenced1;
  edges_created?: EdgesCreated1;
  rejections?: Rejections1;
  created_node_ids?: CreatedNodeIds1;
  referenced_node_ids?: ReferencedNodeIds1;
  touched_edge_ids?: TouchedEdgeIds1;
  rows_held?: RowsHeld1;
  rule_notes?: RuleNotes1;
  [k: string]: unknown;
}
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
  load_id: LoadId1;
  recipe_id: RecipeId1;
  recipe_version: RecipeVersion1;
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
  referenced_node_ids?: ReferencedNodeIds;
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
/**
 * One extract node's run, loud about everything it did and refused (rules 2 and 5): how many
 * documents it read, where its findings went, how many carried an overridden handling, and every
 * refusal in words — a stage that could not run says so here, never silently does nothing.
 */
export interface ExtractStageReport {
  node_id: NodeId1;
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
  node_id: NodeId2;
  geocoder: Geocoder;
  locations_considered?: LocationsConsidered;
  matched_local?: MatchedLocal;
  matched_online?: MatchedOnline;
  unmatched?: Unmatched;
  refusals?: Refusals1;
  [k: string]: unknown;
}
