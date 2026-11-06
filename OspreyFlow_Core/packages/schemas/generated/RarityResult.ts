// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Scope = "dataset" | "case";
export type A = string;
export type B = string;
export type Score = number | null;
export type Dataset = string | null;
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
export type LoadId = string | null;
export type RecipeId = string | null;
export type RecipeVersion = number | null;
export type Reverted = boolean;
export type WithdrawnByLoad = string | null;
export type Datasets = string[];
export type Score1 = number;
export type Shared = SharedAttribute[];
export type ParityRaw = number | null;
export type ParityStrength = number | null;
export type Id = string;
export type Label = string;
export type Change = "add" | "multiply" | "floor" | "exclude";
export type Size = number;
export type Layer = "file" | "installation" | "case";
export type RecordKind = string | null;
export type Dataset1 = string | null;
export type ParityApplied = AppliedInfluencer[];
export type Pairs = PairRarity[];
export type Measure = "share" | "idf";
export type Composition = "standard" | "client_parity";

/**
 * `node_values`: each working-set entity's highest rarity with another working-set entity of
 * its kind (absent when it shares nothing that scores); `pairs`: the pairs asked for.
 */
export interface RarityResult {
  scope: Scope;
  node_values: NodeValues;
  pairs: Pairs;
  measure?: Measure;
  composition?: Composition;
  [k: string]: unknown;
}
export interface NodeValues {
  [k: string]: number;
}
/**
 * Two entities' shared-attribute rarity. `dataset` names the dataset it was worked out in
 * (per-dataset scope), None across the case's readable datasets. `score` None: the two are of
 * different kinds, or share no dataset in per-dataset scope, so there is no rarity to give.
 */
export interface PairRarity {
  a: A;
  b: B;
  score: Score;
  dataset?: Dataset;
  shared?: Shared;
  parity_raw?: ParityRaw;
  parity_strength?: ParityStrength;
  parity_applied?: ParityApplied;
  [k: string]: unknown;
}
/**
 * One attribute node a pair shares, as the viewer may see it, with its score: its
 * contribution to the pair's rarity (`ln(N_visible / df_visible)`) under `idf`, its own rarity
 * (`1 − L/ΣL`) under `share`; a score and never a count.
 */
export interface SharedAttribute {
  node: Node;
  score: Score1;
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
  load_id?: LoadId;
  recipe_id?: RecipeId;
  recipe_version?: RecipeVersion;
  reverted?: Reverted;
  withdrawn_by_load?: WithdrawnByLoad;
  [k: string]: unknown;
}
/**
 * One influencer that changed one link, and the kind of record that evidenced it (None for a
 * direct-links influencer). Only a record the viewer may see is ever named.
 */
export interface AppliedInfluencer {
  id: Id;
  label: Label;
  change: Change;
  size: Size;
  layer: Layer;
  record_kind?: RecordKind;
  dataset?: Dataset1;
  [k: string]: unknown;
}
