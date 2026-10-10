// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type Geocoder = string;
export type LocationsConsidered = number;
export type MatchedLocal = number;
export type MatchedOnline = number;
export type Unmatched = number;
export type Refusals = string[];

/**
 * One enrich node's run (ruling Q5: local gazetteers first, online only via the deployment's
 * configured allow-list, disclosed per run). A `SAME_AS` match is `inferred`, never a merge.
 */
export interface EnrichStageReport {
  node_id: NodeId;
  geocoder: Geocoder;
  locations_considered?: LocationsConsidered;
  matched_local?: MatchedLocal;
  matched_online?: MatchedOnline;
  unmatched?: Unmatched;
  refusals?: Refusals;
  [k: string]: unknown;
}
