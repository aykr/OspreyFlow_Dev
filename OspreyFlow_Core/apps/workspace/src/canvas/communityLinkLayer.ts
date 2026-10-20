// The links between communities, drawn on a canvas of their own between Sigma's links and its nodes
// (ADR-119), so they pass under the nodes as links do. Each runs between the centres of its two
// communities, as wide as the number of links it stands for. Redrawn after every render; a
// community's centre is worked out again only when a node has moved or the communities changed.
import type Sigma from "sigma";

import { activePalette } from "../color/palette";
import { communityLinkWidth, type CommunityLink } from "./communityLinks";

const LAYER = "communityLinks";

export interface CommunityLinkState {
  /** Whether the links between communities are drawn now (`drawsCommunityLinks`). */
  active: boolean;
  /** Every node's community, or null while it is being worked out. */
  assignment: ReadonlyMap<string, number> | null;
  links: readonly CommunityLink[];
}

interface Graphish {
  forEachNode(callback: (node: string, attributes: { x?: number; y?: number }) => void): void;
  on(event: string, listener: () => void): unknown;
  removeListener(event: string, listener: () => void): unknown;
}

/** Puts the layer on `sigma` and returns what takes it off again. `state` is read at every draw. */
export function attachCommunityLinkLayer(sigma: Sigma, state: () => CommunityLinkState): () => void {
  // Sigma gives a canvas it makes only `position: absolute`; this one covers the stage and lets the
  // pointer through to the nodes and the stage beneath.
  const canvas = sigma.createCanvas(LAYER, {
    beforeLayer: "nodes",
    style: { top: "0", left: "0", width: "100%", height: "100%", pointerEvents: "none" },
  });
  const graph = sigma.getGraph() as unknown as Graphish;

  let centres: Map<number, { x: number; y: number }> | null = null;
  let centresFor: ReadonlyMap<string, number> | null = null;
  const moved = () => {
    centres = null;
  };
  for (const event of ["nodeAttributesUpdated", "eachNodeAttributesUpdated", "nodeAdded", "nodeDropped", "cleared"]) {
    graph.on(event, moved);
  }

  const centresOf = (assignment: ReadonlyMap<string, number>) => {
    if (centres && centresFor === assignment) return centres;
    const sums = new Map<number, { x: number; y: number; n: number }>();
    graph.forEachNode((node, attributes) => {
      const community = assignment.get(node);
      if (community === undefined) return;
      const sum = sums.get(community) ?? { x: 0, y: 0, n: 0 };
      sum.x += attributes.x ?? 0;
      sum.y += attributes.y ?? 0;
      sum.n += 1;
      sums.set(community, sum);
    });
    centres = new Map([...sums].map(([community, { x, y, n }]) => [community, { x: x / n, y: y / n }]));
    centresFor = assignment;
    return centres;
  };

  const draw = () => {
    const ratio = globalThis.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
    }
    const context = canvas.getContext("2d");
    if (!context) return;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);
    const { active, assignment, links } = state();
    if (!active || !assignment || links.length === 0) return;
    const at = centresOf(assignment);
    context.strokeStyle = activePalette().textSecondary;
    context.globalAlpha = 0.55;
    context.lineCap = "round";
    for (const link of links) {
      const a = at.get(link.a);
      const b = at.get(link.b);
      if (!a || !b) continue;
      const from = sigma.graphToViewport(a);
      const to = sigma.graphToViewport(b);
      context.lineWidth = communityLinkWidth(link.count);
      context.beginPath();
      context.moveTo(from.x, from.y);
      context.lineTo(to.x, to.y);
      context.stroke();
    }
    context.globalAlpha = 1;
  };

  sigma.on("afterRender", draw);
  return () => {
    sigma.removeListener("afterRender", draw);
    for (const event of ["nodeAttributesUpdated", "eachNodeAttributesUpdated", "nodeAdded", "nodeDropped", "cleared"]) {
      graph.removeListener(event, moved);
    }
    sigma.killLayer(LAYER);
  };
}
