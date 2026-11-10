"""Part A2 (the studio lane, L1.2a): does a Studio load leak across cases through the link merge?

ADR-099 decisions 2–4 and ADR-102 Amendment 3: every write names its dataset, a link write merges
only into a link "visible to exactly the same principals, judged by … the same set of datasets",
and a case reads its own datasets alone. The Conduit's graph stamps the request's case's datasets
on every write that names none (`DatasetStampingGraph`, `run_resources.py`). The scheduler gets
there through its own `check_case` (`scope_to_case`), and *Run now* through `get_principal`'s.
Part A's live test drove the raw adapter, so it stamped nothing and needed unconfined principals,
and its known limit said a Studio load stamps no dataset. This file drives the scheduler's real
`check_case` and `run`, over the stamping graph built as the Conduit builds it, with real ArcadeDB
and the real case and dataset stores in Postgres. Every principal is confined, as `scope_to_case`
makes it. The route's own scoping is `test_studio_run_now_stamps_its_case_dataset_live.py`'s.

- **Two cases on two datasets:** the loader's run, its words and what it reads are the same whether
  or not another case loaded the same pair first. The loader reads its own link (the comparison
  never holds over nothing), and neither case reads the other's.
- **Two cases on one dataset:** by design under ADR-102 Amendment 3: a link write merges "only
  when both are visible to exactly the same principals, judged by … the same set of datasets
  (ADR-099)". On two datasets, a confined load matches within its reach alone, so each case writes its own
  nodes and link (ADR-099 Amendment 16). (ADR-143's "joins the source dataset" is not cited: the
  stamp is the case's first dataset until Part C, Amendment 17.) Both rows merge
  into one link, and both cases read the same link, count and occurrences. A third case on another
  dataset reads none of it.

The test is written to `ids_of_case`'s contract (a case's datasets, its first the one it loads
into), not its current body; L3.1's analyst layer adds to a case's read set. It is red with the
raw adapter in place of the stamping graph, and with `scope_to_case` taken out of `check_case`
(`process/lanes/studio/L1.2a_RED_RECORD.md`).

Stand-ins, so the claim is no wider than the test: `_execute_recipe_run` is replaced by
`run_published_recipe` over `deps.graph` (the rule gate, `run_published_pipeline` and the change
stream are not driven); `resolve_source_handling` is patched to the source's marking; the executor's
state answers the run's other dependencies with placeholders; the tick's owners resolve from a list
and its recipes from a list of drafts. The stamping and the confinement are proven up to the recipe
run (ADR-110 Amendment 17)."""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import services.api.app as app_module
import services.api.recipe_run as run_module
from adapters.graph_arcadedb.testing import arcadedb_adapter
from adapters.media_objectstore.testing import InMemoryMediaStore
from conduit_common.identity import new_id
from schemas.domain import ExpandRequest, Principal
from services.api.config import PostgresConfig
from services.api.dataset_scope import stamping
from services.api.datasets import Dataset, PostgresDatasetStore
from services.api.investigations import InvestigationStore
from services.api.load_records import report_view
from services.api.recipe_runs import RecipeRunStore
from services.api.studio_publish import run_published_recipe

from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)
from tests.ingest.test_row_keys import ONTOLOGY, SCHEME, _published_draft, _row
from tests.services.api.test_snapshot_withdrawal_tells_nothing_live import (
    SOURCE,
    _write,
)

PAIR = _row("SYN-1", "SYN-2", 1)
ANOTHER_DAY = _row("SYN-1", "SYN-2", 2)
VALUES = ("SYN-1", "SYN-2")


def fresh_published_draft(path: Path) -> tuple[Path, Any]:
    """`_published_draft`, under a recipe id of its own: the run ledger in Postgres outlives a test,
    and every row-key question is per recipe. Under the shared id, one world would see another
    world's rows, and every earlier session's, as "another case's"."""
    from services.api.studio_publish import serialise_recipe
    from services.ingest.recipe_loader import load_recipe

    repo, draft = _published_draft(path)
    fresh = f"private-cash-{new_id().lower()}"
    recipe = load_recipe(repo / draft.git_path).model_copy(update={"id": fresh})
    git_path = f"recipes/{fresh}.yaml"
    (repo / git_path).write_text(serialise_recipe(recipe))
    return repo, draft.model_copy(update={"recipe_id": fresh, "git_path": git_path})


