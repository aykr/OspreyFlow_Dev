"""ADR-116: Find connections — the fewest degrees that connect two nodes, and the routes there.

The graph store finds the routes of one length at a time, filtered as it walks (rule 3); this asks
for each length in turn, from one link up, and stops at the first that has a route. So the fewest
degrees it reports are the fewest the reader can see: a shorter route through something hidden was
never found, and nothing here can tell that it exists.
"""

from __future__ import annotations

from ports.graph import GraphPort
from schemas.domain import (
    CONNECTIONS_DEFAULT_REACH,
    CONNECTIONS_SHOWN,
    Connections,
    ConnectionsRequest,
    Principal,
)


async def find_connections(
    graph: GraphPort, req: ConnectionsRequest, principal: Principal
) -> Connections:
    """The routes at `req.degree`, or, with none asked, at the fewest degrees up to six."""

    async def at(length: int) -> Connections:
        routes = await graph.paths_at_length(
            req.source, req.target, length, CONNECTIONS_SHOWN, principal,
            edge_types=req.edge_types,
        )  # fmt: skip
        return Connections(degree=length, paths=routes.paths, more=routes.more, searched_to=length)

    if req.degree is not None:
        return await at(req.degree)
    for length in range(1, CONNECTIONS_DEFAULT_REACH + 1):
        found = await at(length)
        if found.paths:
            return found
    return Connections(degree=None, paths=[], more=False, searched_to=CONNECTIONS_DEFAULT_REACH)
