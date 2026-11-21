"""CO1, C249 and L06: a run's matching job is kept, and what became of it is readable, in words.

Where the failure went. A post-ingest run submits one `resolve_entity_type` job per resolvable type
(`resolution_trigger.submit_post_ingest_resolution_jobs`), and "Resolve now" submits one and answers
its id. The worker marks a job `failed` on its own `job:{id}` record (`JobWorker._process`),
kept for a day. **Nothing read that record**: the only reader of a job's state was the batch
expansion's own route, and `recipe_run.py` threw the ids the hook returned away, so a job that
failed, or whose worker stopped, left the run looking as it had when it began, and a person was
never told.

What this file proves, and the planted fault for each (rule 15):

- `test_a_run_keeps_the_ids_of_the_jobs_it_submitted`: the run's report names its resolution jobs
  (`resolution_jobs`), one per resolvable type the recipe writes. Plant: the ids discarded, as
  `recipe_run.py` did (`await submit_post_ingest_resolution_jobs(...)` with the result unused).
- the states in words, through the real `JobQueue` over a Valkey stand-in that **refuses what the
  real one refuses** (rule 15, the second worked example): an unknown id answers nothing, a record
  past its day's expiry is gone, a marker for a job that does not exist raises `KeyError`, and a
  record that is not a job's is refused when read. A stand-in that only ever held what was put in
  would have said "running" for a job it had lost.
  - failed: said as failed, in this module's words and never the exception's (rule 7);
  - a worker that stopped: a job still "running" past the matching lock's own life is said
    abandoned, not running (the plant: the same record read with no such test says "running");
  - an expired or unknown id and another kind of job's id: the same "no record" answer, so the
    route is no oracle for which ids exist;
  - done with records left out: said, without a count (rules 3 and 7: a count of the corpus's
    records is not a number every reader may have).
- the route (`GET /v1/resolution/jobs/{job_id}`): a reader without the right is refused; one with
  it is answered; and what it says carries no id of a node, no count and no value.

What only a live run can show, owed to the evidence seat (RS1): a real worker failing a real job on
the leased stack, and the Valkey server's own refusals (this stand-in models the ones the code can
meet, not the server's).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api import recipe_run
from services.api.app import app, get_audit, get_jobs, get_principal
from services.api.batch_expansion import JOB_TYPE_BATCH_EXPAND
from services.api.jobs import JOB_TTL_SECONDS, JobQueue
from services.resolve.trigger import JOB_TYPE_RESOLVE_ENTITY_TYPE, LOCK_TTL_SECONDS

from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Principal
from schemas.ingest import LoadReport, RecipeEntity, RowTemplate

ONTOLOGY = load_default_ontology()
READER = Principal(id="reader-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
NO_RIGHT = Principal(id="reader-2", clearance="OFFICIAL", org_unit="unit-1", roles=[])


class _Clock:
    def __init__(self) -> None:
        self.seconds = 0.0

    def advance(self, seconds: float) -> None:
        self.seconds += seconds


class _Valkey:
    """The three commands `JobQueue` uses, refusing as the server does: a key set with `ex` is gone
    after its expiry, `get` of a key never set (or expired) is `None`, and a value that is not what
    was stored is whatever it is. Nothing here makes up a record."""

    def __init__(self, clock: _Clock) -> None:
        self._clock = clock
        self._data: dict[str, tuple[bytes, float | None]] = {}
        self.streams: dict[str, list[dict[str, str]]] = {}

    async def set(self, key: str, value: str, ex: int | None = None, **kwargs: Any) -> bool:
        assert not kwargs, f"unmodelled SET option {sorted(kwargs)}"
        expires = None if ex is None else self._clock.seconds + ex
        self._data[key] = (value.encode(), expires)
        return True

    async def get(self, key: str) -> bytes | None:
        held = self._data.get(key)
        if held is None:
            return None
        value, expires = held
        if expires is not None and self._clock.seconds >= expires:
            del self._data[key]
            return None
        return value

    async def xadd(self, key: str, fields: dict[str, str]) -> str:
        self.streams.setdefault(key, []).append(fields)
        return f"{len(self.streams[key])}-0"

    def plant_raw(self, key: str, value: bytes) -> None:
        self._data[key] = (value, None)


@pytest.fixture
def world() -> SimpleNamespace:
    clock = _Clock()
    valkey = _Valkey(clock)
    return SimpleNamespace(clock=clock, valkey=valkey, jobs=JobQueue(valkey))  # type: ignore[arg-type]


async def _status(world: SimpleNamespace, job_id: str) -> Any:
    from services.api.resolution_job_status import resolution_job_status

    return await resolution_job_status(world.jobs, job_id, now=_now(world))


def _now(world: SimpleNamespace) -> datetime:
    return datetime(2026, 11, 21, 12, 0, tzinfo=UTC) + timedelta(seconds=world.clock.seconds)


async def _submit(world: SimpleNamespace, entity_type: str = "Person") -> str:
    return await world.jobs.submit(JOB_TYPE_RESOLVE_ENTITY_TYPE, {"entity_type": entity_type})


async def _started_at(world: SimpleNamespace, job_id: str, started: datetime) -> None:
    record = await world.jobs.get_status(job_id)
    await world.jobs._save(record.model_copy(update={"state": "running", "started_at": started}))


# --- the states in words --------------------------------------------------------------------------


async def test_a_waiting_job_is_said_to_be_waiting(world: SimpleNamespace) -> None:
    job = await _submit(world)
    said = await _status(world, job)
    assert said.state == "queued"
    assert "waiting" in said.words and "Person" in said.words


async def test_a_running_job_is_said_to_be_running_with_its_stage(world: SimpleNamespace) -> None:
    job = await _submit(world)
    await world.jobs.mark_running(job)
    await world.jobs.mark_progress(job, "Comparing 40 pairs")
    said = await _status(world, job)
    assert said.state == "running"
    assert "running" in said.words and "Comparing 40 pairs" in said.words


async def test_a_failed_job_is_said_failed_in_our_words_never_the_exceptions(
    world: SimpleNamespace,
) -> None:
    job = await _submit(world)
    await world.jobs.mark_running(job)
    secret = "Binder Error: No function matches year(VARCHAR) for node n-4471 'Mercer'"
    await world.jobs.mark_failed(job, secret)
    said = await _status(world, job)
    assert said.state == "failed"
    assert "failed" in said.words and "Person" in said.words
    assert "none of its results were saved" in said.words
    for leaked in ("Binder", "n-4471", "Mercer", "VARCHAR"):
        assert leaked not in said.words, (
            "rule 7: the exception's text is the operator's, not the reader's"
        )


async def test_a_job_still_running_past_the_matching_locks_life_is_said_abandoned(
    world: SimpleNamespace,
) -> None:
    """Its worker stopped: nothing reclaims a stream entry, so it will never finish. The plant is
    the same record read as `running`, the status it kept until this was read (ADR-151's own cost,
    A8): the case below shows it is the age that says abandoned, not the state."""
    job = await _submit(world)
    started = _now(world)
    await _started_at(world, job, started)
    world.clock.advance(LOCK_TTL_SECONDS + 61)
    said = await _status(world, job)
    assert said.state == "abandoned"
    assert "stopped" in said.words and "run it again" in said.words


async def test_a_job_running_within_the_locks_life_is_still_running(
    world: SimpleNamespace,
) -> None:
    job = await _submit(world)
    await _started_at(world, job, _now(world))
    world.clock.advance(LOCK_TTL_SECONDS - 60)
    assert (await _status(world, job)).state == "running"


async def test_a_finished_job_is_said_finished(world: SimpleNamespace) -> None:
    job = await _submit(world)
    await world.jobs.mark_done(
        job,
        {"skipped": False, "nodes_processed": 9, "same_as_written": 2, "records_left_out": 0,
         "left_out": []},
    )  # fmt: skip
    said = await _status(world, job)
    assert said.state == "done" and "finished" in said.words
    assert said.records_left_out is False
    assert "9" not in said.words, "rule 7: no count of the corpus's records in a reader's words"


async def test_a_finished_job_that_left_records_out_says_so_without_a_count(
    world: SimpleNamespace,
) -> None:
    job = await _submit(world)
    await world.jobs.mark_done(
        job,
        {"skipped": False, "nodes_processed": 9, "same_as_written": 2, "records_left_out": 3,
         "left_out": [
             {"node_id": "n-1", "property": "date_of_birth", "reason": "not_an_iso_date"}
         ]},
    )  # fmt: skip
    said = await _status(world, job)
    assert said.state == "done" and said.records_left_out is True
    assert "left out" in said.words and "date" in said.words
    assert "3" not in said.words and "n-1" not in said.words


async def test_a_job_the_overlap_guard_turned_away_is_said_not_to_have_run(
    world: SimpleNamespace,
) -> None:
    job = await _submit(world)
    await world.jobs.mark_done(
        job, {"skipped": True, "reason": "a resolution run is already in progress"}
    )
    said = await _status(world, job)
    assert said.state == "not_run"
    assert "did not run" in said.words and "already" in said.words


# --- what the real store refuses ------------------------------------------------------------------


async def test_an_unknown_id_and_an_expired_one_and_another_kinds_are_answered_alike(
    world: SimpleNamespace,
) -> None:
    unknown = await _status(world, "no-such-job")
    expired_id = await _submit(world)
    world.clock.advance(JOB_TTL_SECONDS + 1)
    expired = await _status(world, expired_id)
    other_id = await world.jobs.submit(JOB_TYPE_BATCH_EXPAND, {"case_id": "c-1"})
    other = await _status(world, other_id)
    assert unknown.state == expired.state == other.state == "gone"
    assert unknown.words == expired.words == other.words, "no oracle for which ids exist"
    assert "day" in unknown.words, "the reader is told records are kept a day, so why it is gone"


async def test_the_stand_in_refuses_a_marker_for_a_job_that_does_not_exist(
    world: SimpleNamespace,
) -> None:
    """The stand-in is not a dict that accepts anything: `JobQueue` raises `KeyError` for a
    transition of a job with no record, as it does against the real server."""
    with pytest.raises(KeyError):
        await world.jobs.mark_failed("never-submitted", "x")
    expired = await _submit(world)
    world.clock.advance(JOB_TTL_SECONDS + 1)
    with pytest.raises(KeyError):
        await world.jobs.mark_done(expired, {})


async def test_a_record_that_is_not_a_job_is_not_reported_as_gone(world: SimpleNamespace) -> None:
    """A corrupt record is a fault of the store, not an absent job: it is raised for the route to
    refuse, never turned into a comforting "no record"."""
    world.valkey.plant_raw("job:corrupt", b"not json at all")
    with pytest.raises(ValueError):
        await _status(world, "corrupt")


# --- the run keeps the ids ------------------------------------------------------------------------


def _template(*types: str) -> RowTemplate:
    return RowTemplate(
        entities=[
            RecipeEntity(ref=f"e{i}", pole_class="object", type=t) for i, t in enumerate(types)
        ]
    )


class _Audit:
    def __init__(self) -> None:
        self.recorded: list[dict[str, Any]] = []

    async def record(self, **fields: Any) -> None:
        self.recorded.append(fields)


async def _run_once(
    monkeypatch: pytest.MonkeyPatch, world: SimpleNamespace, *, enabled: bool = True
) -> tuple[Any, _Audit]:
    audit = _Audit()

    async def no_gate(*_a: Any, **_k: Any) -> None:
        return None

    async def loader(*_a: Any, **_k: Any) -> LoadReport:
        return LoadReport(load_id="l-1", recipe_id="r-1", recipe_version=1, nodes_created=2)

    class _Stream:
        def __init__(self, _valkey: Any) -> None: ...

        async def publish(self, *_a: Any, **_k: Any) -> None:
            return None

    class Deps:
        jobs = world.jobs
        config = SimpleNamespace(post_ingest_resolution=enabled)
        ontology = ONTOLOGY
        handling_scheme = load_uk_le_scheme()
        valkey = None

        def __init__(self) -> None:
            self.audit = audit

        def __getattr__(self, name: str) -> Any:
            return None

    monkeypatch.setattr(recipe_run, "_rule_gate", no_gate)
    monkeypatch.setattr(recipe_run, "run_published_recipe", loader)
    monkeypatch.setattr(recipe_run, "ChangeStreamWriter", _Stream)
    recipe = SimpleNamespace(
        pipeline=None,
        recipe_id="r-1",
        row_template=_template("Person", "Endpoint"),
        dataset_id=None,
    )
    report = await recipe_run._execute_recipe_run(
        Deps(),  # type: ignore[arg-type]
        principal=READER,
        recipe=recipe,  # type: ignore[arg-type]
        investigation_id="case-1",
        source_location=None,
        trigger="manual",
        sink=None,  # type: ignore[arg-type]
    )
    return report, audit


async def test_a_run_keeps_the_ids_of_the_jobs_it_submitted(
    monkeypatch: pytest.MonkeyPatch, world: SimpleNamespace
) -> None:
    report, audit = await _run_once(monkeypatch, world)
    ids = getattr(report, "resolution_jobs", None)
    # Only Person declares a resolution block: one job, and it is on record under that id.
    assert ids is not None and len(ids) == 1, "the run discarded the ids the hook returned"
    record = await world.jobs.get_status(ids[0])
    assert record is not None and record.payload == {"entity_type": "Person"}
    # And the run's own audit row names it, for the operator who has only the audit.
    (entry,) = audit.recorded
    assert entry["resolved_query"]["resolution_jobs"] == ids


async def test_a_run_with_resolution_off_keeps_no_ids(
    monkeypatch: pytest.MonkeyPatch, world: SimpleNamespace
) -> None:
    report, _ = await _run_once(monkeypatch, world, enabled=False)
    assert getattr(report, "resolution_jobs", None) == []


async def test_a_dead_job_of_a_run_is_reported_dead_from_the_runs_own_ids(
    monkeypatch: pytest.MonkeyPatch, world: SimpleNamespace
) -> None:
    """L06 end to end over the stand-in: the run's ids, a worker that failed the job, and the
    status read from the id the run kept says failed, where the run's own state would have said
    only what it said when it began."""
    report, _ = await _run_once(monkeypatch, world)
    (job,) = report.resolution_jobs
    await world.jobs.mark_running(job)
    await world.jobs.mark_failed(job, "ValueError: Invalid isoformat string: '12/03/1980'")
    said = await _status(world, job)
    assert said.state == "failed"
    assert "12/03/1980" not in said.words


# --- the route ------------------------------------------------------------------------------------


@pytest.fixture
def client(world: SimpleNamespace) -> Iterator[TestClient]:
    app.dependency_overrides[get_principal] = lambda: READER
    app.dependency_overrides[get_jobs] = lambda: world.jobs
    app.dependency_overrides[get_audit] = _Audit
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


async def test_the_route_answers_a_reader_who_holds_the_right(
    world: SimpleNamespace, client: TestClient
) -> None:
    job = await _submit(world)
    await world.jobs.mark_failed(job, "boom")
    response = client.get(f"/v1/resolution/jobs/{job}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "failed" and "failed" in body["words"]
    assert set(body) == {"job_id", "state", "words", "records_left_out"}, (
        "nothing of the job's payload or result: no ids, counts or values (rule 7)"
    )
    assert "boom" not in response.text


async def test_the_route_refuses_a_reader_without_the_right(
    world: SimpleNamespace, client: TestClient
) -> None:
    job = await _submit(world)
    app.dependency_overrides[get_principal] = lambda: NO_RIGHT
    response = client.get(f"/v1/resolution/jobs/{job}")
    assert response.status_code == 403
    assert json.loads(response.text)["detail"]["error"] == "right_required"


async def test_the_route_answers_an_unknown_id_as_it_answers_an_expired_one(
    world: SimpleNamespace, client: TestClient
) -> None:
    expired = await _submit(world)
    world.clock.advance(JOB_TTL_SECONDS + 1)
    first = client.get("/v1/resolution/jobs/no-such-job")
    second = client.get(f"/v1/resolution/jobs/{expired}")
    assert first.status_code == second.status_code == 200
    assert first.json()["state"] == second.json()["state"] == "gone"
    assert first.json()["words"] == second.json()["words"]
