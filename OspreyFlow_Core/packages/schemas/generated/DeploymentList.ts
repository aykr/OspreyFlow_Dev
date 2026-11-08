// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Name = string;
export type Template =
  | "ofac_sdn"
  | "ofsi_consolidated"
  | "uk_sanctions_list"
  | "un_consolidated"
  | "eu_consolidated"
  | "opensanctions"
  | "blank";
export type Location = string;
export type Ref = string;
export type PrimaryName = string;
export type Aliases = string | null;
export type DateOfBirth = string | null;
export type Nationality = string | null;
export type Identifiers = string | null;
export type Programme = string | null;
export type Separator = "|" | ";" | ",";
export type EntityType = ("Person" | "Organisation") | null;
export type EntityTypeColumn = string | null;
export type Listing = "sanction" | "pep" | "adverse_media";
export type Dataset = string | null;
export type Synthetic = boolean;
export type Licence = string;
export type LicenceConfirmed = boolean;
export type LicenceNote = string | null;
export type Version = number;
export type Entries = number;
export type UpdatedAt = string | null;
export type AttemptedAt = string | null;
export type Failure = string | null;
export type Every = "daily" | "weekly";
export type Hour = number;
export type Weekday = number | null;
export type ScheduleWords = string | null;
export type NextRefresh = string | null;
export type CreatedBy = string;
export type CreatedAt = string;

/**
 * A deployment-wide screening list as Studio › Sources shows it.
 */
export interface DeploymentList {
  id: Id;
  name: Name;
  template: Template;
  location: Location;
  mapping?: BlankListMapping | null;
  dataset?: Dataset;
  synthetic?: Synthetic;
  licence: Licence;
  licence_confirmed?: LicenceConfirmed;
  licence_note?: LicenceNote;
  version?: Version;
  entries?: Entries;
  updated_at?: UpdatedAt;
  attempted_at?: AttemptedAt;
  failure?: Failure;
  schedule?: ListSchedule | null;
  schedule_words?: ScheduleWords;
  next_refresh?: NextRefresh;
  created_by: CreatedBy;
  created_at: CreatedAt;
  [k: string]: unknown;
}
/**
 * A client's own list, mapped field by field: each screening field is one of the file's
 * columns, or none. A person or an organisation is either one for every row, or read from a
 * column whose cells must say `Person` or `Organisation` (any other value refuses its row).
 */
export interface BlankListMapping {
  ref: Ref;
  primary_name: PrimaryName;
  aliases?: Aliases;
  date_of_birth?: DateOfBirth;
  nationality?: Nationality;
  identifiers?: Identifiers;
  programme?: Programme;
  separator?: Separator;
  entity_type?: EntityType;
  entity_type_column?: EntityTypeColumn;
  listing?: Listing;
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
