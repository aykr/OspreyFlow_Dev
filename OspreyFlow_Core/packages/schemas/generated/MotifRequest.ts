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
export type FilteredCount = number;
export type MotifType = "convoy" | "relay" | "burst";
export type DistanceTolerance = number | null;
export type TimeToleranceSeconds = number | null;

/**
 * Real types, honestly scoped — a disclosed gap: this schema exists because
 * `_pending_port_placeholders.py`'s retirement needs it,
 * not because any phase's bullet list has yet claimed the convoy/relay/burst algorithms
 * themselves. `distance_tolerance`/`time_tolerance_seconds` are named directly from
 * `02_GLASS_FRONTEND.md`'s own Convoy analysis line ("co-located within a distance and time
 * tolerance; tolerances are user-set and shown") — `relay`/`burst` have no comparably specific
 * spec text yet, so their own parameter needs are left to whichever stage actually builds them.
 */
export interface MotifRequest {
  subgraph: Subgraph;
  motif_type: MotifType;
  distance_tolerance?: DistanceTolerance;
  time_tolerance_seconds?: TimeToleranceSeconds;
  [k: string]: unknown;
}
export interface Subgraph {
  nodes: Nodes;
  edges: Edges;
  filtered_count?: FilteredCount;
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
