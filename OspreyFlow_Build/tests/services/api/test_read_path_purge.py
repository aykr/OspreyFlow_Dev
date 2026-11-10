"""L2.10's carry from L2.8b (`process/07_BUILD_PLAN.md` row L2.10): an alert repointed by a settle on
a read path (after a failure between the graph commit and the repoint) kept any working-set copy of
its node at the old marking until the canvas next synchronised, because the settle held no working
set. The settle (`alerts.settle_repoints`) now purges what it re-marked at once, through the
working-set service the app gives the store, published to the connected canvases as every purge
is (`purge_copies`).

Red with the purge removed from `settle_repoints`: the copy stays and the record stays open.
"""

from __future__ import annotations

from typing import Any

from services.api.alerts import settle_repoints


class _Store:
    """The alert store's settle and purge records, as the real one answers them: one record whose
    settle re-marked an alert's node, waiting for its purge."""

    def __init__(self, working_set: Any) -> None:
        self.working_set = working_set
        self.settled = 0
        self.closed: list[str] = []
        self.waiting = [("rec-1", ["alert-node-old"])]

    async def settle_pending(self, graph: Any) -> None:
        self.settled += 1

    async def applied_purges(self) -> list[tuple[str, list[str]]]:
        return [w for w in self.waiting if w[0] not in self.closed]

    async def purged(self, record_id: str) -> None:
        self.closed.append(record_id)


class _WorkingSet:
    """The service's removal, as `working_set_revert.remove_and_publish` calls it."""

    publisher = None

    def __init__(self) -> None:
        self.removed: list[list[str]] = []

    async def remove_reverted(self, nodes: list[str], edges: list[str]) -> list[Any]:
        self.removed.append(list(nodes))
        return []


async def test_a_settle_on_a_read_path_purges_the_copies_it_re_marked_at_once() -> None:
    working_set = _WorkingSet()
    store = _Store(working_set)
    await settle_repoints(store, graph=None)  # type: ignore[arg-type]
    assert store.settled == 1
    assert working_set.removed == [["alert-node-old"]], "the old-marking copy leaves the working sets"
    assert store.closed == ["rec-1"], "and its record is closed once purged"


async def test_a_store_given_no_working_set_leaves_the_purge_to_the_next_working_set_read() -> None:
    store = _Store(None)
    await settle_repoints(store, graph=None)  # type: ignore[arg-type]
    assert store.closed == []
