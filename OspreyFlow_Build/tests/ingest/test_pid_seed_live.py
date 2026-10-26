"""The Prison Intelligence seed against the real stores (ADR-127 Amendment 23; Amendment 32 trimmed
the live cases to these three).

**Live, slow, and outside `make ci`.** Every case reads the real ArcadeDB, Postgres, Valkey and
DuckDB of the throwaway stack (`ARCADEDB_*`, `POSTGRES_*`, `VALKEY_*`, `ANALYTICS_DB_PATH`), seeds
the dataset through the command itself (a subprocess of `python -m scripts.seed_pid`, so what runs
is what an operator runs), and takes a few minutes (the call file is about 100,000 rows). It skips
unless `OSPREYFLOW_RUN_SLOW=1`. Rule 14: run it with nothing else using the stack, and with the
Conduit stopped (the seed opens DuckDB, which has one writer):

    OSPREYFLOW_RUN_SLOW=1 .venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini \\
        ../OspreyFlow_Build/tests/ingest/test_pid_seed_live.py -v        # from OspreyFlow_Core

It keeps its scratch in one fixed folder (`<tmp>/pid-seed-live/{ingest,recipes}`), so a second run
over the same stack finds what the first left (the recipes' rows name their source files by path)
and is itself a test of "safe to run again". The recipe repository is named by
`OSPREY_RECIPE_REPO_ROOT` (the seed refuses to default it), and the engine reads it from
`RunResources.recipe_repo_root`, which each case sets from the same folder.

What each case would catch:

- **`test_a_second_seed_adds_nothing`**: a second seed that re-reads a file, makes a node, a link, a
  picture or a run, rewrites a recipe row, writes a registry row, or commits to the recipe
  repository, or that attaches a picture again (the output's own "0 attached" is matched as a whole
  word, so "10 attached" or "1,000 attached" cannot pass for it), or whose demo numbers fail;
- **`test_the_rehearsal_reset_restores_the_starting_state`**: a reset that leaves a node or link of
  chapter 4 or 9, leaves the reports recipe published (so `feeding` still lists it), leaves two
  drafts, leaves batch 2 in the listing, leaves the reports file as the engineer edited it, or takes
  with it a link an analyst made that rests on nothing the reset reverts. The rehearsal runs the
  reports recipe twice, since a rehearsal that is run twice leaves two loads to revert; **R9
  published live runs through the pipeline path** (`PipelineRunReport`, not a plain load);
- **`test_the_demo_analyst_fetches_one_picture_through_the_picture_route`**: a picture the seed
  attached that the demo analyst, cleared to OFFICIAL and in the case, cannot fetch (Brief 2
  section 7.1 4a). It calls the route's own function, `entity_picture_file_route`, with the real
  `EntityPictureService` over the real graph, working set, media store and audit writer, rather than
  building the application: the FastAPI layer (the token, the rights, the case level) is the route
  tests' (`tests/services/api/test_entity_pictures.py`), and building it here would need Keycloak.

Withdrawn by Amendments 31 and 32, and not written: the case that every element carries the dataset,
the marking replay, Data feeds listing the recipes and withholding R15's counts, and the SECRET
link's absence. The demo numbers (J1, J2, Ch2, Ch3, Ch5, Ch6, Ch11, S2) are the seed's own printed
checks.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from scripts import seed_pid
from services.api.config import ApiConfig
from services.api.dataset_scope import scope_to_case
from services.api.entity_pictures import EntityPictureService
from services.api.recipe_run import run_recipe_as
from services.api.run_resources import RunResources, build_run_resources
from services.api.studio_publish import commit_recipe_file
from services.api.studio_recipes import StudioRecipeStore
from services.api.working_set.service import WorkingSetService
from services.api.working_set.store import ValkeyWorkingSetStore

from conduit_common.identity import new_edge_id
from demo_fixtures import pid_files, pid_plan, pid_writes
from demo_fixtures.datasets import PID
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.domain import (
    EdgeWrite,
    Handling,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from schemas.ingest import PipelineRunReport, StudioRecipeStatus

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("OSPREYFLOW_RUN_SLOW"),
        reason="seeds the whole dataset against real stores: set OSPREYFLOW_RUN_SLOW=1",
    ),
    pytest.mark.asyncio(loop_scope="module"),
]

CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"
SCRATCH = Path(tempfile.gettempdir()) / "pid-seed-live"
INGEST = SCRATCH / "ingest"
RECIPES = SCRATCH / "recipes"
CASE_NAME = PID.case_name or ""
#: The picture the demo analyst fetches: the principal's, whose bytes the plan holds.
PICTURE_SUBJECT = "principal"


def _environment() -> dict[str, str]:
    env = dict(os.environ)
    env["OSPREY_INGEST_ROOT"] = str(INGEST)
    env["OSPREY_RECIPE_REPO_ROOT"] = str(RECIPES)
    env.setdefault("OIDC_JWKS_URL", "http://localhost:9/jwks")
    env["PYTHONPATH"] = os.pathsep.join([str(CORE), str(CORE / "packages")])
    return env


def run_seed(*flags: str) -> subprocess.CompletedProcess[str]:
    """`python -m scripts.seed_pid` as an operator runs it, against the stack in the environment."""
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "scripts.seed_pid", "--case-name", CASE_NAME, *flags],
        cwd=CORE, env=_environment(), capture_output=True, text=True, check=False,
    )  # fmt: skip


def _said(done: subprocess.CompletedProcess[str]) -> str:
    return f"exit {done.returncode}\n{done.stdout}\n{done.stderr}"


def commits_in_the_recipe_repository() -> int:
    """How many commits the recipe repository holds (0 before the first seed made it)."""
    if not (RECIPES / ".git").exists():
        return 0
    counted = subprocess.run(  # noqa: S603
        ["git", "-C", str(RECIPES), "rev-list", "--count", "HEAD"],  # noqa: S607
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    return int(counted.stdout.strip() or 0) if counted.returncode == 0 else 0


@dataclass
class Live:
    resources: RunResources
    store: StudioRecipeStore
    case_id: str
    #: The seed's loader, the demo data engineer, scoped to the case's datasets.
    persona: Principal


@asynccontextmanager
async def opened() -> AsyncIterator[Live]:
    """The stores, as the seed opens them (closed again on exit, so the subprocess can take
    DuckDB's lock)."""
    os.environ.setdefault("OIDC_JWKS_URL", "http://localhost:9/jwks")
    config = ApiConfig.from_env()
    resources = await build_run_resources(config)
    resources.recipe_repo_root = RECIPES
    store = await StudioRecipeStore.connect(config.postgres.dsn)
    try:
        base = seed_pid.engineer()
        case_id = await seed_pid._find_case(
            config.postgres.dsn,
            argparse.Namespace(investigation_scope=None, case_name=CASE_NAME),
            base,
        )
        assert case_id is not None, "the seed made no case"
        yield Live(
            resources, store, case_id, await scope_to_case(base, case_id, resources.datasets_store)
        )
    finally:
        await store.close()
        await resources.close()


def _recipe_ids() -> list[str]:
    return sorted({seed_pid.recipe_id_of(stage.recipe) for stage in pid_files.SEED_ORDER})


async def registry_rows(live: Live) -> list[tuple[Any, ...]]:
    """Every row of the registry for the seed's recipes, every column: a second seed must not write
    one, or rewrite one."""
    async with live.store._pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT recipe_id, version, label, status, content::text, git_path, ontology_version, "
            "pack_versions::text, owning_unit, created_by, created_at, published_by, published_at, "
            "verified_at, dataset_id, schedule_cron, schedule_watch "
            "FROM studio_recipes WHERE recipe_id = ANY($1::text[]) ORDER BY recipe_id, version",
            _recipe_ids(),
        )
    return [tuple(row.values()) for row in rows]


