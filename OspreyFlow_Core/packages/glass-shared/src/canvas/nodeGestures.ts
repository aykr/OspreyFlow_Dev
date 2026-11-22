/**
 * What a click on a node does, kept apart from the canvas so each gesture can be tested without
 * a WebGL context. Seen 3 October 2026, in the running Glass: the browser's own right-click menu
 * opened over the Glass menu; a left click seemed to do nothing (expansion was reachable only
 * through the right-click menu); and a count that could not be fetched sat as `(…)` for ever.
 */

export interface MenuRequest {
  x: number;
  y: number;
  nodeId: string;
  layout: "radial" | "list";
}

/**
 * A right-click on a node. Calls `preventDefault` on the original event: Sigma's own
 * `preventSigmaDefault` only stops Sigma's behaviour, so without this Chrome's "Look up / Copy /
 * Translate" menu opens on top of ours. Opens the list layout, not the ring: the ring is 96 px
 * across and entries such as `COMMUNICATED_WITH (…)` are wider, so they overlapped.
 */
export function menuRequestForRightClick(
  original: MouseEvent,
  nodeId: string,
): MenuRequest {
  original.preventDefault();
  return { x: original.clientX, y: original.clientY, nodeId, layout: "list" };
}

interface SigmaMouseEvent {
  original: MouseEvent | TouchEvent;
  preventSigmaDefault: () => void;
}

/**
 * A double-click on a node brings in its neighbours, across every edge type. Sigma's own default
 * for a double-click is to zoom the camera in, so that is switched off here.
 */
export function expandOnDoubleClick(
  event: SigmaMouseEvent,
  nodeId: string,
  expand: (nodeId: string, x: number, y: number) => void,
): void {
  event.preventSigmaDefault();
  event.original.preventDefault();
  // A touch has no pointer position to anchor an error message on; the canvas's own corner will do.
  const at =
    event.original instanceof MouseEvent
      ? event.original
      : { clientX: 0, clientY: 0 };
  expand(nodeId, at.clientX, at.clientY);
}

export type PreviewCount = number | "unavailable";

/**
 * The figure the menu shows against an action. `candidateNodeCount` is the working set's size
 * *after* the expansion, so what an analyst wants (how many this adds) is the difference. A call
 * that failed is `"unavailable"`, said as such, and never left as an ellipsis that looks as if it
 * were still loading.
 */
export function previewCountFrom(
  reply: { ok: true; candidateNodeCount: number } | { ok: false },
  currentOrder: number,
): PreviewCount {
  if (!reply.ok) return "unavailable";
  return Math.max(0, reply.candidateNodeCount - currentOrder);
}
