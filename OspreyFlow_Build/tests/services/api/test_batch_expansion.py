"""Promote the expansion to a batch job (`06_DECISIONS.md` ADR-151), through the real app and the
real job worker's `_process`, with `worker_main.register_all` binding the handler as the worker image
and the Conduit both do.

The graph is `FakeGraphPort`, given an `expand` that judges each element by its own body (handling and
datasets) for the principal it is given, as the adapter's traversal does: the fake's own `expand`
hands back its result unfiltered, which would accept a job that expanded as no one (rule 15's
third example: the fake refuses what the real adapter refuses). The adapter's own filter is
ArcadeDB's conformance suite, and live on a lease (`process/lanes/rules-b/v052batch/`).

What a mistake here would do, and the case that catches it (each planted red in
`process/lanes/rules-b/v052batch/plants.py`):

- a node the requester may not read saved in the view: `test_a_hidden_node_never_lands_in_the_batch_view`;
- a reader below Editor starting one: `test_a_principal_who_cannot_edit_the_case_cannot_start_a_batch`;
- a requester who lost Editor since still saving one:
  `test_a_batch_whose_requester_lost_edit_is_refused_and_saves_nothing`;
- a result past the cap cut to fit, or saved as a view that never opens:
  `test_a_batch_past_the_cap_is_refused_with_figures_and_saves_nothing`;
- another member reading the job: `test_another_members_batch_is_not_found`;
- an exception's own words served: `test_a_failed_batch_says_this_adrs_words_not_the_exception`;
- a lowered clearance not applied when the view is next opened:
  `test_a_batch_view_opened_after_a_clearance_drop_hides_what_was_lost`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api import app as conduit
from services.api import batch_expansion, worker_main
from services.api import case_views as case_views_module
from services.api.app import app
from services.api.batch_expansion import (
    FAILED_WORDS,
    GONE_WORDS,
    JOB_TYPE_BATCH_EXPAND,
    BatchExpandBindings,
)
from services.api.case_views import InMemoryCaseViewStore
from services.api.dataset_scope import case_datasets
from services.api.investigations import AccessLevel
from services.api.jobs import JobQueue
from services.api.worker import JobWorker
from services.api.working_set.service import WorkingSetService

from ontology.handling import load_uk_le_scheme, withhold_sources
from ontology.loader import load_default_ontology
from schemas.domain import ExpandRequest, Principal, Subgraph

from . import test_case_views as views_world
from .test_case_views import CASE, OTHER, UNIT, _Audit, _in, _Investigations, _Resolver
from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME, edge, node

BATCHES = f"/v1/investigations/{CASE}/batch-expansions"
VIEWS = f"/v1/investigations/{CASE}/views"
FROM_OPEN = {"request": {"node_ids": ["open"], "depth": 1}}


class _Valkey:
    """What `JobQueue` and the batch's claim ask of Valkey, and nothing else: keys with `NX` and
    `GET`, and a stream appended to. Any other command is an `AttributeError`, not a pass."""

    def __init__(self) -> None:
        self.kv: dict[str, bytes] = {}
        self.streams: dict[str, list[dict[str, Any]]] = {}

    async def set(
        self, key: str, value: Any, *, nx: bool = False, ex: int | None = None, get: bool = False
    ) -> Any:
        old = self.kv.get(key)
        if nx and old is not None:
            return None
        self.kv[key] = value if isinstance(value, bytes) else str(value).encode()
        return old if get else True

    async def get(self, key: str) -> bytes | None:
        return self.kv.get(key)

    async def delete(self, key: str) -> int:
        return 1 if self.kv.pop(key, None) is not None else 0

    async def xadd(self, key: str, fields: dict[str, Any]) -> bytes:
        self.streams.setdefault(key, []).append(fields)
        return b"1-0"


class _Graph(FakeGraphPort):
    """`expand` as the adapter's traversal answers it: only what `principal` may read, a link only
    with both its ends."""

    async def expand(self, req: ExpandRequest, principal: Principal) -> Subgraph:
        self.expand_requests.append(req)
        nodes = [n for n in self.expand_result.nodes if self._node_readable(principal, n)]
        shown = {n.id for n in nodes}
        edges = [
            e
            for e in self.expand_result.edges
            if e.source in shown and e.target in shown and self._edge_readable(principal, e)
        ]
        if not shown & set(req.node_ids):  # no seed it may read: nothing to expand from
            return Subgraph(nodes=[], edges=[])
        return Subgraph(
            nodes=[withhold_sources(n, principal) for n in nodes],
            edges=[withhold_sources(e, principal) for e in edges],
        )


class _World:
    def __init__(self) -> None:
        base = views_world._World()
        self.datasets = base.datasets
        nodes = [
            _in("src", node("open")),
            _in("src", node("near")),
            _in("src", node("secret", "SECRET")),
            _in("other", node("elsewhere")),
        ]
        edges = [
            _in("src", edge("e-open-near", "open", "near")),
            _in("src", edge("e-open-secret", "open", "secret")),
            _in("src", edge("e-open-elsewhere", "open", "elsewhere")),
        ]
        self.graph = _Graph(
            Subgraph(nodes=nodes, edges=edges), graph_nodes=nodes, graph_edges=edges
        )
        self.views = InMemoryCaseViewStore()
        self.audit = _Audit()
        self.valkey = _Valkey()
        self.jobs = JobQueue(self.valkey)  # type: ignore[arg-type]
        self.investigations = _Investigations()
        self.worker = JobWorker(self.valkey, self.jobs, self.graph)  # type: ignore[arg-type]
        worker_main.register_all(
            self.worker,
            ontology=load_default_ontology(),
            scheme=load_uk_le_scheme(),
            valkey=self.valkey,
            analyst_layers=self._layers,
            alerts=None,
            judgement_store=None,
            batch=BatchExpandBindings(
                views=self.views,
                investigations=lambda: self.investigations,
                datasets=self.datasets,
                jobs=self.jobs,
                audit=self.audit,
            ),
        )

    @staticmethod
    async def _layers() -> set[str]:
        return set()

    def queued(self) -> list[str]:
        stream = self.jobs.stream_key(JOB_TYPE_BATCH_EXPAND)
        return [str(f["job_id"]) for f in self.valkey.streams.get(stream, [])]

    def run_queued(self) -> None:
        """Every queued batch run as the worker runs one: `JobWorker._process`, the handler
        `register_all` bound, in a task of the worker's own."""
        stream = self.jobs.stream_key(JOB_TYPE_BATCH_EXPAND)
        entries = self.valkey.streams.pop(stream, [])
        handler = self.worker._handlers[JOB_TYPE_BATCH_EXPAND]  # noqa: SLF001

        async def drain() -> None:
            for fields in entries:
                await self.worker._process(JOB_TYPE_BATCH_EXPAND, str(fields["job_id"]), handler)  # noqa: SLF001

        asyncio.run(drain())


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[_World]:
    # Vic is an analyst holding only Viewer on the case: the `investigate` right without the level.
    vic = Principal(id="vic", clearance="SECRET", org_unit=UNIT, roles=["analyst"])
    monkeypatch.setitem(views_world.PEOPLE, "vic", vic)
    monkeypatch.setitem(views_world.LEVELS, "vic", AccessLevel.VIEWER)
    held = _World()
    state = {
        "principal_resolver": _Resolver(),
        "investigations": held.investigations,
        "datasets": held.datasets,
        "audit": held.audit,
        "graph": held.graph,
        "working_set": WorkingSetService(held.graph, FakeWorkingSetStore(), SCHEME),
        "case_views": held.views,
        "target_models": None,
        "jobs": held.jobs,
        "valkey": held.valkey,
    }
    saved = {k: getattr(app.state, k, None) for k in state}
    for key, value in state.items():
        setattr(app.state, key, value)
    try:
        yield held
    finally:
        for key, value in saved.items():
            setattr(app.state, key, value)
        app.dependency_overrides.clear()


