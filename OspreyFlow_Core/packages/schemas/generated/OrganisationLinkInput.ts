// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Subject = string;

/**
 * `POST /v1/admin/people/{user_id}/organisation-link`: the refused arrival to join to this
 * account, by the organisation's id for them (an `OrganisationArrival`'s `subject`).
 */
export interface OrganisationLinkInput {
  subject: Subject;
  [k: string]: unknown;
}
