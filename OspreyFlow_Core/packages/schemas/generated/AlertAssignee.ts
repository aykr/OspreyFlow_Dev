// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Name = string | null;

/**
 * One member an alert may be given to: an Editor or Author of the case, by name.
 */
export interface AlertAssignee {
  id: Id;
  name?: Name;
  [k: string]: unknown;
}
