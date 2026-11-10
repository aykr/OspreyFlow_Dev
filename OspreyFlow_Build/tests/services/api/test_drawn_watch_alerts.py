"""A load meeting a drawn item (ADR-143 Amendment 2 decision 8; ADR-146 decision 4; L3.6).

Drawing an item sets a watch for it on the case's dataset (L3.3). After a load into that dataset,
each node it loaded that looks like the drawn item, by the board's own rule (*Looks like a loaded
item*: the same identifier, or a name alike, of the same type), raises one `drawn_watch` alert in
the watch's case, routed as the one queue routes (L2.10, wired when it lands). These cases prove
the run itself, through the board world's fakes (the graph's handling filter is the adapter's, rule
15):

- one alert per match per case, however often a load meets it again (`claim_match`);
- nothing for a loaded node the owner may not see, of another type or unalike, already decided on
  the board, of another dataset, or for a watch ended (its item withdrawn) or an owner gone;
- each case its own alert for the same loaded node.

What a reader of the queue is shown (withheld whole from one who may not see the drawn item: no
count, no bucket) is the queue's read, red at the adapter once L2.10 lands.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from services.api.drawn_watches import DrawnWatchMatch, DrawnWatchRun

from schemas.domain import Principal

from .test_boards import ONTOLOGY, PEOPLE, B, K, _as, _board, _item, _loaded, world  # noqa: F401


@pytest.fixture
def run(world: SimpleNamespace) -> Iterator[SimpleNamespace]:  # noqa: F811
    raised: list[DrawnWatchMatch] = []
    gone: set[str] = set()

    async def owner_of(account: str) -> Principal | None:
        return None if account in gone else PEOPLE.get(account)

    async def case_datasets(case_id: str) -> list[str]:
        return await world.datasets.ids_of_case(case_id)

    async def raise_alert(match: DrawnWatchMatch) -> None:
        raised.append(match)

    yield SimpleNamespace(
        world=world, raised=raised, gone=gone,
        run=DrawnWatchRun(items=world.items, graph=world.graph, ontology=ONTOLOGY,
                          owner_of=owner_of, case_datasets=case_datasets,
                          raise_alert=raise_alert),
    )  # fmt: skip


def _load(run: SimpleNamespace, node_id: str, marking: str = "OFFICIAL", **props: Any) -> str:
    """A node a load wrote into `src`."""
    run.world.graph._graph_nodes[node_id] = _loaded(node_id, marking, **props)
    return node_id


def _tall(**over: Any) -> dict[str, Any]:
    return _item(_board(), label="Tall", properties={"family_name": "Tall", "pnc_id": "PNC-1"},
                 **over)  # fmt: skip


async def test_a_loaded_node_like_a_drawn_item_raises_one_alert_per_match_per_case(
    run: SimpleNamespace,
) -> None:
    drawn = _tall()
    first = _load(run, "p-new", family_name="Tall", pnc_id="PNC-1")
    assert await run.run.after_load("src", [first], load_id="load-1") == 1
    (match,) = run.raised
    assert (match.watch.case_id, match.drawn.id, match.loaded.id) == (K, drawn["element_id"], first)
    assert (match.score, match.why, match.load_id) == (1.0, "the same pnc_id", "load-1")
    # The same node loaded again: no second alert (one per match per case).
    assert await run.run.after_load("src", [first], load_id="load-2") == 0
    # Another node like it: its own alert.
    second = _load(run, "p-newer", family_name="Tall")
    assert await run.run.after_load("src", [second], load_id="load-3") == 1
    assert [(m.loaded.id, m.why) for m in run.raised[1:]] == [(second, "a name alike")]


async def test_nothing_is_raised_for_a_node_unalike_of_another_type_or_drawn(
    run: SimpleNamespace,
) -> None:
    _tall()
    unalike = _load(run, "p-unalike", family_name="Quite different")
    other_type = _loaded("o-tall").model_copy(
        update={"type": "Organisation", "properties": {"name": "Tall"}}
    )
    run.world.graph._graph_nodes[other_type.id] = other_type
    # Another drawn item, alike it and promoted into `src` (so in the load's dataset): drawn,
    # never loaded, so never a match.
    other_drawn = _item(_board(), label="Tall", properties={"family_name": "Tall"})["element_id"]
    held = run.world.graph._graph_nodes[other_drawn]
    run.world.graph._graph_nodes[other_drawn] = held.model_copy(
        update={"datasets": sorted({*held.datasets, "src"})}
    )
    assert await run.run.after_load("src", [unalike, other_type.id, other_drawn]) == 0
    assert run.raised == []


async def test_nothing_is_raised_for_a_node_the_owner_may_not_see(run: SimpleNamespace) -> None:
    """Bob (OFFICIAL) drew it; a SECRET node alike it is never read for him, so never matched,
    never claimed (rule 3)."""
    _item(_board("bob"), who="bob", label="Tall", properties={"family_name": "Tall"})
    hidden = _load(run, "p-hidden", "SECRET", family_name="Tall")
    assert await run.run.after_load("src", [hidden]) == 0
    assert run.raised == []
    assert run.world.items.matches == {}


async def test_nothing_is_raised_for_another_datasets_load_an_ended_watch_or_an_owner_gone(
    run: SimpleNamespace,
) -> None:
    drawn = _tall()
    alike = _load(run, "p-alike", family_name="Tall", pnc_id="PNC-1")
    assert await run.run.after_load("other", [alike]) == 0  # the watch is on src
    run.gone.add("alice")
    assert await run.run.after_load("src", [alike]) == 0  # its owner no longer resolves
    run.gone.clear()
    withdrawn = _as("alice").post(f"/v1/investigations/{K}/board-items/{drawn['item_id']}/withdraw")
    assert withdrawn.status_code == 200, withdrawn.text
    assert await run.run.after_load("src", [alike]) == 0  # its item withdrawn: the watch ended
    assert run.raised == []


async def test_a_pair_decided_on_the_board_raises_nothing(run: SimpleNamespace) -> None:
    """*Not the same* (or *Same*) already decided between the two: there is nothing to tell."""
    board = _board()
    drawn = _item(board, properties={"family_name": "Mercer", "nino": "AB123456C"})
    decided = _as("alice").post(
        f"/v1/investigations/{K}/boards/{board}/matches",
        json={"drawn": drawn["element_id"], "loaded": "p-loaded", "same": False},
    )
    assert decided.status_code == 201, decided.text
    assert await run.run.after_load("src", ["p-loaded"]) == 0
    assert run.raised == []


async def test_each_case_gets_its_own_alert_for_the_same_loaded_node(run: SimpleNamespace) -> None:
    _tall()
    _item(_board("carol", B), who="carol", case=B, label="Tall",
          properties={"family_name": "Tall"})  # fmt: skip
    alike = _load(run, "p-alike", family_name="Tall")
    assert await run.run.after_load("src", [alike]) == 2
    assert sorted(m.watch.case_id for m in run.raised) == sorted([K, B])
    assert await run.run.after_load("src", [alike]) == 0


async def test_a_load_counted_by_what_it_raised_never_by_what_it_read(
    run: SimpleNamespace,
) -> None:
    """The run says how many alerts it raised, for the run's report; a node read but unmatched,
    or hidden, is not in it (rule 7). Bob (OFFICIAL) drew it."""
    _item(_board("bob"), who="bob", label="Tall", properties={"family_name": "Tall"})
    alike = _load(run, "p-alike", family_name="Tall")
    hidden = _load(run, "p-hidden", "SECRET", family_name="Tall")
    assert await run.run.after_load("src", [alike, hidden, "no-such-node"]) == 1
    assert datetime.now(UTC) >= run.raised[0].matched_at


async def test_nothing_is_raised_once_the_case_reads_the_dataset_no_more(
    run: SimpleNamespace,
) -> None:
    """The watch is on the case's dataset; a case that has moved off it is told nothing of a load
    into it (its readers no longer read it)."""
    _tall()
    alike = _load(run, "p-alike", family_name="Tall", pnc_id="PNC-1")
    run.world.datasets.cases[K] = ["other"]
    assert await run.run.after_load("src", [alike]) == 0
    assert run.raised == []
