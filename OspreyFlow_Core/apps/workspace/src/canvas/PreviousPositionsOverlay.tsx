// Where nodes were before the last re-layout, under reduced motion (`02_GLASS_FRONTEND.md` §3.4):
// the move is instant, so the animation's cue for what moved is replaced by a hollow mark at each
// node's previous place and a dashed line to where it is now. A picture only: it takes no clicks and
// no focus; the control that shows it is in the canvas toolbar's Show group.
import { useEffect, useState, type RefObject } from "react";
import type Sigma from "sigma";

import type { WorkingSetEdgeAttributes, WorkingSetNodeAttributes } from "../workingset/store";

export interface PreviousPosition {
  id: string;
  label: string;
  /** Where it was, in graph coordinates. */
  from: { x: number; y: number };
}

export interface PreviousPositionsOverlayProps {
  sigmaRef: RefObject<Sigma<WorkingSetNodeAttributes, WorkingSetEdgeAttributes> | null>;
  marks: readonly PreviousPosition[];
  /** Where a node is now, in graph coordinates, or null if it is no longer drawn. */
  currentOf: (nodeId: string) => { x: number; y: number } | null;
}

export function PreviousPositionsOverlay({ sigmaRef, marks, currentOf }: PreviousPositionsOverlayProps) {
  const [, redraw] = useState(0);
  const sigma = sigmaRef.current;
  useEffect(() => {
    if (!sigma) return;
    const again = () => redraw((n) => n + 1);
    sigma.on("afterRender", again);
    return () => {
      sigma.removeListener("afterRender", again);
    };
  }, [sigma]);
  if (!sigma || marks.length === 0) return null;
  return (
    <svg className="previous-positions">
      {marks.map((mark) => {
        const now = currentOf(mark.id);
        if (!now) return null;
        const a = sigma.graphToViewport(mark.from);
        const b = sigma.graphToViewport(now);
        return (
          <g key={mark.id} role="img" aria-label={`Where ${mark.label} was`}>
            <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} className="previous-positions__line" />
            <circle cx={a.x} cy={a.y} r={6} className="previous-positions__mark" />
          </g>
        );
      })}
    </svg>
  );
}
