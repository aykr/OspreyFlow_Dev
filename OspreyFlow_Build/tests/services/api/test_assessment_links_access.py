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
OTHER_CASE = "case-another-investigation"

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


def _save_judgement(world: _World, who: Principal, supporting: list[str], case: str = CASE) -> Any:
    return world.as_(who).post(
        f"/v1/investigations/{case}/judgements",
        json={"investigation_id": case, "statement": "The subject is the organiser.", "probability_band": "likely", "supporting": supporting},
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


def _judgement_ids(world: _World, who: Principal, case: str = CASE) -> list[str]:
    listed = world.as_(who).get(f"/v1/investigations/{case}/judgements")
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
    # The visibility step runs, through the graph, as the person: the saver's link is confirmed as the saver, and the reader's
    # list is checked as the reader. (Before the fix of 25 November 2026 this list was empty: the graph was never asked about
    # a gap's links on either side, which was the fault itself.)
    assert world.graph.asked == [(VISIBLE, SECRET_EDITOR.id), (VISIBLE, OFFICIAL_READER.id)]


def test_the_graph_stand_in_refuses_above_clearance_and_unknown_ids() -> None:
    import asyncio

    graph = _ClearanceGraph({VISIBLE: "OFFICIAL", HIDDEN: "SECRET"})
    assert asyncio.run(graph.get_node(VISIBLE, OFFICIAL_READER)) is not None
    assert asyncio.run(graph.get_node(HIDDEN, OFFICIAL_READER)) is None
    assert asyncio.run(graph.get_node(HIDDEN, SECRET_EDITOR)) is not None
    assert asyncio.run(graph.get_node(NOWHERE, SECRET_EDITOR)) is None


# ------------------------------------------------------------------------------------------------ planted faults at the real call site (rule 15)


def _gaps_problems(world: _World) -> list[str]:
    """What the gap read test checks, as a function the real route and each planted one go through."""
    listed = world.as_(OFFICIAL_READER).get(f"/v1/investigations/{CASE}/gaps")
    found = [] if listed.status_code == 200 else [f"the read answered {listed.status_code}"]
    if HIDDEN in listed.text:
        found.append("the OFFICIAL reader was sent the SECRET node's id")
    if VISIBLE not in listed.text:
        found.append("the visible link was dropped")
    return found


def _assumptions_problems(world: _World, hidden_judgement: str, shown_judgement: str) -> list[str]:
    listed = world.as_(OFFICIAL_READER).get(f"/v1/investigations/{CASE}/assumptions")
    found = [] if listed.status_code == 200 else [f"the read answered {listed.status_code}"]
    if hidden_judgement in listed.text:
        found.append("the OFFICIAL reader was sent the id of a judgement hidden from them")
    if shown_judgement not in listed.text:
        found.append("the visible judgement's link was dropped")
    return found


def test_a_hidden_link_put_back_at_the_gaps_routes_call_site_is_found(world: _World, monkeypatch: pytest.MonkeyPatch) -> None:
    """The real `list_gaps_route` calls `list_visible_gaps` (`services/api/app.py`): wrapped so that it puts back the one hidden
    link the real filter removed, the check that finds nothing in the real route finds it."""
    import services.api.app as conduit
    from services.api.assessments import list_visible_gaps

    assert _save_gap(world, SECRET_EDITOR, [VISIBLE, HIDDEN]).status_code == 201
    assert _gaps_problems(world) == []

    async def planted(store: Any, investigation_id: str, principal: Principal, graph: Any) -> Any:
        real = await list_visible_gaps(store, investigation_id, principal, graph)
        return [g.model_copy(update={"linked_entities": [*g.linked_entities, HIDDEN]}) for g in real]

    monkeypatch.setattr(conduit, "list_visible_gaps", planted)
    assert _gaps_problems(world) == ["the OFFICIAL reader was sent the SECRET node's id"]


def test_a_hidden_link_put_back_at_the_assumptions_routes_call_site_is_found(world: _World, monkeypatch: pytest.MonkeyPatch) -> None:
    import services.api.app as conduit
    from services.api.assessments import list_visible_assumptions

    hidden = _save_judgement(world, SECRET_EDITOR, [VISIBLE, HIDDEN]).json()["id"]
    shown = _save_judgement(world, SECRET_EDITOR, [VISIBLE]).json()["id"]
    assert _save_assumption(world, SECRET_EDITOR, [hidden, shown]).status_code == 201
    assert _assumptions_problems(world, hidden, shown) == []

    async def planted(store: Any, judgements: Any, investigation_id: str, principal: Principal, graph: Any) -> Any:
        real = await list_visible_assumptions(store, judgements, investigation_id, principal, graph)
        return [a.model_copy(update={"linked_judgements": [*a.linked_judgements, hidden]}) for a in real]

    monkeypatch.setattr(conduit, "list_visible_assumptions", planted)
    assert _assumptions_problems(world, hidden, shown) == ["the OFFICIAL reader was sent the id of a judgement hidden from them"]


def test_a_filter_that_lets_one_hidden_node_through_is_found(world: _World, monkeypatch: pytest.MonkeyPatch) -> None:
    """The plant inside the real filter's own decision (`_reference_visible`), for the hidden node alone: the gap read is red,
    and nothing else changes (the visible link is still sent)."""
    import services.api.assessments as assessments

    real = assessments._reference_visible

    async def planted(graph: Any, principal: Principal, ref_id: str) -> bool:
        return True if ref_id == HIDDEN else await real(graph, principal, ref_id)

    assert _save_gap(world, SECRET_EDITOR, [VISIBLE, HIDDEN]).status_code == 201
    assert _gaps_problems(world) == []
    monkeypatch.setattr(assessments, "_reference_visible", planted)
    assert _gaps_problems(world) == ["the OFFICIAL reader was sent the SECRET node's id"]


def test_a_save_refusal_names_only_what_the_saver_sent_and_treats_absent_and_hidden_alike(world: _World) -> None:
    """Rule 3 on the write side: refusing a hidden node and an absent one in different words would tell the saver which ids
    are real. Both are 422 `unverifiable_link`, naming only the ids the saver sent, with the same detail shape."""
    hidden = _save_gap(world, OFFICIAL_READER, [HIDDEN])
    absent = _save_gap(world, OFFICIAL_READER, [NOWHERE])
    assert (hidden.status_code, absent.status_code) == (422, 422)
    assert hidden.json()["error"] == absent.json()["error"] == "unverifiable_link"
    assert hidden.json()["link_ids"] == [HIDDEN] and absent.json()["link_ids"] == [NOWHERE]
    assert hidden.json()["detail"].replace(HIDDEN, "X") == absent.json()["detail"].replace(NOWHERE, "X")
    # Nothing was written by either refusal.
    assert world.pool.tables.get("intelligence_gaps", {}) == {}


def _assumption_refusal_problems(world: _World, hidden_judgement: str) -> list[str]:
    """What the assumption save's refusal must be, as a function the real route and each planted one go through: a judgement
    hidden from the saver and an id that names none are both refused alike, naming only what was sent, and nothing is stored."""
    hidden = _save_assumption(world, OFFICIAL_READER, [hidden_judgement])
    absent = _save_assumption(world, OFFICIAL_READER, ["judgement-that-does-not-exist"])
    found: list[str] = []
    if (hidden.status_code, absent.status_code) != (422, 422):
        found.append(f"the save answered {hidden.status_code} and {absent.status_code}, not 422 and 422")
        return found + (["a refused link was stored"] if world.pool.tables.get("assumptions", {}) else [])
    if hidden.json().get("error") != "unverifiable_link" or absent.json().get("error") != "unverifiable_link":
        found.append("the refusal is not `unverifiable_link`")
    if hidden.json().get("link_ids") != [hidden_judgement] or absent.json().get("link_ids") != ["judgement-that-does-not-exist"]:
        found.append("the refusal names something other than the ids the saver sent")
    if hidden.json()["detail"].replace(hidden_judgement, "X") != absent.json()["detail"].replace("judgement-that-does-not-exist", "X"):
        found.append("a hidden judgement and an absent one were refused in different words")
    if world.pool.tables.get("assumptions", {}):
        found.append("a refused link was stored")
    return found


def test_an_assumption_save_refusal_names_only_what_the_saver_sent_and_stores_nothing(world: _World) -> None:
    """The write side's invariant for assumptions, as `..._treats_absent_and_hidden_alike` holds it for gaps (rule 3): the
    refusal is 422 `unverifiable_link` naming only the ids sent, a hidden judgement and an absent one are refused alike, and
    nothing is written (so a SECRET reader of the case is never later served a link the OFFICIAL saver could not confirm)."""
    hidden = _save_judgement(world, SECRET_EDITOR, [VISIBLE, HIDDEN]).json()["id"]
    assert hidden not in _judgement_ids(world, OFFICIAL_READER)  # the precondition: hidden from the saver
    assert _assumption_refusal_problems(world, hidden) == []
    assert world.pool.tables.get("assumptions", {}) == {}
    assert world.as_(SECRET_EDITOR).get(f"/v1/investigations/{CASE}/assumptions").json()["assumptions"] == []


def test_an_assumption_cannot_link_a_judgement_of_another_case(world: _World) -> None:
    """spec/03 line 633: another case's judgement is refused with the absent and the hidden. The judgement is one the saver is
    shown, in the case it belongs to (the precondition), so a check by id or by unit alone would accept it here."""
    other = _save_judgement(world, OFFICIAL_READER, [VISIBLE], case=OTHER_CASE)
    assert other.status_code == 201, other.text
    elsewhere = other.json()["id"]
    assert elsewhere in _judgement_ids(world, OFFICIAL_READER, OTHER_CASE)
    assert elsewhere not in _judgement_ids(world, OFFICIAL_READER, CASE)
    saved = _save_assumption(world, OFFICIAL_READER, [elsewhere])
    assert saved.status_code == 422, f"an assumption linking another case's judgement was stored: {saved.status_code} {saved.text}"
    assert saved.json()["error"] == "unverifiable_link" and saved.json()["link_ids"] == [elsewhere]
    assert world.pool.tables.get("assumptions", {}) == {}
    # The control: a judgement of this case, shown to the same saver, is accepted.
    here = _save_judgement(world, OFFICIAL_READER, [VISIBLE]).json()["id"]
    assert _save_assumption(world, OFFICIAL_READER, [here]).status_code == 201


def _case_scope_problems(world: _World) -> list[str]:
    other = _save_judgement(world, OFFICIAL_READER, [VISIBLE], case=OTHER_CASE).json()["id"]
    saved = _save_assumption(world, OFFICIAL_READER, [other])
    return [] if saved.status_code == 422 else [f"another case's judgement was accepted: {saved.status_code}"]


def _gap_refusal_problems(world: _World) -> list[str]:
    saved = _save_gap(world, OFFICIAL_READER, [HIDDEN])
    found = [] if saved.status_code == 422 else [f"the save answered {saved.status_code}, not 422"]
    if world.pool.tables.get("intelligence_gaps", {}):
        found.append("a refused link was stored")
    return found


# ------------------------------------------------------------------------------------------------ planted faults on the write side (rule 15)


def test_a_save_that_checks_its_links_after_storing_them_is_found(world: _World, monkeypatch: pytest.MonkeyPatch) -> None:
    """The order fault: `save_assumption_route` calls `confirm_assumption_links` before `assumptions_store.save`. Planted at that
    call site, the confirmation runs only after the row is stored: it still answers 422, and only the stored row shows it."""
    import services.api.app as conduit
    from services.api.assessments import confirm_assumption_links, new_assumption

    hidden = _save_judgement(world, SECRET_EDITOR, [VISIBLE, HIDDEN]).json()["id"]
    assert _assumption_refusal_problems(world, hidden) == []

    async def planted(judgements: Any, investigation_id: str, principal: Principal, graph: Any, links: list[str]) -> None:
        await world.assumptions.save(
            new_assumption(investigation_id=investigation_id, statement="x", if_false_impact="y", linked_judgements=links), principal
        )
        await confirm_assumption_links(judgements, investigation_id, principal, graph, links)

    monkeypatch.setattr(conduit, "confirm_assumption_links", planted)
    assert _assumption_refusal_problems(world, hidden) == ["a refused link was stored"]


def test_an_assumption_save_that_confirms_nothing_is_found(world: _World, monkeypatch: pytest.MonkeyPatch) -> None:
    import services.api.app as conduit

    hidden = _save_judgement(world, SECRET_EDITOR, [VISIBLE, HIDDEN]).json()["id"]
    assert _assumption_refusal_problems(world, hidden) == []

    async def planted(*_: Any) -> None:
        return None

    monkeypatch.setattr(conduit, "confirm_assumption_links", planted)
    problems = _assumption_refusal_problems(world, hidden)
    assert problems == ["the save answered 201 and 201, not 422 and 422", "a refused link was stored"]


def test_a_gap_save_that_confirms_nothing_is_found(world: _World, monkeypatch: pytest.MonkeyPatch) -> None:
    import services.api.app as conduit

    assert _gap_refusal_problems(world) == []

    async def planted(*_: Any) -> None:
        return None

    monkeypatch.setattr(conduit, "confirm_gap_links", planted)
    assert _gap_refusal_problems(world) == ["the save answered 201, not 422", "a refused link was stored"]


def test_a_judgement_filter_that_ignores_the_case_is_found(world: _World, monkeypatch: pytest.MonkeyPatch) -> None:
    """The plant inside the filter's own decision (`visible_judgement_ids`): it also counts the judgements of the other case,
    as a check by owning unit alone would. The case-scope test finds it; the real filter does not."""
    import services.api.assessments as assessments

    assert _case_scope_problems(world) == []
    real = assessments.visible_judgement_ids

    async def planted(store: Any, investigation_id: str, principal: Principal, graph: Any) -> set[str]:
        return await real(store, investigation_id, principal, graph) | await real(store, OTHER_CASE, principal, graph)

    monkeypatch.setattr(assessments, "visible_judgement_ids", planted)
    found = _case_scope_problems(world)
    assert len(found) == 1 and found[0].startswith("another case's judgement was accepted: 201")
