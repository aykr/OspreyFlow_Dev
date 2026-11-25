"""Do a case's gaps and assumptions name, to a reader, linked items that reader may not see? (An away round, D246, 25 November
2026: the drafting session's access finding `ACCESS_FINDING_assessments.md`, proved or disproved by tests. CLAUDE.md rules 3
and 4; ADR-046's hide-in-full rule for judgements.)

**What runs is the product's own code.** The real FastAPI routes (`POST/GET /v1/investigations/{id}/gaps`, `.../assumptions`,
`.../judgements`), the real `IntelligenceGapStore`, `AssumptionStore` and `JudgementStore` classes, and the real
`list_visible_judgements` / `judgement_visible_to`, in process (`TestClient` with no lifespan, the stores and the graph given by
`dependency_overrides`, as `test_suggest_route.py` does). This machine's test runner has no PostgreSQL and no ArcadeDB, so two
things stand in for them, and each refuses what it does not model (rule 15):

* `_PinnedPool` stands in for the stores' asyncpg pool. It accepts **only** the exact SQL the real stores send: an `INSERT`
  whose columns it reads from the statement itself, and the one `SELECT * FROM <table> WHERE investigation_id = $1 AND
  owning_unit = $2 ORDER BY created_at` each store's `list_for_investigation` sends. Any other statement raises. If a store
  gains a visibility clause, this pool refuses it and the test errors; it never answers a query it does not understand.
* `_ClearanceGraph` stands in for `GraphPort.get_node`. It returns a node only to a principal cleared for the node's
  classification and returns `None` otherwise, as the real port does for a node the principal may not see. It also returns
  `None` for an id it does not hold.

**The world.** One case and one unit, `unit-1`; two readers of it, both holding the analyst role. `SECRET_EDITOR` is cleared
SECRET and `OFFICIAL_READER` is cleared OFFICIAL. There are two nodes: `VISIBLE` (OFFICIAL) and `HIDDEN` (SECRET). Everything
here is synthetic (rule 9).

**What each test asserts is the safe behaviour.** A test that is red proves the finding for that path: the route sends the
reader an id they may not see. The controls stay green and prove each red is for the reason claimed, not a broken world:
* the save succeeds;
* the judgement is hidden from the lower reader by the real judgements route;
* a visible link is still sent.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_assumptions_store,
    get_audit,
    get_gaps_store,
    get_graph,
    get_investigations,
    get_judgements_store,
    get_principal,
    get_principal_names,
)
from services.api.assessments import AssumptionStore, IntelligenceGapStore, JudgementStore

from schemas.domain import Principal
from tests.services.api.any_case import AnyCase

CASE = "case-estuary-assessments"
UNIT = "unit-1"
SECRET_EDITOR = Principal(id="analyst-secret", clearance="SECRET", org_unit=UNIT, roles=["analyst"])
OFFICIAL_READER = Principal(id="analyst-official", clearance="OFFICIAL", org_unit=UNIT, roles=["analyst"])
VISIBLE = "node-visible-official"
HIDDEN = "node-hidden-secret"
NOWHERE = "node-that-does-not-exist"

_RANK = {"OFFICIAL": 0, "SECRET": 1, "TOP SECRET": 2}


# ------------------------------------------------------------------------------------------------ the stand-ins


class _PinnedConnection:
    """One connection of `_PinnedPool`: the stores' INSERTs and their one list SELECT, and nothing else."""

    _INSERT = re.compile(r"^INSERT INTO (\w+) \(([^)]*)\) VALUES \(([^)]*)\) ON CONFLICT \(id\) DO UPDATE SET ")
    _LIST = re.compile(r"^SELECT \* FROM (\w+) WHERE investigation_id = \$1 AND owning_unit = \$2 ORDER BY created_at$")

    def __init__(self, tables: dict[str, dict[str, dict[str, Any]]], seen: list[str]) -> None:
        self._tables = tables
        self._seen = seen

    async def execute(self, sql: str, *args: Any) -> str:
        self._seen.append(sql)
        found = self._INSERT.match(sql)
        if found is None:
            raise AssertionError(f"_PinnedPool does not model this statement: {sql!r}")
        table, columns = found.group(1), [c.strip() for c in found.group(2).split(",")]
        if len(columns) != len(args):
            raise AssertionError(f"{len(columns)} columns but {len(args)} values: {sql!r}")
        row = dict(zip(columns, args, strict=True))
        # ON CONFLICT (id) DO UPDATE: the row is replaced in place, keeping its order.
        self._tables.setdefault(table, {})[row["id"]] = row
        return "INSERT 0 1"

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        self._seen.append(sql)
        found = self._LIST.match(sql)
        if found is None:
            raise AssertionError(f"_PinnedPool does not model this query: {sql!r}")
        investigation_id, owning_unit = args
        rows = self._tables.get(found.group(1), {}).values()
        chosen = [r for r in rows if r["investigation_id"] == investigation_id and r["owning_unit"] == owning_unit]
        return sorted(chosen, key=lambda r: r["created_at"])

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        raise AssertionError(f"_PinnedPool does not model this query: {sql!r}")


