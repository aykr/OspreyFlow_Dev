// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type Threshold = number;
export type NodeType = string;
export type CumulativePercent = number;
export type ShareUnknown = boolean;
export type Controls = boolean;
export type EdgeId = string;
export type LinkIds = EdgeId[];
export type Kind = "ownership" | "unknown" | "control";
export type Share = number | null;
export type Paths = OwnershipPath[];
export type BeneficialOwner = boolean;
export type PossibleBeneficialOwner = boolean;
export type Owners = OwnerTrace[];
export type Cycles = NodeId[][];
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
export type Datasets = string[];
export type Nodes = Node[];
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

/**
 * An ownership trace as the Glass shows it: the trace, and the parties and links it was
 * computed over, read as the reader (ADR-109 phase C).
 */
export interface OwnershipView {
  trace: OwnershipTrace;
  nodes?: Nodes;
  edges?: Edges;
  [k: string]: unknown;
}
export interface OwnershipTrace {
  target: NodeId;
  threshold: Threshold;
  owners?: Owners;
  cycles?: Cycles;
  [k: string]: unknown;
}
export interface OwnerTrace {
  node_id: NodeId;
  node_type: NodeType;
  cumulative_percent: CumulativePercent;
  share_unknown?: ShareUnknown;
  controls?: Controls;
  paths?: Paths;
  beneficial_owner?: BeneficialOwner;
  possible_beneficial_owner?: PossibleBeneficialOwner;
  [k: string]: unknown;
}
/**
 * One chain from an owner to the target, its links in order. `ownership`: every link owns
 * with a stated percentage, and `share` is their product (as a percentage). `unknown`: a link
 * states no percentage, so the share is not known. `control`: a link controls rather than owns,
 * so the chain confers control, not a share.
 */
export interface OwnershipPath {
  link_ids: LinkIds;
  kind: Kind;
  share?: Share;
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
