"""ADR-110 decisions 2–4 and Amendment 2: the executor, slot by slot, against a real Valkey (the
claim and the lock) and the real run ledger in Postgres.

The edges are fakes, each refusing what the real one refuses (rule 15): the owner resolver raises
only what `PrincipalResolver.resolve_for_owner_detailed` raises, `PrincipalRevoked` for a disabled
account, `PrincipalExchangeRefused` for one the identity provider no longer knows (or an exchange it
refused) and `PrincipalExchangeUnavailable` for an identity provider it cannot reach, and after it
the custom-role read `app._owner_with_custom_roles` adds may fail as a store does; the case check
raises `InsufficientAccessError` for an owner below Editor, as `InvestigationStore.get_authorized`
does. The run itself is a stand-in that writes the ledger as `run_recipe_as` does — the one run path
is `test_recipe_run_path.py`'s and `test_recipe_run_ledger.py`'s to prove.

The two-replica case runs two executors in two processes against the same Valkey and ledger.
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import pytest
from services.api.config import PostgresConfig, ValkeyConfig
from services.api.folder_watch import WatchedFile
from services.api.investigations import AccessLevel, InsufficientAccessError
from services.api.recipe_runs import RecipeRunStore
from services.api.scheduler import ScheduleExecutor, ScheduleRunRefused, SourceWatch
from services.ingest.engine import RowKeyRunInProgress
from valkey.asyncio import Valkey

from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from principal_auth import (
    PrincipalExchangeError,
    PrincipalExchangeRefused,
    PrincipalExchangeUnavailable,
    PrincipalRevoked,
)
from schemas.domain import Principal
from schemas.ingest import LoadReport, StudioRecipeDraft, StudioRecipeStatus

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
    #: The exchange: the owner, or only what the real resolver raises
    #: (`PrincipalExchangeError`'s own).
    owner: Principal | PrincipalExchangeError = field(default_factory=lambda: OWNER)
    #: The custom-role read `with_custom_roles` makes after the exchange: a store's fault, or none.
    roles_read: Exception | None = None
    case_level_ok: bool = True
    runs_made: list[tuple[str, datetime | None]] = field(default_factory=list)
    hold_run: asyncio.Event | None = None
    fail_run: Exception | None = None
    notices: list[tuple[str, str, str]] = field(default_factory=list)
    #: ADR-110 Amendment 4: the files the recipe's folder watch finds waiting, earliest first.
    waiting: list[WatchedFile] = field(default_factory=list)
    files_run: list[str] = field(default_factory=list)
    cases_run: list[str] = field(default_factory=list)
    #: Amendment 6 point 1: the read each run was given (`None` for a pipeline's own watch).
    reads: list[Any] = field(default_factory=list)
    #: ADR-110 Amendment 6 point 6: the owner's case that loads into a dataset, as
    #: `scope_to_dataset` finds it; `None` when they have none.
    case_loading_into: dict[str, str] = field(default_factory=lambda: {"ds-1": "case-1"})

    async def case_for_dataset(self, owner: Principal, dataset_id: str) -> str | None:
        return self.case_loading_into.get(dataset_id)

    async def watch_files(self, recipe: StudioRecipeDraft, now: datetime) -> list[WatchedFile]:
        """As `folder_watch.waiting_files`: only the files whose whole name the watch's pattern
        matches (a fake that ignored the pattern hid a pipeline running by two watches at once)."""
        import fnmatch

        pattern = recipe.schedule_watch or ""
        return [f for f in self.waiting if fnmatch.fnmatchcase(f.name, pattern)]

    async def notify(self, owner_id: str, recipe: StudioRecipeDraft, words: str) -> None:
        self.notices.append((owner_id, recipe.recipe_id, words))

    async def resolve_owner(self, owner_id: str) -> Principal:
        """As `app._owner_with_custom_roles` over `resolve_for_owner_detailed`: the exchange, then
        the owner's custom roles read from their store."""
        if isinstance(self.owner, PrincipalExchangeError):
            raise self.owner
        if self.roles_read is not None:
            raise self.roles_read
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
    recipes: _Recipes,
    edges: _Edges,
    runs: RecipeRunStore,
    valkey: Valkey,
    source_watches: Any = None,
) -> ScheduleExecutor:
    async def run(
        owner: Principal,
        recipe: StudioRecipeDraft,
        case: str,
        slot: datetime | None,
        source_file: WatchedFile | None = None,
        trigger: str | None = None,
        refresh: Any = None,
    ) -> LoadReport:
        """What `run_recipe_as` does to the ledger, around a load that writes nothing."""
        edges.runs_made.append((owner.id, slot))
        edges.reads.append(refresh)
        edges.cases_run.append(case)
        if source_file is not None:
            edges.files_run.append(source_file.location)
        trigger = trigger or ("watch" if source_file else "schedule" if slot else "manual")
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
        source_watches=source_watches,
        case_for_dataset=edges.case_for_dataset,
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
        (
            _Edges(
                owner=PrincipalExchangeRefused(
                    "owner 'approver-1' is not known to the identity provider"
                )
            ),
            "identity provider refused",
        ),
        (_Edges(owner=PrincipalExchangeUnavailable("timed out")), "could not be reached"),
        (_Edges(owner=OWNER.model_copy(update={"roles": ["analyst"]})), "schedule_pipelines"),
        (_Edges(case_level_ok=False), "Editor"),
    ],
    ids=["revoked", "unknown-to-idp", "idp-unreachable", "right-withdrawn", "case-access-lowered"],
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


