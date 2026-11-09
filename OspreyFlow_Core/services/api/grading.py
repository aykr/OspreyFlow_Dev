"""Changing the deployment's grading scheme (`06_DECISIONS.md` ADR-143 decision 11 and C13; ADR-145
O1; L3.7).

Every drawn node and link carries a grade in the deployment's scheme (`DrawnAssertion.grading`).
The scheme changes only by the operator's command (`scripts/grading_change.py`), with a mapping of
every grade of each part of the old scheme to one of the new:

    from: 5x5x5
    to: 3x5x2
    source: {A: A, B: A, C: B, D: C, E: C}
    intelligence: {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5"}
    handling: {"1": P, "2": P, "3": P, "4": C, "5": C}

`change` first reports how many items each mapping line moves (the plan; a dry run stops there and
writes nothing), then rewrites each grade, keeping the grade and scheme the item had before its
first change (`DrawnAssertion.original_grading`) for good, and is audited. It is refused whole,
before anything is written, for a mapping that does not cover the old scheme, a mapping from
another scheme than the deployment's, an item in another scheme, or a registered item that cannot
be read back (rule 2: an item is never skipped silently).

A change stopped part way (`GradingIncomplete`) is finished by running it again: an item already
in the new scheme with an original kept is counted as already changed and left.

Withdrawn items are not changed: they are kept as they were drawn, in the audit's sense (decision
5), and are never shown as live. Under 3x5x2 the handling code (P or C) is part of the grade and is
never merged with the protective marking: the marking is not touched.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

import yaml

from ontology.handling import HandlingScheme, sources_in_full
from ports.graph import GraphPort
from schemas.domain import (
    GRADING_PARTS,
    Edge,
    EdgeWrite,
    Grading,
    Node,
    NodeWrite,
    Principal,
)

from .board_store import BoardItem

PARTS = ("source", "intelligence", "handling")
SCHEMES = tuple(GRADING_PARTS)


class MappingRefused(Exception):
    """The mapping file cannot be used; the message names the part and grade."""


class GradingRefused(Exception):
    """The change is refused whole, before anything is written; the message says why."""


class GradingIncomplete(Exception):
    """A rewrite failed part way: `done` of `total` items carry the new grade. Running the same
    change again finishes it."""

    def __init__(self, done: int, total: int, cause: BaseException) -> None:
        super().__init__(
            f"stopped after {done} of {total} item(s): {cause}. Run the same change again to "
            "finish it; the items already changed are left as they are."
        )
        self.done = done
        self.total = total


@dataclass(frozen=True)
class GradingMapping:
    from_scheme: str
    to_scheme: str
    #: For each part, every grade of the old scheme to one of the new.
    parts: dict[str, dict[str, str]]

    def apply(self, grading: Grading) -> Grading:
        return Grading(
            scheme=self.to_scheme,  # type: ignore[arg-type]
            **{part: self.parts[part][getattr(grading, part)] for part in PARTS},
        )


def parse_mapping(text: str) -> GradingMapping:
    """The mapping file, checked: both schemes known and different, and each part's mapping
    covering exactly the old scheme's grades, onto the new scheme's."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as bad:
        raise MappingRefused(f"the mapping is not YAML: {bad}") from None
    if not isinstance(raw, dict):
        raise MappingRefused("the mapping is a YAML mapping with from, to and the three parts")
    unknown = set(raw) - {"from", "to", *PARTS}
    if unknown:
        raise MappingRefused(
            f"the mapping has unknown keys: {', '.join(sorted(map(str, unknown)))}"
        )
    old, new = str(raw.get("from", "")), str(raw.get("to", ""))
    for name, scheme in (("from", old), ("to", new)):
        if scheme not in GRADING_PARTS:
            raise MappingRefused(
                f"{name}: {scheme!r} is not a grading scheme; the schemes are {', '.join(SCHEMES)}"
            )
    if old == new:
        raise MappingRefused(f"from and to are the same scheme, {old}: there is nothing to change")
    parts: dict[str, dict[str, str]] = {}
    for index, part in enumerate(PARTS):
        given = raw.get(part)
        if not isinstance(given, dict):
            raise MappingRefused(f"{part}: the mapping gives no {part} grades")
        lines = {str(k): str(v) for k, v in given.items()}
        olds, news = GRADING_PARTS[old][index], GRADING_PARTS[new][index]
        for grade in olds:
            if grade not in lines:
                raise MappingRefused(f"{part} {grade} of {old} is not mapped")
        for grade, to in lines.items():
            if grade not in olds:
                raise MappingRefused(f"{part} {grade} is not a grade of {old}")
            if to not in news:
                raise MappingRefused(f"{part} {to} is not a grade of {new}")
        parts[part] = lines
    return GradingMapping(from_scheme=old, to_scheme=new, parts=parts)


