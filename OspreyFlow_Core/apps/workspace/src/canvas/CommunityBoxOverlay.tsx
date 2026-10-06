import { useEffect, useState, type RefObject } from "react";
import type Sigma from "sigma";

import type { WorkingSetEdgeAttributes, WorkingSetNodeAttributes } from "../workingset/store";
import type { Box } from "./communities";

export interface CommunityBoxOverlayProps {
  sigmaRef: RefObject<Sigma<WorkingSetNodeAttributes, WorkingSetEdgeAttributes> | null>;
  /** The boxes now to draw, in graph units. Called on every redraw, so the boxes follow the layout
   * as it settles as well as the camera. */
  getBoxes: () => readonly Box[];
  /** The analyst pressed a box's fold button. */
  onFold: (communityId: string) => void;
}

/** One rectangle round each group (ADR-066), in a DOM overlay over the canvas, redrawn whenever
 * the canvas draws. The rectangles let pointer events through, so the nodes beneath stay clickable;
 * each box has its own real button for folding that group, which a keyboard reaches with Tab. */
export function CommunityBoxOverlay({ sigmaRef, getBoxes, onFold }: CommunityBoxOverlayProps) {
  const [, redraw] = useState(0);

  useEffect(() => {
    const sigma = sigmaRef.current;
    if (!sigma) return;
    const again = () => redraw((n) => n + 1);
    sigma.on("afterRender", again);
    return () => {
      sigma.removeListener("afterRender", again);
    };
  }, [sigmaRef]);

  const sigma = sigmaRef.current;
  if (!sigma) return null;
  const boxes = getBoxes();
  if (boxes.length === 0) return null;

  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none", zIndex: 1 }}>
      <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}>
        {boxes.map((box) => {
          const a = sigma.graphToViewport({ x: box.x0, y: box.y0 });
          const b = sigma.graphToViewport({ x: box.x1, y: box.y1 });
          return (
            <rect
              key={box.id}
              x={Math.min(a.x, b.x)}
              y={Math.min(a.y, b.y)}
              width={Math.abs(b.x - a.x)}
              height={Math.abs(b.y - a.y)}
              rx={6}
              // A community is data, not the selection: a quiet hairline, no tint (ADR-097).
              fill="none"
              stroke="var(--border-strong)"
              strokeWidth={1.25}
              strokeDasharray="5 3"
            />
          );
        })}
      </svg>
      {boxes.map((box) => {
        const a = sigma.graphToViewport({ x: box.x0, y: box.y0 });
        const b = sigma.graphToViewport({ x: box.x1, y: box.y1 });
        return (
          <button
            key={box.id}
            type="button"
            className="radial-menu__item"
            aria-label={`Fold group of ${box.count} nodes`}
            title="Fold this group into one node"
            style={{
              position: "absolute",
              left: Math.min(a.x, b.x),
              top: Math.min(a.y, b.y) - 22,
              pointerEvents: "auto",
              padding: "0 6px",
              fontSize: 11,
              lineHeight: "18px",
            }}
            onClick={() => onFold(box.id)}
          >
            {`▣ ${box.count}`}
          </button>
        );
      })}
    </div>
  );
}
