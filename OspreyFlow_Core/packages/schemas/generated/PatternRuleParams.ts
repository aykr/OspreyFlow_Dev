// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Typology = "pattern";
export type PatternId = string;
export type MaxMatches = number;

/**
 * ADR-109 phase D, the no-code typology builder: a sub-graph drawn in the query builder and
 * saved (a `SavedPattern` the deployer owns, read afresh at each evaluation — ADR-036's own
 * discipline for monitors), deployed as a rule. Matched against the stored graph, so it runs
 * after commit only. A match larger than `max_matches` nodes is refused in words, never alerted on
 * in part (rule 2).
 */
export interface PatternRuleParams {
  typology?: Typology;
  pattern_id: PatternId;
  max_matches?: MaxMatches;
  [k: string]: unknown;
}
