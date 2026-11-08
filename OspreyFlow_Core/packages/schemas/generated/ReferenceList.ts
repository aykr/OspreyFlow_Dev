// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type DatasetId = string;
export type Name = string;
export type Kind = "reference" | "screening";
export type KeyColumn = string;
export type Version = number;
export type Every = "daily" | "weekly";
export type Hour = number;
export type Weekday = number | null;

/**
 * A list the dataset's model refers to (ADR-140 decision 4). Its rows are loaded data, never
 * part of a release's bundle when the list is licensed (ADR-140 Amendment 9 decision 4).
 */
export interface ReferenceList {
  id: Id;
  dataset_id: DatasetId;
  name: Name;
  kind: Kind;
  key_column: KeyColumn;
  version: Version;
  schedule?: ListSchedule | null;
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
