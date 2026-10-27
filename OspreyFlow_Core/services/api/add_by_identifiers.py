"""Add many from a list — `06_DECISIONS.md` ADR-128 decision 1 (B2), `POST
/v1/investigations/{id}/working-set/add-by-identifiers`.

The analyst pastes, or chooses a file of, identifiers: prison numbers, National Insurance numbers,
phone numbers, account references, in any mix. This module reads each (`identifier_reading.py`),
finds it through the access-filtered `GraphPort.find_node`, and says how many were read, found,
matched nothing the analyst can see, and repeated. The route (`app.py`) then adds what was found
through the working set's own add (`WorkingSetService.add_by_identifiers`), after a person has seen
the count and confirmed.

**Rule 3 (and 7): an identifier that does not exist and one the analyst may not see are one
answer.**
`find_node` carries the access filter in the adapter's own traversal, so both come back `None`. This
module adds nothing that could tell them apart: the figure, the lookup (one per distinct identifier,
the same query either way), the response and the audit entry (counts only, never an identifier) are
the same. Whether an identifier is read as a prison number, a number, or nothing depends on its
shape alone.

**The counts.** `read` is the identifiers in what was typed; `found` those that resolved to a node
the analyst may see, a repeat of one that did included; `matched_nothing` is `read` less `found`;
`repeated` those that name what an earlier one in the list did (three spellings of one number are
three read, three found, two repeated, and one node). Nodes are added once.

**The limit.** More than `MAX_IDENTIFIERS` after splitting is refused with
`TooManyIdentifiersError`, carrying how many were given, before any lookup; never truncated
(rule 2). The count-only request is refused too, so a list that cannot be added is not counted as
if it could.

**A kind check on an endpoint.** A number is an `Endpoint` whose `endpoint_kind` is `msisdn`, an
account one whose is `account`; an endpoint of another kind holding the same text (a PIN, `handle`)
is not a match, and falls in "matched nothing" as any other miss does.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from ports.graph import GraphPort
from schemas.domain import Node, Principal

from .identifier_reading import Reading, read_identifier, split_identifiers
from .working_set.models import ExpansionOutcome

#: ADR-128 decision 1: the most identifiers one request reads.
MAX_IDENTIFIERS = 5_000
#: How many lookups are asked of the graph at once. The answer does not depend on it.
LOOKUP_CONCURRENCY = 16
#: A pasted list of 5,000 is some tens of kilobytes; this stops a request that is only a way to
#: make the server hold a very large string, without being a second limit on the list.
MAX_TEXT_CHARS = 1_000_000

#: For each kind: the entity type, the property the lookup is by, and the `endpoint_kind` an
#: endpoint must carry (`None` for a person).
_LOOKUPS: dict[str, tuple[str, str, str | None]] = {
    "prison_number": ("Person", "prison_number", None),
    "nino": ("Person", "nino", None),
    "account": ("Endpoint", "value_normalised", "account"),
    "msisdn": ("Endpoint", "value_normalised", "msisdn"),
}


class IdentifierCounts(BaseModel):
    """The four figures the analyst is shown before anything is added."""

    read: int
    found: int
    matched_nothing: int
    repeated: int


class AddByIdentifiersRequest(BaseModel):
    """The typed strings: each may hold several identifiers, split as `split_identifiers` does.
    `confirm: false` counts; `true` adds. `with_links` adds the links among the added nodes and
    the view too; by default none are added and "Show links among all" draws them."""

    identifiers: list[Annotated[str, StringConstraints(max_length=MAX_TEXT_CHARS)]] = Field(
        max_length=200_000
    )
    confirm: bool = False
    with_links: bool = False


class AddByIdentifiersResponse(BaseModel):
    """The counts always; the working-set outcome (the delta to apply) only when added."""

    counts: IdentifierCounts
    added: ExpansionOutcome | None = None


class TooManyIdentifiersError(Exception):
    """More than `MAX_IDENTIFIERS` were typed. Carries how many, for the typed refusal."""

    def __init__(self, received: int) -> None:
        super().__init__(
            f"{received} identifiers given, the most one request reads is {MAX_IDENTIFIERS}"
        )
        self.received = received


@dataclass(frozen=True)
class Resolution:
    counts: IdentifierCounts
    #: The nodes found, once each, in the order they were first named.
    nodes: list[Node]


async def _lookup(graph: GraphPort, reading: Reading, principal: Principal) -> Node | None:
    spec = _LOOKUPS.get(reading.kind)
    if spec is None:
        return None
    entity_type, field, endpoint_kind = spec
    # The kind is part of the lookup: two visible Endpoints can share `value_normalised` (a handle
    # and an account holding the same text), and the lookup returns one of them.
    also = {"endpoint_kind": endpoint_kind} if endpoint_kind is not None else None
    node = (
        await graph.find_node(entity_type, field, reading.canonical, principal, also=also)
        if also
        else await graph.find_node(entity_type, field, reading.canonical, principal)
    )
    if node is None:
        return None
    if endpoint_kind is not None and node.properties.get("endpoint_kind") != endpoint_kind:
        return None
    return node


async def resolve_identifiers(
    graph: GraphPort, typed: list[str], principal: Principal
) -> Resolution:
    """Reads each typed identifier and finds it as `principal` (see the module docstring)."""
    tokens = split_identifiers(typed)
    if len(tokens) > MAX_IDENTIFIERS:
        raise TooManyIdentifiersError(len(tokens))
    readings = [read_identifier(t) for t in tokens]
    distinct: dict[tuple[str, str], Reading] = {}
    for reading in readings:
        distinct.setdefault(reading.key, reading)
    gate = asyncio.Semaphore(LOOKUP_CONCURRENCY)

    async def one(reading: Reading) -> Node | None:
        async with gate:
            return await _lookup(graph, reading, principal)

    answers = await asyncio.gather(*(one(r) for r in distinct.values()))
    found_by_key = dict(zip(distinct, answers, strict=True))
    seen: set[tuple[str, str]] = set()
    seen_nodes: set[str] = set()
    nodes: list[Node] = []
    found = repeated = 0
    for reading in readings:
        if reading.key in seen:
            repeated += 1
        seen.add(reading.key)
        node = found_by_key[reading.key]
        if node is None:
            continue
        found += 1
        if node.id not in seen_nodes:
            seen_nodes.add(node.id)
            nodes.append(node)
    counts = IdentifierCounts(
        read=len(readings), found=found, matched_nothing=len(readings) - found, repeated=repeated
    )
    return Resolution(counts=counts, nodes=nodes)
