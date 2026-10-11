// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type ClientId = string;
export type AccountId = string;
export type Clearance = string | null;
export type OrgUnit = string | null;
export type LastPulled = string | null;
export type LastFailure = string | null;
export type FailedAt = string | null;
export type CasesPulled = number;

export interface DashboardIdentity {
  client_id: ClientId;
  account_id: AccountId;
  clearance?: Clearance;
  org_unit?: OrgUnit;
  last_pulled?: LastPulled;
  last_failure?: LastFailure;
  failed_at?: FailedAt;
  cases_pulled?: CasesPulled;
  [k: string]: unknown;
}