def _as(who: str) -> TestClient:
    return TestClient(app, headers={"Authorization": f"Bearer {who}"})


def _started(who: str = "bob", body: dict[str, Any] | None = None) -> str:
    response = _as(who).post(BATCHES, json=body or FROM_OPEN)
    assert response.status_code == 202, response.json()
    assert response.json()["state"] == "queued"
    return str(response.json()["id"])


def _status(job_id: str, who: str = "bob") -> dict[str, Any]:
    response = _as(who).get(f"{BATCHES}/{job_id}")
    assert response.status_code == 200, response.json()
    return dict(response.json())


def _stored(world: _World) -> list[Any]:
    return list(world.views.views.values())


# --- access (rules 3 and 4) ---------------------------------------------------------------------


def test_a_hidden_node_never_lands_in_the_batch_view(world: _World) -> None:
    """Bob (OFFICIAL) promotes an expansion from `open`: the saved view holds `open` and `near`,
    never the SECRET node or the node in a dataset the case does not read, though both are a link
    away. Alice (SECRET), opening it once shared, does not see them either: they were never chosen."""
    job_id = _started()
    world.run_queued()
    done = _status(job_id)
    assert done["state"] == "done", done
    assert (done["nodes"], done["links"]) == (2, 1)
    [view] = _stored(world)
    assert sorted(view.node_ids) == ["near", "open"]
    assert view.created_by == "bob" and view.shared is False
    assert _as("bob").post(f"{VIEWS}/{view.id}/share").status_code == 200
    opened = _as("alice").get(f"{VIEWS}/{view.id}")
    assert sorted(n["id"] for n in opened.json()["nodes"]) == ["near", "open"]
    for hidden in ("secret", "elsewhere"):
        assert hidden not in opened.text and hidden not in str(done)


