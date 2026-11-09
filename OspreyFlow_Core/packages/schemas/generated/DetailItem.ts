// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type ElementId = string;
export type Kind = "node" | "link" | "picture" | "match";
export type Type = string;
export type Label = string;
export type Marking = string;
export type SourceNote = string | null;
export type Grading = string | null;

export interface DetailItem {
  element_id: ElementId;
  kind: Kind;
  type: Type;
  label: Label;
  marking: Marking;
  source_note?: SourceNote;
  grading?: Grading;
}
