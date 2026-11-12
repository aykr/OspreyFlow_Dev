// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Clearance = string;
export type OrgUnit = string;
export type Roles = string[];
export type ReceivableHandlingCodes = string[];

/**
 * `GET /v1/me`: the signed-in person's own principal as the Conduit resolved it (ADR-148
 * Amendment 8), which the Glass shows and gates its places on: never a claim of its token. Their
 * own id (an Entra object id, or Keycloak's subject), clearance, unit, roles and handling codes;
 * nothing of anyone else's and no count.
 */
export interface MeResponse {
  id: Id;
  clearance: Clearance;
  org_unit: OrgUnit;
  roles: Roles;
  receivable_handling_codes: ReceivableHandlingCodes;
  [k: string]: unknown;
}
