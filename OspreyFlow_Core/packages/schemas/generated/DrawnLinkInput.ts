// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Label = string;
export type Marking = string;
export type GradingSchemeName = "5x5x5" | "3x5x2";
export type GradeSource = string;
export type GradeIntelligence = string;
export type GradeHandling = string;
export type SourceNote = string | null;
export type DocumentId = string;
export type Type = string;
export type NodeId = string;

/**
 * A link drawn by the handle, by Alt-drag, by *Draw a link from here* or by the link form:
 * between two items on the board, drawn or loaded. The label is what the link says.
 */
export interface DrawnLinkInput {
  label: Label;
  marking: Marking;
  grading: Grading;
  source_note?: SourceNote;
  source_document?: DocumentId | null;
  type: Type;
  source: NodeId;
  target: NodeId;
}
/**
 * A grade in one scheme, kept with its scheme so a later change of scheme (L3.7) keeps the
 * original beside the new one (C13).
 */
export interface Grading {
  scheme?: GradingSchemeName;
  source: GradeSource;
  intelligence: GradeIntelligence;
  handling: GradeHandling;
}
