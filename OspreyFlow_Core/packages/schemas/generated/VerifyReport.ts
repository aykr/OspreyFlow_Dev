// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RowsRead = number;
export type RowsDeduplicated = number;
export type RowsAlreadyLoaded = number;
export type SampleIsWholeSource = boolean;
export type ValuesMasked = boolean;
export type Created = number;
export type Referenced = number;
export type Created1 = number;
export type Reason = string;
export type Count = number;
export type RowIndex = number;
export type Reason1 = string;
export type Sample = string;
export type Table = string;
export type RowIndex1 = number;
export type LoadId = string | null;
export type Side = ("left" | "right") | null;
export type Refs = RejectionRef[];
export type Classification = string;
export type HandlingCode = string;
export type ActionCode = string | null;
export type SanitisationCode = string | null;
export type OrgUnitId = string;
export type ReviewDate = string | null;
export type LegalBasis = string | null;
export type SampleUnreadable = boolean;
export type Samples = RejectionRecord[];
export type Rejections = RejectionGroup[];
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
export type ClusterId = string;
export type ClusterScore = number | null;
export type ResolutionRun = string | null;
export type ManuallyLinked = NodeId[];
export type ManuallySplit = NodeId[];
export type CreatedAt = string;
export type Revision = number;
export type SupersededBy = string | null;
export type LoadId1 = string | null;
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
export type RuleId = string;
export type RuleName = string;
export type Severity = "low" | "medium" | "high";
export type OnHit = "alert" | "hold";
export type EntityId = string;
export type EntityType = string;
export type EntityName = string;
export type WouldRaise = WouldRaise1[];
export type RuleId1 = string;
export type RuleName1 = string;
export type Why = string;
export type ChecksNotJudged = CheckNotJudged[];
export type ChecksJudged = number;
export type ModelVersion = number | null;
export type Step = string;
export type Kind = "sql" | "fuzzy_match";
export type Label = string | null;
export type Summary = string | null;
export type Select = string | null;
export type Reads = string[];
export type Compares = string[];
export type Threshold = number | null;
export type SameAs = string[];
export type ExpertSteps = ExpertStepDisclosure[];

/**
 * The dry run's three outputs (§5) in one response: counts,
 * `rejections`, and the graph it would make (`nodes`/`edges`) — the same
 * `schemas.domain.Node`/`Edge` shapes `GlassCanvas` already renders, not
 * a second preview-only shape invented for this screen.
 */
export interface VerifyReport {
  rows_read: RowsRead;
  rows_deduplicated: RowsDeduplicated;
  rows_already_loaded?: RowsAlreadyLoaded;
  sample_is_whole_source: SampleIsWholeSource;
  values_masked: ValuesMasked;
  entities_by_type?: EntitiesByType;
  edges_by_type?: EdgesByType;
  rejections?: Rejections;
  nodes?: Nodes;
  edges?: Edges;
  would_raise?: WouldRaise;
  checks_not_judged?: ChecksNotJudged;
  checks_judged?: ChecksJudged;
  model_version?: ModelVersion;
  expert_steps?: ExpertSteps;
  [k: string]: unknown;
}
export interface EntitiesByType {
  [k: string]: VerifyEntityCount;
}
/**
 * Per entity-type counts for one dry run — §5: "Counts. Nodes and
 * edges by type, how many referenced an existing node and how many
 * created one."
 */
export interface VerifyEntityCount {
  created?: Created;
  referenced?: Referenced;
  [k: string]: unknown;
}
export interface EdgesByType {
  [k: string]: VerifyEdgeCount;
}
/**
 * An edge has no `match_on`/`on_match` of its own (`RecipeEdge` never
 * declares one) — every edge the dry run resolves is "created" in the
 * sense of "this recipe would write it"; same-pair edges within the
 * sample still merge into one, occurrence-counted, the way a real load's
 * `GraphArcadeDBAdapter.upsert_edges` merges them.
 */
export interface VerifyEdgeCount {
  created?: Created1;
  [k: string]: unknown;
}
/**
 * §5: "The rejection report, grouped by cause with samples." `count`
 * is always the true total for this reason — `samples` is capped
 * (studio_verify.py), but the count itself never is, so a reason with
 * 400 rejections still reads as 400, not silently as however many
 * samples happened to ride along.
 */
export interface RejectionGroup {
  reason: Reason;
  count: Count;
  samples: Samples;
  [k: string]: unknown;
}
/**
 * One rejected row, grouped by cause in the load report — never a
 * silent coercion (`01_DOMAIN_MODEL.md` §7).
 */
export interface RejectionRecord {
  row_index: RowIndex;
  reason: Reason1;
  sample: Sample;
  refs?: Refs;
  marking?: Handling | null;
  sample_unreadable?: SampleUnreadable;
  [k: string]: unknown;
}
/**
 * ADR-140 Amendment 12: a row a rejection came from, in a staged run. The table it is a row of
 * (a source's name, `reference_list:<name>@v<n>`, or a staged step's table), its row number, the
 * load that read it (a source row's; `None` for a list row or a staged table's row) and, for a
 * Join, the side. **No row key, raw or hashed** (rule 7;
 * `tests/schemas/test_staging_report_schemas.py`).
 */
export interface RejectionRef {
  table: Table;
  row_index: RowIndex1;
  load_id?: LoadId;
  side?: Side;
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
  load_id?: LoadId1;
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
/**
 * One alert Verify's sample would raise (decision 6): the rule, what a hit does at this
 * pipeline, and the entity matched, as the person verifying reads it in the sample.
 */
export interface WouldRaise1 {
  rule_id: RuleId;
  rule_name: RuleName;
  severity: Severity;
  on_hit: OnHit;
  entity_id: EntityId;
  entity_type: EntityType;
  entity_name: EntityName;
  [k: string]: unknown;
}
/**
 * A rule that applies at load but that a dry run cannot judge, and why, in words.
 */
export interface CheckNotJudged {
  rule_id: RuleId1;
  rule_name: RuleName1;
  why: Why;
  [k: string]: unknown;
}
/**
 * ADR-140 decision 16 and the redesign brief §5.3–5.4: every run report, and Test, says which
 * expert steps ran and what they were, in words, whether or not its counts are withheld. It is
 * the pipeline's own configuration, never a value of a row: the SQL step's summary and its
 * SELECT; the fuzzy match's tables, comparisons and threshold, and that it writes an inferred
 * `SAME_AS`, never a merge. Its counts are in `staging_steps`, withheld with the others.
 */
export interface ExpertStepDisclosure {
  step: Step;
  kind: Kind;
  label?: Label;
  summary?: Summary;
  select?: Select;
  reads?: Reads;
  compares?: Compares;
  threshold?: Threshold;
  same_as?: SameAs;
}
