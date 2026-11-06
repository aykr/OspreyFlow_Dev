// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type SourceId = string;
export type SourceLabel = string;
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
export type RowsHeld = number;
export type RuleNotes = string[];
export type RowsWithdrawn = number;
export type LinksKeptAnOccurrence = number;
export type RowsLeftInPlace = number;
export type RefreshNotes = string[];
export type RowsBelowWatermark = number;
export type RowsWithoutWatermark = number;
export type WallMs = number;
export type RowsRead1 = number;
export type RowsStaged = number | null;
export type ParquetBytes = number | null;
export type ObjectStoreBytes = number | null;
export type GraphWrites = number;
export type Withheld = boolean;

/**
 * `BranchRunReport` as a route answers it: the branch's `LoadReportView`. Not the file it
 * read: that is the server's path to it, which the Glass never shows (rule 7; build order step
 * 30), and the person running chose it, so the answer does not repeat it.
 */
export interface BranchRunReportView {
  source_id: SourceId;
  source_label: SourceLabel;
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
  rows_already_loaded?: RowsAlreadyLoaded;
  nodes_created?: NodesCreated;
  nodes_referenced?: NodesReferenced;
  edges_created?: EdgesCreated;
  rejections?: Rejections;
  rows_held?: RowsHeld;
  rule_notes?: RuleNotes;
  rows_withdrawn?: RowsWithdrawn;
  links_kept_an_occurrence?: LinksKeptAnOccurrence;
  rows_left_in_place?: RowsLeftInPlace;
  refresh_notes?: RefreshNotes;
  rows_below_watermark?: RowsBelowWatermark;
  rows_without_watermark?: RowsWithoutWatermark;
  metering?: RunMetering | null;
  withheld?: Withheld;
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