class _PinnedPool:
    def __init__(self) -> None:
        self.tables: dict[str, dict[str, dict[str, Any]]] = {}
        self.seen: list[str] = []

    @asynccontextmanager
    async def acquire(self) -> Any:
        yield _PinnedConnection(self.tables, self.seen)


class _ClearanceGraph:
    """`GraphPort.get_node` as far as these routes ask it: a node, or `None` when the principal may not see it (or it is not
    there). `include_superseded` changes nothing here: no node in this world was superseded."""

    def __init__(self, classifications: dict[str, str]) -> None:
        self._classifications = classifications
        self.asked: list[tuple[str, str]] = []

    async def get_node(self, node_id: str, principal: Principal, *, include_superseded: bool = False) -> Any:
        self.asked.append((node_id, principal.id))
        classification = self._classifications.get(node_id)
        if classification is None or _RANK[classification] > _RANK[principal.clearance]:
            return None
        return SimpleNamespace(id=node_id, audit=SimpleNamespace(superseded_by=None))


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


class _NoNames:
    async def display_names(self, ids: Any) -> dict[str, str]:
        list(ids)
        return {}


# ------------------------------------------------------------------------------------------------ the world


class _World:
    def __init__(self) -> None:
        self.pool = _PinnedPool()
        self.graph = _ClearanceGraph({VISIBLE: "OFFICIAL", HIDDEN: "SECRET"})
        self.gaps = IntelligenceGapStore(self.pool)  # type: ignore[arg-type]
        self.assumptions = AssumptionStore(self.pool)  # type: ignore[arg-type]
        self.judgements = JudgementStore(self.pool)  # type: ignore[arg-type]
        self.audit = _Audit()
        self.client = TestClient(app)
        app.dependency_overrides[get_graph] = lambda: self.graph
        app.dependency_overrides[get_investigations] = AnyCase
        app.dependency_overrides[get_audit] = lambda: self.audit
        app.dependency_overrides[get_gaps_store] = lambda: self.gaps
        app.dependency_overrides[get_assumptions_store] = lambda: self.assumptions
        app.dependency_overrides[get_judgements_store] = lambda: self.judgements
        app.dependency_overrides[get_principal_names] = _NoNames

    def as_(self, principal: Principal) -> TestClient:
        app.dependency_overrides[get_principal] = lambda: principal
        return self.client


@pytest.fixture
def world() -> Iterator[_World]:
    yield _World()
    app.dependency_overrides.clear()


def _save_gap(world: _World, who: Principal, links: list[str]) -> Any:
    return world.as_(who).post(
        f"/v1/investigations/{CASE}/gaps",
        json={"investigation_id": CASE, "question": "Who supplied the vehicle?", "linked_entities": links, "status": "open"},
    )


def _save_judgement(world: _World, who: Principal, supporting: list[str]) -> Any:
    return world.as_(who).post(
        f"/v1/investigations/{CASE}/judgements",
        json={"investigation_id": CASE, "statement": "The subject is the organiser.", "probability_band": "likely", "supporting": supporting},
    )


def _save_assumption(world: _World, who: Principal, links: list[str]) -> Any:
    return world.as_(who).post(
        f"/v1/investigations/{CASE}/assumptions",
        json={
            "investigation_id": CASE,
            "statement": "The subject acted alone.",
            "if_false_impact": "The organiser judgement falls over.",
            "linked_judgements": links,
        },
    )


