// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type MatchOn = string;
export type OnMatch = "reference" | "create";

/**
 * A type's rule for when two records are the same (ADR-140 Amendment 22 item 3; the owner's
 * ruling of 21 November 2026: it lives on the type record, not on each pipeline's element).
 *
 * `match_on` is the field a record is found by and `on_match` what the engine does when it finds
 * one: the same two values the recipe engine takes today (`match_on` and `on_match`). A rule is
 * only as good as the matching code can make it: `match_on` must name one of the type's
 * identifiers or one of its indexed properties, because the store answers a lookup for those and
 * no others (`services/ingest/recipe_rules.py`, `reference_match_problems`). The store refuses a
 * rule that does not (`target_models._refuse_a_rule_a_reference_cannot_use`).
 */
export interface MatchingRule {
  match_on: MatchOn;
  on_match?: OnMatch;
}
