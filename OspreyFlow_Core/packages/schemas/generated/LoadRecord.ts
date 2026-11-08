// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type LoadId = string;
export type RecipeId = string;
export type RecipeVersion = number;
export type Source = string;
export type StartedAt = string;
export type CompletedAt = string | null;
export type PrincipalId = string;
export type NodeId = string;
export type CreatedNodeIds = NodeId[];
export type EdgeId = string;
export type TouchedEdgeIds = EdgeId[];
export type RejectedCount = number;
export type SupersededAt = string | null;
export type InvestigationId = string | null;
export type CreatedEdgeIds = EdgeId[];
export type MergedEdgeIds = EdgeId[];
export type MergedNodeIds = NodeId[];
export type RuleNodeIds = NodeId[];
export type CreatedGeometryRefs = string[];
export type UncoveredWrites = boolean;
export type ReleasedFrom = string | null;
export type EventsStamped = boolean;
export type RevertedAt = string | null;
export type RowsWithdrawn = number;
export type WithdrawnNodeIds = NodeId[];
export type WithdrawnEdgeIds = EdgeId[];
export type EdgeType = string;
export type Revision = number;
export type LoadId1 = string | null;
export type Classification = string;
export type HandlingCode = string;
export type ActionCode = string | null;
export type SanitisationCode = string | null;
export type OrgUnitId = string;
export type ReviewDate = string | null;
export type LegalBasis = string | null;
export type LeftDigest = string | null;
export type OwnKeyMerges = LinkPriorState[];
export type SourceId = string;
export type Column = string;
export type Kind = "number" | "time" | "text";
export type Value = string;

/**
 * One execution of a recipe against a source — the persisted form of
 * a `LoadReport`. `created_node_ids` is only the nodes this load
 * created, never one it merely referenced; `touched_edge_ids` is every
 * edge it wrote to, created or merged into. The revert
 * (`services/ingest/load_revert.py`) reads the created lists only and refuses a load that
 * merged: an element a load created can be taken back without affecting another load, but
 * one it merged into is shared, and `GraphArcadeDBAdapter.revert_elements` only ever sets a
 * flag rather than deleting, so the audit trail stays intact regardless. Every
 * element also carries `load_id` on its own `AuditStub`, so filtering
 * the graph directly by load or recipe version never needs this ledger
 * at all; the ledger is for load-level operations (revert, history) a
 * per-element stamp cannot answer by itself.
 */
export interface LoadRecord {
  load_id: LoadId;
  recipe_id: RecipeId;
  recipe_version: RecipeVersion;
  source: Source;
  started_at: StartedAt;
  completed_at?: CompletedAt;
  created_by: PrincipalId;
  created_node_ids?: CreatedNodeIds;
  touched_edge_ids?: TouchedEdgeIds;
  rejected_count?: RejectedCount;
  superseded_at?: SupersededAt;
  investigation_id?: InvestigationId;
  created_edge_ids?: CreatedEdgeIds;
  merged_edge_ids?: MergedEdgeIds;
  merged_node_ids?: MergedNodeIds;
  rule_node_ids?: RuleNodeIds;
  created_geometry_refs?: CreatedGeometryRefs;
  uncovered_writes?: UncoveredWrites;
  released_from?: ReleasedFrom;
  events_stamped?: EventsStamped;
  superseded_by?: PrincipalId | null;
  reverted_at?: RevertedAt;
  reverted_by?: PrincipalId | null;
  rows_withdrawn?: RowsWithdrawn;
  withdrawn_node_ids?: WithdrawnNodeIds;
  withdrawn_edge_ids?: WithdrawnEdgeIds;
  own_key_merges?: OwnKeyMerges;
  watermark?: SourceWatermark | null;
  [k: string]: unknown;
}
/**
 * ADR-110 Amendment 16: a link exactly as it was stored just before a returning row's load
 * merged into it. A row a full snapshot withdrew comes back, and its write merges into the link
 * its own withdrawn key recorded; the load keeps that link's prior state so its revert can put the
 * link back as it was, and refuses if the link was written since (its `revision` or `load_id`
 * moved).
 *
 * **Graph data (rule 3).** `stored` holds the link's properties, provenance and marking as the
 * adapter stores them. It is held in the run ledger for `services/ingest/load_revert.py` alone:
 * no route, view, report, log or metering carries it, and `LoadReport` leaves it out of every
 * dump. `handling` is the link's marking when it was read; a restore writes the link back at it,
 * never at a weaker one.
 */
export interface LinkPriorState {
  edge_id: EdgeId;
  edge_type: EdgeType;
  revision: Revision;
  load_id?: LoadId1;
  handling: Handling;
  stored?: Stored;
  left_digest?: LeftDigest;
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
export interface Stored {
  [k: string]: unknown;
}
/**
 * The highest value of an incremental source's watermark column a run read (ADR-110 Amendment
 * 6 point 1), kept with the load's record: the next refresh of the source, by the same pipeline
 * into the same case, reads only rows past it. `value` is the value as the file held it;
 * `kind` says how it compares (as a number, as an instant, or as text). For the ledger alone: a
 * value of the loader's own source, never in a route's answer.
 */
export interface SourceWatermark {
  source_id: SourceId;
  column: Column;
  kind: Kind;
  value: Value;
  [k: string]: unknown;
}
