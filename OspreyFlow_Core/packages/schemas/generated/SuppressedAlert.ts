// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type AlertId = string;
export type Until = string;
export type Reason = string;
export type By = string;
export type ByName = string | null;

export interface SuppressedAlert {
  alert_id: AlertId;
  until: Until;
  reason: Reason;
  by: By;
  by_name?: ByName;
  [k: string]: unknown;
}
