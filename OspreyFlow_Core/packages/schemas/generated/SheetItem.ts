// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
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
