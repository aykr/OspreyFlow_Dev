// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * @minItems 1
 */
export type Cases = [CaseWhenCase, ...CaseWhenCase[]];
export type Equals = string;
export type Then = string;
export type Otherwise = string | null;

export interface CaseWhenSettings {
  cases: Cases;
  otherwise?: Otherwise;
}
export interface CaseWhenCase {
  equals: Equals;
  then: Then;
}
