import { useEffect, useState, type RefObject } from "react";
import type Sigma from "sigma";

import type { WorkingSetEdgeAttributes, WorkingSetNodeAttributes } from "../workingset/store";

export interface Bubble {
  id: string;
  label: string;
  count: number;
  /** The centre and radius, in graph units. */
  x: number;
  y: number;
  r: number;
}

export interface BubbleOverlayProps {
  sigmaRef: RefObject<Sigma<WorkingSetNodeAttributes, WorkingSetEdgeAttributes> | null>;
  /** The bubbles now to draw. Called on every redraw, so they follow the layout as it settles. */
  getBubbles: () => readonly Bubble[];
}

/** A circle round each group in the Clustered bubbles layout, with its name and size, in a DOM
 * overlay over the canvas. The circles let pointer events through, so the nodes inside stay
 * clickable. They are drawn for the eye only; nothing in them can be pressed. */
export function BubbleOverlay({ sigmaRef, getBubbles }: BubbleOverlayProps) {
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
  const bubbles = getBubbles();
  if (bubbles.length === 0) return null;

  return (
    <div
      data-testid="bubble-overlay"
      style={{ position: "absolute", inset: 0, pointerEvents: "none", zIndex: 1 }}
    >
      <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}>
        {bubbles.map((bubble) => {
          const centre = sigma.graphToViewport({ x: bubble.x, y: bubble.y });
          const edge = sigma.graphToViewport({ x: bubble.x + bubble.r, y: bubble.y });
          const radius = Math.hypot(edge.x - centre.x, edge.y - centre.y);
          return (
            <g key={bubble.id}>
              <circle
                cx={centre.x}
                cy={centre.y}
                r={radius}
                fill="var(--brass)"
                fillOpacity={0.06}
                stroke="var(--brass)"
                strokeOpacity={0.5}
                strokeWidth={1.25}
              />
              <text
                x={centre.x}
                y={centre.y - radius - 6}
                textAnchor="middle"
                fontSize={11}
                fill="var(--text-secondary)"
              >
                {`${bubble.label} (${bubble.count})`}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
