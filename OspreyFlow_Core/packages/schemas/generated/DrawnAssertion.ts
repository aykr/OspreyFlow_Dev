// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type ProvenanceClass = "analyst_drawn";
export type DrawnItemId = string;
export type PrincipalId = string;
export type DrawnBoardId = string;
export type DrawnCaseId = string;
export type DrawnLabel = string;
export type GradingSchemeName = "5x5x5" | "3x5x2";
export type GradeSource = string;
export type GradeIntelligence = string;
export type GradeHandling = string;
export type DrawnSourceNote = string | null;
export type DocumentId = string;
export type DrawnIcon = string | null;

/**
 * ADR-143 decision 4: on the provenance of every drawn node and link. A drawn item is asserted
 * by its author, not model-derived: rule 5's `inferred` is for the matches it raises, not for
 * it.
 */
export interface DrawnAssertion {
  provenance_class?: ProvenanceClass;
  item_id: DrawnItemId;
  asserted_by: PrincipalId;
  board_id: DrawnBoardId;
  case_id: DrawnCaseId;
  label: DrawnLabel;
  grading: Grading;
  source_note?: DrawnSourceNote;
  source_document?: DocumentId | null;
  icon?: DrawnIcon;
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
