// What the timeline dims (ADR-087). A node or a link with no event in the brush window is dimmed
// for as long as the window stands. Under playback the picture emerges: each node and link stays
// dimmed until the playhead passes its first event in the window, then lights up and stays lit, so
// the analyst watches the network appear in the order it did, with nothing moving or vanishing.
import type { FirstSeenResult } from "../../../../packages/schemas/generated";

/** When each node and link first appears in the window, by id, as ISO instants. */
export interface FirstSeen {
  nodes: Record<string, string>;
  edges: Record<string, string>;
}

/** The server's answer with its optional maps made definite. */
export function firstSeenFrom(result: FirstSeenResult): FirstSeen {
  return { nodes: result.nodes ?? {}, edges: result.edges ?? {} };
}

export interface Dimming {
  dimmedNodeIds: ReadonlySet<string>;
  dimmedEdgeIds: ReadonlySet<string>;
}

const NOTHING: Dimming = { dimmedNodeIds: new Set(), dimmedEdgeIds: new Set() };

/**
 * `firstSeen` is `null` when no filter is active (nothing is dimmed); `instant` is the playhead,
 * or `null` when the brush stands still. Ids are the nodes and links in the view.
 */
export function emergence(
  firstSeen: FirstSeen | null,
  instant: Date | null,
  nodeIds: readonly string[],
  edgeIds: readonly string[],
): Dimming {
  if (firstSeen === null) return NOTHING;
  const lit = (first: string | undefined) =>
    first !== undefined && (instant === null || new Date(first).getTime() <= instant.getTime());
  return {
    dimmedNodeIds: new Set(nodeIds.filter((id) => !lit(firstSeen.nodes[id]))),
    dimmedEdgeIds: new Set(edgeIds.filter((id) => !lit(firstSeen.edges[id]))),
  };
}
