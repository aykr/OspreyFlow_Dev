"""ADR-110 decisions 2–4 and Amendment 2: the executor, slot by slot, against a real Valkey (the
claim and the lock) and the real run ledger in Postgres.

The edges are fakes, each refusing what the real one refuses (rule 15): the owner resolver raises
`PrincipalRevoked` for a disabled account and `PrincipalExchangeUnavailable` for an identity
provider it cannot reach, as `PrincipalResolver.resolve_for_owner_detailed` does; the case check
raises `InsufficientAccessError` for an owner below Editor, as `InvestigationStore.get_authorized`
does. The run itself is a stand-in that writes the ledger as `run_recipe_as` does — the one run path
is `test_recipe_run_path.py`'s and `test_recipe_run_ledger.py`'s to prove.

The two-replica case runs two executors in two processes against the same Valkey and ledger.
"""

from __future__ import annotations

import asyncio
import multiprocessing
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from principal_auth import PrincipalExchangeUnavailable, PrincipalRevoked
from schemas.domain import Principal
from schemas.ingest import LoadReport, StudioRecipeDraft, StudioRecipeStatus
from services.api.config import PostgresConfig, ValkeyConfig
from services.api.folder_watch import WatchedFile
from services.api.investigations import AccessLevel, InsufficientAccessError
from services.api.recipe_runs import RecipeRunStore
from services.api.scheduler import ScheduleExecutor, ScheduleRunRefused
from valkey.asyncio import Valkey

SCHEME = load_uk_le_scheme()
OWNER = Principal(
    id="approver-1", clearance="OFFICIAL", org_unit="unit-1", roles=["source_approver"]
)
SET_AT = datetime(2026, 6, 1, 12, tzinfo=UTC)
_HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "owning_unit": "unit-1",
    "originator": "unit-1",
}
FIRST_SLOT = datetime(2026, 6, 2, 5, tzinfo=UTC)  # 06:00 BST


def _recipe(**overrides: Any) -> StudioRecipeDraft:
    fields: dict[str, Any] = {
        "recipe_id": new_id(),
        "version": 2,
        "status": StudioRecipeStatus.PUBLISHED,
        "label": "Daily export",
        "handling": dict(_HANDLING),
        "owning_unit": "unit-1",
        "created_by": "author-1",
        "created_at": SET_AT,
        "ready_for_profile": True,
        "schedule_cron": "0 6 * * *",
        "schedule_owner": OWNER.id,
        "schedule_set_at": SET_AT,
        "schedule_case": "case-1",
    }
    fields.update(overrides)
    return StudioRecipeDraft(**fields)


@dataclass
class _Recipes:
    held: list[StudioRecipeDraft]
    paused: dict[str, str] = field(default_factory=dict)

    async def scheduled(self) -> list[StudioRecipeDraft]:
        return [
            r.model_copy(
                update={"schedule_paused": True, "schedule_paused_reason": self.paused[r.recipe_id]}
            )
            if r.recipe_id in self.paused
            else r
            for r in self.held
        ]

    async def set_paused(self, recipe_id: str, *, paused: bool, reason: str | None) -> None:
        if paused:
            self.paused[recipe_id] = reason or ""
        else:
            self.paused.pop(recipe_id, None)


@dataclass
class _Edges:
    owner: Principal | Exception = field(default_factory=lambda: OWNER)
    case_level_ok: bool = True
    runs_made: list[tuple[str, datetime | None]] = field(default_factory=list)
    hold_run: asyncio.Event | None = None
    fail_run: Exception | None = None
    notices: list[tuple[str, str, str]] = field(default_factory=list)
    #: ADR-110 Amendment 4: the files the recipe's folder watch finds waiting, earliest first.
    waiting: list[WatchedFile] = field(default_factory=list)
    files_run: list[str] = field(default_factory=list)

    async def watch_files(self, recipe: StudioRecipeDraft, now: datetime) -> list[WatchedFile]:
        return list(self.waiting)

    async def notify(self, owner_id: str, recipe: StudioRecipeDraft, words: str) -> None:
        self.notices.append((owner_id, recipe.recipe_id, words))

    async def resolve_owner(self, owner_id: str) -> Principal:
        if isinstance(self.owner, Exception):
            raise self.owner
        return self.owner

    async def check_case(self, owner: Principal, case: str) -> Principal:
        if not self.case_level_ok:
            raise InsufficientAccessError(case, AccessLevel.VIEWER, AccessLevel.EDITOR)
        return owner.model_copy(update={"datasets": ["ds-1"]})