def _judgement_ids(world: _World, who: Principal) -> list[str]:
    listed = world.as_(who).get(f"/v1/investigations/{CASE}/judgements")
    assert listed.status_code == 200, listed.text
    return [j["id"] for j in listed.json()["judgements"]]


# ------------------------------------------------------------------------------------------------ (1) a gap's linked entities


def test_a_gap_never_names_to_its_reader_a_node_they_may_not_see(world: _World) -> None:
    """The finding's case (1). Saved by the SECRET editor with a visible and a hidden node, listed by the OFFICIAL reader."""
    saved = _save_gap(world, SECRET_EDITOR, [VISIBLE, HIDDEN])
    assert saved.status_code == 201, saved.text
    listed = world.as_(OFFICIAL_READER).get(f"/v1/investigations/{CASE}/gaps")
    assert listed.status_code == 200, listed.text
    assert [g["question"] for g in listed.json()["gaps"]] == ["Who supplied the vehicle?"]  # the gap itself is served
    assert HIDDEN not in listed.text, f"the OFFICIAL reader was sent the SECRET node's id: {listed.json()['gaps']}"


def test_a_gap_names_to_its_reader_a_node_they_may_see(world: _World) -> None:
    """The control: a visible link reaches the lower reader, so a red above is the hidden id, not an empty answer."""
    assert _save_gap(world, SECRET_EDITOR, [VISIBLE, HIDDEN]).status_code == 201
    gaps = world.as_(OFFICIAL_READER).get(f"/v1/investigations/{CASE}/gaps").json()["gaps"]
    assert VISIBLE in gaps[0]["linked_entities"]


def test_the_graph_stand_in_hides_the_secret_node_from_the_official_reader(world: _World) -> None:
    """The precondition of every red here, through the product's own refusal: a judgement resting on the SECRET node is
    hidden in full from the OFFICIAL reader by the real judgements route (ADR-046), and shown to the SECRET editor."""
    saved = _save_judgement(world, SECRET_EDITOR, [VISIBLE, HIDDEN])
    assert saved.status_code == 201, saved.text
    assert _judgement_ids(world, OFFICIAL_READER) == []
    assert _judgement_ids(world, SECRET_EDITOR) == [saved.json()["id"]]


# ------------------------------------------------------------------------------------------------ (2) an assumption's linked judgements


def test_an_assumption_never_names_to_its_reader_a_judgement_hidden_from_them(world: _World) -> None:
    """The finding's case (2): an assumption links a judgement that the judgements route hides in full from the OFFICIAL reader."""
    judgement = _save_judgement(world, SECRET_EDITOR, [VISIBLE, HIDDEN])
    assert judgement.status_code == 201, judgement.text
    hidden_judgement = judgement.json()["id"]
    assert hidden_judgement not in _judgement_ids(world, OFFICIAL_READER)  # the precondition: hidden in full
    saved = _save_assumption(world, SECRET_EDITOR, [hidden_judgement])
    assert saved.status_code == 201, saved.text
    listed = world.as_(OFFICIAL_READER).get(f"/v1/investigations/{CASE}/assumptions")
    assert listed.status_code == 200, listed.text
    assert [a["statement"] for a in listed.json()["assumptions"]] == ["The subject acted alone."]
    assert hidden_judgement not in listed.text, (
        f"the OFFICIAL reader was sent the id of a judgement hidden from them: {listed.json()['assumptions']}"
    )


def test_an_assumption_names_to_its_reader_a_judgement_they_may_see(world: _World) -> None:
    """The control: a judgement the OFFICIAL reader is shown stays linked for them."""
    judgement = _save_judgement(world, SECRET_EDITOR, [VISIBLE])
    assert judgement.status_code == 201, judgement.text
    seen = judgement.json()["id"]
    assert seen in _judgement_ids(world, OFFICIAL_READER)
    assert _save_assumption(world, SECRET_EDITOR, [seen]).status_code == 201
    assumptions = world.as_(OFFICIAL_READER).get(f"/v1/investigations/{CASE}/assumptions").json()["assumptions"]
    assert assumptions[0]["linked_judgements"] == [seen]


# ------------------------------------------------------------------------------------------------ (3) the write side


