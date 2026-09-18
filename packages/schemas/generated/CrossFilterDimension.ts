// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and _pending_port_placeholders.py, via generate_ts.py
export type Name = string;
/**
 * `02_GLASS_FRONTEND.md` §3.4: the timeline's two temporal modes.
 * `CATEGORICAL` is what lets `cross_filter` bucket a dimension that
 * isn't time at all — an item type or a cell identifier.
 */
export type HistogramBucketing = "fixed_interval" | "weekday_hour" | "categorical";
export type IntervalSeconds = number | null;
export type Field = string | null;

/**
 * One entry in a `CrossFilterRequest` — a named histogram computed
 * against the same filter, so the timeline, the map and the histogram
 * panel restrict in lockstep (`08_ACCEPTANCE_SCENARIOS.md` A3).
 */
export interface CrossFilterDimension {
  name: Name;
  bucketing: HistogramBucketing;
  interval_seconds?: IntervalSeconds;
  field?: Field;
  [k: string]: unknown;
}
