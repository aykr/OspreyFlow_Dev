// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Clearance = string | null;
export type OrgUnit = string | null;
export type ReceivableHandlingCodes = string[] | null;

/**
 * Access for a person already here (`PUT /v1/admin/people/{id}/access`). On Keycloak, clearance
 * and unit, and the codes (none when not given), as `AccessInput`. On Entra ID with the
 * administrator fallback (ADR-148 Amendment 15), only the values this deployment sets: one not
 * given is left as it is, and a value Entra sends is never given here.
 */
export interface PersonAccessInput {
  clearance?: Clearance;
  org_unit?: OrgUnit;
  receivable_handling_codes?: ReceivableHandlingCodes;
  [k: string]: unknown;
}
