// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type AlertId = string;
export type Kind = "typology" | "hotlist" | "monitor" | "analyst";
export type Severity = "low" | "medium" | "high";
export type Explanation = string;
export type Typology = string | null;
export type HotlistEntry = string | null;
export type ValidFrom = string;
export type ValidTo = string | null;
export type RaisedAt = string;
export type NodeId = string;
export type EntityType = string;
export type Name = string;
export type ListEntryOn = string | null;
export type Entities = AlertEntitySnapshot[];
export type EdgeId = string;
export type Type = string;
export type SourceName = string;
export type TargetName = string;
export type Links = AlertLinkSnapshot[];
export type OccurredAt = string;
export type Amount = number | null;
export type SourceName1 = string;
export type TargetName1 = string;
export type Transactions = AlertTransactionSnapshot[];
export type Status = "open" | "claimed" | "closing" | "closed";
export type Outcome = ("true_positive" | "false_positive" | "duplicate" | "no_further_action" | "referred") | null;
export type Reason = string | null;
export type Match = "inferred" | "confirmed";
export type NodeIds = string[];

/**
 * An alert as its adder read it (ADR-134 decision 1): its explanation, the entity it matched,
 * its evidence, and its outcome and reason if it was closed. Frozen when added, like every item;
 * `status` says what it was then, so an alert still open says so.
 */
export interface AlertSnapshot {
  alert_id: AlertId;
  kind: Kind;
  severity: Severity;
  explanation: Explanation;
  typology?: Typology;
  hotlist_entry?: HotlistEntry;
  window?: Interval | null;
  raised_at: RaisedAt;
  entities?: Entities;
  links?: Links;
  transactions?: Transactions;
  status: Status;
  outcome?: Outcome;
  reason?: Reason;
  match: Match;
  node_ids?: NodeIds;
  [k: string]: unknown;
}
export interface Interval {
  valid_from: ValidFrom;
  valid_to?: ValidTo;
  [k: string]: unknown;
}
/**
 * An entity an alert matched, named as its adder read it.
 */
export interface AlertEntitySnapshot {
  node_id: NodeId;
  entity_type: EntityType;
  name: Name;
  list_entry_on?: ListEntryOn;
  [k: string]: unknown;
}
/**
 * A link an alert cites as evidence.
 */
export interface AlertLinkSnapshot {
  edge_id: EdgeId;
  type: Type;
  source_name: SourceName;
  target_name: TargetName;
  [k: string]: unknown;
}
/**
 * A transaction an alert cites as evidence: when, how much, between whom.
 */
export interface AlertTransactionSnapshot {
  occurred_at: OccurredAt;
  amount?: Amount;
  source_name: SourceName1;
  target_name: TargetName1;
  [k: string]: unknown;
}
