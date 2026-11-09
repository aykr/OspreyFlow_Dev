"""Changing the deployment's grading scheme (`06_DECISIONS.md` ADR-143 decision 11 and Amendment 6;
the owner's ruling C13; ADR-145 O1; L3.7).

Every drawn node and link carries a grade in the deployment's scheme (`DrawnAssertion.grading`):
a built-in one (5x5x5, 3x5x2) or a scheme file's. The scheme changes only by the operator's
command (`ospreyflow grading change`, over `scripts/grading_change.py`), with a mapping of every
grade of each part of the old scheme to one of the new:

    from: 5x5x5
    to: 3x5x2
    source: {A: A, B: A, C: B, D: C, E: C}
    intelligence: {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5"}
    handling: {"1": P, "2": P, "3": P, "4": C, "5": C}

**A dry run first** (C13). A dry run reports how many items each mapping line moves, writes
nothing, and gives a token naming that mapping on that state of the drawn items. A real run is
refused unless it is given that token and the state is still the same: another drawing, an edit
or a different mapping since the dry run gives another token.

Then each grade is changed in place (`GraphPort.regrade_drawn`): the grade and the grade and
scheme the item had before its first change (`original_grading`), kept for good, and nothing else
of the item. The change is audited before the first write (the plan) and after the last (what was
written).

It is refused whole, before anything is written and on a dry run too, for a mapping that does not
cover the old scheme, a mapping from another scheme than the deployment's, an item graded in a
third scheme, or a registered item that cannot be read back (rule 2: an item is never skipped
silently); each refusal names the items' ids (the first ten, and how many more). An item already
in the new scheme with no original (drawn in it, so it needs no mapping) is left and counted.

A run stopped by a store failure (`GradingIncomplete`) is finished by its dry run and the same
change again: an item already changed is counted and left.

Withdrawn items are not changed: they are kept as they were drawn, in the audit's sense (decision
5), and are never shown as live. Under 3x5x2 the handling code (P or C) is part of the grade and is
never merged with the protective marking: the marking is not touched.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import yaml

from ontology.handling import HandlingScheme, sources_in_full
from ports.graph import GraphPort
from schemas.domain import (
    GRADING_PARTS,
    Edge,
    Grading,
    GradingSchemeAnswer,
    Node,
    Principal,
)

from .board_store import BoardItem

PARTS = ("source", "intelligence", "handling")
#: How many ids a refusal names before it counts the rest.
SHOWN_IDS = 10


class MappingRefused(Exception):
    """The mapping file cannot be used; the message names the part and grade."""


class GradingRefused(Exception):
    """The change is refused whole, before anything is written; the message says why."""


class GradingIncomplete(Exception):
    """A rewrite failed part way: `done` of `total` items carry the new grade. A dry run and the
    same change again finish it."""

    def __init__(self, done: int, total: int, cause: BaseException) -> None:
        super().__init__(
            f"stopped after {done} of {total} item(s): {cause}. Run the dry run and the same "
            "change again to finish it; the items already changed are left as they are."
        )
        self.done = done
        self.total = total


def named(ids: Sequence[str]) -> str:
    """The first `SHOWN_IDS` ids, and how many more."""
    shown = ", ".join(ids[:SHOWN_IDS])
    more = len(ids) - SHOWN_IDS
    return shown + (f" and {more} more" if more > 0 else "")


def built_in_schemes() -> dict[str, GradingSchemeAnswer]:
    return {name: GradingSchemeAnswer.of(name) for name in GRADING_PARTS}


@dataclass(frozen=True)
class GradingMapping:
    from_scheme: str
    to_scheme: str
    #: For each part, every grade of the old scheme to one of the new.
    parts: dict[str, dict[str, str]]

    def apply(self, grading: Grading) -> Grading:
        return Grading(
            scheme=self.to_scheme,
            **{part: self.parts[part][getattr(grading, part)] for part in PARTS},
        )

    def canonical(self) -> dict[str, Any]:
        return {
            "from": self.from_scheme,
            "to": self.to_scheme,
            "parts": {p: dict(sorted(self.parts[p].items())) for p in PARTS},
        }


def parse_mapping(text: str, schemes: Mapping[str, GradingSchemeAnswer]) -> GradingMapping:
    """The mapping file, checked against `schemes` (the built-in ones, the deployment's and the
    target's): both schemes known and different, and each part's mapping covering exactly the old
    scheme's grades, onto the new scheme's."""
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
        if scheme not in schemes:
            raise MappingRefused(
                f"{name}: {scheme!r} is not a grading scheme; the schemes are "
                f"{', '.join(sorted(schemes))}"
            )
    if old == new:
        raise MappingRefused(f"from and to are the same scheme, {old}: there is nothing to change")
    parts: dict[str, dict[str, str]] = {}
    for index, part in enumerate(PARTS):
        given = raw.get(part)
        if not isinstance(given, dict):
            raise MappingRefused(f"{part}: the mapping gives no {part} grades")
        lines = {str(k): str(v) for k, v in given.items()}
        olds, news = schemes[old].parts()[index], schemes[new].parts()[index]
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
    #: The element as read (a `Node` or an `Edge`); `id` is what the port rewrites.
    element: Any
    grading: Grading
    original: Grading | None

    @property
    def id(self) -> str:
        return str(self.element.id)

    def state(self) -> list[Any]:
        """What the dry run's token names of this item: its id, its grade, its original and its
        revision (an edit since the dry run is another state)."""
        audit = getattr(self.element, "audit", None)
        return [
            self.id,
            self.grading.model_dump(mode="json"),
            self.original.model_dump(mode="json") if self.original else None,
            getattr(audit, "revision", None),
        ]


@dataclass(frozen=True)
class Inventory:
    items: list[GradedItem]
    #: The registry's ids of live items the port could not read back.
    unread: list[str] = field(default_factory=list)


class GradedItems(Protocol):
    async def inventory(self) -> Inventory: ...
    async def rewrite(self, item: GradedItem, grading: Grading, original: Grading) -> None: ...


def operator_reader(
    scheme: HandlingScheme, *, org_unit: str, by: str = "grading-change"
) -> Principal:
    """Who the command reads as: the scheme's top clearance, every handling code, every dataset.
    A restricted code is also scoped to the reader's unit, so an item of another unit's may still
    be unreadable, and then the change is refused whole, naming it, rather than run past it."""
    return Principal(
        id=by,
        clearance=scheme.classification[-1],
        org_unit=org_unit,
        receivable_handling_codes=list(scheme.handling_codes),
        datasets=None,
    )


Registered = Callable[[], Awaitable[Sequence[BoardItem]]]


class ChangedUnderneath(Exception):
    """`regrade_drawn` found the element gone or no longer drawn since it was read."""


@dataclass
class BoardGradedItems:
    """The drawn nodes and links the board registry holds (`board_store`), read in the graph and
    regraded in place there (`GraphPort.regrade_drawn`). A live item is one not withdrawn; pictures
    and match links carry no grade."""

    graph: GraphPort
    registered: Registered
    reader: Principal

    async def inventory(self) -> Inventory:
        live = [
            i
            for i in await self.registered()
            if i.withdrawn_at is None and i.kind in ("node", "link")
        ]
        node_ids = [i.element_id for i in live if i.kind == "node"]
        edge_ids = [i.element_id for i in live if i.kind == "link"]
        found: dict[str, Node | Edge] = {}
        # The drawn assertion whole (ADR-130 Amendment 2), as stored, not as a reader is shown it.
        with sources_in_full():
            if node_ids:
                found.update((n.id, n) for n in await self.graph.get_nodes(node_ids, self.reader))
            if edge_ids:
                found.update((e.id, e) for e in await self.graph.get_edges(edge_ids, self.reader))
        items: list[GradedItem] = []
        unread: list[str] = []
        for registered in live:
            element = found.get(registered.element_id)
            drawn = element.provenance.drawn if element is not None else None
            if element is None or drawn is None:
                unread.append(registered.item_id)
                continue
            items.append(GradedItem(element, drawn.grading, drawn.original_grading))
        return Inventory(items=items, unread=unread)

    async def rewrite(self, item: GradedItem, grading: Grading, original: Grading) -> None:
        """The grade and original alone, in place: nothing else of the item is written, so a
        link is not weighed again (ADR-120) and a node keeps its resolution state. The port says
        whether it changed exactly that element; anything else stops the run."""
        if not await self.graph.regrade_drawn(item.id, grading, original):
            raise ChangedUnderneath(f"{item.id} is no longer a live drawn item; it was not changed")


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
    #: Items drawn in the new scheme (no original): they need no mapping and are left.
    already_in_new: int = 0
    written: int = 0
    dry_run: bool = True
    #: The dry run's token: this mapping on this state of the drawn items.
    token: str = ""
    #: The audit's two records: `started` before the first write, then `finished` or `stopped`.
    stage: str = "planned"

    def lines(self) -> list[str]:
        said = [
            f"{self.from_scheme} to {self.to_scheme}: {self.to_change} item(s) to change"
            + (f", {self.already_changed} already changed" if self.already_changed else "")
            + (
                f", {self.already_in_new} drawn in {self.to_scheme} and left as they are"
                if self.already_in_new
                else ""
            )
            + "."
        ]
        for part in PARTS:
            for (p, old, new), count in sorted(self.moves.items()):
                if p == part:
                    said.append(f"{part} {old} → {new}: {count} item(s)")
        said.append("Withdrawn items keep the grade they were drawn with and are not counted.")
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
            "already_in_new": self.already_in_new,
            "written": self.written,
            "dry_run_token": self.token,
            "stage": self.stage,
        }


def dry_run_token(
    mapping: GradingMapping,
    current: GradingSchemeAnswer,
    target: GradingSchemeAnswer,
    items: Sequence[GradedItem],
) -> str:
    """Names this mapping, these two schemes and this state of the drawn items: any drawing, edit
    or regrade since gives another."""
    named_state = {
        "mapping": mapping.canonical(),
        "current": current.model_dump(mode="json"),
        "target": target.model_dump(mode="json"),
        "items": sorted(item.state() for item in items),
    }
    digest = hashlib.sha256(json.dumps(named_state, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()[:20]


Audit = Callable[[GradingPlan], Awaitable[None]]
Announce = Callable[[GradingPlan], None]


async def change(
    items: GradedItems,
    mapping: GradingMapping,
    *,
    current: GradingSchemeAnswer,
    target: GradingSchemeAnswer,
    dry_run: bool,
    audit: Audit,
    confirm: str | None = None,
    announce: Announce | None = None,
) -> GradingPlan:
    """The plan, and unless `dry_run` the change itself. `current` is the deployment's scheme
    (`grading.scheme`), `target` the one changed to. A real run needs `confirm`, the token its dry
    run gave, for this state. `announce` is told the plan once every check has passed and before
    the first write; the audit is written before the first write and after the last."""
    if mapping.from_scheme != current.scheme:
        raise GradingRefused(
            f"the mapping is from {mapping.from_scheme}, but this deployment grades in "
            f"{current.scheme}"
        )
    if mapping.to_scheme != target.scheme:
        raise GradingRefused(f"the mapping is to {mapping.to_scheme}, not to {target.scheme}")
    inventory = await items.inventory()
    if inventory.unread:
        raise GradingRefused(
            f"{len(inventory.unread)} drawn item(s) could not be read back, so their grades are "
            f"unknown: {named(inventory.unread)}. Nothing was changed."
        )
    plan = GradingPlan(
        from_scheme=mapping.from_scheme, to_scheme=mapping.to_scheme, dry_run=dry_run
    )
    pending: list[GradedItem] = []
    elsewhere: dict[str, list[str]] = {}
    off_scheme: list[str] = []
    for item in inventory.items:
        scheme = item.grading.scheme
        if scheme == mapping.from_scheme:
            try:
                current.check(item.grading)
            except ValueError:
                off_scheme.append(item.id)
                continue
            pending.append(item)
            for part in PARTS:
                old = getattr(item.grading, part)
                plan.moves[(part, old, mapping.parts[part][old])] += 1
        elif scheme == mapping.to_scheme and item.original is not None:
            plan.already_changed += 1
        elif scheme == mapping.to_scheme:
            plan.already_in_new += 1
        else:
            elsewhere.setdefault(scheme, []).append(item.id)
    if elsewhere:
        said = "; ".join(
            f"{len(ids)} item(s) graded in {s}: {named(ids)}"
            for s, ids in sorted(elsewhere.items())
        )
        raise GradingRefused(
            f"{said}. They are in neither {mapping.from_scheme} nor {mapping.to_scheme}, and the "
            "mapping does not say what they become. Nothing was changed."
        )
    if off_scheme:
        raise GradingRefused(
            f"{len(off_scheme)} item(s) carry a grade that is not one of {current.scheme}'s: "
            f"{named(off_scheme)}. Nothing was changed."
        )
    plan.to_change = len(pending)
    plan.token = dry_run_token(mapping, current, target, inventory.items)
    if not dry_run and confirm != plan.token:
        raise GradingRefused(
            "a dry run of this mapping on the drawn items as they are now comes first (C13): "
            + ("none was given. " if not confirm else "the token given is of another mapping or "
               "of the items as they were before a drawing or edit since. ")
            + "Run the dry run, then this change with the token it gives. Nothing was changed."
        )  # fmt: skip
    if announce is not None:
        announce(plan)
    if dry_run:
        return plan
    if pending:
        plan.stage = "started"
        await audit(plan)  # before any write: never a changed grade with no record of the change
    for done, item in enumerate(pending):
        try:
            await items.rewrite(item, mapping.apply(item.grading), item.original or item.grading)
        except Exception as failed:
            plan.stage = "stopped"
            await audit(plan)
            raise GradingIncomplete(done, len(pending), failed) from failed
        plan.written += 1
    if pending:
        plan.stage = "finished"
        await audit(plan)
    return plan
