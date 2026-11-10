// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DrawnDatasetId = string;
export type DrawnName = string;
export type DatasetId = string;
export type Name = string;
export type HighestMarking = string;
export type Policy = "author_promotes" | "second_person_reviews";
export type Targets = MergeTarget[];

/**
 * *Merge into a dataset…*'s first question. A drawing merged already is reached by no one
 * here: its case reads the target from then on, so the Studio's gate answers 404.
 */
export interface MergeTargets {
  drawn_dataset_id: DrawnDatasetId;
  drawn_name: DrawnName;
  targets: Targets;
}
/**
 * A dataset a drawn dataset may be merged into by this reader: one they are an Author of.
 */
export interface MergeTarget {
  dataset_id: DatasetId;
  name: Name;
  highest_marking: HighestMarking;
  policy: Policy;
}
