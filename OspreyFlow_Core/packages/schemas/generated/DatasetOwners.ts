// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type PrincipalId = string;
export type People = PrincipalId[];
export type Team = string | null;

/**
 * Who answers for a dataset: people, a team, or both (ADR-145 Amendment 4 decision 4). Checked
 * against the System setting and for service accounts where it is given, so the refusal is in
 * words; here only that it names someone.
 */
export interface DatasetOwners {
  people?: People;
  team?: Team;
}