def test_a_gap_cannot_link_a_node_its_saver_cannot_confirm(world: _World) -> None:
    """The finding's case (3), as a judgement's citation is refused (`_unverifiable_citations`). The OFFICIAL reader (an analyst,
    so it holds the right to record assessments) links the SECRET node, and then an id that names nothing."""
    for link in (HIDDEN, NOWHERE):
        saved = _save_gap(world, OFFICIAL_READER, [link])
        assert saved.status_code == 422, f"a gap linking {link!r} was stored: {saved.status_code} {saved.text}"


def test_an_assumption_cannot_link_a_judgement_its_saver_cannot_see(world: _World) -> None:
    """The same for an assumption: a judgement hidden from the saver, and an id that names no judgement."""
    judgement = _save_judgement(world, SECRET_EDITOR, [VISIBLE, HIDDEN])
    assert judgement.status_code == 201, judgement.text
    for link in (judgement.json()["id"], "judgement-that-does-not-exist"):
        saved = _save_assumption(world, OFFICIAL_READER, [link])
        assert saved.status_code == 422, f"an assumption linking {link!r} was stored: {saved.status_code} {saved.text}"


def test_a_judgement_cannot_cite_a_node_its_saver_cannot_confirm(world: _World) -> None:
    """The control for the write side: the existing rule the two above are measured against holds in this world."""
    saved = _save_judgement(world, OFFICIAL_READER, [HIDDEN])
    assert saved.status_code == 422, saved.text
    assert saved.json()["error"] == "unverifiable_citation"


# ------------------------------------------------------------------------------------------------ the stand-ins refuse what they do not model


def test_the_pinned_pool_refuses_a_query_it_does_not_model() -> None:
    """Rule 15: the pool answers only the stores' own list query. A visibility clause added to it would be refused, never
    answered as if it were the old query."""
    import asyncio

    pool = _PinnedPool()

    async def ask(sql: str) -> None:
        async with pool.acquire() as conn:
            await conn.fetch(sql, CASE, UNIT)

    asyncio.run(ask("SELECT * FROM intelligence_gaps WHERE investigation_id = $1 AND owning_unit = $2 ORDER BY created_at"))
    for other in (
        "SELECT * FROM intelligence_gaps WHERE investigation_id = $1 AND owning_unit = $2 AND visible ORDER BY created_at",
        "SELECT * FROM intelligence_gaps WHERE id = $1 AND owning_unit = $2",
    ):
        with pytest.raises(AssertionError, match="does not model"):
            asyncio.run(ask(other))


def test_the_real_list_queries_are_the_ones_the_pool_models(world: _World) -> None:
    """The stores' own SQL, as the routes sent it in this world, is the pinned list query and an INSERT: nothing else ran."""
    _save_gap(world, SECRET_EDITOR, [VISIBLE])
    world.as_(OFFICIAL_READER).get(f"/v1/investigations/{CASE}/gaps")
    _save_assumption(world, SECRET_EDITOR, [])
    world.as_(OFFICIAL_READER).get(f"/v1/investigations/{CASE}/assumptions")
    kinds = [sql.split(" ")[0] + " " + sql.split(" ")[2] if sql.startswith("INSERT") else sql for sql in world.pool.seen]
    assert kinds == [
        "INSERT intelligence_gaps",
        "SELECT * FROM intelligence_gaps WHERE investigation_id = $1 AND owning_unit = $2 ORDER BY created_at",
        "INSERT assumptions",
        "SELECT * FROM assumptions WHERE investigation_id = $1 AND owning_unit = $2 ORDER BY created_at",
    ]
    # And the graph was never asked about a gap's links or an assumption's: no visibility step ran on either read.
    assert world.graph.asked == []


def test_the_graph_stand_in_refuses_above_clearance_and_unknown_ids() -> None:
    import asyncio

    graph = _ClearanceGraph({VISIBLE: "OFFICIAL", HIDDEN: "SECRET"})
    assert asyncio.run(graph.get_node(VISIBLE, OFFICIAL_READER)) is not None
    assert asyncio.run(graph.get_node(HIDDEN, OFFICIAL_READER)) is None
    assert asyncio.run(graph.get_node(HIDDEN, SECRET_EDITOR)) is not None
    assert asyncio.run(graph.get_node(NOWHERE, SECRET_EDITOR)) is None
