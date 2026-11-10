// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Person = string;
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
export type Items = OwnedItem[];
export type NotYetListed = string[];

/**
 * `GET /v1/admin/people/{user_id}/disable-plan`: everything the person owns today, and the
 * kinds not yet listed because their owner route is not built (L2.5b, L3.8's ownership route).
 */
export interface DisablePlan {
  person: Person;
  items: Items;
  not_yet_listed?: NotYetListed;
  [k: string]: unknown;
}
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
