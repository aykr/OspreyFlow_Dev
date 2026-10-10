// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Typology = "document_verification";

/**
 * Component 7: a new customer with no valid verifying document — none, or each one expired
 * or marked fraudulent.
 */
export interface DocumentVerificationParams {
  typology?: Typology;
  [k: string]: unknown;
}
