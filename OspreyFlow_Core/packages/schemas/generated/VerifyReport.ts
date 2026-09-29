// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RowsRead = number;
export type RowsDeduplicated = number;
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
export type Samples = RejectionRecord[];
export type Rejections = RejectionGroup[];
export type NodeId = string;
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
export type CreatedAt = string;
export type Revision = number;
export type SupersededBy = string | null;
export type LoadId = string | null;
export type RecipeId = string | null;
export type RecipeVersion = number | null;
export type Reverted = boolean;
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
export type ComputedAt = string;
export type Edges = Edge[];

/**
 * The dry run's three outputs (§5) in one response: counts,
 * `rejections`, and the graph it would make (`nodes`/`edges`) — the same
 * `schemas.domain.Node`/`Edge` shapes `GlassCanvas` already renders, not
 * a second preview-only shape invented for this screen.
 */
export interface VerifyReport {
  rows_read: RowsRead;
  rows_deduplicated: RowsDeduplicated;
  sample_is_whole_source: SampleIsWholeSource;
  values_masked: ValuesMasked;
  entities_by_type?: EntitiesByType;
  edges_by_type?: EdgesByType;
  rejections?: Rejections;
  nodes?: Nodes;
  edges?: Edges;
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
  created_at: CreatedAt;
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
  provenance: Provenance;
  handling: Handling;
  audit: AuditStub;
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
  computed_at: ComputedAt;
  [k: string]: unknown;
}
