// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Every = "daily" | "weekly" | "never";
export type Hour = number;
export type Weekday = number | null;

/**
 * A watch's schedule (ADR-146 decision 4, G16): every day, every week on one day, or never
 * (as data loads only), at a whole hour.
 */
export interface MonitorScheduleInput {
  every?: Every;
  hour?: Hour;
  weekday?: Weekday;
  [k: string]: unknown;
}
