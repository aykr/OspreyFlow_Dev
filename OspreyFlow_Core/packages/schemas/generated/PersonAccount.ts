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
export type SystemAccount = boolean;
export type OrganisationLinked = boolean;
export type SignedIn = boolean;
export type AccessReadAt = string | null;

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
  system_account?: SystemAccount;
  organisation_linked?: OrganisationLinked;
  signed_in?: SignedIn;
  access_read_at?: AccessReadAt;
  [k: string]: unknown;
}
