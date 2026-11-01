// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "count";
export type LinkType = string;
export type AtLeast = number;
export type WithinDays = number;

/**
 * N or more events of a declared link type within D days.
 */
export interface CountFrequency {
  kind?: Kind;
  link_type: LinkType;
  at_least: AtLeast;
  within_days: WithinDays;
  [k: string]: unknown;
}
