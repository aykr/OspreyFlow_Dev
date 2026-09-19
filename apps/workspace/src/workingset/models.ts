// Hand-written mirror of `services/api/working_set/models.py`'s wire
// contract (`docs/03_CONDUIT_MIDDLEWARE.md` §3.2) and `services/api/
// history.py`'s `HistoryStepSummary`. Not part of the generated-TypeScript
// drift gate (`make schemas-check`) — that gate covers `packages/schemas/*`
// only, which is domain data, not the Conduit's own control-plane envelope
// shapes. Keeping this file in sync with the Python source is manual; a
// change to either side without the other is a real, if modest, drift risk
// worth naming rather than leaving implicit (`CLAUDE.md` rule 12's
// "invariants stated in prose that no test exercises" failure mode,
// applied to a cross-language contract instead of a domain invariant).
// `deltaClient.test.ts` exercises this file against the *real* Python
// WebSocket route, which is what actually proves the two sides still
// agree — not a hope that no one edits one side alone.

import type { Edge, Node } from "../../../../packages/schemas/generated";

// `NodeId`/`EdgeId` are plain `string` aliases in the generated Pydantic
// output too (`Node.ts`/`Edge.ts`) and aren't re-exported from the
// generated `index.ts` — using `string` directly here avoids depending on
// an identifier the drift gate doesn't actually promise to keep exported.
export interface NodePropertyUpdate {
  id: string;
  properties: Record<string, unknown>;
}

export interface DeltaAdd {
  seq: number;
  op: "add";
  nodes: Node[];
  edges: Edge[];
}

export interface DeltaUpdate {
  seq: number;
  op: "update";
  nodes: NodePropertyUpdate[];
}

export interface DeltaRemove {
  seq: number;
  op: "remove";
  node_ids: string[];
}

export interface DeltaReproject {
  seq: number;
  op: "reproject";
  reason: string;
  merged: number;
  split: number;
  affected: number;
  /** Phase 6a Stage 2 — every node whose cluster membership moved, mapped to its new cluster
   * id, mirroring `services/api/working_set/models.py`'s own field. Bounded by `affected`, never
   * the full working set. */
  affected_cluster_ids: Record<string, string>;
}

export interface DeltaNotice {
  seq: number;
  op: "notice";
  level: "info" | "warning";
  message: string;
  count: number;
}

export interface DeltaSnapshot {
  seq: number;
  op: "snapshot";
  nodes: Node[];
  edges: Edge[];
  filtered_count: number;
}

export type WorkingSetDelta =
  | DeltaAdd
  | DeltaUpdate
  | DeltaRemove
  | DeltaReproject
  | DeltaNotice
  | DeltaSnapshot;

export interface HistoryStepSummary {
  id: string;
  label: string;
  created_at: string;
  node_count: number;
  edge_count: number;
}
