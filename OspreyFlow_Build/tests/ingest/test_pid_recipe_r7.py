"""R7, `pid-prisoner-money` (ADR-127 decision 12): one row per transfer from an outside payer to a
prisoner's private-cash account, on Brief 1's real file, loaded after R11, R1 and R3 as the seed
loads them. Every expectation comes from `pid_plan`. Both accounts are `Endpoint`s of kind
`account` (not a FIBO account), read through `account_ref`; the payer is the outside person R3's
visitors are, found on their NINO, so one person is one node across the two files. What a mistake
would do, and the case that catches it:

- an account made twice, or not through `account_ref`, or the payer's account `SYN-70417` not as the
  plan has it (`test_every_account_is_one_endpoint_as_the_plan_holds_it`);
- a payer made again instead of found, so one person is two nodes
  (`test_the_payer_is_the_person_the_visits_file_made`);
- a person not joined to their account (`test_every_person_uses_their_account`);
- a transfer lost, its amount or type wrong, or not at its time
  (`test_every_transfer_is_a_transacted_link_with_its_amount_and_time`);
- an element at a marking other than the first creating row's, as the plan's rows replayed in the
  seed's order give it (`test_every_element_carries_the_marking_its_first_row_gives`);
- a re-run adding anything (`test_a_second_run_creates_nothing`)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pytest

from tests.ingest.pid_golden_support import (
    CASE,
    PLAN,
    assert_exact_instants,
    assert_loaded_markings,
    keys_in,
    load,
    loaded,
    replay,
    rows_of,
)
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    local_staging,
)
from tests.ingest.test_row_keys import KeyStore, Sink

FILE = "pid_prisoner_money.csv"
BEFORE = ("pid_establishment_plan.csv", "pid_nomis_prisoners.csv", "pid_nomis_visits.csv")
PAYER_ACCOUNT = "SYN-70417"


@pytest.fixture(scope="module")
async def money() -> tuple[MergingGraph, KeyStore, Any, list[Any], int]:
    graph, store, _ = await loaded(*BEFORE)
    people = len([n for n in graph.committed_nodes if n.type == "Person"])
    report, events = await load(graph, FILE, Sink(store, CASE))
    assert report.rejections == [], report.rejections[:3]
    return graph, store, report, events, people


def _planned(kind: str) -> list[Any]:
    _, link_keys = keys_in(FILE)
    wanted = set(link_keys)
    return [lk for lk in PLAN.links if lk.key in wanted and lk.link_type == kind]


def _accounts(graph: MergingGraph) -> dict[str, Any]:
    return {
        str(n.properties["value_normalised"]): n
        for n in graph.committed_nodes
        if n.type == "Endpoint" and n.properties.get("endpoint_kind") == "account"
    }


def _label(graph: MergingGraph) -> dict[str, str]:
    return {
        n.id: str(
            n.properties.get(
                "value_normalised", n.properties.get("nino", n.properties.get("prison_number"))
            )
        )
        for n in graph.committed_nodes
        if n.type in ("Endpoint", "Person")
    }


async def test_every_account_is_one_endpoint_as_the_plan_holds_it(
    money: tuple[MergingGraph, KeyStore, Any, list[Any], int],
) -> None:
    graph, _store, report, _events, _people = money
    keys, _ = keys_in(FILE)
    planned = [PLAN.entity(k) for k in keys]
    stored = _accounts(graph)
    assert set(stored) == {str(e.properties["value_normalised"]) for e in planned}
    assert len(stored) == len(planned) == 341
    for entity in planned:
        node = stored[str(entity.properties["value_normalised"])]
        assert node.properties == dict(entity.properties), entity.key
        assert node.properties["endpoint_kind"] == "account", entity.key
    assert (
        PAYER_ACCOUNT in stored and stored[PAYER_ACCOUNT].properties["value_raw"] == PAYER_ACCOUNT
    )
    assert report.nodes_created == len(planned) + 0, "no person is made here"


async def test_the_payer_is_the_person_the_visits_file_made(
    money: tuple[MergingGraph, KeyStore, Any, list[Any], int],
) -> None:
    graph, _store, report, _events, people_before = money
    people = [n for n in graph.committed_nodes if n.type == "Person"]
    assert len(people) == people_before, "a payer or a payee was made again"
    ninos = [str(n.properties["nino"]) for n in people if "nino" in n.properties]
    assert len(ninos) == len(set(ninos)), "one outside person is two nodes"
    payers = {r["payer_nino"] for r in rows_of(FILE)}
    assert payers and payers <= set(ninos)
    assert report.nodes_created == len(_accounts(graph)), "only the accounts are new"


async def test_every_person_uses_their_account(
    money: tuple[MergingGraph, KeyStore, Any, list[Any], int],
) -> None:
    graph, _store, _report, _events, _people = money
    names = _label(graph)
    stored = {
        (names[e.source], names[e.target]): e
        for e in graph.committed_edges
        if e.type == "USES" and names[e.target] in _accounts(graph)
    }

    def person(key: str) -> str:
        props = PLAN.entity(key).properties
        return str(props.get("nino", props.get("prison_number")))

    planned = {
        (person(lk.source), str(PLAN.entity(lk.target).properties["value_normalised"])): lk
        for lk in _planned("USES")
    }
    assert set(stored) == set(planned) and len(planned) == 341
    for pair, lk in planned.items():
        assert stored[pair].properties == dict(lk.properties) == {}, pair
        assert stored[pair].occurrences == lk.occurrences, pair
    assert any(a == PAYER_ACCOUNT for _, a in planned), "the payer's account is used by someone"


async def test_every_transfer_is_a_transacted_link_with_its_amount_and_time(
    money: tuple[MergingGraph, KeyStore, Any, list[Any], int],
) -> None:
    graph, _store, report, events, _people = money
    names = _label(graph)
    stored = {
        (names[e.source], names[e.target]): e
        for e in graph.committed_edges
        if e.type == "TRANSACTED"
    }
    planned = {
        (
            str(PLAN.entity(lk.source).properties["value_normalised"]),
            str(PLAN.entity(lk.target).properties["value_normalised"]),
        ): lk
        for lk in _planned("TRANSACTED")
    }
    assert set(stored) == set(planned) and len(planned) == 273
    assert len(events) == sum(lk.occurrences for lk in planned.values()) == len(rows_of(FILE))
    instants: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for event in events:
        instants[(names[event.source_id], names[event.target_id])].append(event.occurred_at)
    ids = defaultdict(set)
    for row in rows_of(FILE):
        ids[(row["payer_account"].upper(), row["payee_account"].upper())].add(row["transfer_id"])
    for pair, lk in planned.items():
        edge = stored[pair]
        assert edge.properties == dict(lk.properties), pair
        assert edge.properties["transaction_type"] == "TRANSFER"
        assert edge.occurrences == lk.occurrences == len(ids[pair]) == len(instants[pair]), pair
        seen = sorted(instants[pair])
        assert_exact_instants(lk, seen)
        assert edge.interval is not None
        assert (edge.interval.valid_from, edge.interval.valid_to) == (seen[0], seen[-1]), pair
    assert any(pair[0] == PAYER_ACCOUNT for pair in planned), "the payer's account pays"


async def test_every_element_carries_the_marking_its_first_row_gives(
    money: tuple[MergingGraph, KeyStore, Any, list[Any], int],
) -> None:
    """ADR-127 Amendment 18: an element several rows name is created at the marking of the first
    row, in the seed's load order, that creates it. The plan's own rows are replayed in that order
    (R11, R1, R3, then this file), through the store's merge rule for a link, and every node and
    link stored is held to the result; the relay cash accounts and their `USES` links among them."""
    graph, _store, _report, _events, _people = money
    assert_loaded_markings(graph, replay(*BEFORE, FILE))


async def test_an_account_written_with_spaces_or_lower_case_is_the_same_endpoint() -> None:
    """`account_ref` trims, drops inner spaces and upper-cases, so the payer's account written
    `syn-70417` or ` SYN-70 417 ` is the node already there, and the first raw form stays the plan's.
    Brief 1's file writes every reference in its one form, so the variants are planted here, on a
    graph of this test's own: the module's is not touched."""
    graph, store, _ = await loaded(*BEFORE, FILE)
    base = rows_of(FILE)[0]
    assert base["payer_account"] == PAYER_ACCOUNT
    planted = [
        {**base, "transfer_id": "TRF-planted-0001", "payer_account": "syn-70417"},
        {**base, "transfer_id": "TRF-planted-0002", "payer_account": " SYN-70 417 "},
        {**base, "transfer_id": "TRF-planted-0003", "payee_account": base["payee_account"].lower()},
    ]
    before = len(_accounts(graph))
    report, _events2 = await load(graph, FILE, Sink(store, CASE), "load-forms", rows=planted)
    assert report.rejections == [], report.rejections[:3]
    assert report.nodes_created == 0
    assert len(_accounts(graph)) == before, "an account written another way is a second Endpoint"
    assert _accounts(graph)[PAYER_ACCOUNT].properties["value_raw"] == PAYER_ACCOUNT


async def test_a_second_run_creates_nothing(
    money: tuple[MergingGraph, KeyStore, Any, list[Any], int],
) -> None:
    graph, store, _report, _events, _people = money
    before = (len(graph.committed_nodes), len(graph.committed_edges))
    second, events = await load(graph, FILE, Sink(store, CASE), "load-2")
    assert second.rows_already_loaded == len(rows_of(FILE))
    assert (second.nodes_created, second.edges_created, events) == (0, 0, [])
    assert (len(graph.committed_nodes), len(graph.committed_edges)) == before
