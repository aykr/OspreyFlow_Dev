// "Collapse into one node" on a same-as link (ADR-080): which nodes fold together. A way of looking
// at the view, like Communities (ADR-066): nothing is merged or written, and Expand puts every
// node back. Pure, so it can be tested without a renderer.
import type { Community } from "./communities";

/**
 * The group a same-as link folds. When both ends belong to one resolution cluster the whole cluster
 * folds (one entity, one node) — the nodes of it that are in the view. When they do not (the link
 * is below the threshold, or the nodes have no cluster) only the two ends fold. The name depends
 * only on the members, so the group is the same group however it is reached, and `s:` keeps it
 * apart from a community's `c:` name.
 */
export function sameAsGroup(
  source: string,
  target: string,
  inView: readonly string[],
  clusterOf: (id: string) => string | undefined,
): Community {
  const cluster = clusterOf(source);
  const shared = cluster !== undefined && cluster === clusterOf(target);
  const members = shared
    ? inView.filter((id) => clusterOf(id) === cluster)
    : [source, target].filter((id) => inView.includes(id));
  const sorted = [...new Set(members)].sort();
  return {
    id: `s:${sorted.join("|")}`,
    members: sorted,
    label: `Same entity: ${sorted.length} nodes`,
  };
}