async def snapshot(live: Live) -> dict[str, Any]:
    """What a second seed must not change, and what a reset must restore: the nodes and links the
    persona can see, by type, the runs of each recipe, the unreverted loads, the registry's rows and
    the recipe repository's commits."""
    counts = await live.resources.graph.type_counts(live.persona)
    runs = {
        recipe: len(await live.resources.recipe_runs.for_recipe(recipe, limit=1_000))
        for recipe in _recipe_ids()
    }
    loads = await live.resources.recipe_runs.unreverted_loads(live.case_id, _recipe_ids())
    return {
        "nodes": dict(counts.nodes),
        "links": dict(counts.edges),
        "runs": runs,
        "loads": sorted((r.recipe_id, r.source, r.load_id) for r in loads),
        "registry": await registry_rows(live),
        "commits": commits_in_the_recipe_repository(),
    }


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def seeded() -> str:
    """The first seed, from whatever the stack holds: the command's own output."""
    done = run_seed()
    assert done.returncode == 0, _said(done)
    assert "check FAILED" not in done.stdout, _said(done)
    return done.stdout


async def test_a_second_seed_adds_nothing(seeded: str) -> None:
    async with opened() as live:
        before = await snapshot(live)
    second = run_seed()
    assert second.returncode == 0, _said(second)
    async with opened() as live:
        after = await snapshot(live)
    assert after == before, "a second seed changed a node, a link, a run, a load, a row or a commit"
    assert second.stdout.count("already loaded, not read again") == 15, _said(second)
    assert re.search(r"\b0 attached\b", second.stdout), "no picture is attached twice"
    assert "check FAILED" not in second.stdout, _said(second)
    assert "check ok: J1" in second.stdout, "the demo numbers are checked on a reseed too"


