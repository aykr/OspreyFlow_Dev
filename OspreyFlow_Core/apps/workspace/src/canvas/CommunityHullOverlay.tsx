import { useEffect, useState, type RefObject } from "react";
import type Sigma from "sigma";

import { activePalette } from "../color/palette";
import type { WorkingSetEdgeAttributes, WorkingSetNodeAttributes } from "../workingset/store";

export interface CommunityHullOverlayProps {
  sigmaRef: RefObject<Sigma<WorkingSetNodeAttributes, WorkingSetEdgeAttributes> | null>;
  /** Graph-space hull points per community, from `metrics/hulls.ts`'s pure
   * `computeCommunityHulls` — this component only converts to viewport space and draws. */
  hulls: ReadonlyMap<string, readonly [number, number][]>;
}

/** A DOM overlay anchored to Sigma's camera, the same established pattern
 * `EdgeInspectionOverlay`'s own docstring cites (ADR-002's "one honest caveat": some decoration is
 * genuinely easier in HTML/SVG than in the WebGL layer) — extended here from a static popover to a
 * polygon that must track the camera continuously while it pans/zooms, via `Camera`'s own
 * `"updated"` event rather than Sigma's full per-frame render loop, since a hull's vertices only
 * need to move when the *camera* changes, never on every WebGL frame.
 *
 * **Known simplification, disclosed rather than silent:** a container resize with no
 * accompanying camera change (e.g. the sidebar opening) does not itself re-trigger a redraw here,
 * the same class of gap `EdgeInspectionOverlay`'s own static `x`/`y` already has — real, and left
 * for a future pass rather than solved speculatively for a container-resize case this stage's own
 * plan did not name. */
export function CommunityHullOverlay({ sigmaRef, hulls }: CommunityHullOverlayProps) {
  const [, forceRedraw] = useState(0);

  useEffect(() => {
    const sigma = sigmaRef.current;
    if (!sigma) return;
    const camera = sigma.getCamera();
    const onUpdated = () => forceRedraw((n) => n + 1);
    camera.on("updated", onUpdated);
    return () => {
      camera.removeListener("updated", onUpdated);
    };
  }, [sigmaRef]);

  const sigma = sigmaRef.current;
  if (!sigma) return null;

  const communityIds = Array.from(hulls.keys());

  return (
    <svg style={{ position: "absolute", inset: 0, pointerEvents: "none", zIndex: 1 }}>
      {communityIds.map((communityId, index) => {
        const points = hulls.get(communityId);
        if (!points) return null;
        const palette = activePalette();
        const colour = palette.seq[index % palette.seq.length] ?? palette.channel("ochre");
        const viewportPoints = points
          .map(([x, y]) => {
            const p = sigma.graphToViewport({ x, y });
            return `${p.x},${p.y}`;
          })
          .join(" ");
        return (
          <polygon
            key={communityId}
            points={viewportPoints}
            fill={colour}
            fillOpacity={0.12}
            stroke={colour}
            strokeWidth={1.5}
            strokeOpacity={0.6}
          />
        );
      })}
    </svg>
  );
}
