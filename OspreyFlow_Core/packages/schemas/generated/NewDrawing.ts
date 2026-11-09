// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DatasetId = string;
export type InvestigationId = string;
export type Id = string;
export type CaseId = string;
export type Name = string;
export type PrincipalId = string;
export type CreatedAt = string;
export type Shared = boolean;
export type Drawn = number;
export type Start = "blank" | "view" | "selection";

/**
 * `POST /v1/drawings`'s answer: the case made for the drawing and its board.
 */
export interface NewDrawing {
  dataset_id: DatasetId;
  investigation_id: InvestigationId;
  board: Board;
  [k: string]: unknown;
}
/**
 * A board as listed: never naming its items.
 */
export interface Board {
  id: Id;
  case_id: CaseId;
  name: Name;
  created_by: PrincipalId;
  created_at: CreatedAt;
  shared?: Shared;
  drawn?: Drawn;
  start?: Start;
  [k: string]: unknown;
}
