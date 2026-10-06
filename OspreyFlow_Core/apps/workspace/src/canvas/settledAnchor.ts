// Where a node arriving in the layout starts: beside its first already-settled neighbour, in link
// order, so an expansion grows outwards from where the analyst is looking. One pass over the links
// builds each node's neighbours, so the cost is linear in nodes plus links; the earlier per-node
// scan of every link held the perf fixture's first layout for over two minutes.

/** For each node not yet settled, its first settled neighbour, when it has one. */
export function settledAnchors(
  nodes: readonly string[],
  edges: readonly (readonly [string, string])[],
  settled: ReadonlySet<string>,
): Map<string, string> {
  const anchors = new Map<string, string>();
  if (settled.size === 0) return anchors;
  const waiting = new Set(nodes.filter((id) => !settled.has(id)));
  for (const [a, b] of edges) {
    if (waiting.has(a) && !anchors.has(a) && settled.has(b)) anchors.set(a, b);
    if (waiting.has(b) && !anchors.has(b) && settled.has(a)) anchors.set(b, a);
  }
  return anchors;
}
