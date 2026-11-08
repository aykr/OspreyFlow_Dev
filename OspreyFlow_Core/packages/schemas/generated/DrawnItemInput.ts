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
export type Icon = string | null;
export type X = number;
export type Y = number;

/**
 * *Add to board*: a node of a type of the case's model (C14), with its key properties if the
 * analyst knows them (each checked against the type), placed where it was dropped.
 */
export interface DrawnItemInput {
  label: Label;
  marking: Marking;
  grading: Grading;
  source_note?: SourceNote;
  source_document?: DocumentId | null;
  type: Type;
  properties?: Properties;
  icon?: Icon;
  x?: X;
  y?: Y;
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
export interface Properties {
  [k: string]: unknown;
}
