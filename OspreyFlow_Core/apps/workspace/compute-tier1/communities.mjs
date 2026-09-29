// `06_DECISIONS.md` ADR-029's connected-components split, written natively in this tier's own
// language rather than shared with `packages/adapters/compute_rustworkx/communities.py` — the
// ADR's own reasoning: "identical in both tiers so agreement is preserved" means the same
// algorithm run twice, not one implementation imported across a Python/JS boundary that does not
// exist at runtime (Tier 1 has no Python interpreter to call into).
//
// For each label Louvain assigned, finds the connected components of that label's own induced
// subgraph and gives each one its own final id — O(n+m), mirroring the Python function's own BFS.

/**
 * @param {string[]} nodeIds
 * @param {Array<[string, string]>} edges
 * @param {Record<string, number>} partition
 * @returns {Record<string, string>}
 */
export function splitDisconnectedCommunities(nodeIds, edges, partition) {
  const adjacency = new Map(nodeIds.map((id) => [id, []]));
  for (const [a, b] of edges) {
    if (adjacency.has(a) && adjacency.has(b) && partition[a] === partition[b]) {
      adjacency.get(a).push(b);
      adjacency.get(b).push(a);
    }
  }

  const result = {};
  const visited = new Set();
  let nextId = 0;

  for (const start of nodeIds) {
    if (visited.has(start)) continue;
    const component = [start];
    visited.add(start);
    const frontier = [start];
    while (frontier.length > 0) {
      const current = frontier.pop();
      for (const neighbour of adjacency.get(current)) {
        if (!visited.has(neighbour)) {
          visited.add(neighbour);
          component.push(neighbour);
          frontier.push(neighbour);
        }
      }
    }
    const communityId = String(nextId);
    nextId += 1;
    for (const member of component) result[member] = communityId;
  }

  return result;
}
