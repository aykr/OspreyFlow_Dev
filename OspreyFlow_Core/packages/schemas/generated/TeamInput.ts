// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DisplayName = string;
export type Mailbox = string;

/**
 * *Make this role a team* (ADR-112 Amendment 5 decision 3): a display name and a contact
 * mailbox, a distribution list that is a contact, never a sign-in.
 */
export interface TeamInput {
  display_name: DisplayName;
  mailbox: Mailbox;
  [k: string]: unknown;
}
