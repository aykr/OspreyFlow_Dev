// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Admitted = boolean;
export type ChangedBy = string | null;
export type ChangedAt = string | null;

/**
 * `GET|PUT /v1/admin/sign-in/guests` (ADR-148 Amendment 17): whether this deployment admits
 * guest (B2B) accounts on Entra ID, off until an administrator of people turns it on; who last
 * changed it, and when (none, never).
 */
export interface GuestSignIn {
  admitted: Admitted;
  changed_by?: ChangedBy;
  changed_at?: ChangedAt;
  [k: string]: unknown;
}
