// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Typology = "high_risk_jurisdiction";
/**
 * @minItems 1
 * @maxItems 250
 */
export type Jurisdictions = [string, ...string[]];

/**
 * A movement to or from an account held in a jurisdiction on the rule's own list. The list is
 * data in the rule — ISO 3166-1 alpha-2 codes, chosen by the rule's Author (a deployment's
 * policy, such as the FATF's lists, is theirs to enter) — and an account's jurisdiction is its
 * IBAN's country code (ISO 13616: the IBAN's first two letters).
 */
export interface HighRiskJurisdictionParams {
  typology?: Typology;
  jurisdictions: Jurisdictions;
  [k: string]: unknown;
}
