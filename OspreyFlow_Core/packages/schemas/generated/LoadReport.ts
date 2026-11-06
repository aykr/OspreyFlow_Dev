// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
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
export type Classification = string;
export type HandlingCode = string;
export type ActionCode = string | null;
export type SanitisationCode = string | null;
export type OrgUnitId = string;
export type ReviewDate = string | null;
export type LegalBasis = string | null;
export type SampleUnreadable = boolean;
export type Rejections = RejectionRecord[];
export type KeptRowKeys = string[];
export type RowKeyFingerprint = string | null;
export type NodeId = string;
export type NodeIds = NodeId[];
export type EdgeId = string;
export type EdgeIds = EdgeId[];
export type WithdrawnRowKeys = string[];
export type WithdrawnNodeIds = NodeId[];
export type WithdrawnEdgeIds = EdgeId[];
export type RowsWithdrawn = number;
export type LinksKeptAnOccurrence = number;
export type RowsLeftInPlace = number;
export type RefreshNotes = string[];
export type CreatedNodeIds = NodeId[];
export type ReferencedNodeIds = NodeId[];
export type TouchedEdgeIds = EdgeId[];
export type CreatedEdgeIds = EdgeId[];
export type MergedEdgeIds = EdgeId[];
export type MergedNodeIds = NodeId[];
export type RuleNodeIds = NodeId[];
export type RuleCreatedEdgeIds = EdgeId[];
export type RuleMergedEdgeIds = EdgeId[];
export type RowsHeld = number;
export type RuleNotes = string[];
export type Markings = Handling[];

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
  kept_row_elements?: KeptRowElements;
  withdrawn_row_keys?: WithdrawnRowKeys;
  withdrawn_node_ids?: WithdrawnNodeIds;
  withdrawn_edge_ids?: WithdrawnEdgeIds;
  rows_withdrawn?: RowsWithdrawn;
  links_kept_an_occurrence?: LinksKeptAnOccurrence;
  rows_left_in_place?: RowsLeftInPlace;
  refresh_notes?: RefreshNotes;
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
  markings?: Markings;
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
  marking?: Handling | null;
  sample_unreadable?: SampleUnreadable;
  [k: string]: unknown;
}
export interface Handling {
  classification: Classification;
  handling_code: HandlingCode;
  action_code?: ActionCode;
  sanitisation_code?: SanitisationCode;
  originator: OrgUnitId;
  owning_unit: OrgUnitId;
  review_date?: ReviewDate;
  legal_basis?: LegalBasis;
  [k: string]: unknown;
}
export interface KeptRowElements {
  [k: string]: RowElements;
}
/**
 * What one kept row wrote (ADR-110 Amendment 8 point 2): the nodes it wrote or matched and the
 * links it wrote, created or merged into, each by its stored id. For the ledger alone.
 */
export interface RowElements {
  node_ids?: NodeIds;
  edge_ids?: EdgeIds;
  [k: string]: unknown;
}
