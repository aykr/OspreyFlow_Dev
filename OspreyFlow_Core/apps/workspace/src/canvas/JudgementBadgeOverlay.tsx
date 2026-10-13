import { useEffect, useState, type RefObject } from "react";
import type Sigma from "sigma";

import type { WorkingSetEdgeAttributes, WorkingSetNodeAttributes } from "../workingset/store";

export interface NodeBadge {
  /** What is drawn. */
  text: string;
  /** What it says to a screen reader. */
  label: string;
}

export interface NodeBadgeOverlayProps {
  sigmaRef: RefObject<Sigma<WorkingSetNodeAttributes, WorkingSetEdgeAttributes> | null>;
  /** The badge of each node that has one. */
  badges: ReadonlyMap<string, NodeBadge>;
  /** Where a node is drawn now, in pixels over the canvas, or null if it is not drawn. */
  positionOf: (nodeId: string) => { x: number; y: number } | null;
  /** Where the badge sits from the node's centre: its left edge and its top. */
  offset: { x: number; y: number };
}

/** Small badges beside nodes, in a DOM overlay redrawn whenever the canvas draws. They are only a
 * picture: they let every click through and take no focus, since what they say can be reached by
 * keyboard where it is kept (the judgements in the Judgements tab, a route's degrees in Find
 * connections). */
export function NodeBadgeOverlay({ sigmaRef, badges, positionOf, offset }: NodeBadgeOverlayProps) {
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

  if (!sigma || badges.size === 0) return null;
  const drawn: { id: string; badge: NodeBadge; x: number; y: number }[] = [];
  for (const [id, badge] of badges) {
    const at = positionOf(id);
    if (at) drawn.push({ id, badge, x: at.x, y: at.y });
  }
  if (drawn.length === 0) return null;

  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none", zIndex: 1, overflow: "hidden" }}>
      {drawn.map(({ id, badge, x, y }) => (
        <span
          key={id}
          role="img"
          aria-label={badge.label}
          className="value"
          style={{
            position: "absolute",
            left: x + offset.x,
            top: y + offset.y,
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
          {badge.text}
        </span>
      ))}
    </div>
  );
}

export interface JudgementBadgeOverlayProps {
  sigmaRef: NodeBadgeOverlayProps["sigmaRef"];
  /** How many judgements rest on each node; a node absent from the map has none. */
  counts: ReadonlyMap<string, number>;
  positionOf: NodeBadgeOverlayProps["positionOf"];
}

/** A small count up and to the right of each node that has judgements about it (ADR-070). */
export function JudgementBadgeOverlay({ sigmaRef, counts, positionOf }: JudgementBadgeOverlayProps) {
  const badges = new Map(
    [...counts].map(([id, count]) => [id, { text: String(count), label: `${count} ${count === 1 ? "judgement" : "judgements"}` }]),
  );
  return <NodeBadgeOverlay sigmaRef={sigmaRef} badges={badges} positionOf={positionOf} offset={{ x: 8, y: -18 }} />;
}
