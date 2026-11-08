// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type InvestigationId = string;
export type Name = string;
export type Level = "viewer" | "editor" | "author";
export type Through = string | null;
export type Levels = PersonCaseLevel[];

/**
 * `GET /v1/admin/people/rows` (R3): each person's case levels and the cases with no Author
 * (R1), only of cases in the administrator's own unit (ADR-052).
 */
export interface AdminPersonRow {
  id: Id;
  levels?: Levels;
  [k: string]: unknown;
}
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
