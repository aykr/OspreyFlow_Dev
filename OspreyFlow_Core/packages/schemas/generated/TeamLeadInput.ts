// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Lead = string;

/**
 * Name a team's lead, or hand the role over (ADR-112 Amendment 5 decision 4): a member.
 */
export interface TeamLeadInput {
  lead: Lead;
  [k: string]: unknown;
}
