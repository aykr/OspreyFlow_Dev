// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "view" | "board" | "link_type_proposal" | "drawn_watch";
export type Id = string;
export type InvestigationId = string;
export type Label = string;

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
