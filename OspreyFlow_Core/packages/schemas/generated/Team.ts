// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RoleId = string;
export type DisplayName = string;
export type Mailbox = string;
export type Lead = string | null;
export type Cover = string | null;
export type CoverUntil = string | null;
export type ActingLead = string | null;
export type Id = string;
export type Name = string | null;
export type Members = TeamMember[];

/**
 * A team: a custom role's holders (the owner's L2.5 Q4 (a)), its lead, and a cover until a
 * date. `acting_lead` is the cover while the cover lasts, else the lead: the shape ADR-146
 * Amendment 1's queue tools read (rules' L2.10, `services/api/teams.py::acting_lead`).
 */
export interface Team {
  role_id: RoleId;
  display_name: DisplayName;
  mailbox: Mailbox;
  lead?: Lead;
  cover?: Cover;
  cover_until?: CoverUntil;
  acting_lead?: ActingLead;
  members?: Members;
  [k: string]: unknown;
}
export interface TeamMember {
  id: Id;
  name?: Name;
  [k: string]: unknown;
}
