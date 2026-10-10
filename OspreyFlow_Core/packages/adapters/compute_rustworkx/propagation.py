"""Distance-decayed risk (`06_DECISIONS.md` ADR-109 phase E) — Tier 2.

A breadth-first walk from the target over undirected links gives each seed's shortest distance;
each seed within `max_hops` contributes `seed × decay^hops` once. The factor is built by repeated
multiplication (not `**`, whose last bit may differ between Python and JavaScript), contributions
are sorted, then summed in that order — the same operations, in the same order, as Tier 1's
`apps/workspace/compute-tier1/harness.mjs::propagate`, so the two agree exactly.
"""

from __future__ import annotations

from collections import defaultdict, deque

from schemas.compute import PropagationContribution, PropagationRequest, PropagationResult


def propagate(req: PropagationRequest) -> PropagationResult:
    around: dict[str, set[str]] = defaultdict(set)
    for edge in req.edges:
        around[edge.source].add(edge.target)
        around[edge.target].add(edge.source)
    hops: dict[str, int] = {req.target: 0}
    queue: deque[str] = deque([req.target])
    while queue:
        node = queue.popleft()
        if hops[node] == req.max_hops:
            continue
        for nxt in sorted(around[node]):
            if nxt not in hops:
                hops[nxt] = hops[node] + 1
                queue.append(nxt)
    contributions: list[PropagationContribution] = []
    for node_id, seed in req.seeds.items():
        if node_id not in hops or seed <= 0:
            continue
        factor = 1.0
        for _ in range(hops[node_id]):
            factor = factor * req.decay
        contributions.append(
            PropagationContribution(
                node_id=node_id, hops=hops[node_id], seed=seed, contribution=seed * factor
            )
        )
    contributions.sort(key=lambda c: (-c.contribution, c.node_id))
    score = 0.0
    for c in contributions:
        score = score + c.contribution
    return PropagationResult(target=req.target, score=score, contributions=contributions)
