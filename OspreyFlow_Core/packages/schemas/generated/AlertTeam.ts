// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RoleId = string;
export type DisplayName = string;
export type Lead = boolean;
export type Members = string[];

/**
 * A team a rule's alerts may go to (ADR-146 decision 8), and for its lead today the members
 * of it who hold the case, whom its alerts may be given to (Amendment 1).
 */
export interface AlertTeam {
  role_id: RoleId;
  display_name: DisplayName;
  lead?: Lead;
  members?: Members;
  [k: string]: unknown;
}
