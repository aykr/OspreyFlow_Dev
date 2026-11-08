// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
export type Start = "blank" | "view" | "selection";
export type ViewId = string | null;
export type NodeIds = NodeId[] | null;
export type NodeId = string;

/**
 * *New drawing board* in a case: blank, from a view (its loaded items as live references),
 * or from a selection on the canvas.
 */
export interface BoardInput {
  name: Name;
  start?: Start;
  view_id?: ViewId;
  node_ids?: NodeIds;
}
