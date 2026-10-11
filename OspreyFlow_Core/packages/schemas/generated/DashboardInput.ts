// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
export type Clearance = string;
export type OrgUnit = string;

/**
 * A dashboard identity to register: a name, and the clearance and unit it reads with — no
 * higher than the registering administrator's own clearance.
 */
export interface DashboardInput {
  name: Name;
  clearance: Clearance;
  org_unit: OrgUnit;
  [k: string]: unknown;
}
