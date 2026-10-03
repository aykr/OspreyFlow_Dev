// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type InvestigationId = string;
export type EdgeId = string;
export type PrincipalId = string;
export type Body = string;
export type CreatedAt = string;
export type EditedAt = string | null;
export type Mine = boolean;

/**
 * One analyst note on one link (`06_DECISIONS.md` ADR-075). Plain text, several per link,
 * kept in the investigation, shown to everyone who can see the link. Only its author changes or
 * removes it. `mine` is worked out per reader when the note is served and is never stored.
 */
export interface LinkNote {
  id: Id;
  investigation_id: InvestigationId;
  edge_id: EdgeId;
  author: PrincipalId;
  body: Body;
  created_at: CreatedAt;
  edited_at?: EditedAt;
  mine?: Mine;
  [k: string]: unknown;
}
