// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Step = string;
export type Kind = "sql" | "fuzzy_match";
export type Label = string | null;
export type Summary = string | null;
export type Select = string | null;
export type Reads = string[];
export type Compares = string[];
export type Threshold = number | null;
export type SameAs = string[];

/**
 * ADR-140 decision 16 and the redesign brief §5.3–5.4: every run report, and Test, says which
 * expert steps ran and what they were, in words, whether or not its counts are withheld. It is
 * the pipeline's own configuration, never a value of a row: the SQL step's summary and its
 * SELECT; the fuzzy match's tables, comparisons and threshold, and that it writes an inferred
 * `SAME_AS`, never a merge. Its counts are in `staging_steps`, withheld with the others.
 */
export interface ExpertStepDisclosure {
  step: Step;
  kind: Kind;
  label?: Label;
  summary?: Summary;
  select?: Select;
  reads?: Reads;
  compares?: Compares;
  threshold?: Threshold;
  same_as?: SameAs;
}
