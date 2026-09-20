import type { Path as GraphPath } from "../../../../packages/schemas/generated";
import { Button } from "../design/primitives/Button";
import { Popover } from "../design/primitives/Popover";

export interface PathfinderOverlayProps {
  x: number;
  y: number;
  paths: GraphPath[];
  activeIndex: number;
  onCycle: (direction: 1 | -1) => void;
  onClose: () => void;
}

/** Phase 7 Stage 5 — `docs/02_GLASS_FRONTEND.md` §3.1: "Select two nodes, get k-shortest paths;
 * paths render with the on-path node state... everything else dims to 32%." The same transient
 * `Popover` shape `ClusterExplainOverlay`/`EdgeInspectionOverlay` already use, anchored to the
 * triggering radial-menu position — not an Inspector tab, the same reasoning those two already
 * establish for their own class of result. `paths.length === 0` renders "No path found" rather
 * than nothing: `GraphPort.paths` searches the whole access-filtered corpus (`06_DECISIONS.md`
 * ADR-033's own "FIRST" reasoning), so this is the true, complete claim, not "not in your working
 * set" — worth saying plainly rather than leaving the analyst to wonder why nothing happened. */
export function PathfinderOverlay({ x, y, paths, activeIndex, onCycle, onClose }: PathfinderOverlayProps) {
  const active = paths[activeIndex];

  return (
    <Popover x={x} y={y} onClose={onClose}>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-6)", minWidth: 240 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <strong className="value">
            {active
              ? `Path ${activeIndex + 1} of ${paths.length} (${active.length} hop${active.length === 1 ? "" : "s"})`
              : "No path found"}
          </strong>
          <button
            type="button"
            className="icon-btn"
            aria-label="Close pathfinder result"
            onClick={onClose}
          >
            ×
          </button>
        </div>
        {paths.length > 1 && (
          <div style={{ display: "flex", gap: "var(--sp-6)" }}>
            <Button type="button" onClick={() => onCycle(-1)} aria-label="Previous path">
              ‹ Previous
            </Button>
            <Button type="button" onClick={() => onCycle(1)} aria-label="Next path">
              Next ›
            </Button>
          </div>
        )}
      </div>
    </Popover>
  );
}