def test_the_expansion_is_read_with_the_requesters_own_scope(world: _World) -> None:
    """The principal the graph is asked with is Bob's, scoped to the case's datasets now: never an
    unscoped one (`datasets is None` is the Conduit's own background reading, ADR-099)."""
    asked: list[Principal] = []
    real = world.graph.expand

    async def recording(req: ExpandRequest, principal: Principal) -> Subgraph:
        asked.append(principal)
        return await real(req, principal)

    world.graph.expand = recording  # type: ignore[method-assign]
    _started()
    world.run_queued()
    [principal] = asked
    assert principal.id == "bob" and principal.clearance == "OFFICIAL"
    assert principal.datasets is not None and "other" not in principal.datasets


def test_a_principal_who_cannot_edit_the_case_cannot_start_a_batch(world: _World) -> None:
    """Vic holds `investigate` and Viewer on the case: refused 403 as `expand` refuses him, and
    nothing is queued. Carol, of the unit with no level, is told the case does not exist. Rita, a
    Reports Viewer, lacks the right."""
    refused = _as("vic").post(BATCHES, json=FROM_OPEN)
    assert refused.status_code == 403, refused.json()
    assert _as("carol").post(BATCHES, json=FROM_OPEN).status_code == 404
    right = _as("rita").post(BATCHES, json=FROM_OPEN)
    assert right.status_code == 403 and right.json()["detail"]["error"] == "right_required"
    assert world.queued() == []


def test_the_edit_check_fails_with_the_route_at_viewer(world: _World) -> None:
    """Rule 15, at the route's own dependency: with the Editor gate overridden to Viewer, Vic's
    batch is queued, so the case above is what holds the line."""
    app.dependency_overrides[conduit._AT_EDITOR] = conduit._authorized_at(AccessLevel.VIEWER)  # noqa: SLF001
    assert _as("vic").post(BATCHES, json=FROM_OPEN).status_code == 202
    assert len(world.queued()) == 1


