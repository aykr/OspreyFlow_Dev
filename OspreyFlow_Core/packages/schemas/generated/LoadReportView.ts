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
export type RowsHeld = number;
export type RuleNotes = string[];
export type DrawnWatchAlerts = number;
export type RowsWithdrawn = number;
export type LinksKeptAnOccurrence = number;
export type RowsLeftInPlace = number;
export type Step = string;
export type Kind = string;
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
export type Kind1 = "sql" | "fuzzy_match";
export type Label = string | null;
export type Summary = string | null;
export type Select = string | null;
export type Reads = string[];
export type Compares = string[];
export type Threshold1 = number | null;
export type SameAs = string[];
export type ExpertSteps = ExpertStepDisclosure[];
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
  drawn_watch_alerts?: DrawnWatchAlerts;
  rows_withdrawn?: RowsWithdrawn;
  links_kept_an_occurrence?: LinksKeptAnOccurrence;
  rows_left_in_place?: RowsLeftInPlace;
  staging_steps?: StagingSteps;
  expert_steps?: ExpertSteps;
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
/**
 * ADR-140 Amendment 12: what one staging step did in a run, as counts: the rows it read and
 * gave, and every row it did not pass on, by why (rule 2: nothing dropped silently). Counts of
 * the loader's own rows: a route withholds them as it withholds every count (rule 3).
 */
export interface StagingStepCount {
  step: Step;
  kind: Kind;
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
  kind: Kind1;
  label?: Label;
  summary?: Summary;
  select?: Select;
  reads?: Reads;
  compares?: Compares;
  threshold?: Threshold1;
  same_as?: SameAs;
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
