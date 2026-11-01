// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Kind = "trend" | "assessment" | "entity" | "note" | "alert";
export type Marking = string;
export type AddedBy = string;
export type AddedAt = string;
export type TrendId = string | null;
export type Title = string;
export type Source = "events" | "alerts";
/**
 * @maxItems 12
 */
export type EventTypes =
  | []
  | [string]
  | [string, string]
  | [string, string, string]
  | [string, string, string, string]
  | [string, string, string, string, string]
  | [string, string, string, string, string, string]
  | [string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string];
export type TrendMeasure = "count" | "sum";
export type MeasureField = string | null;
export type TrendInterval = "week" | "month";
export type Weeks = number;
export type GroupBy = string | null;
/**
 * @maxItems 5
 */
export type Filters =
  | []
  | [TrendFilter]
  | [TrendFilter, TrendFilter]
  | [TrendFilter, TrendFilter, TrendFilter]
  | [TrendFilter, TrendFilter, TrendFilter, TrendFilter]
  | [TrendFilter, TrendFilter, TrendFilter, TrendFilter, TrendFilter];
export type Field = string;
export type Value = string;
export type TrendInterval1 = "week" | "month";
export type TrendMeasure1 = "count" | "sum";
export type PeriodStart = string;
export type Series = string | null;
export type Value1 = number;
export type Points = TrendPoint[];
export type Series1 = string[];
export type Total = number;
export type Events = number;
export type Unvalued = number;
export type Classifications = string[];
export type Classification = string;
export type HandlingCode = string;
export type OwningUnit = string;
export type Originator = string;
export type Handlings = CountedHandling[];
export type AsOf = string;
export type WindowStart = string;
export type Marking1 = string | null;
export type JudgementId = string;
export type Statement = string;
export type ProbabilityBand = string;
export type Supporting = string[];
export type Contradicting = string[];
export type Author = string;
export type CreatedAt = string;
export type NodeId = string;
export type EntityType = string;
export type Name = string;
export type Caption = string;
export type Note = string | null;
export type AlertId = string;
export type Kind1 = "typology" | "hotlist" | "monitor";
export type Severity = "low" | "medium" | "high";
export type Explanation = string;
export type Typology = string | null;
export type HotlistEntry = string | null;
export type ValidFrom = string;
export type ValidTo = string | null;
export type RaisedAt = string;
export type NodeId1 = string;
export type EntityType1 = string;
export type Name1 = string;
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
export type Status = "open" | "claimed" | "closed";
export type Outcome = ("true_positive" | "false_positive") | null;
export type Reason = string | null;
export type Match = "inferred" | "confirmed";
export type NodeIds = string[];
export type ReplacedAt = string | null;
export type ReplacedBy = string | null;

/**
 * One item as a reader gets it. It carries no position: the order of the list is the order, so
 * a withheld item leaves no gap that says where it was.
 */
export interface PackItem {
  id: Id;
  kind: Kind;
  marking: Marking;
  added_by: AddedBy;
  added_at: AddedAt;
  trend_id?: TrendId;
  trend?: TrendFigures | null;
  assessment?: AssessmentSnapshot | null;
  entity?: EntitySnapshot | null;
  note?: Note;
  alert?: AlertSnapshot | null;
  replaced_at?: ReplacedAt;
  replaced_by?: ReplacedBy;
  [k: string]: unknown;
}
/**
 * A trend computed for the reader at `as_of` — never stored; a pack keeps a snapshot.
 */
export interface TrendFigures {
  definition: TrendDefinitionInput;
  result: TrendResult;
  as_of: AsOf;
  window_start: WindowStart;
  marking?: Marking1;
  [k: string]: unknown;
}
export interface TrendDefinitionInput {
  title: Title;
  source?: Source;
  event_types?: EventTypes;
  measure?: TrendMeasure;
  measure_field?: MeasureField;
  interval?: TrendInterval;
  weeks?: Weeks;
  group_by?: GroupBy;
  filters?: Filters;
  [k: string]: unknown;
}
/**
 * Only events whose property equals this value.
 */
export interface TrendFilter {
  field: Field;
  value: Value;
  [k: string]: unknown;
}
export interface TrendResult {
  interval: TrendInterval1;
  measure: TrendMeasure1;
  points: Points;
  series?: Series1;
  total: Total;
  events: Events;
  unvalued?: Unvalued;
  classifications?: Classifications;
  handlings?: Handlings;
  [k: string]: unknown;
}
export interface TrendPoint {
  period_start: PeriodStart;
  series?: Series;
  value: Value1;
  [k: string]: unknown;
}
/**
 * One distinct handling among the events a trend counted: what a reader of a frozen snapshot
 * must be able to view (ADR-113 Amendment 1) — the restricted code and its units, not only the
 * classification.
 */
export interface CountedHandling {
  classification: Classification;
  handling_code: HandlingCode;
  owning_unit: OwningUnit;
  originator: Originator;
  [k: string]: unknown;
}
/**
 * A judgement as it was written when it was added — later edits to the judgement do not reach
 * the pack.
 */
export interface AssessmentSnapshot {
  judgement_id: JudgementId;
  statement: Statement;
  probability_band: ProbabilityBand;
  supporting?: Supporting;
  contradicting?: Contradicting;
  author: Author;
  created_at: CreatedAt;
  [k: string]: unknown;
}
export interface EntitySnapshot {
  node_id: NodeId;
  entity_type: EntityType;
  name: Name;
  caption: Caption;
  [k: string]: unknown;
}
/**
 * An alert as its adder read it (ADR-134 decision 1): its explanation, the entity it matched,
 * its evidence, and its outcome and reason if it was closed. Frozen when added, like every item;
 * `status` says what it was then, so an alert still open says so.
 */
export interface AlertSnapshot {
  alert_id: AlertId;
  kind: Kind1;
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
  node_id: NodeId1;
  entity_type: EntityType1;
  name: Name1;
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
