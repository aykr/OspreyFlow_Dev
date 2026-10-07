"""`scripts.stamp_datasets` against a real ArcadeDB (ADR-099 step 3): a store loaded before ADR-099
is given its datasets, so the owner's deployment needs no re-seed.

What a mistake here would do, and the case that catches it (all in
`test_a_store_loaded_before_adr_099_is_given_its_datasets`, run on one small store in the shapes
the owner's holds):

- a seed's data left in no dataset, so every case on it reads nothing (the Enron and Fixture Corp
  elements, found by their provenance source);
- a case left reading nothing, or another case's data (the Enron case by its name, Fixture Corp's
  by its load id, a branch by its parent, an empty case given one of its own);
- what an analyst marked or accepted before ADR-099 vanishing from the canvas (the Conduit-written
  node on the Enron canvas, and the working set's own copies, which the canvas is drawn from);
- a dry run that writes (`test_a_dry_run_writes_nothing`), and a second run that adds a dataset
  twice (`test_running_it_again_changes_nothing`).

The SQL it runs was chosen by measurement: `datasets.append(x)` on ArcadeDB 25.5.1 turns the list
into a string, so a test reading back only "is the dataset there" by substring could pass on a
corrupted store; these read the list itself.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from scripts.stamp_datasets import CaseRow, StampReport, _Sql, stamp
from services.api.datasets import InMemoryDatasetStore

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_edge_id, new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    AuditStub,
    EdgeWrite,
    Handling,
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from tests.services.api.working_set.fakes import FakeWorkingSetStore

ONTOLOGY = load_default_ontology()
EVERYONE = Principal(id="reader", clearance="SECRET", org_unit="unit-1")
NOW = datetime(2026, 10, 1, tzinfo=UTC)
HANDLING = Handling(
    classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
)
ENRON_CASE = CaseRow("case-enron", "Enron corpus (real data, this machine only)", "unit-1", None)
FIXTURE_CASE = CaseRow("case-fixture", "Fixture Corp (synthetic demo)", "unit-1", None)
BRANCH = CaseRow("case-branch", "Branch of Fixture Corp", "unit-1", "case-fixture")
SCRATCH = CaseRow("case-scratch", "Scratch", "unit-1", None)
#: Seen on the owner's deployment: the HMP seed's load ids do not name its case, so with an empty
#: canvas only its case name says what it holds.
HMP_CASE = CaseRow("case-hmp", "HMP fixture (synthetic demo)", "unit-1", None)
CASES = [BRANCH, ENRON_CASE, FIXTURE_CASE, SCRATCH, HMP_CASE]  # a branch before its parent


def _person(source: str, *, load_id: str | None = None) -> NodeWrite:
    return NodeWrite(
        id=new_id(),
        type="Person",
        properties={"family_name": "Stamp"},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id=source, locator="row", excerpt_hash="")],
            first_seen=NOW,
        ),
        handling=HANDLING,
        created_by="seed",
        created_at=NOW,
        load_id=load_id,
    )


def _link(source: str, target: str, origin: str) -> EdgeWrite:
    return EdgeWrite(
        id=new_edge_id(),
        type="ASSOCIATE_OF",
        source=source,
        target=target,
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id=origin, locator="row", excerpt_hash="")],
            first_seen=NOW,
        ),
        handling=HANDLING,
        created_by="seed",
        created_at=NOW,
    )


def _body(write: NodeWrite) -> Node:
    return Node(
        id=write.id,
        type=write.type,
        properties=write.properties,
        provenance=write.provenance,
        handling=write.handling,
        audit=AuditStub(created_at=NOW, created_by="seed"),
    )


class _Store:
    def __init__(self, graph: GraphArcadeDBAdapter) -> None:
        self.graph = graph
        self.sql = _Sql(graph._client)  # noqa: SLF001 - the script's own SQL, on the test database
        self.datasets = InMemoryDatasetStore()
        self.working_sets = FakeWorkingSetStore()
        self.ids: dict[str, str] = {}

    async def load_as_before_adr_099(self) -> None:
        enron_a, enron_b = _person("enron-corpus"), _person("enron-corpus")
        fixture = _person("fixture-corp", load_id=f"fixture-corp:{FIXTURE_CASE.id}")
        marked = _person("email:ev-1")  # marked by hand on the Enron canvas, before ADR-099
        stray = _person("somewhere-else")  # in no case at all
        # Seen on the owner's deployment: the HMP seed loads through the Studio, whose rows name
        # their file after the seed's source, so an exact match missed 1,600 of its elements.
        studio_hmp = _person("hmp-fixture:persons.csv")
        lookalike = _person("hmp-fixturex")  # a different source that merely starts the same
        link = _link(enron_a.id, enron_b.id, "enron-corpus")
        tx = await self.graph.begin_transaction()
        await self.graph.upsert_nodes(
            [enron_a, enron_b, fixture, marked, stray, studio_hmp, lookalike], tx
        )
        await self.graph.upsert_edges([link], tx)
        await self.graph.commit_transaction(tx)
        self.ids = {
            "enron_a": enron_a.id,
            "enron_b": enron_b.id,
            "fixture": fixture.id,
            "marked": marked.id,
            "stray": stray.id,
            "studio_hmp": studio_hmp.id,
            "lookalike": lookalike.id,
            "link": link.id,
        }
        await self.working_sets.add_nodes(ENRON_CASE.id, [_body(enron_a), _body(marked)])
        await self.working_sets.add_nodes(FIXTURE_CASE.id, [_body(fixture)])
        await self.working_sets.add_nodes(BRANCH.id, [_body(fixture)])

    async def run(self, *, write: bool = True) -> StampReport:
        return await stamp(
            sql=self.sql,
            ontology=ONTOLOGY,
            datasets=self.datasets,
            working_sets=self.working_sets,
            cases=CASES,
            org_unit="unit-1",
            write=write,
            say=lambda _line: None,
        )

    async def datasets_of(self, key: str) -> list[str]:
        node = await self.graph.get_node(self.ids[key], EVERYONE)
        assert node is not None
        return sorted(node.datasets)


@pytest.fixture
async def store() -> AsyncIterator[_Store]:
    async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
        held = _Store(graph)
        await held.load_as_before_adr_099()
        yield held


async def test_a_store_loaded_before_adr_099_is_given_its_datasets(store: _Store) -> None:
    report = await store.run()

    assert await store.datasets_of("enron_a") == ["enron"]
    assert await store.datasets_of("fixture") == ["fixture-corp"]
    (link,) = await store.graph.edges_among(
        [store.ids["enron_a"], store.ids["enron_b"]],
        EVERYONE.model_copy(update={"datasets": ["enron"]}),
    )
    assert link.datasets == ["enron"]

    assert await store.datasets.ids_of_case(ENRON_CASE.id) == ["enron"]
    assert await store.datasets.ids_of_case(FIXTURE_CASE.id) == ["fixture-corp"]
    assert await store.datasets.ids_of_case(BRANCH.id) == ["fixture-corp"]
    assert await store.datasets.ids_of_case(HMP_CASE.id) == ["hmp"]
    (own,) = await store.datasets.of_case(SCRATCH.id)
    assert own.name == "Scratch" and own.owning_unit == "unit-1"

    # Marked by hand on the Enron canvas: now in the Enron case's dataset, in the graph and in the
    # working set's copy the canvas is drawn from.
    assert await store.datasets_of("marked") == ["enron"]
    copies = await store.working_sets.source_fidelity_nodes(ENRON_CASE.id)
    assert {n.id: n.datasets for n in copies.values()} == {
        store.ids["enron_a"]: ["enron"],
        store.ids["marked"]: ["enron"],
    }

    assert await store.datasets_of("studio_hmp") == ["hmp"]

    # In no case: left in no dataset, and said so.
    assert await store.datasets_of("stray") == []
    assert await store.datasets_of("lookalike") == []
    assert report.unstamped == {"Person": 2}


async def test_a_dry_run_writes_nothing(store: _Store) -> None:
    report = await store.run(write=False)
    assert report.stamped_by_source["enron"] == 3  # two people and their link, found
    assert await store.datasets_of("enron_a") == []
    assert await store.datasets.ids_of_case(ENRON_CASE.id) == []
    assert store.datasets.datasets == {}


async def test_running_it_again_changes_nothing(store: _Store) -> None:
    await store.run()
    first = {case.id: await store.datasets.ids_of_case(case.id) for case in CASES}
    again = await store.run()
    assert {case.id: await store.datasets.ids_of_case(case.id) for case in CASES} == first
    assert again.stamped_by_source == {d: 0 for d in again.stamped_by_source}
    assert await store.datasets_of("enron_a") == ["enron"]
    assert again.own_datasets_made == []


def test_every_seeds_case_name_is_known_to_the_stamping() -> None:
    """The case each seed makes (`seed_internal.DATASETS`, host-side) is recognised by name by the
    stamping (`demo_fixtures.datasets`, in the image), so a seed whose load ids do not name its
    case is still read by it, and the two lists cannot drift apart."""
    from scripts.seed_internal import DATASETS
    from scripts.stamp_datasets import SEED_CASE_NAMES

    assert {
        name: SEED_CASE_NAMES.get(name) for name in (d.case_name for d in DATASETS.values())
    } == {d.case_name: key for key, d in DATASETS.items()}


def test_the_seeds_unit_is_the_one_every_case_is_in_unless_told() -> None:
    from scripts.stamp_datasets import unit_for

    verify = [CaseRow("a", "A", "verify", None), CaseRow("b", "B", "verify", None)]
    assert unit_for(None, verify) == "verify"
    assert unit_for("unit-1", verify) == "unit-1"
    with pytest.raises(SystemExit, match="more than one unit"):
        unit_for(None, [*verify, CaseRow("c", "C", "unit-2", None)])