@pytest.fixture
async def stores() -> AsyncIterator[SimpleNamespace]:
    dsn = PostgresConfig.from_env().dsn
    runs = await RecipeRunStore.connect(dsn)
    cases = await InvestigationStore.connect(dsn)
    datasets = await PostgresDatasetStore.connect(dsn)
    try:
        yield SimpleNamespace(runs=runs, cases=cases, datasets=datasets)
    finally:
        await runs.close()
        await cases.close()
        await datasets.close()


def _loader(name: str) -> Principal:
    return Principal(id=f"{name}-{new_id()}", clearance="SECRET", org_unit="unit-1")


async def _case(stores: SimpleNamespace, who: Principal, dataset: str) -> str:
    """A case `who` authored, loading into `dataset` (its first and only)."""
    case = await stores.cases.create(who, name=f"A2 {new_id()}")
    await stores.datasets.set_for_case(case.id, [dataset], who)
    return case.id


async def _dataset(stores: SimpleNamespace, who: Principal) -> str:
    dataset = Dataset(
        id=new_id(), name=f"A2 data {new_id()}", owning_unit=who.org_unit,
        created_at=datetime.now(UTC), created_by=who.id,
    )  # fmt: skip
    await stores.datasets.add(dataset)
    return dataset.id


@dataclasses.dataclass
class World:
    stores: SimpleNamespace
    graph: Any
    repo: Path
    draft: Any
    monkeypatch: pytest.MonkeyPatch

    def executor(self) -> Any:
        """The scheduler's own executor (`app._schedule_executor`) over this world's stores: its
        `check_case` is the real one, and its `run` the real `run_recipe_as`."""
        names = {f.name for f in dataclasses.fields(run_module.RecipeRunDeps)}
        state = SimpleNamespace(
            **{run_module._RUN_DEP_STATE_NAMES.get(n, n): object() for n in names},
        )
        state.graph = self.graph
        state.recipe_runs = self.stores.runs
        state.media = InMemoryMediaStore()
        state.investigations = self.stores.cases
        state.datasets = self.stores.datasets
        state.studio_recipes = object()
        state.sources = object()
        state.valkey = object()
        state.handling_scheme = SCHEME
        state.run_quotas = None  # no quota set (ADR-141 decision 6)
        state.principal_resolver = SimpleNamespace(resolve_for_owner_detailed=None)
        return app_module._schedule_executor(SimpleNamespace(state=state))  # type: ignore[arg-type]

    async def run(self, who: Principal, case: str, rows: list[dict[str, str]]) -> Any:
        """One run of the published pipeline into `case`, as the scheduler makes it: the owner
        scoped by `check_case`, then `run`, in the one task (so the case's datasets are stamped)."""
        _write(Path(self.draft.source_location), rows)

        async def execute(deps: Any, **kwargs: Any) -> Any:
            # As `_execute_recipe_run` hands the load its graph: `deps.graph`, the Conduit's.
            return await run_published_recipe(
                self.draft, kwargs["principal"], graph=deps.graph, ontology=ONTOLOGY,
                load_id=new_id(), investigation_scope=kwargs["investigation_id"],
                repo_root=self.repo, analytics=None, media=kwargs["media"], scheme=SCHEME,
                sink=kwargs["sink"],
            )  # fmt: skip

        self.monkeypatch.setattr(run_module, "_execute_recipe_run", execute)
        self.monkeypatch.setattr(
            run_module, "resolve_source_handling", lambda draft: SOURCE
        )
        executor = self.executor()
        owner = await executor.check_case(who, case)
        report = await executor.run(owner, self.draft, case, None)
        said = report_view(report, owner, SCHEME).model_dump(
            exclude={"load_id", "recipe_id"}
        )
        if said.get("metering"):
            said["metering"].pop("wall_ms", None)  # the clock, not the data
        return owner, said

    async def reads(self, owner: Principal) -> dict[str, Any]:
        """What `owner` (scoped to its case) reads of the pair: its nodes, and each link with its
        occurrences, by value not id."""
        found = {}
        for value in VALUES:
            node = await self.graph.find_node(
                "Endpoint", "value_normalised", value, owner
            )
            if node is not None:
                found[node.id] = value
        if not found:
            return {"nodes": [], "links": []}
        near = await self.graph.expand(
            ExpandRequest(node_ids=sorted(found), depth=1), owner
        )
        links = sorted(
            (e.type, found.get(e.source, "?"), found.get(e.target, "?"), e.occurrences)
            for e in near.edges
        )
        return {"nodes": sorted(found.values()), "links": links}


