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
export type Table = string;
export type RowIndex1 = number;
export type LoadId1 = string | null;
export type Side = ("left" | "right") | null;
export type Refs = RejectionRef[];
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
export type SourceId1 = string;
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
export type DrawnWatchAlerts = number;
export type Markings = Handling[];
export type WallMs = number;
export type RowsRead1 = number;
export type RowsStaged = number | null;
export type ParquetBytes = number | null;
export type ObjectStoreBytes = number | null;
export type GraphWrites = number;
export type Step = string;
export type Kind1 = string;
export type RowsIn = number;
export type RowsOut = number;
export type Unmatched = number;
export type FilteredOut = number;
export type RepeatsFolded = number;
export type Rejected = number;
export type RightRowsIn = number;
export type RightUnmatched = number;
export type Threshold = number | null;
export type Matched = number;
export type RowsWithheld = number;
export type StagingSteps = StagingStepCount[];
export type Step1 = string;
export type Kind2 = "sql" | "fuzzy_match";
export type Label = string | null;
export type Summary = string | null;
export type Select = string | null;
export type Reads = string[];
export type Compares = string[];
export type Threshold1 = number | null;
export type SameAs = string[];
export type ExpertSteps = ExpertStepDisclosure[];

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
  drawn_watch_alerts?: DrawnWatchAlerts;
  markings?: Markings;
  metering?: RunMetering | null;
  staging_steps?: StagingSteps;
  expert_steps?: ExpertSteps;
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
  refs?: Refs;
  marking?: Handling | null;
  sample_unreadable?: SampleUnreadable;
  [k: string]: unknown;
}
/**
 * ADR-140 Amendment 12: a row a rejection came from, in a staged run. The table it is a row of
 * (a source's name, `reference_list:<name>@v<n>`, or a staged step's table), its row number, the
 * load that read it (a source row's; `None` for a list row or a staged table's row) and, for a
 * Join, the side. **No row key, raw or hashed** (rule 7;
 * `tests/schemas/test_staging_report_schemas.py`).
 */
export interface RejectionRef {
  table: Table;
  row_index: RowIndex1;
  load_id?: LoadId1;
  side?: Side;
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
  source_id: SourceId1;
  column: Column;
  kind: Kind;
  value: Value;
  [k: string]: unknown;
}
/**
 * What a run cost (ADR-110 Amendment 6 point 9, ADR-141 decision 2;
 * `services/ingest/metering.py` has how each is counted). `None` is *not measured*, never 0:
 * rows staged and bytes written to Parquet are a staged run's (ADR-140 Amendment 12), `None` for
 * any other. Counts of the run's own rows and writes: a route withholds them as it withholds
 * every count (rule 3).
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
/**
 * ADR-140 Amendment 12: what one staging step did in a run, as counts: the rows it read and
 * gave, and every row it did not pass on, by why (rule 2: nothing dropped silently). Counts of
 * the loader's own rows: a route withholds them as it withholds every count (rule 3).
 */
export interface StagingStepCount {
  step: Step;
  kind: Kind1;
  rows_in: RowsIn;
  rows_out: RowsOut;
  unmatched?: Unmatched;
  filtered_out?: FilteredOut;
  repeats_folded?: RepeatsFolded;
  rejected?: Rejected;
  right_rows_in?: RightRowsIn;
  right_unmatched?: RightUnmatched;
  threshold?: Threshold;
  matched?: Matched;
  rows_withheld?: RowsWithheld;
}
/**
 * ADR-140 decision 16 and the redesign brief §5.3–5.4: every run report, and Test, says which
 * expert steps ran and what they were, in words, whether or not its counts are withheld. It is
 * the pipeline's own configuration, never a value of a row: the SQL step's summary and its
 * SELECT; the fuzzy match's tables, comparisons and threshold, and that it writes an inferred
 * `SAME_AS`, never a merge. Its counts are in `staging_steps`, withheld with the others.
 */
export interface ExpertStepDisclosure {
  step: Step1;
  kind: Kind2;
  label?: Label;
  summary?: Summary;
  select?: Select;
  reads?: Reads;
  compares?: Compares;
  threshold?: Threshold1;
  same_as?: SameAs;
}