@pytest.fixture
async def runs() -> AsyncIterator[RecipeRunStore]:
    store = await RecipeRunStore.connect(PostgresConfig.from_env().dsn)
    try:
        yield store
    finally:
        await store.close()


@pytest.fixture
async def valkey() -> AsyncIterator[Valkey]:
    config = ValkeyConfig.from_env()
    client = Valkey(host=config.host, port=config.port)
    try:
        yield client
    finally:
        await client.aclose()


def _executor(
    recipes: _Recipes, edges: _Edges, runs: RecipeRunStore, valkey: Valkey
) -> ScheduleExecutor:
    async def run(
        owner: Principal,
        recipe: StudioRecipeDraft,
        case: str,
        slot: datetime | None,
        source_file: WatchedFile | None = None,
    ) -> LoadReport:
        """What `run_recipe_as` does to the ledger, around a load that writes nothing."""
        edges.runs_made.append((owner.id, slot))
        if source_file is not None:
            edges.files_run.append(source_file.location)
        trigger = "watch" if source_file else "schedule" if slot else "manual"
        run_id = await runs.start(
            recipe_id=recipe.recipe_id, recipe_version=recipe.version, investigation_id=case,
            trigger=trigger, slot=slot, run_as=owner.id, source=_source(recipe),
            now=datetime.now(UTC), source_file=source_file.identity if source_file else None,
        )  # fmt: skip
        if edges.hold_run is not None:
            await edges.hold_run.wait()
        if edges.fail_run is not None:
            await runs.fail(run_id, failure=str(edges.fail_run), now=datetime.now(UTC))
            raise edges.fail_run
        report = LoadReport(load_id=new_id(), recipe_id=recipe.recipe_id, recipe_version=2)
        await runs.finish(run_id, report=report, now=datetime.now(UTC))
        return report

    return ScheduleExecutor(
        recipes=recipes,  # type: ignore[arg-type]
        runs=runs,
        valkey=valkey,
        scheme=SCHEME,
        resolve_owner=edges.resolve_owner,
        check_case=edges.check_case,
        run=run,
        notify=edges.notify,
        watch_files=edges.watch_files,
    )


def _source(recipe: StudioRecipeDraft) -> Any:
    from services.api.studio_map import resolve_source_handling

    return resolve_source_handling(recipe)


async def _outcomes(runs: RecipeRunStore, recipe: StudioRecipeDraft) -> list[tuple[str, Any]]:
    return [(r.outcome, r.slot) for r in reversed(await runs.for_recipe(recipe.recipe_id))]


async def test_nothing_is_due_before_the_first_slot(runs: RecipeRunStore, valkey: Valkey) -> None:
    recipe, edges = _recipe(), _Edges()
    await _executor(_Recipes([recipe]), edges, runs, valkey).tick(FIRST_SLOT - timedelta(minutes=1))
    assert edges.runs_made == [] and await _outcomes(runs, recipe) == []


