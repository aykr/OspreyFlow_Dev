// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Scope = "dataset" | "unit";
export type Key = string;
export type RunsPerDay = number | null;
export type AlertAtShare = number;

/**
 * A dataset's or a unit's quota (decision 6). `None` is no limit. A run past a quota is refused
 * in words at the run path, whatever triggered it; `alert_at_share` of a quota raises the budget
 * alert to the administrators first.
 */
export interface RunQuota {
  scope: Scope;
  key: Key;
  runs_per_day?: RunsPerDay;
  alert_at_share?: AlertAtShare;
}
