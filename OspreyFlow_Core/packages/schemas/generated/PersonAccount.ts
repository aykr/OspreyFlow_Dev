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
