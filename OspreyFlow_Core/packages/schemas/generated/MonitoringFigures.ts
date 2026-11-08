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
export type Label2 = string;
export type Typology1 = string;
export type Age = "under a day" | "1 to 7 days" | "7 to 30 days" | "over 30 days";
export type Count1 = number;
export type OpenBySource = AgeCount[];
export type Label3 = string;
export type Typology2 = string;
export type Unassigned = number;
export type Mine = number;
export type OlderThanWeek = number;
export type Closed = number;
export type NotOfInterest = number;
export type Team = TeamCount[];

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
  open_by_source?: OpenBySource;
  team?: Team;
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
/**
 * How many alerts of one rule group are open in one age band (ADR-146 decision 9: the
 * *Alerts* panel's open by source and age). `label` and `typology` are `LabelledWeekCount`'s;
 * `age` is one of the `open_by_age` bands. Never a rule's own name or an alert's words.
 */
export interface AgeCount {
  label: Label2;
  typology?: Typology1;
  age: Age;
  count: Count1;
  [k: string]: unknown;
}
/**
 * The team view of one rule group (ADR-145 Amendment 4 decision 9): its alerts still in the
 * queue with no one on them, those claimed by the reader, those open longer than seven days, and
 * those closed in the period, of which closed as not of interest (False positive or No further
 * action). Counted as the reader, from the same queue as every other figure.
 */
export interface TeamCount {
  label: Label3;
  typology?: Typology2;
  unassigned?: Unassigned;
  mine?: Mine;
  older_than_week?: OlderThanWeek;
  closed?: Closed;
  not_of_interest?: NotOfInterest;
  [k: string]: unknown;
}
