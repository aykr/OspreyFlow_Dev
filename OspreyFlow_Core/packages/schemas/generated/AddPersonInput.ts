// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * The person's Entra object id, in lower case
 */
export type ObjectId = string;

/**
 * A person added to Admin › People by their Entra object id, ahead of their first sign-in
 * (ADR-148 Amendment 8). Only on Entra ID sign-in; Graph gives the object id.
 */
export interface AddPersonInput {
  object_id: ObjectId;
  [k: string]: unknown;
}
