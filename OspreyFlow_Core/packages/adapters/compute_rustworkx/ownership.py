"""Cumulative ownership (`06_DECISIONS.md` ADR-109 phase C, ruling 9) — Tier 2.

One walk back from the target enumerates every simple chain that reaches it: each node reached is
an owner through the chain walked so far. A chain's share is the product of its percentages, an
owner's the sum over its chains, in a fixed order (chains sorted by their link ids, links multiplied
owner first) so that Tier 1 (`apps/workspace/compute-tier1/harness.mjs::ownership`), doing the same
operations in the same order, agrees to the last bit. Circles of cross-holdings are the structure's
strongly connected components of more than one party (or a party owning itself): never looped,
since a chain never revisits a party, and listed so the reader is told.
"""

from __future__ import annotations

from collections import defaultdict

from schemas.compute import (
    OwnershipLink,
    OwnershipPath,
    OwnershipRequest,
    OwnershipTooComplex,
    OwnershipTrace,
    OwnerTrace,
)

#: The most chains one trace enumerates before refusing the structure as too tangled (rule 2).
MAX_CHAINS = 20_000


def _path(links: list[OwnershipLink]) -> OwnershipPath:
    ids = [link.id for link in links]
    if any(link.kind == "controls" for link in links):
        return OwnershipPath(link_ids=ids, kind="control")
    if any(link.percent is None for link in links):
        return OwnershipPath(link_ids=ids, kind="unknown")
    share = 100.0
    for link in links:
        share = share * float(link.percent) / 100  # type: ignore[arg-type]
    return OwnershipPath(link_ids=ids, kind="ownership", share=share)


def _cycles(links: list[OwnershipLink]) -> list[list[str]]:
    """Tarjan's strongly connected components, iteratively; those of more than one party, or one
    owning itself."""
    graph: dict[str, list[str]] = defaultdict(list)
    nodes: set[str] = set()
    self_owned: set[str] = set()
    for link in links:
        graph[link.source].append(link.target)
        nodes.update((link.source, link.target))
        if link.source == link.target:
            self_owned.add(link.source)
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    found: list[list[str]] = []
    counter = 0
    for root in sorted(nodes):
        if root in index:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, child = work.pop()
            if child == 0:
                index[node] = low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            successors = sorted(graph[node])
            if child < len(successors):
                work.append((node, child + 1))
                nxt = successors[child]
                if nxt not in index:
                    work.append((nxt, 0))
                elif nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
                continue
            if low[node] == index[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1 or node in self_owned:
                    found.append(sorted(component))
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
    return sorted(found)


def trace_ownership(req: OwnershipRequest) -> OwnershipTrace:
    types = {node.id: node.type for node in req.nodes}
    into: dict[str, list[OwnershipLink]] = defaultdict(list)
    for link in req.links:
        into[link.target].append(link)
    for incoming in into.values():
        incoming.sort(key=lambda link: link.id)

    chains: dict[str, list[OwnershipPath]] = defaultdict(list)
    count = 0
    # Each frame: the party reached, the links from it to the target (owner first), the parties
    # on the chain (never revisited).
    work: list[tuple[str, list[OwnershipLink], frozenset[str]]] = [
        (req.target, [], frozenset({req.target}))
    ]
    while work:
        node, links, seen = work.pop()
        for link in into.get(node, []):
            owner = link.source
            if owner in seen:
                continue
            chain = [link, *links]
            if len(chain) > req.max_depth:
                raise OwnershipTooComplex(
                    f"a chain of more than {req.max_depth} links reaches the target; the "
                    "structure is not traced in part"
                )
            count += 1
            if count > MAX_CHAINS:
                raise OwnershipTooComplex(
                    f"more than {MAX_CHAINS:,} chains reach the target; the structure is not "
                    "traced in part"
                )
            chains[owner].append(_path(chain))
            work.append((owner, chain, seen | {owner}))

    owners: list[OwnerTrace] = []
    for owner, paths in chains.items():
        paths.sort(key=lambda p: p.link_ids)
        cumulative = 0.0
        for p in paths:
            if p.kind == "ownership" and p.share is not None:
                cumulative += p.share
        unknown = any(p.kind == "unknown" for p in paths)
        controls = any(p.kind == "control" for p in paths)
        person = types.get(owner) == "Person"
        beneficial = person and (cumulative >= req.threshold or controls)
        owners.append(
            OwnerTrace(
                node_id=owner,
                node_type=types.get(owner, "unknown"),
                cumulative_percent=cumulative,
                share_unknown=unknown,
                controls=controls,
                paths=paths,
                beneficial_owner=beneficial,
                possible_beneficial_owner=person and not beneficial and unknown,
            )
        )
    owners.sort(key=lambda o: (-o.cumulative_percent, o.node_id))
    return OwnershipTrace(
        target=req.target, threshold=req.threshold, owners=owners, cycles=_cycles(req.links)
    )
