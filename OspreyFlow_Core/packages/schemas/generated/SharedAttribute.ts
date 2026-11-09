// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type Type = string;
export type ProvenanceState = "asserted" | "inferred" | "unresolved";
export type DocumentId = string;
export type Locator = string;
export type ExcerptHash = string;
export type SourceLoadId = string | null;
export type Sources = SourceRef[];
export type SourcesWithheld = boolean;
export type ExtractedBy = string | null;
export type ExtractionConfidence = number | null;
export type FirstSeen = string;
export type LastConfirmed = string | null;
export type PrincipalId = string;
export type ProvenanceClass = "analyst_drawn";
export type DrawnItemId = string;
export type DrawnBoardId = string;
export type DrawnCaseId = string;
export type DrawnLabel = string;
export type GradingSchemeName = string;
export type GradeSource = string;
export type GradeIntelligence = string;
export type GradeHandling = string;
export type DrawnOriginalGrading = Grading | null;
export type DrawnSourceNote = string | null;
export type DrawnIcon = string | null;
export type Classification = string;
export type HandlingCode = string;
export type ActionCode = string | null;
export type SanitisationCode = string | null;
export type OrgUnitId = string;
export type ReviewDate = string | null;
export type LegalBasis = string | null;
export type ClusterId = string;
export type ClusterScore = number | null;
export type ResolutionRun = string | null;
export type ManuallyLinked = NodeId[];
export type ManuallySplit = NodeId[];
export type CreatedAt = string;
export type Revision = number;
export type SupersededBy = string | null;
export type LoadId = string | null;
export type RecipeId = string | null;
export type RecipeVersion = number | null;
export type Reverted = boolean;
export type WithdrawnByLoad = string | null;
export type Datasets = string[];
export type Score = number;

/**
 * One attribute node a pair shares, as the viewer may see it, with its score: its
 * contribution to the pair's rarity (`ln(N_visible / df_visible)`) under `idf`, its own rarity
 * (`1 − L/ΣL`) under `share`; a score and never a count.
 */
export interface SharedAttribute {
  node: Node;
  score: Score;
  [k: string]: unknown;
}
export interface Node {
  id: NodeId;
  type: Type;
  properties?: Properties;
  provenance: Provenance;
  handling: Handling;
  resolution?: ResolutionState;
  audit: AuditStub;
  datasets?: Datasets;
  [k: string]: unknown;
}
export interface Properties {
  [k: string]: unknown;
}
export interface Provenance {
  state: ProvenanceState;
  sources: Sources;
  sources_withheld?: SourcesWithheld;
  extracted_by?: ExtractedBy;
  extraction_confidence?: ExtractionConfidence;
  first_seen: FirstSeen;
  last_confirmed?: LastConfirmed;
  confirmed_by?: PrincipalId | null;
  drawn?: DrawnAssertion | null;
  [k: string]: unknown;
}
export interface SourceRef {
  document_id: DocumentId;
  locator: Locator;
  excerpt_hash: ExcerptHash;
  load_id?: SourceLoadId;
  [k: string]: unknown;
}
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
export interface Handling {
  classification: Classification;
  handling_code: HandlingCode;
  action_code?: ActionCode;
  sanitisation_code?: SanitisationCode;
  originator: OrgUnitId;
  owning_unit: OrgUnitId;
  review_date?: ReviewDate;
  legal_basis?: LegalBasis;
  [k: string]: unknown;
}
export interface ResolutionState {
  cluster_id?: ClusterId | null;
  cluster_score?: ClusterScore;
  resolution_run?: ResolutionRun;
  manually_linked?: ManuallyLinked;
  manually_split?: ManuallySplit;
  [k: string]: unknown;
}
export interface AuditStub {
  created_at: CreatedAt;
  created_by: PrincipalId;
  revision?: Revision;
  superseded_by?: SupersededBy;
  load_id?: LoadId;
  recipe_id?: RecipeId;
  recipe_version?: RecipeVersion;
  reverted?: Reverted;
  withdrawn_by_load?: WithdrawnByLoad;
  [k: string]: unknown;
}
