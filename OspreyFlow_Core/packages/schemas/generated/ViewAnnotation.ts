// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type ElementId = string;
export type Kind = "node" | "link";
export type Label = string;
export type Marking = string;
export type Grading = string | null;
export type SourceNote = string | null;
export type Words = string;
export type Merged = boolean;

/**
 * What a merged drawing keeps of a drawn item on its view (Amendment 2 decision 7): what did
 * not become data, read through the reader's own handling, so an item they may not see has none
 * (rule 3).
 */
export interface ViewAnnotation {
  element_id: ElementId;
  kind: Kind;
  label: Label;
  marking: Marking;
  grading?: Grading;
  source_note?: SourceNote;
  words: Words;
  merged: Merged;
}
