// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Customers = number;
export type Verified = number;
export type Unverified = number;
export type Label = string;
export type Value = number;
export type ByBand = ReportCount[];

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
 * One labelled figure of a report (ADR-111): a fixed label and a count, never free text.
 */
export interface ReportCount {
  label: Label;
  value: Value;
  [k: string]: unknown;
}
