// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type BoardId = string;
export type DatasetId = string | null;
export type DatasetName = string | null;
export type HighestMarking = string;
export type Policy = "author_promotes" | "second_person_reviews";
export type ItemId = string;
export type ElementId = string;
export type Kind = "node" | "link" | "picture" | "match";
export type Type = string;
export type Label = string;
export type Marking = string;
export type Follows = boolean;
export type Source = string | null;
export type Target = string | null;
export type Problems = string[];
export type Items = SheetItem[];
export type Name = string;
export type Passed = boolean;
export type Words = string;
export type Checks = PromotionCheck[];
export type Warnings = string[];
export type RecordedAs = string;
export type Refused = string | null;

/**
 * The *Promote…* sheet for a board (decision 8).
 */
export interface PromotionSheet {
  board_id: BoardId;
  dataset_id: DatasetId;
  dataset_name: DatasetName;
  highest_marking: HighestMarking;
  policy: Policy;
  items: Items;
  checks: Checks;
  warnings?: Warnings;
  recorded_as: RecordedAs;
  refused?: Refused;
}
/**
 * One drawn item on the sheet. `problems` says, in words, every check it fails; an item with
 * a problem cannot be ticked. A link, picture or match decision `follows` its items: it goes when
 * both its ends will be in the dataset, and is listed with the reason when it will not.
 */
export interface SheetItem {
  item_id: ItemId;
  element_id: ElementId;
  kind: Kind;
  type: Type;
  label: Label;
  marking: Marking;
  follows?: Follows;
  source?: Source;
  target?: Target;
  problems?: Problems;
}
export interface PromotionCheck {
  name: Name;
  passed: Passed;
  words: Words;
}
