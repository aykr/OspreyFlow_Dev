// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Subject = string;
export type ProviderUsername = string;
export type LastRefused = string;
export type Attempts = number;

/**
 * Someone the organisation's sign-in refused because an OspreyFlow account already holds their
 * email address (ADR-114 Amendment 33, "Step 28 (e)"), not yet joined to any account — read from
 * the identity provider's record of the refusal (ADR-112 Amendment 3 (b)).
 */
export interface OrganisationArrival {
  subject: Subject;
  provider_username: ProviderUsername;
  last_refused: LastRefused;
  attempts: Attempts;
  [k: string]: unknown;
}
