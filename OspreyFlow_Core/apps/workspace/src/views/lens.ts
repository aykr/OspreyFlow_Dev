// An opened view as the canvas shows it (the owner's ruling of 8 November 2026, ADR-144 Amendment 2:
// a read-only lens). A working set of its own, never joined to the case's delta stream, holding what
// the Conduit gave: the items this reader may see now, each already collapsed at the view's
// threshold, placed where the view keeps them. The case's own working set is left as it is.
import type { Edge, Node } from "../../../../packages/schemas/generated";
import type { DeltaSnapshot } from "../workingset/models";
import { createWorkingSet, type WorkingSet } from "../workingset/store";
import type { CaseViewOpened } from "./viewsApi";

export interface Lens {
  opened: CaseViewOpened;
  workingSet: WorkingSet;
}

export function buildLens(opened: CaseViewOpened): Lens {
  const workingSet = createWorkingSet();
  const snapshot: DeltaSnapshot = {
    seq: 0,
    op: "snapshot",
    nodes: opened.nodes as unknown as DeltaSnapshot["nodes"],
    edges: opened.edges as unknown as DeltaSnapshot["edges"],
  };
  workingSet.store.getState().applyDelta(snapshot);
  for (const [id, at] of Object.entries(opened.layout ?? {})) {
    if (!workingSet.graph.hasNode(id)) continue;
    workingSet.graph.setNodeAttribute(id, "x", at.x);
    workingSet.graph.setNodeAttribute(id, "y", at.y);
  }
  return { opened, workingSet };
}

/** The view's timeline window, in the timeline's own shape; `null` when it keeps none. */
export function lensWindow(opened: CaseViewOpened): { validFrom: string; validTo: string | null } | null {
  const window = opened.view.window;
  return window ? { validFrom: window.valid_from, validTo: window.valid_to ?? null } : null;
}

export type { Edge, Node };
