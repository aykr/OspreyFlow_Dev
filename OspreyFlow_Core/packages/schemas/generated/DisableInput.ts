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
/**
 * @maxItems 2000
 */
export type Transfers = OwnedTransfer[];

/**
 * *Transfer and disable*: a recipient for every item of the plan; refused, in words, while any
 * item has none (409 `untransferred`), nothing changed.
 */
export interface DisableInput {
  transfers?: Transfers;
  [k: string]: unknown;
}
export interface OwnedTransfer {
  kind: Kind;
  id: Id;
  to: To;
  [k: string]: unknown;
}
