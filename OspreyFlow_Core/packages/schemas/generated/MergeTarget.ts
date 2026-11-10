// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DatasetId = string;
export type Name = string;
export type HighestMarking = string;
export type Policy = "author_promotes" | "second_person_reviews";

/**
 * A dataset a drawn dataset may be merged into by this reader: one they are an Author of.
 */
export interface MergeTarget {
  dataset_id: DatasetId;
  name: Name;
  highest_marking: HighestMarking;
  policy: Policy;
}
