// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
/**
 * @maxItems 64
 */
export type Rights = string[];

/**
 * A custom role (ADR-112 Amendment 4): a name and a set of existing rights. Refused at the
 * route: a name already used, no rights, a right the giver does not hold, a forbidden pair
 * (ADR-145 decision 7), and a change that leaves no enabled person holding `manage_people`
 * (ADR-145 Amendment 5).
 */
export interface CustomRoleInput {
  name: Name;
  rights: Rights;
  [k: string]: unknown;
}