# --- the graded items -----------------------------------------------------------------------


@dataclass(frozen=True)
class GradedItem:
    #: The port's own reference to the item; opaque to `change`.
    ref: Any
    grading: Grading
    original: Grading | None


@dataclass(frozen=True)
class Inventory:
    items: list[GradedItem]
    #: Registered live items the port could not read back.
    unread: int


class GradedItems(Protocol):
    async def inventory(self) -> Inventory: ...
    async def rewrite(self, item: GradedItem, grading: Grading, original: Grading) -> None: ...


def operator_reader(
    scheme: HandlingScheme, *, org_unit: str, by: str = "grading-change"
) -> Principal:
    """Who the command reads as: the scheme's top clearance, every handling code, every dataset.
    A restricted code is also scoped to the reader's unit, so an item of another unit's may still
    be unreadable, and then the change is refused whole rather than run past it."""
    return Principal(
        id=by,
        clearance=scheme.classification[-1],
        org_unit=org_unit,
        receivable_handling_codes=list(scheme.handling_codes),
        datasets=None,
    )


Registered = Callable[[], Awaitable[Sequence[BoardItem]]]


@dataclass
class BoardGradedItems:
    """The drawn nodes and links the board registry holds (`board_store`), read and rewritten in the
    graph. A live item is one not withdrawn; pictures and match links carry no grade."""

    graph: GraphPort
    registered: Registered
    reader: Principal
    written_by: str

    async def inventory(self) -> Inventory:
        live = [
            i
            for i in await self.registered()
            if i.withdrawn_at is None and i.kind in ("node", "link")
        ]
        node_ids = [i.element_id for i in live if i.kind == "node"]
        edge_ids = [i.element_id for i in live if i.kind == "link"]
        found: dict[str, Node | Edge] = {}
        # A read that is written back (ADR-130 Amendment 2): the body whole, its sources and its
        # board kept, or the rewrite would store what a reader is shown in their place.
        with sources_in_full():
            if node_ids:
                found.update((n.id, n) for n in await self.graph.get_nodes(node_ids, self.reader))
            if edge_ids:
                found.update((e.id, e) for e in await self.graph.get_edges(edge_ids, self.reader))
        items: list[GradedItem] = []
        unread = 0
        for registered in live:
            element = found.get(registered.element_id)
            drawn = element.provenance.drawn if element is not None else None
            if element is None or drawn is None:
                unread += 1
                continue
            items.append(GradedItem(element, drawn.grading, drawn.original_grading))
        return Inventory(items=items, unread=unread)

    async def rewrite(self, item: GradedItem, grading: Grading, original: Grading) -> None:
        """The element written again under its own id, as `Boards.edit` writes an edit: only its
        drawn grade and original change; marking, datasets and properties are its own."""
        element: Node | Edge = item.ref
        drawn = element.provenance.drawn
        assert drawn is not None
        if element.provenance.sources_withheld or not drawn.board_id:
            # Read as a reader is shown it, not as it is stored: written back, it would lose them.
            raise GradingRefused(
                f"a drawn item ({drawn.item_id}) was read with its sources or board withheld; "
                "it is not written back so"
            )
        provenance = element.provenance.model_copy(
            update={
                "drawn": drawn.model_copy(update={"grading": grading, "original_grading": original})
            }
        )
        now = datetime.now(UTC)
        tx = await self.graph.begin_transaction()
        try:
            if isinstance(element, Node):
                await self.graph.upsert_nodes(
                    [NodeWrite(
                        id=element.id, type=element.type, properties=element.properties,
                        provenance=provenance, handling=element.handling,
                        created_by=self.written_by, created_at=now, datasets=element.datasets,
                    )],
                    tx,
                )  # fmt: skip
            else:
                # A link's second write of the same pair and audience merges into it (ADR-102),
                # its body the latest write's: the change lands on the same link.
                await self.graph.upsert_edges(
                    [EdgeWrite(
                        id=element.id, type=element.type, source=element.source,
                        target=element.target, properties=element.properties,
                        interval=element.interval, basis=element.basis,
                        provenance=provenance, handling=element.handling,
                        created_by=self.written_by, created_at=now, datasets=element.datasets,
                    )],
                    tx,
                )  # fmt: skip
        except Exception:
            await self.graph.rollback_transaction(tx)
            raise
        await self.graph.commit_transaction(tx)


