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
  [k: string]: unknown;
}
export interface Interval {
  valid_from: ValidFrom;
  valid_to?: ValidTo;
  [k: string]: unknown;
}
