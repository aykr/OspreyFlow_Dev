// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type InvestigationId = string;
export type Name = string;
export type Level = "viewer" | "editor" | "author";
export type Through = string | null;

/**
 * One of a person's case levels, as their row says it (R3): "Author of Kestrel"; `through`
 * names the team that gives it, when a team does.
 */
export interface PersonCaseLevel {
  investigation_id: InvestigationId;
  name: Name;
  level: Level;
  through?: Through;
  [k: string]: unknown;
}
