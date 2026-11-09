// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type ProvenanceClass = "analyst_drawn";
export type DrawnItemId = string;
export type PrincipalId = string;
export type DrawnBoardId = string;
export type DrawnCaseId = string;
export type DrawnLabel = string;
export type GradingSchemeName = string;
export type GradeSource = string;
export type GradeIntelligence = string;
export type GradeHandling = string;
export type DrawnOriginalGrading = Grading | null;
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
  original_grading?: DrawnOriginalGrading;
  source_note?: DrawnSourceNote;
  source_document?: DocumentId | null;
  icon?: DrawnIcon;
}
/**
 * A grade in one scheme, kept with its scheme so a later change of scheme (L3.7) keeps the
 * original beside the new one (C13).
 *
 * A grade of a built-in scheme is checked against its parts here. A grade of a scheme file's
 * scheme (Amendment 6) is checked where a grade enters, against the deployment's scheme: the
 * board routes and the grading change. A stored one is read as stored, since an original may be of
 * a scheme the deployment no longer has.
 */
export interface Grading {
  scheme?: GradingSchemeName;
  source: GradeSource;
  intelligence: GradeIntelligence;
  handling: GradeHandling;
}