def _two_prisoners_with_no_link_between_them(plan: pid_plan.Plan) -> tuple[str, str]:
    """Two background prisoners the plan does not join, so a link between them is the analyst's own
    and is merged into no link of the seed's."""
    people = [
        e.key
        for e in plan.entities
        if e.key.startswith("prisoner:") and "prison_number" in e.properties
    ]
    joined = {frozenset((lk.source, lk.target)) for lk in plan.links}
    for first in people:
        for second in people[1:]:
            if first != second and frozenset((first, second)) not in joined:
                return first, second
    raise AssertionError("every pair of prisoners is joined")


async def _make_an_analysts_link(live: Live, plan: pid_plan.Plan) -> str:
    """A link an analyst makes between two prisoners the seed's first loads made: it rests on
    nothing the reset reverts, so the reset must leave it. Written through the case's stamping
    graph, as the link route writes one."""
    graph = live.resources.graph
    ends = []
    for key in _two_prisoners_with_no_link_between_them(plan):
        entity_type, field, value = seed_pid.identity_of(plan, key)
        node = await graph.find_node(entity_type, field, value, live.persona)
        assert node is not None, key
        ends.append(node.id)
    now = datetime.now(UTC)
    link = EdgeWrite(
        id=new_edge_id(), type="ASSOCIATE_OF", source=ends[0], target=ends[1],
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="analyst:live-test", locator="link", excerpt_hash="")],
            first_seen=now,
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="verify", owning_unit="verify"
        ),
        created_by="demo-analyst", created_at=now,
    )  # fmt: skip
    tx = await graph.begin_transaction()
    try:
        (link_id,) = await graph.upsert_edges([link], tx)
    except Exception:
        await graph.rollback_transaction(tx)
        raise
    await graph.commit_transaction(tx)
    return str(link_id)


