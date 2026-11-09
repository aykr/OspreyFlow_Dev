// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * Part of a place's name
 */
export type Query = string;
/**
 * How many places to show at most
 */
export type Limit = number;

/**
 * The analyst's place search (`02_GLASS_FRONTEND.md` §3.5's gazetteer search, ADR-147
 * Amendment 1): words to find among the loaded gazetteer's places, in the case's datasets.
 */
export interface PlaceSearchRequest {
  query: Query;
  limit?: Limit;
  [k: string]: unknown;
}
