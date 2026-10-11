// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * @maxItems 64
 */
export type Roles = string[];

/**
 * A person's roles, set whole: the four roles, `right:<name>` grants, the old role names.
 */
export interface RolesInput {
  roles: Roles;
  [k: string]: unknown;
}
