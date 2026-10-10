// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Typology = "shared_attributes";
export type MinOthers = number;
/**
 * @minItems 1
 */
export type Kinds = ["msisdn" | "email" | "ip" | "handle", ...("msisdn" | "email" | "ip" | "handle")[]];

/**
 * Component 6's synthetic-identity check: a new customer's phone, email, IP address or handle
 * already used by at least `min_others` other customers.
 */
export interface SharedAttributesParams {
  typology?: Typology;
  min_others?: MinOthers;
  kinds?: Kinds;
  [k: string]: unknown;
}