async def _in_a_world(
    stores: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> tuple[World, Any]:
    repo, draft = fresh_published_draft(tmp_path / name)
    return World(stores, None, repo, draft, monkeypatch), arcadedb_adapter(
        ONTOLOGY, SCHEME
    )


async def _conduits_graph(raw: Any, stores: SimpleNamespace) -> Any:
    """As `run_resources` builds it: the adapter, stamping, checked against the dataset store."""
    graph = stamping(raw)
    graph.check_against(stores.datasets)
    return graph


async def _loader_alone_or_beside(
    stores: SimpleNamespace,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    beside: bool,
) -> dict[str, Any]:
    name = "beside" if beside else "alone"
    world, opened = await _in_a_world(stores, tmp_path, monkeypatch, name)
    loader, other = _loader("loader"), _loader("other")
    ours = await _case(stores, loader, await _dataset(stores, loader))
    theirs = await _case(stores, other, await _dataset(stores, other))
    async with opened as raw:
        world.graph = await _conduits_graph(raw, stores)
        if beside:
            their_owner, _ = await world.run(other, theirs, [PAIR])
        owner, said = await world.run(loader, ours, [PAIR])
        read = await world.reads(owner)
        their_read = await world.reads(their_owner) if beside else None
    return {"said": said, "read": read, "their_read": their_read}


async def test_a_studio_load_tells_and_shows_its_case_the_same_whatever_another_dataset_holds(
    stores: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    alone = await _loader_alone_or_beside(stores, tmp_path, monkeypatch, beside=False)
    beside = await _loader_alone_or_beside(stores, tmp_path, monkeypatch, beside=True)

    # The loader reads its own nodes and its own link, one occurrence: the comparison is over data.
    assert alone["read"] == {
        "nodes": ["SYN-1", "SYN-2"],
        "links": [("TRANSACTED", "SYN-1", "SYN-2", 1)],
    }, "the loader reads what it loaded"
    assert beside["said"] == alone["said"], "what the run tells its loader"
    assert beside["read"] == alone["read"], "what the loader reads"
    # The other case reads its own link alone, one occurrence: nothing of ours merged into it.
    assert beside["their_read"] == alone["read"], "what the other case reads"


async def test_two_cases_loading_into_one_dataset_read_one_link_and_a_third_reads_none(
    stores: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world, opened = await _in_a_world(stores, tmp_path, monkeypatch, "shared")
    first, second, third = _loader("first"), _loader("second"), _loader("third")
    shared = await _dataset(stores, first)
    one, two = await _case(stores, first, shared), await _case(stores, second, shared)
    elsewhere = await _case(stores, third, await _dataset(stores, third))
    async with opened as raw:
        world.graph = await _conduits_graph(raw, stores)
        one_owner, _ = await world.run(first, one, [PAIR])
        two_owner, _ = await world.run(second, two, [ANOTHER_DAY])
        third_owner = await world.executor().check_case(third, elsewhere)

        one_read, two_read = await world.reads(one_owner), await world.reads(two_owner)
        third_read = await world.reads(third_owner)

    # ADR-102 Amendment 3: one audience (one dataset, one marking), so one link of two occurrences.
    assert (
        one_read
        == two_read
        == {
            "nodes": ["SYN-1", "SYN-2"],
            "links": [("TRANSACTED", "SYN-1", "SYN-2", 2)],
        }
    )
    assert third_read == {"nodes": [], "links": []}, (
        "another dataset's case reads none of it"
    )


async def test_one_tick_stamps_each_scheduled_run_with_its_own_cases_dataset(
    stores: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scheduler itself (`ScheduleExecutor.tick` and `run_now`) over the real `check_case` and
    `run`: `run` scopes nothing of its own, so each run's stamp is whatever its own `_owner` set
    just before it (`_consider_slot`, `run_now`). Two pipelines due in one tick, in two cases on two
    datasets, and a third run now in a third, each read their own link alone. Red if owners are
    resolved for every recipe before any runs (`L1.2a_RED_RECORD.md`). A source refresh through
    `case_for_dataset` is not driven here: this fixture's pipeline names no dataset, which a watch
    refuses."""
    from services.api.config import ValkeyConfig
    from services.api.scheduler import ScheduleExecutor
    from valkey.asyncio import Valkey

    owners = [
        Principal(id=f"owner-{new_id()}", clearance="SECRET", org_unit="unit-1",
                  roles=["source_approver"])
        for _ in range(3)
    ]  # fmt: skip
    cases = [await _case(stores, o, await _dataset(stores, o)) for o in owners]
    set_at, slot = (
        datetime(2026, 6, 1, 12, tzinfo=UTC),
        datetime(2026, 6, 2, 5, tzinfo=UTC),
    )
    published = [fresh_published_draft(tmp_path / f"pipeline-{n}") for n in range(3)]
    repos = {draft.recipe_id: repo for repo, draft in published}
    drafts = [
        draft.model_copy(update={
            "schedule_cron": "0 6 * * *", "schedule_owner": o.id, "schedule_set_at": set_at,
            "schedule_case": case,
        })
        for (_, draft), o, case in zip(published, owners, cases, strict=True)
    ]  # fmt: skip
    for draft in drafts:
        _write(Path(draft.source_location), [PAIR])

    async def execute(deps: Any, **kwargs: Any) -> Any:
        recipe = kwargs["recipe"]
        return await run_published_recipe(
            recipe, kwargs["principal"], graph=deps.graph, ontology=ONTOLOGY, load_id=new_id(),
            investigation_scope=kwargs["investigation_id"], repo_root=repos[recipe.recipe_id],
            analytics=None, media=kwargs["media"], scheme=SCHEME, sink=kwargs["sink"],
        )  # fmt: skip

    monkeypatch.setattr(run_module, "_execute_recipe_run", execute)
    monkeypatch.setattr(run_module, "resolve_source_handling", lambda draft: SOURCE)
    monkeypatch.setattr(
        "services.api.scheduler.resolve_source_handling", lambda draft: SOURCE
    )

    class Due:
        async def scheduled(self) -> list[Any]:
            return drafts[:2]

        async def set_paused(self, *_: Any, **__: Any) -> None:
            return None

    async def resolve(owner_id: str) -> Principal:
        return next(o for o in owners if o.id == owner_id)

    async def notify(*_: Any) -> None:
        return None

    config = ValkeyConfig.from_env()
    valkey = Valkey(host=config.host, port=config.port)
    world = World(stores, None, published[0][0], drafts[0], monkeypatch)
    try:
        async with arcadedb_adapter(ONTOLOGY, SCHEME) as raw:
            world.graph = await _conduits_graph(raw, stores)
            closures = world.executor()
            scheduler = ScheduleExecutor(
                recipes=Due(), runs=stores.runs, valkey=valkey, scheme=SCHEME,  # type: ignore[arg-type]
                resolve_owner=resolve, check_case=closures.check_case, run=closures.run,
                notify=notify, watch_files=None, source_watches=None, case_for_dataset=None,
            )  # fmt: skip
            await scheduler.tick(slot + timedelta(seconds=20))
            await scheduler.run_now(drafts[2])
            reads = [
                await world.reads(await closures.check_case(o, case))
                for o, case in zip(owners, cases, strict=True)
            ]
    finally:
        await valkey.aclose()

    own = {"nodes": ["SYN-1", "SYN-2"], "links": [("TRANSACTED", "SYN-1", "SYN-2", 1)]}
    assert reads == [own, own, own], "each run stamped with its own case's dataset"
