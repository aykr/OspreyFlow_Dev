// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type Name = string;
export type Status = "verified" | "unverified";
export type Title = string | null;
export type DocumentKind = string | null;
export type ExpiresOn = string | null;
export type State = "valid" | "expired" | "fraudulent";
export type Documents = KycDocument[];
export type RiskScore = number;
export type RiskBand = "low" | "medium" | "high";
export type Factor = string;
export type Weight = number;
export type Words = string;
export type Factors = RiskFactor[];
export type AssessedOn = string;

/**
 * A customer's KYC status and baseline risk assessment (ADR-109 phase F, rulings 7 and 10):
 * computed at each read, as the reader reads the graph, never stored. `verified` while at least
 * one verifying document is valid — so an expiry or a fraud mark downgrades it the moment it
 * applies, with nothing written.
 */
export interface KycStatus {
  node_id: NodeId;
  name: Name;
  status: Status;
  documents?: Documents;
  risk_score?: RiskScore;
  risk_band?: RiskBand;
  factors?: Factors;
  assessed_on: AssessedOn;
  [k: string]: unknown;
}
/**
 * A document verifying a customer, and whether it still does.
 */
export interface KycDocument {
  node_id: NodeId;
  title?: Title;
  document_kind?: DocumentKind;
  expires_on?: ExpiresOn;
  state: State;
  [k: string]: unknown;
}
/**
 * One reason a customer's baseline risk is what it is, with its weight and its words.
 */
export interface RiskFactor {
  factor: Factor;
  weight: Weight;
  words: Words;
  [k: string]: unknown;
}
