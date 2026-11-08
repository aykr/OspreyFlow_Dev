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
export type EventIds = string[];
export type WithdrawnRowKeys = string[];
export type WithdrawnNodeIds = NodeId[];
export type WithdrawnEdgeIds = EdgeId[];
export type RowsWithdrawn = number;
export type LinksKeptAnOccurrence = number;
export type RowsLeftInPlace = number;
export type RefreshNotes = string[];
export type SourceId = string;
export type Column = string;
export type Kind = "number" | "time" | "text";
export type Value = string;
export type RowsBelowWatermark = number;
export type RowsWithoutWatermark = number;
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
export type WallMs = number;
export type RowsRead1 = number;
export type RowsStaged = number | null;
export type ParquetBytes = number | null;
export type ObjectStoreBytes = number | null;
export type GraphWrites = number;

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
  watermark?: SourceWatermark | null;
  rows_below_watermark?: RowsBelowWatermark;
  rows_without_watermark?: RowsWithoutWatermark;
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
  metering?: RunMetering | null;
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
 * links it wrote, created or merged into, each by its stored id, and the events it wrote, by
 * `event_id` (Amendment 15: a full snapshot withdraws a dropped row's own events by these, never
 * by link). For the ledger alone.
 */
export interface RowElements {
  node_ids?: NodeIds;
  edge_ids?: EdgeIds;
  event_ids?: EventIds;
  edge_types?: EdgeTypes;
  [k: string]: unknown;
}
export interface EdgeTypes {
  [k: string]: string;
}
/**
 * The highest value of an incremental source's watermark column a run read (ADR-110 Amendment
 * 6 point 1), kept with the load's record: the next refresh of the source, by the same pipeline
 * into the same case, reads only rows past it. `value` is the value as the file held it;
 * `kind` says how it compares (as a number, as an instant, or as text). For the ledger alone: a
 * value of the loader's own source, never in a route's answer.
 */
export interface SourceWatermark {
  source_id: SourceId;
  column: Column;
  kind: Kind;
  value: Value;
  [k: string]: unknown;
}
/**
 * What a run cost (ADR-110 Amendment 6 point 9, ADR-141 decision 2;
 * `services/ingest/metering.py` has how each is counted). `None` is *not measured*, never 0:
 * rows staged and bytes written to Parquet wait for phase 7's staging. Counts of the run's own
 * rows and writes: a route withholds them as it withholds every count (rule 3).
 */
export interface RunMetering {
  wall_ms: WallMs;
  rows_read: RowsRead1;
  rows_staged?: RowsStaged;
  parquet_bytes?: ParquetBytes;
  object_store_bytes?: ObjectStoreBytes;
  graph_writes: GraphWrites;
  [k: string]: unknown;
}
