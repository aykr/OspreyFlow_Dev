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
export type Trigger = ("pre_commit" | "post_commit") | null;
export type Status = "open" | "claimed" | "closed";
export type Assignee = string | null;
export type Disposition = ("true_positive" | "false_positive") | null;
export type DispositionReason = string | null;
export type DecidedBy = string | null;
export type DecidedAt = string | null;
export type Summary = string;
export type Type = string;
export type ProvenanceState = "asserted" | "inferred" | "unresolved";
export type DocumentId = string;
export type Locator = string;
export type ExcerptHash = string;
export type Sources = SourceRef[];
export type ExtractedBy = string | null;
export type ExtractionConfidence = number | null;
export type FirstSeen = string;
export type LastConfirmed = string | null;
export type PrincipalId = string;
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
export type ComputedAt = string;
export type Basis = ("direct" | "probabilistic") | null;
export type Datasets1 = string[];
export type Edges = Edge[];
export type EventId = string;
export type OccurredAt = string;
export type Amount = number | null;
export type Transactions = ExplainedTransaction[];

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
 * corpus-wide resolution trigger). B14's "jump" branches a new investigation from this field via
 * `InvestigationStore.create(principal, branched_from=...)` — the identical mechanism
 * `branch_investigation` already uses, not new investigation-linking infrastructure. `None` here
 * means the jump starts an unbranched investigation instead of one carrying that link, disclosed
 * to the analyst rather than silently omitted.
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
  extracted_by?: ExtractedBy;
  extraction_confidence?: ExtractionConfidence;
  first_seen: FirstSeen;
  last_confirmed?: LastConfirmed;
  confirmed_by?: PrincipalId | null;
  [k: string]: unknown;
}
export interface SourceRef {
  document_id: DocumentId;
  locator: Locator;
  excerpt_hash: ExcerptHash;
  [k: string]: unknown;
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
