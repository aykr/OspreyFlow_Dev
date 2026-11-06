"""A full snapshot's withdrawal of its dropped rows (`06_DECISIONS.md` ADR-110 Amendment 8 point 3).

A source refreshed as a *full snapshot* with *withdraw* reads the whole table each time; a row a
pipeline kept for the case that the snapshot no longer carries is *dropped*, and its elements are
withdrawn (`GraphPort.withdraw_elements`), in the refresh's own graph transaction, before it
commits. `plan_withdrawal` decides which:

- **the dropped keys**: the pipeline's kept keys for the case that no row of the snapshot carries
  (a held or rejected row still carries its key, so it is not dropped);
- **their elements**, from each key's record (Amendment 8 point 2), less every one that is also:
  in another kept row's record (any pipeline, any case); written or matched by the snapshot's own
  rows; listed by an unreverted load's record other than the ones that kept the dropped keys; or,
  for a node, an end of a live link that is not being withdrawn (`GraphPort.live_edges_touching`,
  which catches a load that keeps no keys);
- **what it says** (`Withdrawal.notes`), in words, never silently: the links kept because a kept
  row also wrote them, counted only among those the loader may read (rule 3: a link they may not
  read is kept and not counted, as `_count_hidden_merges` withholds a merge); and the dropped keys
  kept before rows recorded what they wrote, which are left in place.

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
    """Which elements the snapshot's dropped rows withdraw (the module docstring has the rule).
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
    own_nodes = {
        *report.created_node_ids,
        *report.referenced_node_ids,
        *report.merged_node_ids,
        *(n for e in report.kept_row_elements.values() for n in e.node_ids),
    }
    own_edges = {
        *report.touched_edge_ids,
        *(x for e in report.kept_row_elements.values() for x in e.edge_ids),
    }
    by_records = await ledger.elements_in_other_records(
        nodes,
        edges,
        excluding_loads=sorted({d.load_id for d in dropped} | {report.load_id}),
    )
    kept_by_rows = (by_rows[1] | own_edges) & set(edges)
    kept_edges = kept_by_rows | by_records[1]
    plan.edge_ids = [e for e in edges if e not in kept_edges]
    if kept_by_rows:
        readable = await graph.get_edges(sorted(kept_by_rows), principal)
        plan.links_kept = len(readable)

    candidates = [n for n in nodes if n not in by_rows[0] | own_nodes | by_records[0]]
    withdrawn_edges = set(plan.edge_ids)
    # One question for every candidate; only if a live link outside the withdrawal touches one of
    # them is each asked alone, to find which. Unmeasured for a large drop with many such links.
    foreign = await graph.live_edges_touching(candidates) - withdrawn_edges if candidates else set()
    if foreign:
        resting: set[str] = set()
        for node in candidates:
            if await graph.live_edges_touching([node]) - withdrawn_edges:
                resting.add(node)
        candidates = [n for n in candidates if n not in resting]
    plan.node_ids = candidates
    return plan
