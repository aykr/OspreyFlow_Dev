// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type HasEvents = boolean;
export type InvestigationId = string;
export type Name = string | null;
export type HeldBy = CaseEventHolder[];

/**
 * Whether a case holds events this reader may count, and — when it holds none — which other
 * cases the reader can open read one of its datasets and do (ADR-099 Amendment 9). Events stay
 * with the case they were loaded into (decision 7); this only says where they are. A case the
 * reader cannot open is never named, and an event they may not see makes no case a holder.
 */
export interface CaseEvents {
  has_events: HasEvents;
  held_by?: HeldBy;
  [k: string]: unknown;
}
export interface CaseEventHolder {
  investigation_id: InvestigationId;
  name?: Name;
  [k: string]: unknown;
}
