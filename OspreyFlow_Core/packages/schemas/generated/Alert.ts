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
export type Trigger = ("pre_commit" | "post_commit" | "schedule" | "list_refresh") | null;
export type Status = "open" | "claimed" | "closing" | "closed";
export type Assignee = string | null;
export type Disposition = ("true_positive" | "false_positive" | "duplicate" | "no_further_action" | "referred") | null;
export type DispositionReason = string | null;
export type DecidedBy = string | null;
export type DecidedAt = string | null;
export type CloseProposedBy = string | null;
export type CloseProposedAt = string | null;
export type Severity = ("low" | "medium" | "high") | null;
export type Team = string | null;
export type RoutedTeam = string | null;
export type SuppressedUntil = string | null;
export type SuppressReason = string | null;
export type SuppressedBy = string | null;
export type Words1 = string;
export type NodeIds = NodeId[];
export type EdgeIds1 = EdgeId[];
export type Status1 = "open" | "closing" | "closed";
export type Disposition1 = ("true_positive" | "false_positive" | "duplicate" | "no_further_action" | "referred") | null;
export type DispositionReason1 = string | null;
export type DecidedBy1 = string | null;
export type DecidedAt1 = string | null;
export type CloseProposedBy1 = string | null;
export type Citations = AlertCitation[];

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
 * corpus-wide resolution trigger). B14's "jump" opens a case of the jumper's own from the
 * alert; since L3.2 that case records no case it came from (ADR-144 Amendment 1), and the jump's
 * audit row names this one.
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
  close_proposed_by?: CloseProposedBy;
  close_proposed_at?: CloseProposedAt;
  severity?: Severity;
  team?: Team;
  routed_team?: RoutedTeam;
  suppressed_until?: SuppressedUntil;
  suppress_reason?: SuppressReason;
  suppressed_by?: SuppressedBy;
  citations?: Citations;
  [k: string]: unknown;
}
export interface Interval {
  valid_from: ValidFrom;
  valid_to?: ValidTo;
  [k: string]: unknown;
}
/**
 * ADR-146 Amendment 7: one of the things an alert cites that a reader may be cleared for or
 * not, apart from the rest of it: a screening alert's match on one list (the listed party and the
 * scored `SAME_AS` to it). The alert is shown to a reader who may read everything it rests on
 * outside its citations and at least one citation; each citation is shown only to a reader who
 * may read every node and link it names, and a hidden one is left out of the alert as served
 * (its words, its ids and how many there are), so the alert never says which lists, or how many,
 * a reader cannot see (rule 3).
 */
export interface AlertCitation {
  words: Words1;
  node_ids?: NodeIds;
  edge_ids?: EdgeIds1;
  status?: Status1;
  disposition?: Disposition1;
  disposition_reason?: DispositionReason1;
  decided_by?: DecidedBy1;
  decided_at?: DecidedAt1;
  close_proposed_by?: CloseProposedBy1;
  [k: string]: unknown;
}
