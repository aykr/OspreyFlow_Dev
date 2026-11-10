// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "on_screening_list";
export type MinScore = number;
export type ListId = string | null;

/**
 * The subject's name screens against the deployment's screening lists (ADR-109 phase F's
 * `screen`, reused): a person or an organisation only.
 */
export interface OnScreeningListRelationship {
  kind?: Kind;
  min_score?: MinScore;
  list_id?: ListId;
  [k: string]: unknown;
}
