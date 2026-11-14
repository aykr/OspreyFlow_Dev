// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Admitted = boolean;

/**
 * `PUT /v1/admin/sign-in/guests`: admit guests, or no longer.
 */
export interface GuestSignInInput {
  admitted: Admitted;
}
