// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type LoadId = string;
export type Trigger = "analyst_promotion" | "layer_merge" | "drawn_merge";
export type DatasetId = string;
export type DatasetName = string;
export type CaseId = string;
export type CaseName = string;
export type BoardId = string | null;
export type ProposedBy = string;
export type ProposedByName = string;
export type ProposedAt = string;
export type Status = "awaiting_review" | "committed" | "rejected" | "reverted";
export type ReviewedBy = string | null;
export type ReviewedByName = string | null;
export type ReviewedAt = string | null;
export type Reason = string | null;
export type Nodes = number;
export type Links = number;
export type ItemId = string;
export type Label = string;
export type Why = string;
export type LeftOut = LeftOut1[];
export type RevertCommand = string | null;
export type MayReview = boolean;
export type WhyNot = string | null;

/**
 * One promotion (decision 10): the load, what it adds as counts, who, the case, its status.
 * Never the items themselves: those are read through `PromotionDetails`, by the reader's own
 * principal.
 */
export interface Promotion {
  id: Id;
  load_id: LoadId;
  trigger: Trigger;
  dataset_id: DatasetId;
  dataset_name: DatasetName;
  case_id: CaseId;
  case_name: CaseName;
  board_id?: BoardId;
  proposed_by: ProposedBy;
  proposed_by_name: ProposedByName;
  proposed_at: ProposedAt;
  status: Status;
  reviewed_by?: ReviewedBy;
  reviewed_by_name?: ReviewedByName;
  reviewed_at?: ReviewedAt;
  reason?: Reason;
  nodes: Nodes;
  links: Links;
  left_out?: LeftOut;
  revert_command?: RevertCommand;
  may_review?: MayReview;
  why_not?: WhyNot;
}
export interface LeftOut1 {
  item_id: ItemId;
  label: Label;
  why: Why;
}
