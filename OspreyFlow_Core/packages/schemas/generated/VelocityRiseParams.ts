// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Typology = "velocity_rise";
export type RecentDays = number;
export type BaselineDays = number;
export type Factor = number;
export type MinRecent = number;
export type Measure = "count" | "amount";

/**
 * An account's movements over the last `recent_days` days at `factor` times or more its own
 * daily rate over the `baseline_days` before — counted, or by amount — with at least
 * `min_recent` movements in the recent days. An account with no movements in the baseline has no
 * rate to rise from and is not judged.
 */
export interface VelocityRiseParams {
  typology?: Typology;
  recent_days?: RecentDays;
  baseline_days?: BaselineDays;
  factor?: Factor;
  min_recent?: MinRecent;
  measure?: Measure;
  [k: string]: unknown;
}
