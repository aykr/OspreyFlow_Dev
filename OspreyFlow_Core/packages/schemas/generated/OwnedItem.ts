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
  | "list_schedule"
  | "view"
  | "board"
  | "link_type_proposal"
  | "drawn_watch";
export type Id = string;
export type Label = string;
export type InvestigationId = string | null;
export type NeedsClearance = string | null;

/**
 * One thing a person answers for, as *Disable…* lists it (ADR-145 decision 6): each needs a
 * *Transfer to…* before *Transfer and disable* is accepted.
 */
export interface OwnedItem {
  kind: Kind;
  id: Id;
  label: Label;
  investigation_id?: InvestigationId;
  needs_clearance?: NeedsClearance;
  [k: string]: unknown;
}