async def test_the_rehearsal_reset_restores_the_starting_state(seeded: str) -> None:
    ontology, scheme = load_deployment_ontology(), load_uk_le_scheme()
    reports_id = seed_pid.reports_recipe_id()
    plan = pid_plan.build_plan("demo")
    async with opened() as live:
        # The starting state: the reports recipe a draft with Map not done, listed once, not live.
        assert reports_id not in [r.recipe_id for r in await live.store.feeding([PID.id])], (
            "the reports recipe is not published at the start"
        )
        drafts = [
            d for d in await live.store.list_drafts(live.persona) if d.recipe_id == reports_id
        ]
        assert len(drafts) == 1 and drafts[0].row_template is None
        start_analysts = await _make_an_analysts_link(live, plan)
        start = await snapshot(live)
        start_version = drafts[0].version
        start_reports = (seed_pid.listed_folder(INGEST) / pid_files.REPORTS).read_bytes()

        # Chapter 4: the fallback publication, the reports (twice), then the incident links.
        fallback_principal = live.persona.model_copy(update={"datasets": [PID.id]})
        published = await seed_pid.publish_reports_fallback(
            live.store, fallback_principal, ontology=ontology, scheme=scheme, repo_root=RECIPES,
            commit=commit_recipe_file, audit=live.resources.audit, now=datetime.now(UTC),
        )  # fmt: skip
        assert published.status is StudioRecipeStatus.PUBLISHED and published.pipeline is not None
        deps = seed_pid.without_post_ingest_resolution(live.resources.run_deps())
        rows = {
            reports_id: published,
            seed_pid.incidents_recipe_id(): await live.store.get(seed_pid.incidents_recipe_id()),
            seed_pid.comms_recipe_id(): await live.store.get(seed_pid.comms_recipe_id()),
        }

        async def run(item: seed_pid.Resolved) -> Any:
            return await run_recipe_as(
                deps, principal=live.persona, recipe=rows[item.recipe_id],
                investigation_id=live.case_id, source_location=item.source, trigger="manual",
            )  # fmt: skip

        stages = [seed_pid.resolve(s, INGEST) for s in pid_files.SEED_ORDER[15:]]
        loaded = await seed_pid.loaded_so_far(live.resources.recipe_runs, live.case_id, stages)
        reports_report = (await seed_pid.run_stages(stages[:1], loaded, run=run))[0].report
        assert isinstance(reports_report, PipelineRunReport), (
            "the published reports recipe runs through the pipeline path"
        )
        assert reports_report.nodes_created > 0
        # A second run of the reports: a rehearsal run twice leaves another load for the reset.
        assert isinstance(await run(stages[0]), PipelineRunReport)
        loaded = await seed_pid.loaded_so_far(live.resources.recipe_runs, live.case_id, stages)
        await seed_pid.run_stages(stages[1:2], loaded, run=run)
        # Chapter 9: batch 2 is listed, then loaded.
        seed_pid.release_batch_2(INGEST)
        loaded = await seed_pid.loaded_so_far(live.resources.recipe_runs, live.case_id, stages)
        await seed_pid.run_stages(stages[2:], loaded, run=run)
        rehearsed = await snapshot(live)
        assert rehearsed["nodes"] != start["nodes"] or rehearsed["links"] != start["links"]
        assert len(rehearsed["loads"]) > len(start["loads"]) + 3, "two reports loads, R17, batch 2"

    done = run_seed("--reset-live")
    assert done.returncode == 0, _said(done)
    for phrase in ("What the reset cannot undo", "removed " + pid_files.BATCH_2):
        assert phrase in done.stdout, _said(done)

    async with opened() as live:
        end = await snapshot(live)
        assert end["nodes"] == start["nodes"], "every node of the rehearsal is gone"
        assert end["links"] == start["links"], (
            "every link of the rehearsal is gone, the analyst's kept"
        )
        assert end["loads"] == start["loads"], "every load of the rehearsal is reverted"
        assert end["runs"] != start["runs"], "the reverted runs stay in the ledger, said in words"
        kept = await live.resources.graph.get_edges([start_analysts], live.persona)
        assert [e.id for e in kept] == [start_analysts], "the analyst's own link survived the reset"
        assert reports_id not in [r.recipe_id for r in await live.store.feeding([PID.id])]
        drafts = [
            d for d in await live.store.list_drafts(live.persona) if d.recipe_id == reports_id
        ]
        assert len(drafts) == 1 and drafts[0].row_template is None
        assert drafts[0].version > start_version, "R9's version climbs, said in words"
        assert drafts[0].pipeline == seed_pid.starting_pipeline(
            seed_pid.source_of(INGEST, pid_files.REPORTS)
        )
        assert [r for r in end["registry"] if r[0] != reports_id] == [
            r for r in start["registry"] if r[0] != reports_id
        ], "no other recipe's row moved"
    listed = seed_pid.listed_folder(INGEST)
    assert not (listed / pid_files.BATCH_2).exists(), "batch 2 is out of the listing again"
    assert (listed / "incoming" / pid_files.BATCH_2).is_file()
    assert (listed / pid_files.REPORTS).read_bytes() == start_reports


async def test_the_demo_analyst_fetches_one_picture_through_the_picture_route(seeded: str) -> None:
    from services.api.app import entity_picture_file_route

    plan = pid_plan.build_plan("demo")
    by_subject = dict(zip(plan.picture_subjects, pid_writes.picture_writes(plan), strict=True))
    _, picture_name, picture_bytes = by_subject[PICTURE_SUBJECT]
    async with opened() as live:
        analyst = await scope_to_case(
            Principal(
                id="demo-analyst", clearance="OFFICIAL", org_unit=seed_pid.WORKER_UNIT,
                roles=["analyst"],
            ),
            live.case_id,
            live.resources.datasets_store,
        )  # fmt: skip
        entity_type, field, value = seed_pid.identity_of(plan, PICTURE_SUBJECT)
        subject = await live.resources.graph.find_node(entity_type, field, value, analyst)
        assert subject is not None, "the demo analyst reads the subject the seed pictured"
        working = WorkingSetService(
            live.resources.graph,
            ValkeyWorkingSetStore(live.resources.valkey),
            live.resources.handling_scheme,
            valkey=live.resources.valkey,
        )
        # The analyst has the subject in their working set, as "add the principal" would.
        await working.add_written(live.case_id, [subject], [], analyst)
        service = EntityPictureService(
            working,
            live.resources.graph,
            live.resources.media,
            live.resources.ontology,
            scheme=live.resources.handling_scheme,
            audit=live.resources.audit,
        )
        answer = await entity_picture_file_route(
            investigation=SimpleNamespace(id=live.case_id),  # type: ignore[arg-type]
            node_id=subject.id,
            principal=analyst,
            pictures=service,
            audit=live.resources.audit,
        )
    assert answer.status_code == 200
    assert answer.body == picture_bytes, f"the bytes the plan holds for {picture_name}"
    assert answer.media_type == "image/png"