# --- the change -----------------------------------------------------------------------------


@dataclass
class GradingPlan:
    from_scheme: str
    to_scheme: str
    #: (part, old grade, new grade) → how many items that mapping line moves.
    moves: Counter[tuple[str, str, str]] = field(default_factory=Counter)
    to_change: int = 0
    #: Items a stopped earlier run already changed (in the new scheme, their original kept).
    already_changed: int = 0
    written: int = 0
    dry_run: bool = True

    def lines(self) -> list[str]:
        said = [
            f"{self.from_scheme} to {self.to_scheme}: {self.to_change} item(s) to change"
            + (f", {self.already_changed} already changed" if self.already_changed else "")
            + "."
        ]
        for part in PARTS:
            for (p, old, new), count in sorted(self.moves.items()):
                if p == part:
                    said.append(f"{part} {old} → {new}: {count} item(s)")
        return said

    def record(self) -> dict[str, Any]:
        return {
            "from": self.from_scheme,
            "to": self.to_scheme,
            "moves": [
                {"part": p, "from": o, "to": n, "items": c}
                for (p, o, n), c in sorted(self.moves.items())
            ],
            "to_change": self.to_change,
            "already_changed": self.already_changed,
            "written": self.written,
        }


Audit = Callable[[GradingPlan], Awaitable[None]]


async def change(
    items: GradedItems,
    mapping: GradingMapping,
    *,
    current: str,
    dry_run: bool,
    audit: Audit,
) -> GradingPlan:
    """The plan, and unless `dry_run` the change itself, audited once it is whole. `current` is
    the deployment's scheme (`grading.scheme`)."""
    if mapping.from_scheme != current:
        raise GradingRefused(
            f"the mapping is from {mapping.from_scheme}, but this deployment grades in {current}"
        )
    inventory = await items.inventory()
    if inventory.unread:
        raise GradingRefused(
            f"{inventory.unread} drawn item(s) could not be read back, so their grades are "
            "unknown. Nothing was changed."
        )
    plan = GradingPlan(
        from_scheme=mapping.from_scheme, to_scheme=mapping.to_scheme, dry_run=dry_run
    )
    pending: list[GradedItem] = []
    elsewhere: Counter[str] = Counter()
    for item in inventory.items:
        scheme = item.grading.scheme
        if scheme == mapping.from_scheme:
            pending.append(item)
            for part in PARTS:
                old = getattr(item.grading, part)
                plan.moves[(part, old, mapping.parts[part][old])] += 1
        elif scheme == mapping.to_scheme and item.original is not None:
            plan.already_changed += 1
        else:
            elsewhere[scheme] += 1
    if elsewhere:
        said = ", ".join(f"{n} item(s) graded in {s}" for s, n in sorted(elsewhere.items()))
        raise GradingRefused(
            f"{said}, not in {mapping.from_scheme}: the mapping does not say what they become. "
            "Nothing was changed."
        )
    plan.to_change = len(pending)
    if dry_run:
        return plan
    for done, item in enumerate(pending):
        try:
            await items.rewrite(item, mapping.apply(item.grading), item.original or item.grading)
        except Exception as failed:
            # What was written is audited too, so the record holds every changed grade.
            if done:
                await audit(plan)
            raise GradingIncomplete(done, len(pending), failed) from failed
        plan.written += 1
    await audit(plan)
    return plan
