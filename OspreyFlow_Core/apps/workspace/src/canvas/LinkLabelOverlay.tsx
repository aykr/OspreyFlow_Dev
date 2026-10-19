import { useEffect, useState, type RefObject } from "react";
import type Sigma from "sigma";

import type { WorkingSetEdgeAttributes, WorkingSetNodeAttributes } from "../workingset/store";
import { LINK_LABEL_FONT, LINK_LABEL_SIZE } from "./labelStyle";

export interface PlacedLinkLabel {
  x: number;
  y: number;
  /** Degrees, always between -90 and 90, so the text reads left to right. */
  angle: number;
}

/** Where a link's label goes: at the middle of the link, along it, turned so it never reads upside
 * down, and moved off the line to the side above the text. Sigma 4 draws a link's label along the
 * link from its source to its target, so one pointing left read upside down; Sigma 3 turned it. */
export function placeLinkLabel(
  a: { x: number; y: number },
  b: { x: number; y: number },
  lineWidth: number,
): PlacedLinkLabel {
  let angle = (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI;
  if (angle > 90) angle -= 180;
  if (angle < -90) angle += 180;
  // Above the text is the side its tops face: perpendicular to the line, on screen.
  const away = lineWidth / 2 + 2 + LINK_LABEL_SIZE / 2;
  const turn = (angle * Math.PI) / 180;
  return {
    x: (a.x + b.x) / 2 + Math.sin(turn) * away,
    y: (a.y + b.y) / 2 - Math.cos(turn) * away,
    angle,
  };
}

export interface LinkLabelOverlayProps {
  sigmaRef: RefObject<Sigma<WorkingSetNodeAttributes, WorkingSetEdgeAttributes> | null>;
  /** The links that have a label to show now, kept by the edge reducer. */
  labelledRef: RefObject<ReadonlySet<string>>;
}

/** The links' labels, in a DOM overlay redrawn whenever the canvas draws (spec 02 §1: labels are
 * DOM overlays positioned from the camera). Only a picture: they let every click through, take no
 * focus, and are hidden from a screen reader, since a link's type and count are read in the
 * Inspector. They are left out while the camera moves, as the links are (`hideEdgesOnMove`). */
export function LinkLabelOverlay({ sigmaRef, labelledRef }: LinkLabelOverlayProps) {
  const [, redraw] = useState(0);
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

  const labelled = labelledRef.current;
  if (!sigma || !labelled || labelled.size === 0) return null;
  const state = sigma.getGraphState();
  if (state.isPanning || state.isZooming) return null;
  const graph = sigma.getGraph();
  const drawn: { id: string; text: string; at: PlacedLinkLabel }[] = [];
  for (const id of labelled) {
    if (!graph.hasEdge(id)) continue;
    const shown = sigma.getEdgeDisplayData(id);
    if (!shown || shown.visibility === "hidden" || !shown.label) continue;
    const end = (node: string) =>
      sigma.graphToViewport({ x: graph.getNodeAttribute(node, "x") ?? 0, y: graph.getNodeAttribute(node, "y") ?? 0 });
    drawn.push({ id, text: shown.label, at: placeLinkLabel(end(graph.source(id)), end(graph.target(id)), shown.size) });
  }
  if (drawn.length === 0) return null;

  return (
    <div aria-hidden="true" style={{ position: "absolute", inset: 0, pointerEvents: "none", zIndex: 1, overflow: "hidden" }}>
      {drawn.map(({ id, text, at }) => (
        <span
          key={id}
          style={{
            position: "absolute",
            left: at.x,
            top: at.y,
            transform: `translate(-50%, -50%) rotate(${at.angle}deg)`,
            whiteSpace: "nowrap",
            font: `${LINK_LABEL_SIZE}px ${LINK_LABEL_FONT}`,
            color: "var(--text-primary)",
            pointerEvents: "none",
          }}
        >
          {text}
        </span>
      ))}
    </div>
  );
}
