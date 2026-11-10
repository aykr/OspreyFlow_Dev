// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RunsPerDay = number | null;
export type AlertAtShare = number;

export interface RunQuotaInput {
  runs_per_day?: RunsPerDay;
  alert_at_share?: AlertAtShare;
}
