// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RowsSampled = number;
export type SampleIsWholeSource = boolean;
export type ValuesMasked = boolean;
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
export type Columns = ColumnProfile[];
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
export type Sample = string;
export type Anomalies = ProfileAnomaly[];

export interface SourceProfile {
  rows_sampled: RowsSampled;
  sample_is_whole_source: SampleIsWholeSource;
  values_masked: ValuesMasked;
  columns: Columns;
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
  sample: Sample;
  [k: string]: unknown;
}
