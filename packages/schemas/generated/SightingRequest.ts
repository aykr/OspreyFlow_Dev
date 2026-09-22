// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type InvestigationScope = string;
export type ValidFrom = string;
export type ValidTo = string | null;
export type NodeId = string;
export type NodeIds = NodeId[];
export type EdgeTypes = string[];

/**
 * B18's own backend dependency, found genuinely missing while building it, not assumed to
 * exist — `AnalyticsPort` had `histogram`/`geo_bins`/`cross_filter`, all aggregate-shaped, and no
 * method returning ordered, timestamped, per-entity points at all. `filter.node_ids` names the
 * one entity; `filter.window` is the brush window `02_GLASS_FRONTEND.md` §3.5's own "Snail trail"
 * row scopes the track to. Raw points, not server-side binned like `geo_bins` — deliberately: a
 * snail trail is one entity's own sighting history inside an already-brushed window, not a
 * corpus-wide density query, so the "never ship a million points" concern `geo_bins`'s own
 * docstring names does not apply at this scale.
 */
export interface SightingRequest {
  filter: EventFilter;
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
