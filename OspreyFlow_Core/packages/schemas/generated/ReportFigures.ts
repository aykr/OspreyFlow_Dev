// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type PeriodWeeks = number;
export type AsOf = string;
export type GeneratedAt = string;
export type AlertsTotal = number;
export type WeekStart = string;
export type Typology = string;
export type Count = number;
export type AlertsByWeek = WeekCount[];
export type Label = string;
export type Value = number;
export type OpenByAge = ReportCount[];
export type Typology1 = string;
export type Open = number;
export type Claimed = number;
export type TruePositive = number;
export type FalsePositive = number;
export type Outcomes = OutcomeCount[];
export type WeekStart1 = string;
export type Label1 = string;
export type Typology2 = string;
export type Count1 = number;
export type RaisedByRule = LabelledWeekCount[];
export type ClosedByOutcome = LabelledWeekCount[];
export type TimeToClose = ReportCount[];
export type HotlistMatches = LabelledWeekCount[];
export type Held = number;
export type Released = number;
export type Rejected = number;
export type Customers = number;
export type Verified = number;
export type Unverified = number;
export type ByBand = ReportCount[];
/**
 * The five-class upper ontology. Closed: a deployment may add entity
 * types, never a sixth POLE class — `01_DOMAIN_MODEL.md` §1.1.
 */
export type PoleClass = "person" | "object" | "location" | "event" | "organisation";
export type Total = number;
export type EntityType = string;
export type Count2 = number;
export type Types = PoleTypeCount[];
export type Classes = PoleClassCount[];
export type Other = PoleTypeCount[];
export type Links = number;
export type CountedAt = string;

/**
 * A case's report (`06_DECISIONS.md` ADR-111): the Reports view and the dashboards' feed are
 * both this, from one computation, so they cannot disagree. Every figure is counted as its
 * reader — an alert the reader cannot see whole is in no total and no bucket (rule 3). Figures
 * only: labels, dates and numbers, never a name, an identifier or an alert's words.
 */
export interface ReportFigures {
  period_weeks: PeriodWeeks;
  as_of: AsOf;
  generated_at: GeneratedAt;
  alerts_total: AlertsTotal;
  alerts_by_week?: AlertsByWeek;
  open_by_age?: OpenByAge;
  outcomes?: Outcomes;
  monitoring?: MonitoringFigures;
  held?: HeldFigures | null;
  kyc?: KycFigures | null;
  pole?: PoleFigures | null;
  [k: string]: unknown;
}
/**
 * Alerts raised in one week (Monday to Sunday) of one typology, as the reader sees them.
 */
export interface WeekCount {
  week_start: WeekStart;
  typology: Typology;
  count: Count;
  [k: string]: unknown;
}
/**
 * One labelled figure of a report (ADR-111): a fixed label and a count, never free text.
 */
export interface ReportCount {
  label: Label;
  value: Value;
  [k: string]: unknown;
}
/**
 * Where one typology's alerts of the period stand: open, claimed, closed true or false.
 */
export interface OutcomeCount {
  typology: Typology1;
  open?: Open;
  claimed?: Claimed;
  true_positive?: TruePositive;
  false_positive?: FalsePositive;
  [k: string]: unknown;
}
/**
 * The monitoring dashboard's figures (ADR-134 decision 2): every kind of alert the one queue
 * holds for the reader — typology, hotlist and monitor — counted as them, per case. A hotlist
 * kept "only me" is in its owner's figures alone (the queue's own scope).
 */
export interface MonitoringFigures {
  raised_by_rule?: RaisedByRule;
  closed_by_outcome?: ClosedByOutcome;
  time_to_close?: TimeToClose;
  hotlist_matches?: HotlistMatches;
  [k: string]: unknown;
}
/**
 * A count in one week under a fixed label (ADR-134 decision 2): the rule group an alert was
 * raised by (`typology`, with its typology, `hotlists` or `monitors`), the outcome it was closed
 * with, or `hotlists` for a hotlist's matches. Never a rule's own name or an alert's words.
 */
export interface LabelledWeekCount {
  week_start: WeekStart1;
  label: Label1;
  typology?: Typology2;
  count: Count1;
  [k: string]: unknown;
}
/**
 * The case's held rows by what became of them — for Editors and above only, as the Held rows
 * tab is (ADR-111 decision 2).
 */
export interface HeldFigures {
  held: Held;
  released: Released;
  rejected: Rejected;
  [k: string]: unknown;
}
/**
 * The case's customers — people and organisations holding a verifying document — by KYC
 * status and risk band, each assessed as the reader at the moment of reading.
 */
export interface KycFigures {
  customers: Customers;
  verified: Verified;
  unverified: Unverified;
  by_band?: ByBand;
  [k: string]: unknown;
}
/**
 * The POLE summary of a case (ADR-126 decision 4), from the kept per-access-class counts the
 * Explore page reads: the reader's own, for the case's datasets, never a second count.
 *
 * `classes` is always the five classes in the order person, object, location, event,
 * organisation. `other` holds stored types the current ontology does not know, so no node
 * vanishes from the figures. `links` counts links of every type that is not `system`, a type the
 * ontology does not know included. `Alert` is in no figure: alerts are the Figures tab's own
 * subject. `counted_at` is when the kept counts were computed.
 */
export interface PoleFigures {
  classes: Classes;
  other?: Other;
  links: Links;
  counted_at: CountedAt;
  [k: string]: unknown;
}
/**
 * One POLE class: its total, and its types largest first, then by name, with no zero rows.
 */
export interface PoleClassCount {
  pole_class: PoleClass;
  total: Total;
  types?: Types;
  [k: string]: unknown;
}
/**
 * How many nodes of one entity type the reader can see (ADR-126 decision 4). `entity_type` is
 * a closed ontology type name, never an entity's own text.
 */
export interface PoleTypeCount {
  entity_type: EntityType;
  count: Count2;
  [k: string]: unknown;
}
