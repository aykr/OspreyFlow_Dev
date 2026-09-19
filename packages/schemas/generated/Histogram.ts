// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * `02_GLASS_FRONTEND.md` §3.4: the timeline's two temporal modes.
 * `CATEGORICAL` is what lets `cross_filter` bucket a dimension that
 * isn't time at all — an item type or a cell identifier.
 */
export type HistogramBucketing = "fixed_interval" | "weekday_hour" | "categorical";
export type Start = string | null;
export type End = string | null;
export type Weekday = number | null;
export type Hour = number | null;
export type Label = string | null;
export type Count = number;
export type Buckets = HistogramBucket[];
export type Total = number;

export interface Histogram {
  bucketing: HistogramBucketing;
  buckets: Buckets;
  total: Total;
  [k: string]: unknown;
}
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
