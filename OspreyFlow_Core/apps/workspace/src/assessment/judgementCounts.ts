// How many judgements rest on each node (ADR-070): the figure drawn beside a node on the canvas so
// an analyst can see at a glance which entities already have an assessment about them. A judgement
// rests on a node when the node is among its supporting or contradicting references; it counts
// once per node however many times it names it. Only a number leaves here, never the statement or
// the band, so the canvas shows no more than that a judgement exists.
export function judgementCountsByNode(
  judgements: readonly { supporting?: readonly string[]; contradicting?: readonly string[] }[],
): Map<string, number> {
  const counts = new Map<string, number>();
  for (const judgement of judgements) {
    const nodes = new Set([...(judgement.supporting ?? []), ...(judgement.contradicting ?? [])]);
    for (const id of nodes) counts.set(id, (counts.get(id) ?? 0) + 1);
  }
  return counts;
}
