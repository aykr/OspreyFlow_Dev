// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Scope = "dataset" | "unit";
export type Key = string;
export type RunsPerDay = number | null;
export type AlertAtShare = number;
export type RunsToday = number | null;
export type Used = boolean;

/**
 * The quota as the Runs tab's bar shows it. `runs_today` counts every unit's runs into the
 * dataset, so only a reader holding `administer_system` is given it (rules 3 and 7, the strict
 * reading; ADR-141 Amendment 1); anyone else is told only whether the quota is `used`.
 */
export interface RunQuotaUse {
  quota?: RunQuota | null;
  runs_today?: RunsToday;
  used?: Used;
}
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
