// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Name = string;
export type Kind = "reference" | "screening";
export type KeyColumn = string;
export type Version = number;
export type Every = "daily" | "weekly";
export type Hour = number;
export type Weekday = number | null;
export type Rows = string | null;

/**
 * One reference list's definition, and its rows' file when they travel.
 */
export interface ReleasedReferenceList {
  id: Id;
  name: Name;
  kind: Kind;
  key_column: KeyColumn;
  version: Version;
  schedule?: ListSchedule | null;
  rows?: Rows;
}
/**
 * A screening list's refresh schedule (ADR-133 Amendment 3, item 4): every day, or every week
 * on one day, at a whole hour, read in Europe/London. That a weekly one names its day, and a daily
 * one none, is checked by `services/api/list_schedule.check_list_schedule`, so the route says it
 * in words.
 */
export interface ListSchedule {
  every?: Every;
  hour?: Hour;
  weekday?: Weekday;
}
