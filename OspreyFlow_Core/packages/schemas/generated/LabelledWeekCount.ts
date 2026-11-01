// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type WeekStart = string;
export type Label = string;
export type Typology = string;
export type Count = number;

/**
 * A count in one week under a fixed label (ADR-134 decision 2): the rule group an alert was
 * raised by (`typology`, with its typology, `hotlists` or `monitors`), the outcome it was closed
 * with, or `hotlists` for a hotlist's matches. Never a rule's own name or an alert's words.
 */
export interface LabelledWeekCount {
  week_start: WeekStart;
  label: Label;
  typology?: Typology;
  count: Count;
  [k: string]: unknown;
}