def test_a_batch_whose_requester_lost_edit_is_refused_and_saves_nothing(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = _started()
    monkeypatch.setitem(views_world.LEVELS, "bob", AccessLevel.VIEWER)
    world.run_queued()
    refused = _status(job_id)
    assert refused["state"] == "refused"
    assert refused["refusal"]["code"] == "no_longer_an_editor"
    assert refused["words"] == (
        "You can no longer edit this case, so the expansion was not run and nothing was saved."
    )
    assert _stored(world) == [] and world.graph.expand_requests == []


def test_another_members_batch_is_not_found(world: _World) -> None:
    """A job is its requester's: Alice, the case's Author, is told Bob's does not exist, as is Bob
    asking for it through another case or for an id nobody made."""
    job_id = _started()
    assert _as("alice").get(f"{BATCHES}/{job_id}").status_code == 404
    elsewhere = _as("bob").get(f"/v1/investigations/{OTHER}/batch-expansions/{job_id}")
    assert elsewhere.status_code == 404
    unknown = _as("bob").get(f"{BATCHES}/no-such-job")
    assert unknown.status_code == 404
    assert elsewhere.json() == unknown.json() == {"error": "batch_expansion_not_found"}


# --- never cut (rule 2) -------------------------------------------------------------------------


def test_a_batch_past_the_cap_is_refused_with_figures_and_saves_nothing(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(batch_expansion, "MAX_NODES", 1)
    nodes = _started()
    world.run_queued()
    refused = _status(nodes)
    assert refused["state"] == "refused"
    assert refused["refusal"] == {
        "code": "too_many_nodes", "cap_kind": "nodes", "cap": 1, "would_be": 2
    }  # fmt: skip
    assert refused["words"] == (
        "The expansion found 2 nodes, more than the 1 a view can show, so nothing was saved. "
        "Narrow it by link type, depth or dates and try again."
    )
    monkeypatch.setattr(batch_expansion, "MAX_NODES", 50_000)
    monkeypatch.setattr(batch_expansion, "MAX_EDGES", 0)
    links = _started()
    world.run_queued()
    refused = _status(links)
    assert refused["refusal"] == {
        "code": "too_many_links", "cap_kind": "edges", "cap": 0, "would_be": 1
    }  # fmt: skip
    assert refused["words"].startswith("The expansion found 1 links among its nodes")
    assert _stored(world) == []


def test_the_caps_are_the_working_sets() -> None:
    """The batch's limit is the view's, which `open_view` refuses past (ADR-151 decision 5)."""
    from services.api.working_set import models

    assert (batch_expansion.MAX_NODES, batch_expansion.MAX_EDGES) == (
        models.MAX_NODES,
        models.MAX_EDGES,
    )


def test_a_batch_finding_nothing_is_refused(world: _World) -> None:
    """Expanding from the SECRET node, Bob finds nothing he may see: refused, and said as for a
    node that does not exist."""
    job_id = _started(body={"request": {"node_ids": ["secret"]}})
    world.run_queued()
    refused = _status(job_id)
    assert refused["refusal"]["code"] == "found_nothing"
    assert refused["words"] == "The expansion found nothing you may see, so nothing was saved."
    assert _stored(world) == []


def test_a_second_batch_while_one_runs_is_refused_naming_it(world: _World) -> None:
    first = _started()
    again = _as("bob").post(BATCHES, json=FROM_OPEN)
    assert again.status_code == 409
    assert again.json() == {
        "error": "batch_expansion_running",
        "detail": batch_expansion.RUNNING_WORDS,
        "id": first,
    }
    # Another requester is not held up by Bob's.
    assert _as("alice").post(BATCHES, json=FROM_OPEN).status_code == 202
    world.run_queued()
    assert _status(first)["state"] == "done"
    assert _as("bob").post(BATCHES, json=FROM_OPEN).status_code == 202


def test_a_claim_left_by_a_finished_job_is_taken_over(world: _World) -> None:
    """A job that failed without clearing its claim does not block the next."""
    first = _started()
    asyncio.run(world.jobs.mark_failed(first, "worker died"))
    assert _as("bob").post(BATCHES, json=FROM_OPEN).status_code == 202


def test_a_batch_that_takes_too_long_is_refused_with_its_stage(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(batch_expansion, "TIME_LIMIT_SECONDS", 0.05)
    real = world.graph.expand

    async def slow(req: ExpandRequest, principal: Principal) -> Subgraph:
        await asyncio.sleep(1)
        return await real(req, principal)

    world.graph.expand = slow  # type: ignore[method-assign]
    job_id = _started()
    world.run_queued()
    refused = _status(job_id)
    assert refused["refusal"]["code"] == "took_too_long"
    assert refused["words"] == (
        "The expansion took longer than ten minutes, so nothing was saved. It had reached: "
        "expanding from 1 node. Narrow it by link type, depth or dates and try again."
    )
    assert _stored(world) == []


# --- its words ----------------------------------------------------------------------------------


def test_a_failed_batch_says_this_adrs_words_not_the_exception(world: _World) -> None:
    async def broken(req: ExpandRequest, principal: Principal) -> Subgraph:
        raise RuntimeError("gremlin: vertex secret-17 in dataset other")

    world.graph.expand = broken  # type: ignore[method-assign]
    job_id = _started()
    world.run_queued()
    response = _as("bob").get(f"{BATCHES}/{job_id}")
    assert response.json() == {
        "id": job_id, "state": "failed", "words": FAILED_WORDS,
        "view": None, "nodes": None, "links": None, "refusal": None,
    }  # fmt: skip
    assert "secret-17" not in response.text and "gremlin" not in response.text


def test_a_view_saved_but_not_audited_is_taken_away_and_the_job_fails(world: _World) -> None:
    """`FAILED_WORDS` says nothing was saved: a failure after the save deletes the view."""

    async def refusing(**kwargs: Any) -> None:
        if kwargs["action"] == "save_case_view":
            raise RuntimeError("audit down")

    world.audit.record = refusing  # type: ignore[method-assign]
    job_id = _started()
    world.run_queued()
    assert _status(job_id)["state"] == "failed"
    assert _stored(world) == []


def test_queued_and_running_are_said_in_words(world: _World) -> None:
    job_id = _started()
    assert _status(job_id) == {
        "id": job_id, "state": "queued", "words": "Waiting for the batch expansion to start.",
        "view": None, "nodes": None, "links": None, "refusal": None,
    }  # fmt: skip
    asyncio.run(world.jobs.mark_running(job_id))
    asyncio.run(world.jobs.mark_progress(job_id, "Counting the links among 41,203 nodes"))
    running = _status(job_id)
    assert (running["state"], running["words"]) == (
        "running",
        "Counting the links among 41,203 nodes.",
    )


def test_done_names_what_was_saved_and_says_so_once_the_view_is_gone(world: _World) -> None:
    job_id = _started(body={**FROM_OPEN, "name": "Open's contacts"})
    world.run_queued()
    done = _status(job_id)
    assert done["words"] == "Saved 2 nodes and 1 link as your private view “Open's contacts”."
    assert done["view"]["name"] == "Open's contacts" and done["view"]["chosen"] == 2
    assert _as("bob").delete(f"{VIEWS}/{done['view']['id']}").status_code in (200, 204)
    gone = _status(job_id)
    assert (gone["state"], gone["words"], gone["view"]) == ("done", GONE_WORDS, None)


def test_the_view_is_named_after_its_seeds_when_no_name_is_given(world: _World) -> None:
    job_id = _started()
    world.run_queued()
    assert _status(job_id)["view"]["name"].startswith("Expanded from 1 node, ")


# --- the saved view -----------------------------------------------------------------------------


def test_the_saved_view_opens_as_the_lens(world: _World) -> None:
    job_id = _started(body={**FROM_OPEN, "justification": "Kestrel's contacts"})
    world.run_queued()
    view_id = _status(job_id)["view"]["id"]
    opened = _as("bob").get(f"{VIEWS}/{view_id}")
    assert opened.status_code == 200
    assert sorted(n["id"] for n in opened.json()["nodes"]) == ["near", "open"]
    assert [e["id"] for e in opened.json()["edges"]] == ["e-open-near"]
    assert opened.json()["missing"] == 0
    actions = [r["action"] for r in world.audit.records]
    assert "batch_expand" in actions and "save_case_view" in actions
    saved = next(r for r in world.audit.records if r["action"] == "save_case_view")
    assert saved["resolved_query"] == {"view_id": view_id, "from_batch": job_id}
    assert saved["justification"] == "Kestrel's contacts"


def test_a_batch_view_opened_after_a_clearance_drop_hides_what_was_lost(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cost of ADR-151's clearance snapshot, bounded: Alice (SECRET) saves the SECRET node in
    her view; her clearance then drops to OFFICIAL, and her next open of the view does not show it,
    counting it missing without naming it. ADR-144's own case proves a different reader; this is the
    same reader later. Red with `open_view` returning the stored selection (the plant below)."""
    job_id = _started("alice")
    world.run_queued()
    view = _status(job_id, "alice")["view"]
    assert sorted(_stored(world)[0].node_ids) == ["near", "open", "secret"]
    lowered = views_world.PEOPLE["alice"].model_copy(update={"clearance": "OFFICIAL"})
    monkeypatch.setitem(views_world.PEOPLE, "alice", lowered)
    opened = _as("alice").get(f"{VIEWS}/{view['id']}")
    assert sorted(n["id"] for n in opened.json()["nodes"]) == ["near", "open"]
    assert opened.json()["missing"] == 1
    assert "secret" not in opened.text


def test_the_clearance_drop_check_fails_with_the_stored_selection_returned(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15: `_read_selection` planted to read what the view stored as its saver could."""
    job_id = _started("alice")
    world.run_queued()
    view = _status(job_id, "alice")["view"]

    async def stored(graph: Any, node_ids: Any, principal: Principal) -> Any:
        unscoped = principal.model_copy(update={"datasets": None, "clearance": "SECRET"})
        nodes = await graph.get_nodes(list(node_ids), unscoped)
        return nodes, await graph.edges_among([n.id for n in nodes], unscoped)

    monkeypatch.setattr(case_views_module, "_read_selection", stored)
    lowered = views_world.PEOPLE["alice"].model_copy(update={"clearance": "OFFICIAL"})
    monkeypatch.setitem(views_world.PEOPLE, "alice", lowered)
    assert "secret" in _as("alice").get(f"{VIEWS}/{view['id']}").text


# --- where it runs ------------------------------------------------------------------------------


def test_the_worker_registers_batch_expand() -> None:
    """`register_all` names it, so the worker image runs it and the Conduit registers the same."""
    assert worker_main.registered_job_types()[JOB_TYPE_BATCH_EXPAND] == (
        "services.api.batch_expansion:run_batch_expand_job"
    )


def test_the_case_scope_ends_with_the_job(world: _World) -> None:
    """`scope_to_case` sets the request's case in a context variable; the job runs in a task of
    its own, so the next job the worker takes is not read as this case's."""

    async def run_and_look() -> Any:
        record = await world.jobs.get_status(_started())
        handler = world.worker._handlers[JOB_TYPE_BATCH_EXPAND]  # noqa: SLF001
        assert record is not None
        await handler(record.payload, graph=world.graph, tx="tx")
        return case_datasets()

    assert asyncio.run(run_and_look()) in (None, [], ())


# --- the view's input ---------------------------------------------------------------------------


def test_a_batch_view_passes_the_same_validators_a_client_view_does(world: _World) -> None:
    """The orchestrator's ruling on ADR-151: the batch's view is validated as a client's is, its
    selection bound alone raised to the view's cap. Every validator `CaseViewInput` has,
    `BatchViewInput` has; and a job whose payload names a view no client could post (a name past
    200 characters) fails and saves nothing. Red with the input built by `model_construct`, which
    skips them all (`process/lanes/rules-b/v052batch/plants.py`)."""
    from schemas.case_views import CaseViewInput
    from services.api.batch_expansion import BatchViewInput

    client = CaseViewInput.__pydantic_decorators__
    batch = BatchViewInput.__pydantic_decorators__
    assert set(client.model_validators) <= set(batch.model_validators)
    assert set(client.field_validators) <= set(batch.field_validators)
    assert BatchViewInput.model_fields["name"].metadata == CaseViewInput.model_fields["name"].metadata
    assert BatchViewInput(name="n", node_ids=["a"] * 50_000).node_ids is not None
    with pytest.raises(ValueError, match="exactly one"):
        BatchViewInput(name="n")

    async def overlong() -> Any:
        job_id = _started()
        record = await world.jobs.get_status(job_id)
        assert record is not None
        payload = {**record.payload, "name": "x" * 201}
        await world.jobs._save(record.model_copy(update={"payload": payload}))  # noqa: SLF001
        return job_id

    job_id = asyncio.run(overlong())
    world.run_queued()
    assert _status(job_id)["state"] == "failed"
    assert _stored(world) == []


def test_a_job_left_running_by_a_stopped_worker_is_failed_and_does_not_block(world: _World) -> None:
    """Nothing reclaims a pending stream entry, so a job whose worker stopped stays `running`.
    A minute past its own limit it is said as failed, and the requester may start another. Red with
    `abandoned` never true (`plants.py`): held up for the record's 24 hours."""
    from datetime import UTC, datetime, timedelta

    job_id = _started()

    async def left() -> None:
        await world.jobs.mark_running(job_id)
        record = await world.jobs.get_status(job_id)
        assert record is not None and record.started_at is not None
        then = datetime.now(UTC) - timedelta(seconds=batch_expansion.TIME_LIMIT_SECONDS + 61)
        await world.jobs._save(record.model_copy(update={"started_at": then}))  # noqa: SLF001

    asyncio.run(left())
    assert _status(job_id)["words"] == FAILED_WORDS
    assert _as("bob").post(BATCHES, json=FROM_OPEN).status_code == 202


def test_a_job_running_within_its_limit_still_blocks(world: _World) -> None:
    job_id = _started()
    asyncio.run(world.jobs.mark_running(job_id))
    assert _status(job_id)["state"] == "running"
    assert _as("bob").post(BATCHES, json=FROM_OPEN).status_code == 409
