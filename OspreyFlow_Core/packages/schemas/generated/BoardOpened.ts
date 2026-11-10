// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type CaseId = string;
export type Name = string;
export type PrincipalId = string;
export type CreatedAt = string;
export type Shared = boolean;
export type Drawn = number;
export type Start = "blank" | "view" | "selection";
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
export type Gazetteer = string | null;
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
export type CreatedAt1 = string;
export type Revision = number;
export type SupersededBy = string | null;
export type LoadId = string | null;
export type RecipeId = string | null;
export type RecipeVersion = number | null;
export type Reverted = boolean;
export type WithdrawnByLoad = string | null;
export type Datasets = string[];
export type Nodes = Node[];
export type EdgeId = string;
export type Type1 = string;
export type ValidFrom = string;
export type ValidTo = string | null;
export type Occurrences = number;
export type Weight = number;
export type Occurrences1 = number;
export type CorpusPairCount = number;
export type CorpusSourceDegree = number;
export type CorpusTargetDegree = number;
export type CorpusTotalOccurrences = number;
export type ParameterSet = string | null;
export type ComputedAt = string;
export type Basis = ("direct" | "probabilistic") | null;
export type Datasets1 = string[];
export type Edges = Edge[];
export type Drawn1 = string[];
export type Missing = number;
export type NodeTypes = string[];
export type LinkTypes = string[];
export type Markings = string[];
export type Ceiling = string | null;
export type GradingScheme = string;
export type GradingSchemeName1 = string;
/**
 * @minItems 1
 * @maxItems 12
 */
export type GradeSources =
  | [string]
  | [string, string]
  | [string, string, string]
  | [string, string, string, string]
  | [string, string, string, string, string]
  | [string, string, string, string, string, string]
  | [string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string];
/**
 * @minItems 1
 * @maxItems 12
 */
export type GradeIntelligences =
  | [string]
  | [string, string]
  | [string, string, string]
  | [string, string, string, string]
  | [string, string, string, string, string]
  | [string, string, string, string, string, string]
  | [string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string];
/**
 * @minItems 1
 * @maxItems 12
 */
export type GradeHandlings =
  | [string]
  | [string, string]
  | [string, string, string]
  | [string, string, string, string]
  | [string, string, string, string, string]
  | [string, string, string, string, string, string]
  | [string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string];
export type MayDraw = boolean;

/**
 * A board opened now, as the reader may see it. `nodes` are its drawn items and its loaded
 * references; `drawn` names which are drawn (the rest are live references, not editable here);
 * `missing` counts what it could not show and names none (rule 3).
 */
export interface BoardOpened {
  board: Board;
  nodes: Nodes;
  edges: Edges;
  drawn?: Drawn1;
  items?: Items;
  layout?: Layout;
  missing?: Missing;
  node_types?: NodeTypes;
  link_types?: LinkTypes;
  markings?: Markings;
  ceiling?: Ceiling;
  grading_scheme?: GradingScheme;
  grading_grades?: GradingSchemeAnswer | null;
  may_draw?: MayDraw;
  [k: string]: unknown;
}
/**
 * A board as listed: never naming its items.
 */
export interface Board {
  id: Id;
  case_id: CaseId;
  name: Name;
  created_by: PrincipalId;
  created_at: CreatedAt;
  shared?: Shared;
  drawn?: Drawn;
  start?: Start;
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
  gazetteer?: Gazetteer;
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
  created_at: CreatedAt1;
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
export interface Edge {
  id: EdgeId;
  type: Type1;
  source: NodeId;
  target: NodeId;
  properties?: Properties1;
  interval?: Interval | null;
  occurrences?: Occurrences;
  weight?: Weight;
  weight_components?: WeightComponents | null;
  basis?: Basis;
  provenance: Provenance;
  handling: Handling;
  audit: AuditStub;
  datasets?: Datasets1;
  [k: string]: unknown;
}
export interface Properties1 {
  [k: string]: unknown;
}
export interface Interval {
  valid_from: ValidFrom;
  valid_to?: ValidTo;
  [k: string]: unknown;
}
/**
 * Inputs to `01_DOMAIN_MODEL.md` §6.1's weight formula, captured at
 * load time. `weight` on `Edge` is a load-time snapshot, using the
 * corpus as it stood then — never treat it as frozen ground truth. These
 * counts are what make an honest recompute (the working set; a corpus
 * that has since grown) arithmetic over stored numbers rather than a
 * full corpus rescan.
 */
export interface WeightComponents {
  occurrences: Occurrences1;
  corpus_pair_count: CorpusPairCount;
  corpus_source_degree: CorpusSourceDegree;
  corpus_target_degree: CorpusTargetDegree;
  corpus_total_occurrences: CorpusTotalOccurrences;
  parameter_set?: ParameterSet;
  computed_at: ComputedAt;
  [k: string]: unknown;
}
export interface Items {
  [k: string]: string;
}
export interface Layout {
  [k: string]: unknown;
}
/**
 * A grading scheme and each of its parts' grades: `GET /v1/grading-scheme`'s answer (for
 * Admin's read-only display and the boards' grade fields), and the shape of a scheme file
 * (`grading.scheme` naming a YAML file, ADR-143 decision 11 and Amendment 6). A scheme file may
 * not take a built-in scheme's name.
 */
export interface GradingSchemeAnswer {
  scheme: GradingSchemeName1;
  source: GradeSources;
  intelligence: GradeIntelligences;
  handling: GradeHandlings;
}
