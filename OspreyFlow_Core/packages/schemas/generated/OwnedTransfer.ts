// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind =
  | "case_author"
  | "home_case_author"
  | "team_lead"
  | "hotlist"
  | "monitor"
  | "saved_pattern"
  | "typology_rule"
  | "pipeline_schedule"
  | "list_schedule";
export type Id = string;
export type To = string;

export interface OwnedTransfer {
  kind: Kind;
  id: Id;
  to: To;
  [k: string]: unknown;
}
