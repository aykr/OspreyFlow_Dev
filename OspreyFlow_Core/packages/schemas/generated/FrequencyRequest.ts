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
export type EventIds = string[];
export type WeekdayHours = WeekdayHour[] | null;
export type Weekday = number;
export type Hour = number;
export type Scopes = string[];
export type EdgeIds1 = EdgeId[];
export type SpanDays = number;
export type AmountProperty = string | null;

/**
 * How often each of `filter.node_ids` took part in an event, for a rule's frequency or amount
 * condition (ADR-133 decision 1): "3 or more times in 7 days", "a total of an amount over X in
 * D days", "the first time ever".
 *
 * `filter.node_ids` are the subjects, at either end of an event; a caller passes only nodes it
 * has read as `principal` (a rule's subjects are matched as its own author). `filter.window`
 * bounds the events counted. Within it, for each subject, the most events — and the largest total
 * of `amount_property` — in any span of `span_days` days ending at one of its events. The access
 * step is in the query (rule 3): an event the principal may not see adds nothing to a count or a
 * total, and cannot be a subject's first.
 */
export interface FrequencyRequest {
  filter: EventFilter;
  span_days: SpanDays;
  amount_property?: AmountProperty;
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
  event_ids?: EventIds;
  value_filters?: ValueFilters;
  weekday_hours?: WeekdayHours;
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
 * One cell of the weekly view (ADR-130 decision 2): the weekday (0 = Monday) and the hour
 * (0-23), read in UTC, the numbering the `weekday_hour` histogram buckets by.
 */
export interface WeekdayHour {
  weekday: Weekday;
  hour: Hour;
  [k: string]: unknown;
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
  window?: Interval | null;
  [k: string]: unknown;
}
