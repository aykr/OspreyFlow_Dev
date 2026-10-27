// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type LoadId = string | null;
export type RecipeId = string | null;
export type RecipeVersion = number | null;
export type Nodes = number;
export type Links = number;
export type Latest = string;
export type Loads = LoadSummary[];
export type LoadsTotal = number;
export type NodeId = string;
export type Type = string;
export type ProvenanceState = "asserted" | "inferred" | "unresolved";
export type DocumentId = string;
export type Locator = string;
export type ExcerptHash = string;
export type Sources = SourceRef[];
export type SourcesWithheld = boolean;
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
export type LoadId1 = string | null;
export type RecipeId1 = string | null;
export type RecipeVersion1 = number | null;
export type Reverted = boolean;
export type Datasets = string[];
export type ConfirmedAt = string;
export type ConfirmedBy = string;
export type Confirmed = ConfirmedNode[];
export type ConfirmedTotal = number;
export type MarkedAt = string;
export type MarkedBy = string;
export type Reason = string;
export type Marked = MarkedNode[];
export type MarkedTotal = number;
export type ComputedAt = string | null;

/**
 * ADR-100 decision 7: the latest loads into the case's datasets, and what colleagues
 * confirmed or marked in them, each the latest first with how many there are in all.
 */
export interface WhatsNew {
  loads: Loads;
  loads_total: LoadsTotal;
  confirmed: Confirmed;
  confirmed_total: ConfirmedTotal;
  marked: Marked;
  marked_total: MarkedTotal;
  computed_at?: ComputedAt;
  [k: string]: unknown;
}
/**
 * One load into the case's datasets (ADR-100 decision 7), as far as the reader can see it:
 * only what it wrote that they can see is counted, and `latest` is the newest of those.
 */
export interface LoadSummary {
  load_id: LoadId;
  recipe_id?: RecipeId;
  recipe_version?: RecipeVersion;
  nodes: Nodes;
  links: Links;
  latest: Latest;
  [k: string]: unknown;
}
export interface ConfirmedNode {
  node: Node;
  confirmed_at: ConfirmedAt;
  confirmed_by: ConfirmedBy;
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
  load_id?: LoadId1;
  recipe_id?: RecipeId1;
  recipe_version?: RecipeVersion1;
  reverted?: Reverted;
  [k: string]: unknown;
}
/**
 * A node an analyst has marked for suppression (owner ruling R7): a proposal, not a change.
 */
export interface MarkedNode {
  node: Node;
  marked_at: MarkedAt;
  marked_by: MarkedBy;
  reason: Reason;
  [k: string]: unknown;
}
