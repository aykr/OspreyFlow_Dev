// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Person = string;
export type Kind = "view" | "board" | "link_type_proposal" | "drawn_watch";
export type Id = string;
export type InvestigationId = string;
export type Label = string;
export type Items = OwnershipItem[];
export type Withheld = boolean;
export type NotYetListed = string[];

/**
 * `GET /v1/admin/people/{user_id}/ownership`: what the person owns in the administrator's own
 * unit, within their clearance; `counts` by kind, of these items only; `not_yet_listed` names the
 * kinds whose store is not built yet, so the list is never taken for whole.
 */
export interface PersonOwnership {
  person: Person;
  items?: Items;
  counts?: Counts;
  withheld?: Withheld;
  not_yet_listed?: NotYetListed;
  [k: string]: unknown;
}
/**
 * One thing the person answers for, needing a *Transfer to…* before they are disabled.
 */
export interface OwnershipItem {
  kind: Kind;
  id: Id;
  investigation_id: InvestigationId;
  label: Label;
  [k: string]: unknown;
}
export interface Counts {
  [k: string]: number;
}
