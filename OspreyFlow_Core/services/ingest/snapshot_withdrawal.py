"""A full snapshot's withdrawal of its dropped rows (`06_DECISIONS.md` ADR-110 Amendment 8 point 3,
as ADR-110 Amendment 15 narrows it).

A source refreshed as a *full snapshot* with *withdraw* reads the whole table each time; a row a
pipeline kept for the case that the snapshot no longer carries is *dropped*, and its **links**,
with their events, are withdrawn (`GraphPort.withdraw_elements`), in the refresh's own graph
transaction, before it commits. **Its nodes are never withdrawn** (Amendment 15, the owner's
ruling "Never withdraw nodes"): whether a node may go depends on links and rows the loader may
not read, and a node that stayed or went would tell them so, through the graph and through the
run's figures (rule 3's hidden degree). A node is left exactly as *keep* leaves every element.
`plan_withdrawal` decides:

- **the dropped keys**: the pipeline's kept keys for the case that no row of the snapshot carries
  (a held or rejected row still carries its key, so it is not dropped);
- **their links**, from each key's record (Amendment 8 point 2), less every one that is also: in
  another kept row's record (any pipeline, any case); written by the snapshot's own rows; or listed
  by an unreverted load's record other than the ones that kept the dropped keys;
- **what it says** (`Withdrawal.notes`), in words, never silently, and the same whatever the loader
  may not read (Amendment 15): the links kept because **this pipeline's** rows in the case (the
  snapshot's own, or its other kept ones) also wrote them,
  counted only among those the loader may read (a link kept because another case's row or another
  load holds it is kept and never counted, as `_count_hidden_merges` withholds a merge); and the
  dropped keys kept before rows recorded what they wrote, which are left in place.

The questions it asks of the ledger are `WithdrawalLedger`'s, which `RecipeRunStore` answers
(`services/api/recipe_runs.py`) and `LedgerSink` passes through."""

from __future__ import annotations

import asyncio
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from ports.graph import GraphPort
from schemas.domain import Principal
from schemas.ingest import LoadReport, Recipe

from .engine import row_group_keys


class DroppedRow(Protocol):
    """A kept key a snapshot no longer carries, with its record (`recipe_runs.KeptRow`)."""

    @property
    def row_key(self) -> str: ...

    @property
    def load_id(self) -> str: ...

    @property
    def node_ids(self) -> tuple[str, ...] | None: ...

    @property
    def edge_ids(self) -> tuple[str, ...] | None: ...


class WithdrawalLedger(Protocol):
    async def dropped_row_keys(
        self, recipe_id: str, case: str, *, present: Collection[str]
    ) -> Sequence[DroppedRow]: ...

    async def elements_kept_by_other_rows(
        self,
        node_ids: Sequence[str],
        edge_ids: Sequence[str],
        *,
        recipe_id: str,
        case: str,
        excluding: Sequence[str],
        only_this_pipeline: bool = False,
    ) -> tuple[set[str], set[str]]: ...

    async def elements_in_other_records(
        self, node_ids: Sequence[str], edge_ids: Sequence[str], *, excluding_loads: Sequence[str]
    ) -> tuple[set[str], set[str]]: ...


@dataclass
class Withdrawal:
    """What a full snapshot withdraws: the dropped keys with a record (moved aside by the ledger),
    the nodes and links withdrawn, and the counts its words say."""

    row_keys: list[str] = field(default_factory=list)
    node_ids: list[str] = field(default_factory=list)
    edge_ids: list[str] = field(default_factory=list)
    links_kept: int = 0
    rows_left_in_place: int = 0

    @property
    def notes(self) -> list[str]:
        words: list[str] = []
        if self.links_kept:
            words.append(
                f"{self.links_kept} link{'' if self.links_kept == 1 else 's'} kept an occurrence "
                "from a dropped row"
            )
        if self.rows_left_in_place:
            one = self.rows_left_in_place == 1
            words.append(
                f"{self.rows_left_in_place} dropped row{'' if one else 's'} "
                f"{'was' if one else 'were'} loaded before rows recorded what they wrote, and "
                f"{'was' if one else 'were'} left in place"
            )
        return words


async def plan_withdrawal(
    recipe: Recipe,
    rows: Sequence[dict[str, str]],
    report: LoadReport,
    *,
    case: str,
    ledger: WithdrawalLedger,
    graph: GraphPort,
    principal: Principal,
) -> Withdrawal:
    """Which links the snapshot's dropped rows withdraw, never a node (the module docstring has the
    rule).
    `report` is the snapshot's own load, written and not yet committed; `rows` every row it read."""
    present = await asyncio.to_thread(
        lambda: {k for k in row_group_keys(recipe, rows) if k is not None}
    )
    dropped = await ledger.dropped_row_keys(recipe.id, case, present=present)
    recorded = [d for d in dropped if d.node_ids is not None and d.edge_ids is not None]
    plan = Withdrawal(
        row_keys=[d.row_key for d in recorded], rows_left_in_place=len(dropped) - len(recorded)
    )
    if not recorded:
        return plan
    nodes = list(dict.fromkeys(n for d in recorded for n in d.node_ids or ()))
    edges = list(dict.fromkeys(e for d in recorded for e in d.edge_ids or ()))

    by_rows = await ledger.elements_kept_by_other_rows(
        nodes, edges, recipe_id=recipe.id, case=case, excluding=[d.row_key for d in dropped]
    )
    own_edges = {
        *report.touched_edge_ids,
        *(x for e in report.kept_row_elements.values() for x in e.edge_ids),
    }
    by_records = await ledger.elements_in_other_records(
        nodes,
        edges,
        excluding_loads=sorted({d.load_id for d in dropped} | {report.load_id}),
    )
    kept_edges = (by_rows[1] | own_edges | by_records[1]) & set(edges)
    plan.edge_ids = [e for e in edges if e not in kept_edges]
    # Counted only from this pipeline's own rows in this case (the snapshot's and its kept ones),
    # and only what the loader may read: a link kept because another case's or another pipeline's
    # row, or another load, holds it changes no figure (Amendment 15).
    own_rows = await ledger.elements_kept_by_other_rows(
        [], edges, recipe_id=recipe.id, case=case, excluding=[d.row_key for d in dropped],
        only_this_pipeline=True,
    )  # fmt: skip
    rewritten = (own_rows[1] | own_edges) & set(edges)
    if rewritten:
        plan.links_kept = len(await graph.get_edges(sorted(rewritten), principal))
    # Amendment 15: nodes are never withdrawn, whatever rests on them.
    plan.node_ids = []
    return plan