async def test_an_owner_out_of_date_on_entra_is_refused_in_its_words_and_never_pauses_the_schedule(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    """ADR-148 Amendment 16: an owner not signed in within 24 hours decides nothing about them, so
    four slots in a row are refused, each in the 24-hour words and told so, and the schedule is
    never paused; once they sign in it runs at its next slot. Held at the ledger and the pause, not
    only at the refusal's flag (the lane review of 876383a, should 9)."""
    from principal_auth import ACCESS_OUT_OF_DATE_WORDS, NEXT_SLOT_WORDS, PrincipalAccessOutOfDate

    recipe = _recipe()
    recipes, edges = _Recipes([recipe]), _Edges(owner=PrincipalAccessOutOfDate(OWNER.id, None))
    executor = _executor(recipes, edges, runs, valkey)
    for day in range(4):
        await executor.tick(FIRST_SLOT + timedelta(days=day))
    assert recipe.recipe_id not in recipes.paused
    rows = await runs.for_recipe(recipe.recipe_id)
    assert [r.outcome for r in rows] == ["refused"] * 4
    assert all(f"{ACCESS_OUT_OF_DATE_WORDS}: {NEXT_SLOT_WORDS}" in (r.failure or "") for r in rows)
    assert all("could not be reached" not in (r.failure or "") for r in rows)
    assert all("has not signed in to OspreyFlow within the last 24 hours" in words
               for _, _, words in edges.notices)  # fmt: skip
    edges.owner = OWNER
    await executor.tick(FIRST_SLOT + timedelta(days=4))
    assert len(edges.runs_made) == 1


async def test_an_owner_the_identity_provider_no_longer_knows_pauses_on_the_third_slot(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    """ADR-110 Amendment 19 (the merger's round-4 review): the identity provider reached and
    refusing (here a deleted account, as `resolve_for_owner_detailed` raises it) is a fact about the
    owner, so it counts toward the three that pause (Amendment 3, point 3), told "was refused" each
    time."""
    recipe = _recipe()
    refused = PrincipalExchangeRefused("owner 'x' is not known to the identity provider")
    recipes, edges = _Recipes([recipe]), _Edges(owner=refused)
    executor = _executor(recipes, edges, runs, valkey)
    for day in range(2):
        await executor.tick(FIRST_SLOT + timedelta(days=day))
    assert recipe.recipe_id not in recipes.paused
    await executor.tick(FIRST_SLOT + timedelta(days=2))
    assert "three refused runs in a row" in recipes.paused[recipe.recipe_id]
    assert [o for o, _ in await _outcomes(runs, recipe)] == ["refused"] * 3
    assert all(
        words.endswith("was refused: its owner may no longer run it.")
        and "identity provider" not in words
        for _, _, words in edges.notices
    )


async def test_a_fault_acting_as_the_owner_is_told_failed_and_never_pauses_the_schedule(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    """ADR-110 Amendment 19 (Admin's review): a fault acting as the owner that is no refusal of the
    exchange (here the custom-role store's read failing, as asyncpg raises it) is told "failed",
    and, being nothing about the owner, never counts toward the three refusals that pause the
    schedule, as an identity provider outage does not."""
    recipe = _recipe()
    lost = asyncpg.exceptions.ConnectionDoesNotExistError(
        "connection was closed in the middle of operation"
    )
    recipes, edges = _Recipes([recipe]), _Edges(roles_read=lost)
    executor = _executor(recipes, edges, runs, valkey)
    for day in range(4):
        await executor.tick(FIRST_SLOT + timedelta(days=day))
    assert recipe.recipe_id not in recipes.paused
    assert [o for o, _ in await _outcomes(runs, recipe)] == ["refused"] * 4
    assert all(
        words.endswith("failed. Its pipeline's Runs, in the Ingest Studio, say why.")
        and "connection was closed" not in words
        for _, _, words in edges.notices
    )


async def test_a_fault_acting_as_the_owner_keeps_its_error_in_the_log(
    runs: RecipeRunStore, valkey: Valkey, caplog: pytest.LogCaptureFixture
) -> None:
    """ADR-110 Amendment 19 point 5: the notice says "failed" and never the error, which "stays in
    the run's ledger and the log". The ledger's words for a fault acting as the owner carry none of
    it, so the log must: one record at ERROR naming the owner, with the error itself attached (the
    studio lane's review of rules-hyg 531aa24). The error is planted where the real resolver's
    caller meets it, the custom-role read after the exchange, in asyncpg's shape."""
    recipe = _recipe()
    lost = asyncpg.exceptions.ConnectionDoesNotExistError(
        "connection was closed in the middle of operation"
    )
    edges = _Edges(roles_read=lost)
    with caplog.at_level(logging.ERROR, logger="services.api.scheduler"):
        await _executor(_Recipes([recipe]), edges, runs, valkey).tick(FIRST_SLOT)
    kept = [r for r in caplog.records if r.exc_info and r.exc_info[1] is lost]
    assert len(kept) == 1 and kept[0].name == "services.api.scheduler"
    assert kept[0].levelno == logging.ERROR
    assert OWNER.id in kept[0].getMessage()
    assert [o for o, _ in await _outcomes(runs, recipe)] == ["refused"]
    assert [words for _, _, words in edges.notices] and all(
        "connection was closed" not in words for _, _, words in edges.notices
    )


async def test_resolving_the_owner_logs_a_fault_but_not_a_refusal(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The same, offline, at `_resolve` itself (no store: the ledger and Valkey are never reached):
    a fault is logged with its error attached; a refusal of the exchange (revoked, refused, not
    reached) is the owner's or the identity provider's, in fixed words, and is not logged as a
    fault."""
    from services.api.scheduler import _Refused

    lost = asyncpg.exceptions.ConnectionDoesNotExistError(
        "connection was closed in the middle of operation"
    )
    cases: list[tuple[Exception, _Edges, bool]] = [
        (lost, _Edges(roles_read=lost), True),
        *(
            (refusal, _Edges(owner=refusal), False)
            for refusal in (
                PrincipalRevoked("disabled"),
                PrincipalExchangeRefused("not known"),
                PrincipalExchangeUnavailable("down"),
            )
        ),
    ]
    for planted, edges, logged in cases:
        executor = _executor(_Recipes([]), edges, None, None)  # type: ignore[arg-type]
        caplog.clear()
        with caplog.at_level(logging.ERROR, logger="services.api.scheduler"):
            with pytest.raises(_Refused) as refused:
                await executor._resolve(OWNER.id)
        kept = [r for r in caplog.records if r.exc_info and r.exc_info[1] is planted]
        assert (len(kept) == 1) is logged, (planted, caplog.records)
        assert "connection was closed" not in str(refused.value)
        if logged:
            assert refused.value.kind == "failed" and OWNER.id in kept[0].getMessage()


async def test_a_run_refused_as_in_progress_is_never_a_refusal_and_never_pauses_the_schedule(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    """ADR-127 decision 5: a scheduled run that finds another run of the recipe into the case
    still going is refused (`RowKeyRunInProgress`), which says nothing about the owner. It is
    recorded as a failed run, never as `refused`, so no number of them is three refusals (ADR-110
    Amendment 3), and the owner is told in words."""
    recipe = _recipe()
    recipes = _Recipes([recipe])
    edges = _Edges(fail_run=RowKeyRunInProgress(recipe.recipe_id))
    executor = _executor(recipes, edges, runs, valkey)
    for day in range(5):
        await executor.tick(FIRST_SLOT + timedelta(days=day))
    assert recipe.recipe_id not in recipes.paused
    outcomes = [o for o, _ in await _outcomes(runs, recipe)]
    assert outcomes == ["failed"] * 5 and "refused" not in outcomes
    assert all(words.endswith("did not run: an earlier run into its case was still going.")
               for _, _, words in edges.notices)  # fmt: skip
    assert await runs.refusals_in_a_row(recipe.recipe_id) == 0


async def test_a_refused_run_tells_its_owner_in_words(runs: RecipeRunStore, valkey: Valkey) -> None:
    """ADR-110 decision 10 and Amendment 3, point 1."""
    recipe, edges = _recipe(), _Edges(owner=PrincipalRevoked("disabled"))
    await _executor(_Recipes([recipe]), edges, runs, valkey).tick(FIRST_SLOT)
    ((owner, recipe_id, words),) = edges.notices
    assert (owner, recipe_id) == ("approver-1", recipe.recipe_id)
    assert words.startswith("The scheduled run of Daily export due ")
    # ADR-110 Amendment 19: the kind's fixed sentence; the refusal's own words (which name the
    # owner's id) stay in the ledger.
    assert words.endswith("was refused: its owner may no longer run it.")
    assert "approver-1" not in words and "sign in" not in words


async def test_a_failed_run_tells_its_owner_in_words(runs: RecipeRunStore, valkey: Valkey) -> None:
    recipe, edges = _recipe(), _Edges(fail_run=FileNotFoundError("no such file: a.csv"))
    await _executor(_Recipes([recipe]), edges, runs, valkey).tick(FIRST_SLOT)
    ((owner, _, words),) = edges.notices
    assert owner == "approver-1"
    assert words.endswith("failed. Its pipeline's Runs, in the Ingest Studio, say why.")
    # The error's own text stays in the ledger and the log (rule 7).
    assert "no such file" not in words


async def test_a_graph_store_error_never_reaches_the_owners_words(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    """ADR-110 Amendment 19, rule 7: an error raised while a run loads is told by its kind alone.
    Planted in the shape the graph adapter raises (`ArcadeDBError` carries the server's whole
    reply, `client.py`), naming a host, a type and a row's key."""
    from adapters.graph_arcadedb.client import ArcadeDBError

    reply = ('ArcadeDB error 500: {"error":"Internal error","exception":"com.arcadedb.exception.'
             'DuplicatedKeyException","detail":"Duplicated key [ROW-7731] on Person[source_key] at '
             'arcadedb.internal:2480"}')  # fmt: skip
    recipe = _recipe()
    edges = _Edges(fail_run=ArcadeDBError(reply, status_code=500))
    await _executor(_Recipes([recipe]), edges, runs, valkey).tick(FIRST_SLOT)
    ((_, _, words),) = edges.notices
    lead = ScheduleExecutor._due(recipe, FIRST_SLOT)  # "The scheduled run of Daily export due …"
    assert words == f"{lead} failed. Its pipeline's Runs, in the Ingest Studio, say why."
    for leaked in ("ArcadeDB", "ROW-7731", "source_key", "arcadedb.internal", "Duplicated"):
        assert leaked not in words


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


async def test_a_quota_refusal_tells_its_owner_in_the_quota_sentence(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    """ADR-110 Amendment 19 with ADR-141 decision 6: a run refused past a quota tells its owner the
    fixed quota sentence, never the quota's own words, which name its scope and number."""
    from services.api.run_quotas import QuotaRefused, quota_words

    recipe, edges = _recipe(), _Edges(fail_run=QuotaRefused(quota_words("dataset", 3)))
    await _executor(_Recipes([recipe]), edges, runs, valkey).tick(FIRST_SLOT)
    ((_, _, words),) = edges.notices
    lead = ScheduleExecutor._due(recipe, FIRST_SLOT)
    assert words == (f"{lead} was refused: today's run quota is used. The next may start after "
                     "midnight, or an administrator may raise the quota in Admin › Running › "
                     "Operations.")  # fmt: skip


async def test_a_quota_refused_file_tells_its_owner_the_quota_sentence(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    """ADR-110 Amendment 19 with ADR-141 decision 6, at the watched-file site: the fixed quota
    sentence, never the quota's own words."""
    from services.api.run_quotas import QuotaRefused, quota_words

    recipe = _watched()
    edges = _Edges(fail_run=QuotaRefused(quota_words("unit", 5)), waiting=[_file("a.csv")])
    await _executor(_Recipes([recipe]), edges, runs, valkey).tick(FIRST_SLOT)
    ((_, _, words),) = edges.notices
    assert words == ("The run of Daily export on the file a.csv was refused: today's run quota is "
                     "used. The next may start after midnight, or an administrator may raise the "
                     "quota in Admin › Running › Operations.")  # fmt: skip
    assert "5 runs" not in words and "unit's" not in words


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
    assert words == (
        "The run of Daily export on the file a.csv was refused: its owner may no longer run it."
    )


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
    assert words == (
        "The run of Daily export on the file a.csv failed. Its pipeline's Runs, in the "
        "Ingest Studio, say why."
    )
    assert "column amount" not in words


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


# --- ADR-110 Amendment 6 point 5: a source's watch runs every pipeline that reads it -------------


@dataclass
class _SourceWatches:
    """The deployed pipelines reading a watched source, as the Postgres stores answer them: every
    published or needing-attention recipe of the source's dataset reading its location."""

    pairs: list[tuple[StudioRecipeDraft, SourceWatch]]
    paused: dict[str, str] = field(default_factory=dict)

    async def watching(self) -> list[tuple[StudioRecipeDraft, SourceWatch]]:
        return [
            (r, replace(w, paused=True)) if w.source_id in self.paused else (r, w)
            for r, w in self.pairs
        ]

    async def set_paused(self, source_id: str, *, paused: bool, reason: str | None) -> None:
        if paused:
            self.paused[source_id] = reason or ""
        else:
            self.paused.pop(source_id, None)


def _keyed(**overrides: Any) -> StudioRecipeDraft:
    from schemas.ingest import DeduplicateConfig, FieldBinding

    fields: dict[str, Any] = {
        "schedule_cron": None,
        "schedule_owner": None,
        "schedule_set_at": None,
        "dataset_id": "ds-1",
        "deduplicate": DeduplicateConfig(key=[FieldBinding(field="caller")]),
    }
    return _recipe(**(fields | overrides))


WATCH = SourceWatch(
    source_id="src-1", dataset_id="ds-1", pattern="calls-*.csv", owner=OWNER.id, set_at=SET_AT
)


async def _refresh_rows(runs: RecipeRunStore, recipe: StudioRecipeDraft) -> list[tuple[str, Any]]:
    return [
        (r.outcome, r.source_file)
        for r in reversed(await runs.for_recipe(recipe.recipe_id))
        if r.trigger == "source_refresh"
    ]


async def test_a_source_watch_runs_each_pipeline_reading_it_once_on_the_file_as_its_owner(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    calls, visits = _keyed(label="Calls"), _keyed(label="Visits")
    edges = _Edges(waiting=[_file("calls-0601.csv")])
    watches = _SourceWatches([(calls, WATCH), (visits, WATCH)])
    executor = _executor(_Recipes([]), edges, runs, valkey, watches)
    await executor.tick(FIRST_SLOT)
    await executor.tick(FIRST_SLOT + timedelta(minutes=1))
    assert edges.runs_made == [(OWNER.id, None), (OWNER.id, None)]
    assert edges.cases_run == ["case-1", "case-1"]
    taken = _file("calls-0601.csv").identity
    for recipe in (calls, visits):
        assert await _refresh_rows(runs, recipe) == [("succeeded", taken)]
    rows = [r for recipe in (calls, visits) for r in await runs.for_recipe(recipe.recipe_id)]
    load_ids = {r.load_id for r in rows}
    assert len(load_ids) == 2, "each pipeline under its own load"


async def test_a_source_watch_runs_its_pipelines_in_the_sources_mode(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    """Amendment 6 point 1: each file is read as the source's policy says, not as a full snapshot
    that keeps every row; a pipeline's own watch has no source, so no read."""
    from services.ingest.watermark import RefreshRead

    snapshot = replace(WATCH, dropped_rows="withdraw")
    incremental = replace(
        WATCH, source_id="src-2", pattern="visits-*.csv", mode="incremental",
        watermark_column="seq",
    )  # fmt: skip
    calls, visits = _keyed(label="Calls"), _keyed(label="Visits")
    own = _keyed(schedule_watch="other-*.csv", schedule_owner=OWNER.id, schedule_set_at=SET_AT)
    edges = _Edges(
        waiting=[_file("calls-0601.csv"), _file("visits-0601.csv"), _file("other-0601.csv")]
    )
    watches = _SourceWatches([(calls, snapshot), (visits, incremental)])
    executor = _executor(_Recipes([own]), edges, runs, valkey, watches)
    await executor.tick(FIRST_SLOT)
    assert edges.reads == [
        RefreshRead(source_id="src-1", mode="snapshot", dropped_rows="withdraw"),
        RefreshRead(source_id="src-2", mode="incremental", watermark_column="seq"),
        None,
    ]


async def test_a_pipeline_reading_a_watched_source_runs_by_the_source_not_by_its_own_watch(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    both = _keyed(schedule_watch="*.csv", schedule_owner=OWNER.id, schedule_set_at=SET_AT)
    # visits.csv matches the pipeline's own pattern and not the source's: it must wait.
    edges = _Edges(waiting=[_file("calls-0601.csv"), _file("visits.csv", minute=1)])
    executor = _executor(_Recipes([both]), edges, runs, valkey, _SourceWatches([(both, WATCH)]))
    for minute in range(3):
        await executor.tick(FIRST_SLOT + timedelta(minutes=minute))
    assert edges.files_run == ["/var/lib/osprey/ingest/ds-1/calls-0601.csv"]
    assert [r.trigger for r in await runs.for_recipe(both.recipe_id)] == ["source_refresh"]


async def test_a_needs_attention_pipeline_is_recorded_blocked_and_the_others_run(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    flagged = _keyed(label="Flagged", status=StudioRecipeStatus.FLAGGED)
    fine = _keyed(label="Fine")
    edges = _Edges(waiting=[_file("calls-0601.csv")])
    watches = _SourceWatches([(flagged, WATCH), (fine, WATCH)])
    executor = _executor(_Recipes([]), edges, runs, valkey, watches)
    await executor.tick(FIRST_SLOT)
    await executor.tick(FIRST_SLOT + timedelta(minutes=1))
    taken = _file("calls-0601.csv").identity
    assert await _refresh_rows(runs, flagged) == [("blocked", taken)]
    assert await _refresh_rows(runs, fine) == [("succeeded", taken)]
    assert len(edges.files_run) == 1


async def test_a_keyless_pipeline_is_refused_in_words_and_never_run(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    keyless = _keyed(deduplicate=None)
    edges = _Edges(waiting=[_file("calls-0601.csv")])
    executor = _executor(_Recipes([]), edges, runs, valkey, _SourceWatches([(keyless, WATCH)]))
    await executor.tick(FIRST_SLOT)
    await executor.tick(FIRST_SLOT + timedelta(minutes=1))
    assert edges.files_run == []
    (row,) = await runs.for_recipe(keyless.recipe_id)
    assert (row.outcome, row.trigger) == ("refused", "source_refresh")
    assert "deduplication key" in (row.failure or "")


async def test_a_paused_source_watch_takes_nothing(runs: RecipeRunStore, valkey: Valkey) -> None:
    recipe = _keyed()
    edges = _Edges(waiting=[_file("calls-0601.csv")])
    watches = _SourceWatches([(recipe, WATCH)], paused={"src-1": "waiting for chapter 9"})
    executor = _executor(_Recipes([]), edges, runs, valkey, watches)
    await executor.tick(FIRST_SLOT)
    assert edges.files_run == []
    assert await runs.for_recipe(recipe.recipe_id) == []


async def test_a_refresh_whose_owner_lost_clearance_or_their_account_is_refused(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    """The fakes refuse what the real ones refuse (rule 15): a source marked above the owner's
    clearance, and an owner the identity provider has disabled (`PrincipalRevoked`)."""
    secret = _keyed(label="Secret", handling=dict(_HANDLING, classification="SECRET"))
    edges = _Edges(waiting=[_file("calls-0601.csv")])
    executor = _executor(_Recipes([]), edges, runs, valkey, _SourceWatches([(secret, WATCH)]))
    await executor.tick(FIRST_SLOT)
    (row,) = await runs.for_recipe(secret.recipe_id)
    assert (row.outcome, row.trigger) == ("refused", "source_refresh")
    assert "clearance" in (row.failure or "")

    revoked = _keyed(label="Revoked")
    edges = _Edges(waiting=[_file("calls-0602.csv")], owner=PrincipalRevoked(OWNER.id))
    executor = _executor(_Recipes([]), edges, runs, valkey, _SourceWatches([(revoked, WATCH)]))
    await executor.tick(FIRST_SLOT)
    (row,) = await runs.for_recipe(revoked.recipe_id)
    assert row.outcome == "refused"
    assert "can no longer sign in" in (row.failure or "")
    assert edges.files_run == []


async def test_three_refused_refreshes_pause_the_sources_policy_not_the_pipeline(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    recipe = _keyed(handling=dict(_HANDLING, classification="SECRET"))
    recipes = _Recipes([])
    watches = _SourceWatches([(recipe, WATCH)])
    for minute in range(3):
        edges = _Edges(waiting=[_file(f"calls-{minute}.csv", minute=minute)])
        executor = _executor(recipes, edges, runs, valkey, watches)
        await executor.tick(FIRST_SLOT + timedelta(minutes=minute))
    assert "three refused runs in a row" in watches.paused["src-1"]
    assert recipes.paused == {}


async def test_the_run_goes_through_the_owners_case_loading_into_the_dataset_or_is_refused(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    """ADR-110 Amendment 6 point 6: a pipeline that names no case runs through a case of the owner's
    that loads into the source's dataset; with none, it is refused in words and reads nothing."""
    caseless = _keyed(schedule_case=None)
    edges = _Edges(waiting=[_file("calls-0601.csv")], case_loading_into={"ds-1": "case-9"})
    executor = _executor(_Recipes([]), edges, runs, valkey, _SourceWatches([(caseless, WATCH)]))
    await executor.tick(FIRST_SLOT)
    assert edges.cases_run == ["case-9"]

    stranded = _keyed(schedule_case=None, label="Stranded")
    edges = _Edges(waiting=[_file("calls-0602.csv")], case_loading_into={})
    executor = _executor(_Recipes([]), edges, runs, valkey, _SourceWatches([(stranded, WATCH)]))
    await executor.tick(FIRST_SLOT)
    assert edges.files_run == []
    (row,) = await runs.for_recipe(stranded.recipe_id)
    assert row.outcome == "refused"
    assert "loads into" in (row.failure or "")


async def test_a_file_a_refresh_took_is_not_taken_again_once_valkey_lost_its_claims(
    runs: RecipeRunStore, valkey: Valkey
) -> None:
    """As Amendment 4 point 5 for a pipeline's own watch: the ledger remembers the file a source
    refresh took, so a lost claim never runs the pipeline on it twice."""
    recipe = _keyed()
    edges = _Edges(waiting=[_file("calls-0601.csv")])
    executor = _executor(_Recipes([]), edges, runs, valkey, _SourceWatches([(recipe, WATCH)]))
    await executor.tick(FIRST_SLOT)
    async for key in valkey.scan_iter(match=f"schedule:watch:{recipe.recipe_id}:*"):
        await valkey.delete(key)
    await executor.tick(FIRST_SLOT + timedelta(minutes=1))
    assert len(edges.files_run) == 1


async def test_a_ledger_made_before_source_refresh_takes_it_once_connected(
    runs: RecipeRunStore,
) -> None:
    """The trigger's CHECK is the column's own: a ledger made before `source_refresh` existed
    refuses it until connecting puts the current list back."""
    import asyncpg

    dsn = PostgresConfig.from_env().dsn
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "ALTER TABLE recipe_runs DROP CONSTRAINT IF EXISTS recipe_runs_trigger_check; "
            "ALTER TABLE recipe_runs ADD CONSTRAINT recipe_runs_trigger_check "
            # NOT VALID: the old list for new rows, whatever earlier cases have written.
            "CHECK (trigger IN ('manual', 'schedule', 'watch', 'release')) NOT VALID"
        )
    finally:
        await conn.close()
    store = await RecipeRunStore.connect(dsn)
    try:
        recipe = _keyed()
        run_id = await store.start(
            recipe_id=recipe.recipe_id, recipe_version=2, investigation_id="case-1",
            trigger="source_refresh", slot=None, run_as=OWNER.id, source=_source(recipe),
            now=datetime.now(UTC),
        )  # fmt: skip
        assert run_id
    finally:
        await store.close()
