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
export type Held = number;
export type Released = number;
export type Rejected = number;
export type Customers = number;
export type Verified = number;
export type Unverified = number;
export type ByBand = ReportCount[];

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
  held?: HeldFigures | null;
  kyc: KycFigures;
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
