// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * @minItems 1
 * @maxItems 1000
 */
export type Ids = [string, ...string[]];
export type Reason = string | null;

/**
 * A reviewer's release or rejection of named held rows — enumerated ids, never a filter
 * (one decision over exactly what was seen, as bulk accept is in ADR-108 Amendment 3). A
 * rejection needs its reason.
 */
export interface HeldRowDecision {
  ids: Ids;
  reason?: Reason;
  [k: string]: unknown;
}
