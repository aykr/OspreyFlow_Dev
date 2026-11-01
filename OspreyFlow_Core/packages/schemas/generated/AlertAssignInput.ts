// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Assignee = string;

/**
 * ADR-133 stage (a): giving an open or claimed alert to one member of the case.
 */
export interface AlertAssignInput {
  assignee: Assignee;
  [k: string]: unknown;
}
