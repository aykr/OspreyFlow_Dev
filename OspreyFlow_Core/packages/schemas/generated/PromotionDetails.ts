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
export type ElementId = string;
export type Kind = "node" | "link" | "picture" | "match";
export type Type = string;
export type Label1 = string;
export type Marking = string;
export type SourceNote = string | null;
export type Grading = string | null;
export type GoesInAs = string | null;
export type Items = DetailItem[];
export type Withheld = boolean;
export type Drawn = string;
export type DrawnLabel = string;
export type Loaded = string;
export type LoadedLabel = string;
export type LoadedType = string;
export type Score = number;
export type Why1 = string;
export type Matches = MergeMatch[];

/**
 * What a reviewer reads of the promotion they review: its own items, nothing else of the
 * case. `withheld` counts nothing and names nothing: it says only that some item is not shown to
 * this reader, who therefore may not approve (rule 3: approving what one cannot read would
 * commit it unseen).
 */
export interface PromotionDetails {
  promotion: Promotion;
  items: Items;
  withheld?: Withheld;
  matches?: Matches;
}
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
export interface DetailItem {
  element_id: ElementId;
  kind: Kind;
  type: Type;
  label: Label1;
  marking: Marking;
  source_note?: SourceNote;
  grading?: Grading;
  goes_in_as?: GoesInAs;
}
/**
 * Step 2, *Match*: a drawn node and a loaded node of the target the reader may see, offered
 * as alike. Chosen, it is written as a scored, `inferred` `SAME_AS` with the merge (rule 5): a
 * person confirms it later, and nothing is collapsed in storage (rule 6).
 */
export interface MergeMatch {
  drawn: Drawn;
  drawn_label: DrawnLabel;
  loaded: Loaded;
  loaded_label: LoadedLabel;
  loaded_type: LoadedType;
  score: Score;
  why: Why1;
}
