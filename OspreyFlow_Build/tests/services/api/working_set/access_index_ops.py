"""Random store operations and the check that the access index still says what the bodies say.

Shared by `test_access_index.py` (the in-memory fake) and `../test_valkey_store.py` (the real
store, live). Not a test file: it holds no `test_` function.
"""

from __future__ import annotations

import random
from typing import Any

from services.api.working_set.access_index import (
    ABSENT,
    build_counted_index,
    counted_index_differences,
)

from schemas.domain import Edge, Handling, Node

from .test_visible_link import edge, node

CLASSIFICATIONS = ["OFFICIAL", "SECRET"]
UNITS = ["unit-1", "unit-2"]
DATASET_SETS: list[list[str]] = [[], ["enron"], ["fixture"], ["enron", "fixture"]]
NODE_IDS = [f"n{i}" for i in range(8)]
EDGE_IDS = [f"e{i}" for i in range(10)]


def random_node(rng: random.Random, node_id: str) -> Node:
    """A node with this id and a random access signature, so adding it again replaces the old."""
    made = node(node_id, rng.choice(CLASSIFICATIONS))
    return made.model_copy(
        update={
            "handling": Handling(
                classification=made.handling.classification,
                handling_code=rng.choice(["P", "C"]),
                originator=rng.choice(UNITS),
                owning_unit=rng.choice(UNITS),
            ),
            "datasets": rng.choice(DATASET_SETS),
        }
    )


def random_edge(rng: random.Random, edge_id: str) -> Edge:
    """A link with this id, random ends (one may not be stored at all) and a random signature."""
    made = edge(
        edge_id, rng.choice(NODE_IDS + ["gone"]), rng.choice(NODE_IDS), rng.choice(CLASSIFICATIONS)
    )
    return made.model_copy(
        update={
            "handling": Handling(
                classification=made.handling.classification,
                handling_code=rng.choice(["P", "C"]),
                originator=rng.choice(UNITS),
                owning_unit=rng.choice(UNITS),
            ),
            "datasets": rng.choice(DATASET_SETS),
        }
    )


async def apply_random_operation(store: Any, case: str, rng: random.Random) -> str:
    """One add, replace, remove or clear, and its name. An add of an id already held is a replace:
    the same id with another signature."""
    kind = rng.choices(
        ["add_nodes", "add_edges", "remove_nodes", "remove_edges", "clear"],
        weights=[30, 30, 15, 15, 2],
    )[0]
    if kind == "add_nodes":
        await store.add_nodes(
            case, [random_node(rng, i) for i in rng.sample(NODE_IDS, rng.randint(1, 4))]
        )
    elif kind == "add_edges":
        await store.add_edges(
            case, [random_edge(rng, i) for i in rng.sample(EDGE_IDS, rng.randint(1, 4))]
        )
    elif kind == "remove_nodes":
        await store.remove_nodes(case, rng.sample(NODE_IDS, rng.randint(1, 4)))
    elif kind == "remove_edges":
        await store.remove_edges(case, rng.sample(EDGE_IDS, rng.randint(1, 4)))
    else:
        await store.clear(case)
    return kind


async def assert_index_matches_bodies(store: Any, case: str, context: str = "") -> None:
    """Everything the store's index holds (the signatures, the counts of nodes and of links by
    triple, each element's entry, the adjacency) equals what its bodies say it should be. The store
    is read directly: `counted_index` on the fake, `read_counted_index` on the Valkey store."""
    expected = build_counted_index(
        await store.source_fidelity_nodes(case), await store.source_fidelity_edges(case)
    )
    read = getattr(store, "counted_index", None) or store.read_counted_index
    actual = await read(case)
    differences = counted_index_differences(actual, expected)
    assert differences == [], (context, differences)


def a_dangling_triple_is_counted(index_edge_counts: dict[tuple[str, str, str], int]) -> bool:
    """Whether any link is counted with an end that is not stored: which a node's removal makes."""
    return any(ABSENT in (a, b) for (_, a, b) in index_edge_counts)
