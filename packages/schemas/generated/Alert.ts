// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type RuleId = string;
export type OwnerId = string;
export type AlertMode = "full" | "notify_stub";
export type NodeId = string;
export type ReferentNodeIds = NodeId[];
export type CreatedAt = string;

/**
 * A persisted alert row — `06_DECISIONS.md` ADR-038/039, Phase 7 Stage 6a's own foundation.
 * Stores references to evidence, never copies (`rule_id` plus `referent_node_ids`) — access is
 * re-checked at read time against those referents, not trusted from whatever was true when this
 * row was written. `NOTIFY_STUB` rows never carry a referent at all, enforced by every producer
 * this stage builds (`services/api/alerts.py`'s own `record_match` is the one place a row is
 * constructed), not merely a convention this model documents without holding to.
 */
export interface Alert {
  id: Id;
  rule_id: RuleId;
  owner_id: OwnerId;
  mode: AlertMode;
  referent_node_ids?: ReferentNodeIds;
  created_at: CreatedAt;
  [k: string]: unknown;
}
