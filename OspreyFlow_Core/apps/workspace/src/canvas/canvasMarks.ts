// The canvas's own marks, read by its tests and harnesses in place of the class names Sigma 3 gives its elements
// (slice WS4a; ADR-152 decision 9: Sigma 4 has no nodes canvas of Sigma 3's kind). A version-bound file (decision 6's table): it
// alone knows which of the renderer's layers is which, so the port to another Sigma changes this file and no test.
//
//   data-canvas-state   on the "Network canvas" application element:
//                         "mounted"  the renderer is constructed on the canvas, with its layers in the page (what the
//                                    budget gate's readiness has always meant: `perf/harness.tsx`'s `readyAt`, which
//                                    until WS4a waited for Sigma 3's nodes canvas to appear);
//                         "drawn"    the renderer has since finished a frame. On Sigma 3 that is not its first: the
//                                    constructor draws that one before anything can listen, so a canvas still
//                                    "mounted" has been drawn once already.
//                       Absent while no renderer is mounted (before the first, and after it is taken down).
//   data-canvas-layer   on each canvas the renderer draws on: "links", "link-labels", "nodes", "labels", "hovers",
//                       "hover-nodes", "pointer", and the canvas's own "community-links" (ADR-119).
//
// `canvasMarks.test.ts` holds both states and their taking off, without a browser. The developer repository's
// `tests/glass_trees/test_no_sigma_class_names_in_the_workspace.py` fails on any `sigma-` class name left in the
// workspace, so nothing finds the canvas any other way.
import type Sigma from "sigma";

export const CANVAS_STATE = "data-canvas-state";
export const CANVAS_LAYER = "data-canvas-layer";

export type CanvasState = "mounted" | "drawn";

/** Sigma 3's names for its layers (the `id` each canvas was made with), as the canvas names them. */
const LAYER_NAMES: Readonly<Record<string, string>> = {
  edges: "links",
  edgeLabels: "link-labels",
  nodes: "nodes",
  labels: "labels",
  hovers: "hovers",
  hoverNodes: "hover-nodes",
  mouse: "pointer",
  communityLinks: "community-links",
};

/** Names every canvas the renderer draws on now. Run again after a layer is added (`createCanvas`). */
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- any graph's renderer: only its canvases are read
export function markLayers(sigma: Sigma<any, any, any>): void {
  for (const [id, canvas] of Object.entries(sigma.getCanvases())) {
    canvas.setAttribute(CANVAS_LAYER, LAYER_NAMES[id] ?? id);
  }
}

/** Marks the application element with the renderer's state, or takes the mark off (`null`). */
export function markState(element: HTMLElement | null, state: CanvasState | null): void {
  if (!element) return;
  if (state === null) element.removeAttribute(CANVAS_STATE);
  else element.setAttribute(CANVAS_STATE, state);
}

/** Marks the element "mounted" now and "drawn" after the next frame the renderer finishes; returns what takes the
 * marks off (the renderer's teardown calls it). */
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- any graph's renderer: only its events are heard
export function markRenderer(element: HTMLElement | null, sigma: Sigma<any, any, any>): () => void {
  markLayers(sigma);
  markState(element, "mounted");
  const drawn = () => {
    markState(element, "drawn");
    sigma.removeListener("afterRender", drawn);
  };
  sigma.on("afterRender", drawn);
  return () => {
    sigma.removeListener("afterRender", drawn);
    markState(element, null);
  };
}
