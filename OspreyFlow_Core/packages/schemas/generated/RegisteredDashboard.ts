// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type ClientId = string;
export type AccountId = string;
export type Clearance = string | null;
export type OrgUnit = string | null;
export type Secret = string;

export interface RegisteredDashboard {
  dashboard: DashboardIdentity;
  secret: Secret;
  [k: string]: unknown;
}
export interface DashboardIdentity {
  client_id: ClientId;
  account_id: AccountId;
  clearance?: Clearance;
  org_unit?: OrgUnit;
  [k: string]: unknown;
}
