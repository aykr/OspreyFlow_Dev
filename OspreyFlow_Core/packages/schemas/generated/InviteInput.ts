// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Clearance = string;
export type OrgUnit = string;
export type ReceivableHandlingCodes = string[];
export type Username = string;
export type FirstName = string;
export type LastName = string;
export type Email = string | null;
/**
 * @maxItems 64
 */
export type Roles = string[];

/**
 * A new person (ADR-114 Amendment 5): signed in by an emailed link when the deployment has a
 * mail server, else by a one-time code shown once to the administrator.
 */
export interface InviteInput {
  clearance: Clearance;
  org_unit: OrgUnit;
  receivable_handling_codes?: ReceivableHandlingCodes;
  username: Username;
  first_name?: FirstName;
  last_name?: LastName;
  email?: Email;
  roles?: Roles;
  [k: string]: unknown;
}
