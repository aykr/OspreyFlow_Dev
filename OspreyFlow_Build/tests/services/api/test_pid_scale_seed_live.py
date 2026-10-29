"""The scale cohort's seed against a real ArcadeDB (the throwaway one), ADR-127 Amendment 40,
"Tests that would fail": `scripts.seed_pid_scale.seed_scale` into a fresh database.

**Live, and slow** (30,000 links through the bulk loader). Like `test_pid_access_control.py`, it
uses `arcadedb_adapter` directly (a fresh database, dropped afterwards) with the composed
ontology (core and NIEM) and the UK handling scheme, and the adapter wrapped in `stamping` for the
scale dataset as the seed wraps it. It needs the throwaway stack, so the coordinator runs it
(rule 14).

What each test proves:

- **The case reads the cohort.** A principal whose case reads only `prison-intelligence-scale`
  sees 7,176 nodes and 30,000 links, counted in the store with the access step.
- **Rule 4, a read path.** A principal whose case reads only `prison-intelligence` sees none of
  them: no node, no link, and the first prisoner is not found by id.
- **Safe to run again.** A second `seed_scale` says the cohort is here, writes nothing and leaves
  both counts as they were.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from scripts.seed_pid_scale import SeedResult, seed_scale
from services.api.dataset_scope import stamping

from adapters.graph_arcadedb.testing import arcadedb_adapter
from demo_fixtures import pid_plan
from demo_fixtures.datasets import PID, PID_SCALE
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.domain import Principal

pytestmark = pytest.mark.asyncio(loop_scope="module")

ONTOLOGY = load_deployment_ontology()
SCHEME = load_uk_le_scheme()
LOCAL = pid_plan.LOCAL_UNIT

SEEDER = Principal(id="pid-scale-seed-worker", clearance="OFFICIAL", org_unit=LOCAL)
#: A principal whose case reads the scale dataset alone, and one whose case reads the demo's alone.
SCALE_READER = Principal(
    id="pid-scale-reader", clearance="OFFICIAL", org_unit=LOCAL, datasets=[PID_SCALE.id]
)
DEMO_READER = Principal(
    id="pid-demo-reader", clearance="OFFICIAL", org_unit=LOCAL, datasets=[PID.id]
)
CREATED = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)


def first_prisoner_id() -> str:
    """The store id of the scale plan's first prisoner."""
    plan = pid_plan.build_plan("scale")
    key = next(
        e.key
        for e in plan.entities
        if e.entity_type == "Person" and "prison_number" in e.properties
    )
    return pid_plan.node_id(key)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def raw() -> AsyncIterator[Any]:
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        yield graph


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def seeded(raw: Any) -> tuple[Any, SeedResult]:
    graph = stamping(raw, dataset=PID_SCALE.id)
    return graph, await seed_scale(graph, SEEDER, created_at=CREATED)


async def _counts(graph: Any, principal: Principal) -> tuple[int, int]:
    """(nodes, links) the principal reads, counted in the store."""
    counts = await graph.type_counts(principal)
    return sum(counts.nodes.values()), sum(counts.edges.values())


async def test_the_first_run_writes_the_whole_cohort(seeded: tuple[Any, SeedResult]) -> None:
    _, result = seeded
    assert (result.nodes, result.links, result.already_here) == (7_176, 30_000, False)


async def test_a_principal_whose_case_reads_the_scale_dataset_reads_all_of_it(
    seeded: tuple[Any, SeedResult],
) -> None:
    graph, _ = seeded
    assert await _counts(graph, SCALE_READER) == (7_176, 30_000)
    found = await graph.get_nodes([first_prisoner_id()], SCALE_READER)
    assert [n.datasets for n in found] == [[PID_SCALE.id]]


async def test_a_principal_whose_case_reads_only_the_demo_dataset_reads_none_of_it(
    seeded: tuple[Any, SeedResult],
) -> None:
    """Rule 4: an unauthorised principal finds no node, no link and no count."""
    graph, _ = seeded
    assert await _counts(graph, DEMO_READER) == (0, 0)
    assert await graph.get_nodes([first_prisoner_id()], DEMO_READER) == []
    page = await graph.busiest_links(DEMO_READER, limit=10, offset=0)
    assert page.total == 0 and not page.links


async def test_a_second_run_says_it_is_here_and_leaves_the_counts_unchanged(
    seeded: tuple[Any, SeedResult],
) -> None:
    graph, _ = seeded
    before = await _counts(graph, SCALE_READER)
    again = await seed_scale(graph, SEEDER, created_at=CREATED)
    assert (again.nodes, again.links, again.already_here) == (0, 0, True)
    assert await _counts(graph, SCALE_READER) == before == (7_176, 30_000)
    assert await _counts(graph, DEMO_READER) == (0, 0)
