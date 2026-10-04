// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type InvestigationScope = string;
export type ValidFrom = string;
export type ValidTo = string | null;
export type NodeId = string;
export type NodeIds = NodeId[];
export type EdgeTypes = string[];
export type EdgeId = string;
export type EdgeIds = EdgeId[];
export type Scopes = string[];
export type EdgeIds1 = EdgeId[];
export type Offset = number;
export type Limit = number;

/**
 * A page of the events a filter describes, newest first (ADR-089): the emails behind one
 * link, read fifty at a time with the total said so the list can page.
 */
export interface EventListRequest {
  filter: EventFilter;
  offset?: Offset;
  limit?: Limit;
  [k: string]: unknown;
}
/**
 * Restricts the event population a method aggregates over. Every
 * field here is a predicate the adapter applies inside its own `WHERE`
 * clause before aggregation, never after (`03_CONDUIT_MIDDLEWARE.md`
 * §6) — `04_VAULT_BACKEND.md` §2 partitions the event tables by
 * `(investigation_scope, month)`, which is why scope is required rather
 * than optional.
 */
export interface EventFilter {
  investigation_scope: InvestigationScope;
  window?: Interval | null;
  node_ids?: NodeIds;
  edge_types?: EdgeTypes;
  edge_ids?: EdgeIds;
  value_filters?: ValueFilters;
  inherited?: InheritedEvents | null;
  [k: string]: unknown;
}
export interface Interval {
  valid_from: ValidFrom;
  valid_to?: ValidTo;
  [k: string]: unknown;
}
export interface ValueFilters {
  [k: string]: string[];
}
/**
 * The events a branch reads from the cases it came from (ADR-084 Amendment 2).
 *
 * A branch is a case of its own holding copies of some of its parent's links; the events behind
 * those links stay under the parent's scope. An event under one of `scopes` counts only if its
 * link is one of `edge_ids`, the links the branch holds, so a branch never reads its parent's
 * events for links it did not take. Every other `EventFilter` predicate and the access filter
 * apply to these events exactly as to the case's own. Set by the Conduit from the case's own
 * record and working set, never taken from a caller.
 */
export interface InheritedEvents {
  scopes?: Scopes;
  edge_ids?: EdgeIds1;
  [k: string]: unknown;
}
