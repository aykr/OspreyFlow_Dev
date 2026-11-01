// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type WeekStart = string;
export type Label = string;
export type Typology = string;
export type Count = number;
export type RaisedByRule = LabelledWeekCount[];
export type ClosedByOutcome = LabelledWeekCount[];
export type Label1 = string;
export type Value = number;
export type TimeToClose = ReportCount[];
export type HotlistMatches = LabelledWeekCount[];

/**
 * The monitoring dashboard's figures (ADR-134 decision 2): every kind of alert the one queue
 * holds for the reader — typology, hotlist and monitor — counted as them, per case. A hotlist
 * kept "only me" is in its owner's figures alone (the queue's own scope).
 */
export interface MonitoringFigures {
  raised_by_rule?: RaisedByRule;
  closed_by_outcome?: ClosedByOutcome;
  time_to_close?: TimeToClose;
  hotlist_matches?: HotlistMatches;
  [k: string]: unknown;
}
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
/**
 * One labelled figure of a report (ADR-111): a fixed label and a count, never free text.
 */
export interface ReportCount {
  label: Label1;
  value: Value;
  [k: string]: unknown;
}
