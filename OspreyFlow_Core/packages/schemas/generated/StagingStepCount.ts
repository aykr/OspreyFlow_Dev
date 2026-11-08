// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
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
}
