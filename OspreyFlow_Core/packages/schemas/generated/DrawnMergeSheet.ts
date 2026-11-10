// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DrawnDatasetId = string;
export type DrawnName = string;
export type TargetDatasetId = string;
export type TargetName = string;
export type HighestMarking = string;
export type Policy = "author_promotes" | "second_person_reviews";
export type Kind = "node" | "link";
export type DrawnType = string;
export type TargetType = string | null;
export type Items = number;
export type WhyNot = string | null;
export type Choices = string[];
export type DrawnProperties = string[];
export type Mapping = TypeMapping[];
export type Kind1 = "node" | "link";
export type Name = string;
export type Properties = string[];
export type Required = string[];
export type TargetTypes = TargetType1[];
export type Drawn = string;
export type DrawnLabel = string;
export type Loaded = string;
export type LoadedLabel = string;
export type LoadedType = string;
export type Score = number;
export type Why = string;
export type Matches = MergeMatch[];
export type MoreMatches = boolean;
export type ItemId = string;
export type ElementId = string;
export type Kind2 = "node" | "link" | "picture" | "match";
export type Type = string;
export type Label = string;
export type Marking = string;
export type Follows = boolean;
export type Source = string | null;
export type Target = string | null;
export type Problems = string[];
export type Items1 = SheetItem[];
export type Name1 = string;
export type Passed = boolean;
export type Words = string;
export type Checks = PromotionCheck[];
export type RecordedAs = string;

/**
 * *Merge into a dataset…* for one target: the mapping, the matches, the drawn items with every
 * check each fails, and how it will be recorded. Only what the reader may see (rule 3).
 */
export interface DrawnMergeSheet {
  drawn_dataset_id: DrawnDatasetId;
  drawn_name: DrawnName;
  target_dataset_id: TargetDatasetId;
  target_name: TargetName;
  highest_marking: HighestMarking;
  policy: Policy;
  mapping: Mapping;
  target_types?: TargetTypes;
  matches: Matches;
  more_matches?: MoreMatches;
  items: Items1;
  checks: Checks;
  recorded_as: RecordedAs;
}
/**
 * Step 1, *Map the models* (ADR-143 Amendment 7, the owner's ruling): one drawn type and the
 * target's type its items go in as, proposed as the same name when the target's model holds it,
 * else `None` with why not. `choices` are every type of the target's live model of this kind,
 * any of which it may be mapped to, as a Studio load's Map step maps; `drawn_properties` the
 * properties its items carry. Counts only the items the reader may see.
 */
export interface TypeMapping {
  kind: Kind;
  drawn_type: DrawnType;
  target_type: TargetType;
  items: Items;
  why_not?: WhyNot;
  choices?: Choices;
  drawn_properties?: DrawnProperties;
}
/**
 * A type of the target's live model, with what a drawn property may be mapped onto: its
 * properties and identifiers, and those it requires.
 */
export interface TargetType1 {
  kind: Kind1;
  name: Name;
  properties: Properties;
  required?: Required;
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
  why: Why;
}
/**
 * One drawn item on the sheet. `problems` says, in words, every check it fails; an item with
 * a problem cannot be ticked. A link, picture or match decision `follows` its items: it goes when
 * both its ends will be in the dataset, and is listed with the reason when it will not.
 */
export interface SheetItem {
  item_id: ItemId;
  element_id: ElementId;
  kind: Kind2;
  type: Type;
  label: Label;
  marking: Marking;
  follows?: Follows;
  source?: Source;
  target?: Target;
  problems?: Problems;
}
export interface PromotionCheck {
  name: Name1;
  passed: Passed;
  words: Words;
}
