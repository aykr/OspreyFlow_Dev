// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Step = string;
export type Problems = string[];
export type Columns = string[];
export type Rows = {
  [k: string]: string;
}[];
export type ValuesMasked = boolean;
export type RowsSampled = number;
export type Step1 = string;
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
export type Counts = StagingStepCount[];
export type RowIndex = number;
export type Reason = string;
export type Sample = string;
export type Table = string;
export type RowIndex1 = number;
export type LoadId = string | null;
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
export type RowsSampled1 = number;
export type SampleIsWholeSource = boolean;
export type ValuesMasked1 = boolean;
export type Name = string;
export type SampleSize = number;
export type NullCount = number;
export type DistinctCount = number;
/**
 * `date` and `datetime` are not split here — a profiler is advisory,
 * not a normaliser, and a bare `2026-01-10` is just a datetime at
 * midnight for this purpose. The real distinction (and the real
 * rejection of an undated/ambiguous value) belongs to the `datetime`
 * Knowledge Adapter at mapping time, not to the profiler's guess.
 */
export type InferredType = "string" | "integer" | "float" | "boolean" | "datetime";
export type TypeConfidence = number;
export type SampleValues = string[];
export type Adapter = string;
export type MatchRate = number;
export type PatternMatches = PatternMatch[];
export type Columns1 = ColumnProfile[];
/**
 * `09_INGEST_STUDIO.md` §3: "The profile also flags what will hurt
 * later." `ENCODING_NOT_UTF8` is deliberately absent — detecting it
 * needs the raw bytes a connector decoded, not the already-decoded rows
 * this profiler receives; it belongs to the connector layer, not here
 * (`services/ingest/profiler.py`'s module docstring records this as a
 * stated gap, not a silent omission).
 */
export type AnomalyKind = "ragged_row" | "duplicate_row" | "mixed_datetime_formats" | "undetermined_timezone";
export type Column = string | null;
export type Count = number;
export type Sample1 = string;
export type Anomalies = ProfileAnomaly[];

/**
 * The steps up to `step`, run over the first ten rows of each source of the saved pipeline,
 * writing nothing. `problems` are the save gate's refusals for the pipeline the drawer holds, in
 * its own words, with any word of the preview's own (a source not saved, a sample withheld); the
 * sample is still run when the steps up to `step` can be, and is empty when they cannot. Rule 3:
 * a reader who may not view every sampled row, or a Lookup's list rows, is given nothing of the
 * run (`values_masked`, the rest empty). No row key, raw or hashed, is here (rule 7): rows are
 * cells, refs are tables and row numbers. `profile` is the staged table's profile.
 */
export interface StagingPreview {
  step: Step;
  problems?: Problems;
  columns?: Columns;
  rows?: Rows;
  values_masked?: ValuesMasked;
  rows_sampled?: RowsSampled;
  counts?: Counts;
  rejections?: Rejections;
  profile?: SourceProfile | null;
}
/**
 * ADR-140 Amendment 12: what one staging step did in a run, as counts: the rows it read and
 * gave, and every row it did not pass on, by why (rule 2: nothing dropped silently). Counts of
 * the loader's own rows: a route withholds them as it withholds every count (rule 3).
 */
export interface StagingStepCount {
  step: Step1;
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
  load_id?: LoadId;
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
export interface SourceProfile {
  rows_sampled: RowsSampled1;
  sample_is_whole_source: SampleIsWholeSource;
  values_masked: ValuesMasked1;
  columns: Columns1;
  anomalies?: Anomalies;
  [k: string]: unknown;
}
export interface ColumnProfile {
  name: Name;
  sample_size: SampleSize;
  null_count: NullCount;
  distinct_count: DistinctCount;
  inferred_type: InferredType;
  type_confidence: TypeConfidence;
  sample_values?: SampleValues;
  pattern_matches?: PatternMatches;
  [k: string]: unknown;
}
/**
 * One Knowledge Adapter tried against a column's non-null sample
 * values. `match_rate` is the fraction that parsed without the adapter
 * raising `NormalisationError`. Only adapters with a genuine reject
 * condition are tried — `services/ingest/profiler.py`'s module
 * docstring records which, and why `person_name`/`address` are excluded
 * (both reject only an empty string, so they would "match" almost any
 * text column and the signal would be worthless).
 */
export interface PatternMatch {
  adapter: Adapter;
  match_rate: MatchRate;
  [k: string]: unknown;
}
export interface ProfileAnomaly {
  kind: AnomalyKind;
  column?: Column;
  count: Count;
  sample: Sample1;
  [k: string]: unknown;
}
