// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
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
export type Type2 = string;
export type Nodes1 = StructureNode[];
export type Weight1 = number;
export type Edges1 = StructureEdge[];

/**
 * Louvain, with a connected-components split pass — `06_DECISIONS.md` ADR-029: Leiden
 * (`01_DOMAIN_MODEL.md` §6.3's own original preference) is unavailable on either compute tier —
 * no browser-ecosystem implementation with the maturity this build requires, and the standard
 * Python route (`leidenalg`) is GPL, the same dependency ADR-021 already rejected for Splink.
 * The split pass closes §6.3's own specific objection to Louvain (it can merge two disconnected
 * components into one labelled community) without restoring Leiden's own partition quality — a
 * disclosed trade, not a free fix. No algorithm choice is exposed; only one is sanctioned.
 *
 * Of exactly one graph: the records (`subgraph`, the canvas's own), or only their structure
 * (`structure`, a whole case's, ADR-100 Amendment 5). The algorithm reads ids and ends alone.
 */
export interface CommunityRequest {
  subgraph?: Subgraph | null;
  structure?: LinkStructure | null;
  [k: string]: unknown;
}
/**
 * Nodes and links a read returned. It carries no count of what was left out (ADR-124
 * decision 1): `filtered_count` was on it and was 0 on every read the adapter made, a field
 * that claims completeness and is sent wherever a `Subgraph` is a response.
 */
export interface Subgraph {
  nodes: Nodes;
  edges: Edges;
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
/**
 * A graph as only its structure (ADR-100 Amendment 5): each node's id and type, each link's
 * id, ends and weight. What groups are found from in a large case, whose records read in full are
 * hundreds of megabytes (measured: 1.6 KB a link on the Enron case).
 */
export interface LinkStructure {
  nodes: Nodes1;
  edges: Edges1;
  [k: string]: unknown;
}
export interface StructureNode {
  id: NodeId;
  type: Type2;
  [k: string]: unknown;
}
export interface StructureEdge {
  id: EdgeId;
  source: NodeId;
  target: NodeId;
  weight?: Weight1;
  [k: string]: unknown;
}