async def test_a_due_slot_runs_once_as_its_owner_and_is_not_run_again(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    recipe, edges = _recipe(), _Edges()
    executor = _executor(_Recipes([recipe]), edges, runs, valkey)
    await executor.tick(FIRST_SLOT + timedelta(seconds=20))
    await executor.tick(FIRST_SLOT + timedelta(seconds=80))  # the next minute's tick
    assert edges.runs_made == [(OWNER.id, FIRST_SLOT)]
    assert await _outcomes(runs, recipe) == [("succeeded", FIRST_SLOT)]


async def test_after_downtime_the_latest_slot_runs_once_and_the_rest_are_missed(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    recipe, edges = _recipe(), _Edges()
    await _executor(_Recipes([recipe]), edges, runs, valkey).tick(
        FIRST_SLOT + timedelta(days=2, hours=1)
    )
    slots = [FIRST_SLOT + timedelta(days=d) for d in range(3)]
    assert edges.runs_made == [(OWNER.id, slots[2])]
    assert await _outcomes(runs, recipe) == [
        ("missed", slots[0]),
        ("missed", slots[1]),
        ("succeeded", slots[2]),
    ]


async def test_a_flagged_recipe_is_blocked_not_run(runs: RecipeRunStore, valkey: Valkey) -> None:
    recipe, edges = _recipe(status=StudioRecipeStatus.FLAGGED), _Edges()
    await _executor(_Recipes([recipe]), edges, runs, valkey).tick(FIRST_SLOT)
    assert edges.runs_made == []
    (row,) = await runs.for_recipe(recipe.recipe_id)
    assert row.outcome == "blocked" and "ontology changed" in (row.failure or "")


async def test_a_paused_schedule_does_nothing(runs: RecipeRunStore, valkey: Valkey) -> None:
    recipe, edges = _recipe(), _Edges()
    await _executor(_Recipes([recipe], paused={recipe.recipe_id: "by hand"}), edges, runs,
                    valkey).tick(FIRST_SLOT)  # fmt: skip
    assert edges.runs_made == [] and await _outcomes(runs, recipe) == []


@pytest.mark.parametrize(
    ("edges", "words"),
    [
        (_Edges(owner=PrincipalRevoked("approver-1 is disabled")), "can no longer sign in"),
        (_Edges(owner=PrincipalExchangeUnavailable("timed out")), "could not be reached"),
        (_Edges(owner=OWNER.model_copy(update={"roles": ["analyst"]})), "schedule_pipelines"),
        (_Edges(case_level_ok=False), "Editor"),
    ],
    ids=["revoked", "idp-unreachable", "right-withdrawn", "case-access-lowered"],
)
async def test_an_owner_who_may_no_longer_run_it_is_refused_in_words(
    runs: RecipeRunStore, valkey: Valkey, edges: _Edges, words: str
) -> None:
    recipe = _recipe()
    await _executor(_Recipes([recipe]), edges, runs, valkey).tick(FIRST_SLOT)
    assert edges.runs_made == []
    (row,) = await runs.for_recipe(recipe.recipe_id)
    assert row.outcome == "refused" and words in (row.failure or "")


async def test_an_owner_whose_clearance_dropped_below_the_source_is_refused(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    recipe = _recipe(handling={**_HANDLING, "classification": "SECRET"})
    edges = _Edges()
    await _executor(_Recipes([recipe]), edges, runs, valkey).tick(FIRST_SLOT)
    (row,) = await runs.for_recipe(recipe.recipe_id)
    assert edges.runs_made == []
    assert row.outcome == "refused" and "above" in (row.failure or "")


async def test_the_third_refusal_in_a_row_pauses_the_schedule(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    recipe = _recipe()
    recipes, edges = _Recipes([recipe]), _Edges(owner=PrincipalRevoked("disabled"))
    executor = _executor(recipes, edges, runs, valkey)
    for day in range(2):
        await executor.tick(FIRST_SLOT + timedelta(days=day))
    assert recipe.recipe_id not in recipes.paused
    await executor.tick(FIRST_SLOT + timedelta(days=2))
    assert "three refused runs in a row" in recipes.paused[recipe.recipe_id]
    await executor.tick(FIRST_SLOT + timedelta(days=3))
    assert [o for o, _ in await _outcomes(runs, recipe)] == ["refused"] * 3


async def test_a_slot_due_while_the_last_run_is_still_going_is_skipped(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    recipe = _recipe(schedule_cron="0 * * * *")
    edges = _Edges(hold_run=asyncio.Event())
    executor = _executor(_Recipes([recipe]), edges, runs, valkey)
    first = datetime(2026, 6, 2, 5, tzinfo=UTC)
    running = asyncio.create_task(executor.tick(first))
    await _until_running(edges, running)
    # Bounded: were the second slot run rather than skipped, it would wait on the first for ever.
    await asyncio.wait_for(executor.tick(first + timedelta(hours=1)), timeout=10)
    assert edges.hold_run is not None
    edges.hold_run.set()
    await asyncio.wait_for(running, timeout=10)
    outcomes = await _outcomes(runs, recipe)
    assert ("skipped", first + timedelta(hours=1)) in outcomes
    assert ("succeeded", first) in outcomes and len(edges.runs_made) == 1


async def _until_running(edges: _Edges, task: asyncio.Task[Any]) -> None:
    """Bounded: a run that fails at once must fail the test, not leave it waiting for ever."""
    for _ in range(500):
        if edges.runs_made:
            return
        if task.done():
            task.result()  # raises what the run raised
            raise AssertionError("the run finished without starting")
        await asyncio.sleep(0.01)
    raise AssertionError("the run never started")


def _tick_in_a_process(
    recipe_json: str, at: str, ready: Any, go: Any, result: Any, waiting_json: str = ""
) -> None:
    """One replica: its own Valkey and Postgres connections, its own executor."""

    async def main() -> None:
        store = await RecipeRunStore.connect(PostgresConfig.from_env().dsn)
        config = ValkeyConfig.from_env()
        client = Valkey(host=config.host, port=config.port)
        edges = _Edges()
        if waiting_json:
            edges.waiting = [WatchedFile.model_validate_json(waiting_json)]
        recipe = StudioRecipeDraft.model_validate_json(recipe_json)
        executor = _executor(_Recipes([recipe]), edges, store, client)
        ready.set()
        go.wait()
        await executor.tick(datetime.fromisoformat(at))
        result.put(len(edges.runs_made))
        await client.aclose()
        await store.close()

    asyncio.run(main())


def test_two_replicas_ticking_together_run_a_slot_once() -> None:
    """Amendment 2, point 3: two executors, two processes, one Valkey, one ledger."""
    _two_replicas_run_it_once(_recipe(), FIRST_SLOT, "")


def test_two_replicas_ticking_together_take_a_watched_file_once() -> None:
    """Amendment 4, point 5: the file's claim, as the slot's, across two processes."""
    recipe = _recipe(schedule_cron=None, schedule_watch="*.csv", dataset_id="ds-1")
    _two_replicas_run_it_once(recipe, FIRST_SLOT, _file("a.csv").model_dump_json())


def _two_replicas_run_it_once(recipe: StudioRecipeDraft, at: datetime, waiting: str) -> None:
    context = multiprocessing.get_context("spawn")
    go, result = context.Event(), context.Queue()
    readies = [context.Event(), context.Event()]
    processes = [
        context.Process(
            target=_tick_in_a_process,
            args=(recipe.model_dump_json(), at.isoformat(), ready, go, result, waiting),
        )
        for ready in readies
    ]
    for process in processes:
        process.start()
    for ready in readies:
        assert ready.wait(30)
    go.set()
    for process in processes:
        process.join(60)
        assert process.exitcode == 0
    assert sorted(result.get(timeout=5) for _ in processes) == [0, 1]

    async def ledger() -> list[str]:
        store = await RecipeRunStore.connect(PostgresConfig.from_env().dsn)
        try:
            return [r.outcome for r in await store.for_recipe(recipe.recipe_id)]
        finally:
            await store.close()

    assert asyncio.run(ledger()) == ["succeeded"]
    assert os.environ.get("POSTGRES_PORT"), "needs the live Postgres"


async def test_an_identity_provider_outage_is_refused_but_never_pauses_the_schedule(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    """ADR-110 Amendment 3, point 3: only refusals about the owner count toward the three."""
    recipe = _recipe()
    recipes, edges = _Recipes([recipe]), _Edges(owner=PrincipalExchangeUnavailable("down"))
    executor = _executor(recipes, edges, runs, valkey)
    for day in range(4):
        await executor.tick(FIRST_SLOT + timedelta(days=day))
    assert recipe.recipe_id not in recipes.paused
    assert [o for o, _ in await _outcomes(runs, recipe)] == ["refused"] * 4
    # An outage between owner refusals neither counts nor resets them.
    edges.owner = PrincipalRevoked("disabled")
    await executor.tick(FIRST_SLOT + timedelta(days=4))
    await executor.tick(FIRST_SLOT + timedelta(days=5))
    edges.owner = PrincipalExchangeUnavailable("down")
    await executor.tick(FIRST_SLOT + timedelta(days=6))
    assert recipe.recipe_id not in recipes.paused
    edges.owner = PrincipalRevoked("disabled")
    await executor.tick(FIRST_SLOT + timedelta(days=7))
    assert "three refused runs in a row" in recipes.paused[recipe.recipe_id]


async def test_a_refused_run_tells_its_owner_in_words(runs: RecipeRunStore, valkey: Valkey) -> None:
    """ADR-110 decision 10 and Amendment 3, point 1."""
    recipe, edges = _recipe(), _Edges(owner=PrincipalRevoked("disabled"))
    await _executor(_Recipes([recipe]), edges, runs, valkey).tick(FIRST_SLOT)
    ((owner, recipe_id, words),) = edges.notices
    assert (owner, recipe_id) == ("approver-1", recipe.recipe_id)
    assert words.startswith("The scheduled run of Daily export due ")
    assert "was refused: the schedule's owner, approver-1, can no longer sign in" in words


async def test_a_failed_run_tells_its_owner_in_words(runs: RecipeRunStore, valkey: Valkey) -> None:
    recipe, edges = _recipe(), _Edges(fail_run=FileNotFoundError("no such file: a.csv"))
    await _executor(_Recipes([recipe]), edges, runs, valkey).tick(FIRST_SLOT)
    ((owner, _, words),) = edges.notices
    assert owner == "approver-1" and "failed: no such file: a.csv" in words


async def test_a_run_that_succeeds_or_is_missed_tells_nobody(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    recipe, edges = _recipe(), _Edges()
    await _executor(_Recipes([recipe]), edges, runs, valkey).tick(FIRST_SLOT + timedelta(days=2))
    assert edges.notices == []


# --- ADR-110 Amendment 3, point 2: the Admin area's Run now, as the schedule's owner ------------


async def test_run_now_runs_at_once_as_the_owner(runs: RecipeRunStore, valkey: Valkey) -> None:
    recipe, edges = _recipe(), _Edges()
    await _executor(_Recipes([recipe]), edges, runs, valkey).run_now(recipe)
    assert edges.runs_made == [(OWNER.id, None)]


@pytest.mark.parametrize(
    ("edges", "words"),
    [
        (_Edges(owner=PrincipalRevoked("disabled")), "can no longer sign in"),
        (_Edges(case_level_ok=False), "Editor"),
    ],
    ids=["revoked", "case-access-lowered"],
)
async def test_run_now_is_refused_in_words_when_the_owner_may_not_run_it(
    runs: RecipeRunStore, valkey: Valkey, edges: _Edges, words: str
) -> None:
    recipe = _recipe()
    with pytest.raises(ScheduleRunRefused, match=words):
        await _executor(_Recipes([recipe]), edges, runs, valkey).run_now(recipe)
    assert edges.runs_made == []


async def test_run_now_is_refused_while_a_run_of_the_recipe_is_going(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    recipe = _recipe()
    edges = _Edges(hold_run=asyncio.Event())
    executor = _executor(_Recipes([recipe]), edges, runs, valkey)
    running = asyncio.create_task(executor.run_now(recipe))
    await _until_running(edges, running)
    with pytest.raises(ScheduleRunRefused, match="still going"):
        await asyncio.wait_for(executor.run_now(recipe), timeout=10)
    assert edges.hold_run is not None
    edges.hold_run.set()
    await asyncio.wait_for(running, timeout=10)


# --- ADR-110 decision 5, Amendment 4: the folder watch ------------------------------------------


def _file(name: str, size: int = 10, minute: int = 0) -> WatchedFile:
    arrived = FIRST_SLOT + timedelta(minutes=minute)
    return WatchedFile(
        name=name,
        location=f"/var/lib/osprey/ingest/ds-1/{name}",
        identity=f"{name}|{size}|{arrived.timestamp():.6f}",
        arrived_at=arrived,
    )


def _watched(**overrides: Any) -> StudioRecipeDraft:
    return _recipe(schedule_cron=None, schedule_watch="*.csv", dataset_id="ds-1", **overrides)


async def _watch_rows(runs: RecipeRunStore, recipe: StudioRecipeDraft) -> list[tuple[str, Any]]:
    return [
        (r.outcome, r.source_file)
        for r in reversed(await runs.for_recipe(recipe.recipe_id))
        if r.trigger == "watch"
    ]


async def test_a_waiting_file_runs_once_as_the_owner_on_that_file(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    recipe, edges = _watched(), _Edges(waiting=[_file("a.csv")])
    executor = _executor(_Recipes([recipe]), edges, runs, valkey)
    await executor.tick(FIRST_SLOT)
    await executor.tick(FIRST_SLOT + timedelta(minutes=1))
    assert edges.runs_made == [(OWNER.id, None)]
    assert edges.files_run == ["/var/lib/osprey/ingest/ds-1/a.csv"]
    assert await _watch_rows(runs, recipe) == [("succeeded", _file("a.csv").identity)]


async def test_a_replaced_file_is_a_new_file_and_runs_again(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    recipe, edges = _watched(), _Edges(waiting=[_file("a.csv")])
    executor = _executor(_Recipes([recipe]), edges, runs, valkey)
    await executor.tick(FIRST_SLOT)
    edges.waiting = [_file("a.csv", size=20, minute=5)]
    await executor.tick(FIRST_SLOT + timedelta(minutes=6))
    assert len(edges.files_run) == 2


async def test_one_file_a_tick_the_earliest_first(runs: RecipeRunStore, valkey: Valkey) -> None:
    recipe = _watched()
    edges = _Edges(waiting=[_file("first.csv", minute=0), _file("second.csv", minute=1)])
    executor = _executor(_Recipes([recipe]), edges, runs, valkey)
    await executor.tick(FIRST_SLOT + timedelta(minutes=2))
    assert [f.rsplit("/", 1)[1] for f in edges.files_run] == ["first.csv"]
    await executor.tick(FIRST_SLOT + timedelta(minutes=3))
    assert [f.rsplit("/", 1)[1] for f in edges.files_run] == ["first.csv", "second.csv"]


async def test_a_file_waits_while_a_run_of_the_recipe_is_going(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    recipe = _watched()
    edges = _Edges(waiting=[_file("first.csv")], hold_run=asyncio.Event())
    executor = _executor(_Recipes([recipe]), edges, runs, valkey)
    running = asyncio.create_task(executor.tick(FIRST_SLOT))
    await _until_running(edges, running)
    edges.waiting = [_file("first.csv"), _file("second.csv", minute=1)]
    await asyncio.wait_for(executor.tick(FIRST_SLOT + timedelta(minutes=2)), timeout=10)
    assert len(edges.files_run) == 1
    assert [o for o, _ in await _watch_rows(runs, recipe)] == ["running"]  # nothing recorded
    assert edges.hold_run is not None
    edges.hold_run.set()
    await asyncio.wait_for(running, timeout=10)
    await executor.tick(FIRST_SLOT + timedelta(minutes=3))
    assert [f.rsplit("/", 1)[1] for f in edges.files_run] == ["first.csv", "second.csv"]


async def test_a_flagged_recipes_files_wait_and_run_once_it_is_published_again(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    recipe, edges = _watched(status=StudioRecipeStatus.FLAGGED), _Edges(waiting=[_file("a.csv")])
    await _executor(_Recipes([recipe]), edges, runs, valkey).tick(FIRST_SLOT)
    assert edges.files_run == [] and await _watch_rows(runs, recipe) == []
    republished = recipe.model_copy(update={"status": StudioRecipeStatus.PUBLISHED})
    await _executor(_Recipes([republished]), edges, runs, valkey).tick(FIRST_SLOT)
    assert len(edges.files_run) == 1


async def test_a_paused_watch_takes_nothing(runs: RecipeRunStore, valkey: Valkey) -> None:
    recipe, edges = _watched(), _Edges(waiting=[_file("a.csv")])
    await _executor(_Recipes([recipe], paused={recipe.recipe_id: "by hand"}), edges, runs,
                    valkey).tick(FIRST_SLOT)  # fmt: skip
    assert edges.files_run == [] and await _watch_rows(runs, recipe) == []


async def test_a_refused_file_is_recorded_its_owner_told_and_it_is_not_retried(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    recipe = _watched()
    edges = _Edges(owner=PrincipalRevoked("disabled"), waiting=[_file("a.csv")])
    executor = _executor(_Recipes([recipe]), edges, runs, valkey)
    await executor.tick(FIRST_SLOT)
    await executor.tick(FIRST_SLOT + timedelta(minutes=1))
    assert edges.files_run == []
    assert await _watch_rows(runs, recipe) == [("refused", _file("a.csv").identity)]
    ((owner, _, words),) = edges.notices
    assert owner == OWNER.id
    assert words.startswith("The run of Daily export on the file a.csv was refused: ")
    assert "can no longer sign in" in words


async def test_a_failed_file_tells_its_owner_and_is_not_retried(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    recipe = _watched()
    edges = _Edges(fail_run=ValueError("column amount is missing"), waiting=[_file("a.csv")])
    executor = _executor(_Recipes([recipe]), edges, runs, valkey)
    await executor.tick(FIRST_SLOT)
    await executor.tick(FIRST_SLOT + timedelta(minutes=1))
    assert len(edges.files_run) == 1
    ((_, _, words),) = edges.notices
    assert words == "The run of Daily export on the file a.csv failed: column amount is missing"


async def test_three_refused_files_in_a_row_pause_the_watch(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    recipe = _watched()
    edges, recipes = _Edges(owner=PrincipalRevoked("disabled")), _Recipes([recipe])
    executor = _executor(recipes, edges, runs, valkey)
    for minute in range(3):
        assert recipe.recipe_id not in recipes.paused
        edges.waiting = [_file(f"{minute}.csv", minute=minute)]
        await executor.tick(FIRST_SLOT + timedelta(minutes=minute + 1))
    assert "three refused runs in a row" in recipes.paused[recipe.recipe_id]


async def test_a_schedule_and_a_watch_on_one_recipe_both_run(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    recipe = _recipe(schedule_watch="*.csv", dataset_id="ds-1")
    edges = _Edges(waiting=[_file("a.csv")])
    await _executor(_Recipes([recipe]), edges, runs, valkey).tick(FIRST_SLOT)
    assert sorted(edges.runs_made, key=str) == sorted([(OWNER.id, FIRST_SLOT), (OWNER.id, None)],
                                                      key=str)  # fmt: skip
    assert len(edges.files_run) == 1


async def test_a_watch_whose_dataset_left_the_case_is_refused_and_reads_nothing(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    """Rule 4: the folder read is the recipe's dataset's, so the owner, scoped to the case the watch
    was set in, must still have that dataset there (the case check scopes the owner to `ds-1`)."""
    recipe = _recipe(schedule_cron=None, schedule_watch="*.csv", dataset_id="ds-2")
    edges = _Edges(waiting=[_file("a.csv")])
    await _executor(_Recipes([recipe]), edges, runs, valkey).tick(FIRST_SLOT)
    assert edges.files_run == []
    (row,) = await runs.for_recipe(recipe.recipe_id)
    assert row.outcome == "refused" and "ds-2" in (row.failure or "")


async def test_a_file_taken_before_valkey_lost_its_claims_is_not_taken_again(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    """Amendment 4, point 5: the ledger, not only the claim, remembers a taken file — Valkey keeps
    its claims a week at most, and a restart can lose them sooner."""
    recipe, edges = _watched(), _Edges(waiting=[_file("a.csv")])
    executor = _executor(_Recipes([recipe]), edges, runs, valkey)
    await executor.tick(FIRST_SLOT)
    async for key in valkey.scan_iter(match=f"schedule:watch:{recipe.recipe_id}:*"):
        await valkey.delete(key)
    await executor.tick(FIRST_SLOT + timedelta(minutes=1))
    assert len(edges.files_run) == 1


async def test_a_replica_that_read_the_ledger_before_anothers_run_began_does_not_take_it_too(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    """Amendment 4, point 5: the claim covers the gap the ledger cannot — a replica that read which
    files were taken just before another started the run, and took the lock once it was free."""

    class _StaleLedger:
        def __init__(self, real: RecipeRunStore) -> None:
            self._real = real

        async def watched_files(self, recipe_id: str) -> set[str]:
            return set()  # read before the other replica's run began

        def __getattr__(self, name: str) -> Any:
            return getattr(self._real, name)

    recipe, edges = _watched(), _Edges(waiting=[_file("a.csv")])
    await _executor(_Recipes([recipe]), edges, runs, valkey).tick(FIRST_SLOT)
    stale = _executor(_Recipes([recipe]), edges, _StaleLedger(runs), valkey)  # type: ignore[arg-type]
    await stale.tick(FIRST_SLOT + timedelta(seconds=30))
    assert len(edges.files_run) == 1
