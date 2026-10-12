// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Username = string;
export type Name = string;
export type Enabled = boolean;
export type Roles = string[];
export type Clearance = string | null;
export type OrgUnit = string | null;
export type Email = string | null;
export type ReceivableHandlingCodes = string[];
export type MustSetPassword = boolean;
export type Delivery = "email" | "one_time_code";
export type OneTimeCode = string | null;

/**
 * How the person signs in next: by the identity provider's own emailed link, or by the one-time
 * code in this answer — shown once, never stored by OspreyFlow, changed at first sign-in.
 */
export interface SignInDelivery {
  person: PersonAccount;
  delivery: Delivery;
  one_time_code?: OneTimeCode;
  [k: string]: unknown;
}
export interface PersonAccount {
  id: Id;
  username: Username;
  name: Name;
  enabled: Enabled;
  roles: Roles;
  clearance?: Clearance;
  org_unit?: OrgUnit;
  email?: Email;
  receivable_handling_codes?: ReceivableHandlingCodes;
  must_set_password?: MustSetPassword;
  [k: string]: unknown;
}
