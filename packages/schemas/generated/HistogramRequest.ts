// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type InvestigationScope = string;
export type ValidFrom = string;
export type ValidTo = string | null;
export type NodeId = string;
export type NodeIds = NodeId[];
export type EdgeTypes = string[];
/**
 * `02_GLASS_FRONTEND.md` §3.4: the timeline's two temporal modes.
 * `CATEGORICAL` is what lets `cross_filter` bucket a dimension that
 * isn't time at all — an item type or a cell identifier.
 */
export type HistogramBucketing = "fixed_interval" | "weekday_hour" | "categorical";
export type IntervalSeconds = number | null;
export type Field = string | null;

export interface HistogramRequest {
  filter: EventFilter;
  bucketing?: HistogramBucketing;
  interval_seconds?: IntervalSeconds;
  field?: Field;
  [k: string]: unknown;
}
/**
 * Restricts the event population a method aggregates over. Every
 * field here is a predicate the adapter applies inside its own `WHERE`
 * clause before aggregation, never after (`03_CONDUIT_MIDDLEWARE.md`
 * §6) — `04_VAULT_BACKEND.md` §2 partitions the event tables by
 * `(investigation_scope, month)`, which is why scope is required rather
 * than optional.
 */
export interface EventFilter {
  investigation_scope: InvestigationScope;
  window?: Interval | null;
  node_ids?: NodeIds;
  edge_types?: EdgeTypes;
  [k: string]: unknown;
}
export interface Interval {
  valid_from: ValidFrom;
  valid_to?: ValidTo;
  [k: string]: unknown;
}
