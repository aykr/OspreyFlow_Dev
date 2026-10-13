import { NodeBadgeOverlay, type NodeBadgeOverlayProps } from "./JudgementBadgeOverlay";

export interface DegreeMarkOverlayProps {
  sigmaRef: NodeBadgeOverlayProps["sigmaRef"];
  /** Each marked node's degree from From (From itself is 0). */
  degrees: ReadonlyMap<string, number>;
  positionOf: NodeBadgeOverlayProps["positionOf"];
}

/** ADR-116 decision 4: a route put on the canvas from Find connections marks each of its nodes with
 * its degree from From, below and to the left of the node, clear of a judgement count. */
export function DegreeMarkOverlay({ sigmaRef, degrees, positionOf }: DegreeMarkOverlayProps) {
  const badges = new Map(
    [...degrees].map(([id, degree]) => [
      id,
      degree === 0
        ? { text: "From", label: "From" }
        : { text: `${degree}°`, label: `${degree} ${degree === 1 ? "degree" : "degrees"} from From` },
    ]),
  );
  return <NodeBadgeOverlay sigmaRef={sigmaRef} badges={badges} positionOf={positionOf} offset={{ x: -26, y: 6 }} />;
}
