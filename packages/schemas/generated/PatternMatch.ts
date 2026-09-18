// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and _pending_port_placeholders.py, via generate_ts.py
export type Adapter = string;
export type MatchRate = number;

/**
 * One Knowledge Adapter tried against a column's non-null sample
 * values. `match_rate` is the fraction that parsed without the adapter
 * raising `NormalisationError`. Only adapters with a genuine reject
 * condition are tried — `services/ingest/profiler.py`'s module
 * docstring records which, and why `person_name`/`address` are excluded
 * (both reject only an empty string, so they would "match" almost any
 * text column and the signal would be worthless).
 */
export interface PatternMatch {
  adapter: Adapter;
  match_rate: MatchRate;
  [k: string]: unknown;
}
