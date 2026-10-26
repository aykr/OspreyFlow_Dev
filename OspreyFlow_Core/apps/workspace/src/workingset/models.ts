// Hand-written mirror of `services/api/working_set/models.py`'s wire
// contract (`spec/03_CONDUIT_MIDDLEWARE.md` §3.2) and `services/api/
// history.py`'s `HistoryStepSummary`. Not part of the generated-TypeScript
// drift gate (`make schemas-check`) — that gate covers `packages/schemas/*`
// only, which is domain data, not the Conduit's own control-plane envelope
// shapes. Keeping this file in sync with the Python source is manual; a
// change to either side without the other is a real, if modest, drift risk
// worth naming rather than leaving implicit (the "invariant stated
// in prose that no test exercises" failure mode,
// applied to a cross-language contract instead of a domain invariant).
// `deltaClient.integration.test.ts` exercises this file against the *real* Python
// WebSocket route, which is what actually proves the two sides still
// agree — not a hope that no one edits one side alone.

import type { Edge, Node } from "../../../../packages/schemas/generated";

// `NodeId`/`EdgeId` are plain `string` aliases in the generated Pydantic
// output too (`Node.ts`/`Edge.ts`) and aren't re-exported from the
// generated `index.ts` — using `string` directly here avoids depending on
// an identifier the drift gate doesn't actually promise to keep exported.
export interface DeltaAdd {
  seq: number;
  op: "add";
  nodes: Node[];
  edges: Edge[];
}

/** What a removal looks like on the wire (`DeltaRemoveSent` in `models.py`, ADR-124 decision 4):
 * only the ids this reader may read, never the record the server keeps of what each was.
 * `edge_ids` takes a link off the canvas and leaves its ends; a node's removal still takes its
 * links with it. Absent from an older server's message, which means none. */
export interface DeltaRemove {
  seq: number;
  op: "remove";
  node_ids: string[];
  edge_ids?: string[];
}

/** One link stands in for another (ADR-080): a link was changed, so the old one leaves the view
 * and the new one arrives in the same step. Mirrors `DeltaReplaceEdge` in `models.py`. */
export interface DeltaReplaceEdge {
  seq: number;
  op: "replace_edge";
  old_edge_id: string;
  edge: Edge;
}

export interface DeltaReproject {
  seq: number;
  op: "reproject";
  reason: string;
  /** Phase 6a Stage 2 — every node whose cluster membership moved, mapped to its new cluster
   * id, mirroring `services/api/working_set/models.py`'s own field. Bounded by `affected`, never
   * the full working set. */
  affected_cluster_ids: Record<string, string>;
}

/** ADR-124 decision 1: the answer to each of the three resolution routes (a change of match
 * strictness, a manual same-as, a manual split): the delta every reader receives, and the figures
 * the change made, as the acting analyst's own view counts them. The figures are on this answer
 * only, never on the delta. Mirrors `ResolutionOutcome` in `models.py`. */
export interface ResolutionOutcome {
  delta: DeltaReproject;
  merged: number;
  split: number;
  affected: number;
}

export interface DeltaSnapshot {
  seq: number;
  op: "snapshot";
  nodes: Node[];
  edges: Edge[];
  /** ADR-124 decision 5: `true` when the case holds anything this reader may not view. Set only in
   * the full snapshot `sync` returns; `null` or absent everywhere else, and then the Glass keeps
   * what it last had. Never a number. */
  withheld?: boolean | null;
}

/** `LimitExceeded` in `models.py`: a refused request's own answer, and what `DeltaViewOverCap`
 * carries (ADR-124 decision 2). `would_be` is the reader's own figure for the cap named, never
 * anyone else's. */
export interface LimitExceeded {
  error: "limit_exceeded";
  cap_kind: "nodes" | "edges";
  cap: number;
  would_be: number;
  options: ["branch", "filter", "promote_to_batch"];
}

/** Sent in place of a snapshot or a delta when the reader's own view of the case is past a cap
 * (ADR-124 decision 2, Amendment 9). `seq` is the sequence number of what it replaces: it neither
 * advances the client's sequence nor trips its gap check. Mirrors `DeltaViewOverCap` in
 * `models.py`; not part of `WorkingSetDelta`, which is what changes the graph. */
export interface DeltaViewOverCap {
  seq: number;
  op: "view_over_cap";
  would_be: LimitExceeded;
}

export type WorkingSetDelta =
  | DeltaAdd
  | DeltaRemove
  | DeltaReplaceEdge
  | DeltaReproject
  | DeltaSnapshot;

export interface HistoryStepSummary {
  id: string;
  label: string;
  created_at: string;
  /** `false` for a step that holds no canvas snapshot (ADR-128: an edit to the case brief): it is
   * listed and never restored. Absent is restorable, as every step was before the field. */
  restorable?: boolean;
}

// `services/api/working_set/models.py`'s `PairwiseExplanation`/`ClusterExplanation` — the
// `GET .../resolution/explain/{cluster_id}` response, Phase 6a Stage 3 (B10). `score`/
// `model_version`/`comparison_vector` are `null` together for a manually-asserted edge — the
// Python side's own docstring: "a human decision, not a model score, has none of those to report."
export interface PairwiseExplanation {
  node_a: string;
  node_b: string;
  edge_type: "SAME_AS" | "NOT_SAME_AS";
  score: number | null;
  model_version: string | null;
  comparison_vector: Record<string, unknown> | null;
  manually_asserted: boolean;
  meets_threshold: boolean;
}

export interface ClusterExplanation {
  cluster_id: string;
  member_node_ids: string[];
  pairs: PairwiseExplanation[];
}
