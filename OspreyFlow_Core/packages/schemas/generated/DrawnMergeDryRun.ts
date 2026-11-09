// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type TargetDatasetId = string;
export type Nodes = number;
export type Links = number;
export type Matches = number;
export type Retyped = number;
export type NotCarried = string[];
export type ItemId = string;
export type Label = string;
export type Why = string;
export type LeftOut = LeftOut1[];
export type RecordedAs = string;

/**
 * Step 3: what the merge would add and match, counting only what the reader may see; nothing
 * written.
 */
export interface DrawnMergeDryRun {
  target_dataset_id: TargetDatasetId;
  nodes: Nodes;
  links: Links;
  matches: Matches;
  retyped?: Retyped;
  not_carried?: NotCarried;
  left_out?: LeftOut;
  recorded_as: RecordedAs;
}
export interface LeftOut1 {
  item_id: ItemId;
  label: Label;
  why: Why;
}
