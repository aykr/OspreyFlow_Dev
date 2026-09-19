// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type InvestigationScope = string;
export type ValidFrom = string;
export type ValidTo = string | null;
export type NodeId = string;
export type NodeIds = NodeId[];
export type EdgeTypes = string[];
export type Precision = number;

/**
 * `precision` sets the bin size — higher is finer, each step halving
 * the latitude span a bin covers (not a geohash: no base-32 cell-id
 * encoding, and bins are equal-*area* via a sinusoidal projection, not
 * equal-degree — see `adapters/analytics_duckdb`). Binning happens here,
 * server-side, so a heat map never ships a million raw points to the
 * Glass (`00_ARCHITECTURE.md` §1.1).
 */
export interface GeoBinRequest {
  filter: EventFilter;
  precision: Precision;
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
