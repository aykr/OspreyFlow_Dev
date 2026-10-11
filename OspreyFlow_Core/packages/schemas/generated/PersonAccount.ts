// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Username = string;
export type Name = string;
export type Enabled = boolean;
export type Roles = string[];
export type Clearance = string | null;
export type OrgUnit = string | null;

export interface PersonAccount {
  id: Id;
  username: Username;
  name: Name;
  enabled: Enabled;
  roles: Roles;
  clearance?: Clearance;
  org_unit?: OrgUnit;
  [k: string]: unknown;
}
