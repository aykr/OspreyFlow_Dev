// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type RuleId = string;
export type OwnerId = string;
export type AlertMode = "full" | "notify_stub";
export type NodeId = string;
export type ReferentNodeIds = NodeId[];
export type InvestigationId = string | null;
export type CreatedAt = string;
export type DatasetId = string | null;
export type Typology = string | null;
export type Words = string | null;
export type EdgeId = string;
export type EdgeIds = EdgeId[];
export type EventIds = string[];
export type ValidFrom = string;
export type ValidTo = string | null;
export type Trigger = ("pre_commit" | "post_commit" | "schedule") | null;
export type Status = "open" | "claimed" | "closing" | "closed";
export type Assignee = string | null;
export type Disposition = ("true_positive" | "false_positive" | "duplicate" | "no_further_action" | "referred") | null;
export type DispositionReason = string | null;
export type DecidedBy = string | null;
export type DecidedAt = string | null;
export type CloseProposedBy = string | null;
export type CloseProposedAt = string | null;
export type Severity = ("low" | "medium" | "high") | null;
export type Team = string | null;
export type RoutedTeam = string | null;
export type SuppressedUntil = string | null;
export type SuppressReason = string | null;
export type SuppressedBy = string | null;
export type Summary = string;
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
export type Type1 = string;
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
export type EventId = string;
export type OccurredAt = string;
export type Amount = number | null;
export type Transactions = ExplainedTransaction[];
export type Kind = "typology" | "hotlist" | "monitor" | "analyst" | "drawn_watch";
export type Severity1 = "low" | "medium" | "high";
export type Audience = "case" | "team" | "owner";
export type Team1 = string | null;
export type CloseProposedByName = string | null;
export type AssigneeName = string | null;
export type Identifier = string;
export type KeptAsWritten = boolean;
export type ReviewDate1 = string;
export type FiredOn = FiredOn1[] | null;
export type Type2 = string;
export type Label = string;
export type Name = string;
export type Row = number | null;
export type Rows = number | null;
export type Records = number | null;
export type Files = FiredFile[];
export type MoreFiles = number;
export type SourcesWithheld1 = boolean;
export type TeamName = string | null;
export type Suppressed = boolean;
export type Lead = boolean;

/**
 * What fired an alert, for the reader (ADR-109 phase B): the entities it concerns and its
 * own node, the links it cites (and the `ALERTED_ON` links), and each transaction it cites. Every
 * part is read as the reader; an alert any part of which the reader cannot see is not shown at
 * all (ADR-039's all-or-nothing, rule 3).
 */
export interface AlertExplanation {
  alert: Alert;
  summary: Summary;
  nodes?: Nodes;
  edges?: Edges;
  transactions?: Transactions;
  kind?: Kind;
  severity?: Severity1;
  audience?: Audience;
  team?: Team1;
  close_proposed_by_name?: CloseProposedByName;
  assignee_name?: AssigneeName;
  hotlist?: AlertHotlist | null;
  fired_on?: FiredOn;
  team_name?: TeamName;
  suppressed?: Suppressed;
  lead?: Lead;
  [k: string]: unknown;
}
/**
 * A persisted alert row — `06_DECISIONS.md` ADR-038/039, Phase 7 Stage 6a's own foundation.
 * Stores references to evidence, never copies (`rule_id` plus `referent_node_ids`) — access is
 * re-checked at read time against those referents, not trusted from whatever was true when this
 * row was written. `NOTIFY_STUB` rows never carry a referent at all, enforced by every producer
 * this stage builds (`services/api/alerts.py`'s own `record_match` is the one place a row is
 * constructed), not merely a convention this model documents without holding to.
 *
 * `investigation_id` (Stage 6c): a best-effort audit-shaped hint, not an access-control scope —
 * the same distinction `run_studio_recipe`'s own docstring already draws for `EventRecord.
 * investigation_scope`. Threaded from `ChangeStreamEntry.investigation_id`, itself threaded from
 * whichever producer route was investigation-scoped at the point the triggering write happened
 * (ingest); `None` for a producer that genuinely has no single investigation in scope (the
 * corpus-wide resolution trigger). B14's "jump" opens a case of the jumper's own from the
 * alert; since L3.2 that case records no case it came from (ADR-144 Amendment 1), and the jump's
 * audit row names this one.
 */
export interface Alert {
  id: Id;
  rule_id: RuleId;
  owner_id: OwnerId;
  mode: AlertMode;
  referent_node_ids?: ReferentNodeIds;
  investigation_id?: InvestigationId;
  created_at: CreatedAt;
  dataset_id?: DatasetId;
  typology?: Typology;
  words?: Words;
  edge_ids?: EdgeIds;
  event_ids?: EventIds;
  window?: Interval | null;
  trigger?: Trigger;
  alert_node_id?: NodeId | null;
  status?: Status;
  assignee?: Assignee;
  disposition?: Disposition;
  disposition_reason?: DispositionReason;
  decided_by?: DecidedBy;
  decided_at?: DecidedAt;
  close_proposed_by?: CloseProposedBy;
  close_proposed_at?: CloseProposedAt;
  severity?: Severity;
  team?: Team;
  routed_team?: RoutedTeam;
  suppressed_until?: SuppressedUntil;
  suppress_reason?: SuppressReason;
  suppressed_by?: SuppressedBy;
  [k: string]: unknown;
}
export interface Interval {
  valid_from: ValidFrom;
  valid_to?: ValidTo;
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
 * One transaction an alert cites, as the reader may read it: the link it is on, its ends,
 * when, and how much.
 */
export interface ExplainedTransaction {
  event_id: EventId;
  edge_id: EdgeId;
  source_id: NodeId;
  target_id: NodeId;
  occurred_at: OccurredAt;
  amount?: Amount;
  [k: string]: unknown;
}
/**
 * ADR-130 decision 1: the hotlist a `hotlist:` alert came from, read at display time and only
 * for the hotlist's owner. The identifier is as typed (else as stored).
 */
export interface AlertHotlist {
  identifier: Identifier;
  kept_as_written: KeptAsWritten;
  review_date: ReviewDate1;
  [k: string]: unknown;
}
/**
 * ADR-130 decision 1: what a matched node is, and where it was read from. `files` are in the
 * order of first appearance, at most five; `more_files` counts the rest.
 *
 * ADR-130 Amendment 1: when the node belongs to a dataset the reader's case does not read, its
 * sources are not said at all: `sources_withheld` is true, `files` is empty and `more_files` 0.
 */
export interface FiredOn1 {
  type: Type2;
  label: Label;
  files: Files;
  more_files: MoreFiles;
  sources_withheld?: SourcesWithheld1;
  [k: string]: unknown;
}
/**
 * One source file of a matched node: its name (the final path segment of the document id; two
 * loads' `calls.csv` are two entries), and what is cited in it. `row` is the single row (its
 * offset under the header, counted from 0; the Glass shows it counted from 1, ADR-131) when
 * exactly one `row N` is cited and nothing else; otherwise `rows` counts the distinct `row N`
 * locators and `records` the distinct locators of any other form (ADR-130 Amendment 1).
 */
export interface FiredFile {
  name: Name;
  row?: Row;
  rows?: Rows;
  records?: Records;
  [k: string]: unknown;
}
