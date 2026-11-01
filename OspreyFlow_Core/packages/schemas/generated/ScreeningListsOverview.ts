// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type ListName = string;
export type Source = "ofac_sdn" | "ofsi_consolidated" | "un_consolidated" | "eu_consolidated" | "opensanctions";
export type Location = string;
export type Dataset = string | null;
export type Synthetic = boolean;
export type Licence = string;
export type Version = string | null;
export type Entries = number;
export type UpdatedAt = string | null;
export type AttemptedAt = string | null;
export type Failure = string | null;
export type Every = "daily" | "weekly";
export type Hour = number;
export type Weekday = number | null;
export type ScheduleWords = string | null;
export type ScheduleOwner = string | null;
export type NextRefresh = string | null;
export type Lists = ScreeningListStatus[];
export type CanManage = false;

/**
 * The Lists screen for a reader of the alert queue: the lists alone. No refreshes — their
 * counts of customers re-screened and alerts raised are for whoever may load lists, in their own
 * unit (rule 7) — and no field that could hold them, so the route cannot send them, not merely
 * does not.
 */
export interface ScreeningListsOverview {
  lists: Lists;
  can_manage?: CanManage;
  [k: string]: unknown;
}
/**
 * One list as the Lists screen shows it: its version, entries, last update and the failure of
 * its last attempt, in words.
 */
export interface ScreeningListStatus {
  list_name: ListName;
  source: Source;
  location: Location;
  dataset?: Dataset;
  synthetic: Synthetic;
  licence: Licence;
  version?: Version;
  entries?: Entries;
  updated_at?: UpdatedAt;
  attempted_at?: AttemptedAt;
  failure?: Failure;
  schedule?: ListSchedule | null;
  schedule_words?: ScheduleWords;
  schedule_owner?: ScheduleOwner;
  next_refresh?: NextRefresh;
  [k: string]: unknown;
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
