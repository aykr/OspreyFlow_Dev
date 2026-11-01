// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type MostInSpan = number;
export type LargestTotal = number | null;
export type FirstAt = string | null;

/**
 * Every subject asked about that has at least one visible event up to the window's end; a
 * subject with none is absent.
 */
export interface FrequencyResult {
  nodes?: Nodes;
  [k: string]: unknown;
}
export interface Nodes {
  [k: string]: NodeFrequency;
}
/**
 * One subject's answer. `most_in_span` and `largest_total` are over the request's window;
 * `first_at` is the subject's earliest visible event at all, up to the window's end (its start is
 * not applied), so "the first time ever" is `first_at` falling inside the window.
 */
export interface NodeFrequency {
  most_in_span: MostInSpan;
  largest_total?: LargestTotal;
  first_at?: FirstAt;
  [k: string]: unknown;
}
