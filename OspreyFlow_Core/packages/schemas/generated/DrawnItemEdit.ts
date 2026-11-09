// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Label = string | null;
export type Marking = string | null;
export type GradingSchemeName = "5x5x5" | "3x5x2";
export type GradeSource = string;
export type GradeIntelligence = string;
export type GradeHandling = string;
export type SourceNote = string | null;
export type DocumentId = string;
export type Properties = {
  [k: string]: unknown;
} | null;
export type Icon = string | null;

/**
 * The author changes their own item: what is not given stays. A marking is never lowered.
 */
export interface DrawnItemEdit {
  label?: Label;
  marking?: Marking;
  grading?: Grading | null;
  source_note?: SourceNote;
  source_document?: DocumentId | null;
  properties?: Properties;
  icon?: Icon;
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
