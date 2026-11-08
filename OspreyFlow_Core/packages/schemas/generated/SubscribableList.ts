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
export type Version = number;
export type Entries = number;
export type UpdatedAt = string | null;
export type Failing = boolean;
export type ScheduleWords = string | null;

/**
 * A deployment-wide list as a dataset's source author sees it to subscribe to: what it is and
 * how current, never where its file is, who added it, the real dataset it is, its mapping or its
 * failure's words, which are for whoever may load screening lists (the lane review of L1.6).
 */
export interface SubscribableList {
  id: Id;
  name: Name;
  template: Template;
  version?: Version;
  entries?: Entries;
  updated_at?: UpdatedAt;
  failing?: Failing;
  schedule_words?: ScheduleWords;
  [k: string]: unknown;
}
