// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Label = string;
export type Marking = string;
export type GradingSchemeName = string;
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
