// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and _pending_port_placeholders.py, via generate_ts.py
export type Start = string | null;
export type End = string | null;
export type Weekday = number | null;
export type Hour = number | null;
export type Label = string | null;
export type Count = number;

/**
 * Exactly one label shape is populated, matching the request's
 * `bucketing`: `start`/`end` for `fixed_interval`, `weekday`/`hour` for
 * `weekday_hour`, `label` for `categorical`.
 */
export interface HistogramBucket {
  start?: Start;
  end?: End;
  weekday?: Weekday;
  hour?: Hour;
  label?: Label;
  count: Count;
  [k: string]: unknown;
}
