import { useEffect, useState, type RefObject } from "react";
import type Sigma from "sigma";

import type { WorkingSetEdgeAttributes, WorkingSetNodeAttributes } from "../workingset/store";

export interface JudgementBadgeOverlayProps {
  sigmaRef: RefObject<Sigma<WorkingSetNodeAttributes, WorkingSetEdgeAttributes> | null>;
  /** How many judgements rest on each node; a node absent from the map has none. */
  counts: ReadonlyMap<string, number>;
  /** Where a node is drawn now, in pixels over the canvas, or null if it is not drawn. */
  positionOf: (nodeId: string) => { x: number; y: number } | null;
}

/** A small count up and to the right of each node that has judgements about it (ADR-070), in a DOM
 * overlay redrawn whenever the canvas draws. It is only a picture: it lets every click through and
 * takes no focus, because the judgements themselves are read in the Judgements tab, which a
 * keyboard reaches. */
export function JudgementBadgeOverlay({ sigmaRef, counts, positionOf }: JudgementBadgeOverlayProps) {
  const [, redraw] = useState(0);
  // The canvas is created after the first render of whatever holds this overlay, so wait for it.
  const [sigma, setSigma] = useState(sigmaRef.current);

  useEffect(() => {
    if (sigma) return;
    let frame = 0;
    const look = () => {
      if (sigmaRef.current) setSigma(sigmaRef.current);
      else frame = requestAnimationFrame(look);
    };
    frame = requestAnimationFrame(look);
    return () => cancelAnimationFrame(frame);
  }, [sigma, sigmaRef]);

  useEffect(() => {
    if (!sigma) return;
    const again = () => redraw((n) => n + 1);
    sigma.on("afterRender", again);
    again();
    return () => {
      sigma.removeListener("afterRender", again);
    };
  }, [sigma]);

  if (!sigma || counts.size === 0) return null;
  const badges: { id: string; count: number; x: number; y: number }[] = [];
  for (const [id, count] of counts) {
    const at = positionOf(id);
    if (at) badges.push({ id, count, x: at.x, y: at.y });
  }
  if (badges.length === 0) return null;

  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none", zIndex: 1, overflow: "hidden" }}>
      {badges.map((badge) => (
        <span
          key={badge.id}
          role="img"
          aria-label={`${badge.count} ${badge.count === 1 ? "judgement" : "judgements"}`}
          className="value"
          style={{
            position: "absolute",
            left: badge.x + 8,
            top: badge.y - 18,
            minWidth: 14,
            padding: "0 4px",
            borderRadius: 999,
            // A count, not an action: neutral, with a hairline (ADR-097, DESIGN.md §3.2).
            background: "var(--surface-raised)",
            color: "var(--text-primary)",
            border: "1px solid var(--border)",
            fontSize: 10,
            lineHeight: "14px",
            textAlign: "center",
            pointerEvents: "none",
          }}
        >
          {badge.count}
        </span>
      ))}
    </div>
  );
}
