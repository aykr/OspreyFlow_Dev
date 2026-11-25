"""Whether a case report's figures were lowered by what the reader may not see (SE8b, the owner's
ruling of 21 November 2026: every export writes its ledger row, the `withheld` flag as the route
computes it; the first fix's verifier finding: the flag must be the figures' own, not a stand-in).

The report's ledger row carries `withheld`. Its first version asked the case's working-set sentence
(`withheld_for`), a question about what the case's stored set holds, of a set no figure is counted
from: it said `False` for a reader whose alerts the queue had left out, and `True` for one whose
figures were whole. These tests run the real `reports.case_report_and_withheld` and the real alert
queue, against fakes that answer as the adapters do (a hidden id is absent from a batched read), and
plant both directions:

- figures lowered (an alert citing what the reader cannot read) -> the flag is true, and the total
  is lower: the flag follows the lowering, not a constant;
- figures whole but the case's working set holds material the reader may not view -> the flag is
  false (red against the first version);
- an alert left out only by a status filter is not withheld from the reader;
- an alert on a dataset the case does not read, which the store's query drops before the queue sees
  it: **not** the reader's rights, so the flag stays false (the owner's ruling of 23 November 2026,
  option A: in a case route `principal.datasets` is the case's read set, `scope_to_case`, and an
  owned or team monitor or hotlist alert raised on another dataset is not a figure of this case;
  round 5 recorded it as withheld, the false record this file now plants);
- an alert on the borrowed read-only layer of a case made from another, which `readable_of_case`
  drops when the reader holds no level on the original case: the reader's rights, so the flag is
  true, from `AlertStore.left_out_on_borrowed_layer`; with a level held, false. These two run the
  **real** `AlertStore` and the real `queue_scope` SQL over `_PostgresRefusingPool` (DuckDB, which
  refuses a statement whose placeholders and parameters disagree, an unknown column, a gap in the
  numbering, as Postgres does), the principal and the borrowed layer set by the real `scope_to_case`.

Held rows: the real `HeldRowStore.left_out_for` is Postgres (its live counterpart is
`test_reports.py::test_the_held_flag_follows_what_the_reader_may_not_read`, owed), so here it is
held to its query: the same clauses and the same parameters as `list_authorized`, which is what
keeps the flag and the figure from being asked differently.

**Folders this test walks** (for the line's scan map): none. It runs functions against fakes and reads no
file.
"""

from __future__ import annotations

import contextlib
import json
import re
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from services.api import reports
from services.api.alerts import _COLUMNS, AlertStore
from services.api.held_rows import HeldRowStore

from ontology.handling import load_uk_le_scheme
from schemas.domain import Alert, AlertMode, Principal
from tests.services.api.test_alert_evidence_withheld import (
    CASE,
    OVER_LINK,
    READER,
    V1,
    V2,
    Store,
    _world,
)

TODAY = date(2026, 11, 7)


class _EmptyGraph:
    """The reader's whole graph, empty: nothing for the KYC book to count."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def list_nodes(self, *args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(nodes=[], next_cursor=None)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _Held:
    """Held rows by classification, as the store answers for a reader cleared to OFFICIAL: the
    figures count what it may list, and `left_out_for` is true when it listed fewer than there are."""

    def __init__(self, classifications: list[str]) -> None:
        self.rows = classifications
        self.asked: list[str] = []

    async def list_authorized(
        self, case: str, reader: Principal, *, status: str = "held"
    ) -> list[str]:
        return [c for c in self.rows if c == "OFFICIAL"] if status == "held" else []

    async def left_out_for(self, case: str, reader: Principal, *, status: str = "held") -> bool:
        self.asked.append(status)
        return status == "held" and any(c != "OFFICIAL" for c in self.rows)


async def _report(
    hidden: set[str],
    alerts: list[Any],
    *,
    held: _Held | None = None,
    show_held: bool = False,
) -> tuple[Any, bool]:
    store, graph, analytics, _ = _world(hidden, alerts)
    return await reports.case_report_and_withheld(
        alerts=store, graph=_EmptyGraph(graph), analytics=analytics,  # type: ignore[arg-type]
        held=held or _Held([]),  # type: ignore[arg-type]
        compute=None, explore=None, ontology=None,  # type: ignore[arg-type]
        domains=["fibo"], investigation_id=CASE, reader=READER, today=TODAY, show_held=show_held,
    )  # fmt: skip


async def test_figures_lowered_by_what_the_reader_cannot_read_say_so() -> None:
    """An alert over a link the reader cannot read is in no figure; the flag says it. Red with the
    first version's predicate (the working set: here it knows nothing of the alert) and with the
    old constant `False`."""
    shown, flag = await _report({"e-secret"}, [V1, OVER_LINK, V2])
    whole, whole_flag = await _report(set(), [V1, OVER_LINK, V2])
    assert shown.alerts_total == whole.alerts_total - 1, "the figures were lowered"
    assert flag is True
    assert whole_flag is False, "nothing hidden: the flag is not a constant `True` either"


# --- the real alert store over a pool that refuses what Postgres refuses ----------------------------


class _Refused(Exception):
    """What Postgres answers a statement it cannot run (bind count, unknown column, ...)."""


class _PostgresRefusingPool:
    """`asyncpg.Pool`'s `acquire()` over DuckDB, which runs the store's own SQL (`queue_scope`, the
    kind, shared and routed expressions) as written. It refuses what the database would: a statement
    whose `$n` placeholders are not exactly `$1..$n` for the arguments given (Postgres: "bind
    message supplies N parameters, but prepared statement requires M", or "could not determine data
    type of parameter $k" for a gap), and a column the table does not have. It answers any other
    statement by running it, never with a canned value."""

    def __init__(self) -> None:
        import duckdb

        self._db = duckdb.connect()
        columns = [c.strip() for c in _COLUMNS.split(",")] + ["handlings", "cited_handlings"]
        self._columns = columns
        self._db.execute("CREATE TABLE alerts (" + ", ".join(f"{c} TEXT" for c in columns) + ")")
        self._db.execute("CREATE TABLE hotlists (id TEXT, audience TEXT)")
        self._db.execute(
            "CREATE TABLE alert_repoint_records (id TEXT, links TEXT, alert_nodes TEXT, "
            "referents TEXT, recorded_at TEXT, held_open BOOLEAN, applied BOOLEAN)"
        )
        self.statements: list[str] = []

    def put(self, alert: Alert) -> None:
        row = {c: None for c in self._columns} | {
            "id": alert.id, "rule_id": alert.rule_id, "owner_id": alert.owner_id,
            "mode": alert.mode.value, "referent_node_ids": json.dumps(alert.referent_node_ids),
            "investigation_id": alert.investigation_id, "created_at": alert.created_at.isoformat(),
            "dataset_id": alert.dataset_id, "typology": alert.typology, "team": alert.team,
            "status": "open",
        }  # fmt: skip
        names = ", ".join(row)
        marks = ", ".join(f"${i + 1}" for i in range(len(row)))
        self._db.execute(f"INSERT INTO alerts ({names}) VALUES ({marks})", list(row.values()))

    def acquire(self) -> _PostgresRefusingPool:
        return self

    async def __aenter__(self) -> _PostgresRefusingPool:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def _run(self, sql: str, args: tuple[Any, ...]) -> list[dict[str, Any]]:
        numbers = sorted({int(n) for n in re.findall(r"\$(\d+)", sql)})
        if numbers != list(range(1, len(args) + 1)):
            raise _Refused(f"placeholders {numbers} for {len(args)} arguments: {sql[:80]}")
        self.statements.append(sql)
        cursor = self._db.execute(sql, list(args))
        names = [d[0] for d in cursor.description]
        rows = [dict(zip(names, r, strict=True)) for r in cursor.fetchall()]
        for row in rows:
            if isinstance(row.get("created_at"), str):
                row["created_at"] = datetime.fromisoformat(row["created_at"])
        return rows

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        return self._run(sql, args)

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        rows = self._run(sql, args)
        return rows[0] if rows else None

    async def fetchval(self, sql: str, *args: Any) -> Any:
        rows = self._run(sql, args)
        return next(iter(rows[0].values())) if rows else None


class _CaseDatasets:
    """The dataset store `scope_to_case` asks: a case made from another reads `reads`, the layer it
    borrows read-only being `borrowed`, the layer of the original case `original`."""

    def __init__(self, reads: list[str], borrowed: str | None, original: str | None) -> None:
        self._reads, self._borrowed, self._original = reads, borrowed, original

    async def ids_of_case(self, investigation_id: str) -> list[str]:
        return list(self._reads)

    async def layer_of_case(self, investigation_id: str) -> str | None:
        return None

    async def read_only_layer_of(self, investigation_id: str) -> str | None:
        return self._borrowed

    async def case_of_layer(self, layer: str) -> str | None:
        return self._original


def _mine(name: str, dataset: str) -> Alert:
    """A monitor alert the reader owns, raised in another case, on `dataset`: it reaches this case's
    queue through its owner (`queue_scope`), as every owned alert does, and is cut by dataset."""
    return Alert(id=name, rule_id=f"monitor:{name}", owner_id=READER.id, mode=AlertMode.FULL,
                 referent_node_ids=["n-a"], investigation_id="case-elsewhere", dataset_id=dataset,
                 team=READER.org_unit, created_at=datetime(2026, 11, 7, 9, 0, tzinfo=UTC))  # fmt: skip


async def _as_the_route(
    alerts: list[Alert], *, reads: list[str], borrowed: str | None = None, holds: bool = False
) -> tuple[Any, bool, list[str]]:
    """What a Reports route does for `READER` in `CASE`: the principal scoped to the case's read set
    by the real `scope_to_case` (so `principal.datasets` is that set and the borrowed layer is
    noted for the request), then the real `case_report_and_withheld` and the real queue over the
    real `AlertStore`. Returns the figures, the flag and the ids the reader's queue lists."""
    from services.api import alert_queue
    from services.api.dataset_scope import scope_to_case, set_case_datasets

    pool = _PostgresRefusingPool()
    for alert in alerts:
        pool.put(alert)
    store = AlertStore(pool, None)  # type: ignore[arg-type]
    _, graph, analytics, _ = _world(set(), [])

    async def holds_a_level(principal: Principal, investigation_id: str) -> bool:
        return holds

    try:
        reader = await scope_to_case(
            READER, CASE, _CaseDatasets(reads, borrowed, "case-original"),  # type: ignore[arg-type]
            holds_a_level=holds_a_level,
        )  # fmt: skip
        figures, flag = await reports.case_report_and_withheld(
            alerts=store, graph=_EmptyGraph(graph), analytics=analytics,  # type: ignore[arg-type]
            held=_Held([]),  # type: ignore[arg-type]
            compute=None, explore=None, ontology=None,  # type: ignore[arg-type]
            domains=["fibo"], investigation_id=CASE, reader=reader, today=TODAY, show_held=False,
        )  # fmt: skip
        shown = await alert_queue.monitoring_queue(store, graph, analytics, CASE, reader)  # type: ignore[arg-type]
    finally:
        set_case_datasets(None)
    return figures, flag, [q.alert.id for q in shown]


async def test_an_owned_alert_on_a_dataset_the_case_does_not_read_is_not_withheld() -> None:
    """Case 7 (round 4), the verifier's planted shape: the reader owns two monitor alerts, one on a
    dataset this case reads and one on another dataset (raised in another case). Their principal's
    `datasets` is the case's read set, so the second never reaches this case's queue: it is not a
    figure of this case and the reader's rights lowered nothing. Red on the round-5 tip
    (`left_out_by_reach` read the case's scope as the reader's rights and said true)."""
    figures, flag, shown = await _as_the_route(
        [_mine("m-here", "ds-1"), _mine("m-there", "ds-other")], reads=["ds-1"]
    )
    assert shown == ["m-here"], "the alert on the other dataset is in no figure of this case"
    assert flag is False


async def test_an_alert_on_the_borrowed_layer_is_withheld_from_a_reader_with_no_level_on_the_original() -> (
    None
):
    """The reader's rights, the one refusal in a case's read set (`readable_of_case`): a case made
    from another reads the original's layer only for a reader who holds a level on the original.
    Without one the layer is left out of `principal.datasets` and the alert on it, which the reader
    owns, is in no figure: the flag says so. With a level it is in the figures and the flag is
    false. Both over the real store, so the SQL that takes it out is the one that runs."""
    alerts = [_mine("m-here", "ds-1"), _mine("m-borrowed", "ds-borrowed")]
    reads = ["ds-1", "ds-borrowed"]
    _, flag, shown = await _as_the_route(alerts, reads=reads, borrowed="ds-borrowed", holds=False)
    assert shown == ["m-here"], "the figures were lowered"
    assert flag is True

    _, flag, shown = await _as_the_route(alerts, reads=reads, borrowed="ds-borrowed", holds=True)
    assert sorted(shown) == ["m-borrowed", "m-here"]
    assert flag is False, "the reader holds a level on the original: nothing was left out"


async def test_the_borrowed_layer_and_another_datasets_alert_are_told_apart() -> None:
    """Both at once, no level held: the alert on the borrowed layer sets the flag; the same case
    with only the other dataset's alert (the borrowed layer holding none) does not. The flag follows
    the reader's rights, not how many alerts the case's scope dropped."""
    reads = ["ds-1", "ds-borrowed"]
    _, only_other, _ = await _as_the_route(
        [_mine("m-here", "ds-1"), _mine("m-there", "ds-other")],
        reads=reads, borrowed="ds-borrowed", holds=False,
    )  # fmt: skip
    assert only_other is False
    _, both, _ = await _as_the_route(
        [_mine("m-there", "ds-other"), _mine("m-borrowed", "ds-borrowed")],
        reads=reads, borrowed="ds-borrowed", holds=False,
    )  # fmt: skip
    assert both is True


async def test_whole_figures_are_not_withheld_whatever_the_working_set_holds() -> None:
    """The figures are counted as the reader from the alerts' own evidence, never from the case's
    stored working set, so material in that set the reader may not view changes no figure and the
    flag stays false. The case report is built here with no working set at all: a route that asked
    one for the flag has nothing to ask."""
    figures, flag = await _report(set(), [V1, V2])
    assert figures.alerts_total == 2
    assert flag is False


async def test_an_alert_left_out_by_a_status_filter_is_not_withheld() -> None:
    """The queue's own filters narrow what is asked for, not what the reader may see: a closed alert
    filtered out of an open-only listing is not 'withheld'. Only evidence the reader cannot read
    sets the flag."""
    from services.api import alert_queue

    store, graph, analytics, _ = _world(set(), [V1, V2])
    shown, left_out = await alert_queue.monitoring_queue_and_left_out(
        store, graph, analytics, CASE, READER, statuses=["closed"]  # type: ignore[arg-type]
    )  # fmt: skip
    assert shown == [] and left_out is False


async def test_the_queue_says_what_it_left_out_beside_the_list() -> None:
    from services.api import alert_queue

    store, graph, analytics, _ = _world({"e-secret"}, [V1, OVER_LINK, V2])
    shown, left_out = await alert_queue.monitoring_queue_and_left_out(
        store, graph, analytics, CASE, READER  # type: ignore[arg-type]
    )  # fmt: skip
    assert [q.alert.id for q in shown] == ["v1", "v2"] and left_out is True
    # and `monitoring_queue` is the same list, unchanged for every other caller
    again = await alert_queue.monitoring_queue(store, graph, analytics, CASE, READER)  # type: ignore[arg-type]
    assert [q.alert.id for q in again] == ["v1", "v2"]


async def test_held_rows_the_reader_may_not_read_set_the_flag_only_where_the_figures_show_them() -> (
    None
):
    """An editor's held figures leave out a SECRET row for an OFFICIAL reader: flagged. A viewer
    (`show_held` false) is sent no held figure, so a held row lowers nothing for them."""
    held = _Held(["OFFICIAL", "SECRET"])
    figures, flag = await _report(set(), [V1], held=held, show_held=True)
    assert figures.held.held == 1, "the SECRET row is in no figure"
    assert flag is True
    assert held.asked == ["held", "released", "rejected"], "every status the figures count"

    viewer_held = _Held(["OFFICIAL", "SECRET"])
    figures, flag = await _report(set(), [V1], held=viewer_held, show_held=False)
    assert figures.held is None and flag is False
    assert viewer_held.asked == []

    figures, flag = await _report(set(), [V1], held=_Held(["OFFICIAL"]), show_held=True)
    assert figures.held.held == 1 and flag is False


# --- the held store's own query: the flag and the figure are asked the same way -------------------


class _Conn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.answer: dict[str, int] = {"every": 2, "readable": 1}

    async def fetch(self, sql: str, *args: Any) -> list[Any]:
        self.calls.append((sql, args))
        return []

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, int]:
        self.calls.append((sql, args))
        return self.answer


class _Pool:
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn

    @contextlib.asynccontextmanager
    async def acquire(self) -> AsyncIterator[_Conn]:
        yield self.conn


def _store(conn: _Conn) -> HeldRowStore:
    return HeldRowStore(_Pool(conn), load_uk_le_scheme())  # type: ignore[arg-type]


@pytest.mark.parametrize("datasets", [None, ["ds-1"]])
async def test_left_out_for_is_asked_with_the_clauses_and_parameters_of_the_listing(
    datasets: list[str] | None,
) -> None:
    """A flag asked with a looser or different predicate than the figure would say 'nothing left
    out' about rows the figure leaves out. Both queries are made with the same marking and reach
    clauses and the same bound values (red if either drifts)."""
    reader = Principal(id="r", clearance="OFFICIAL", org_unit="unit-1", datasets=datasets)
    conn = _Conn()
    store = _store(conn)
    await store.list_authorized(CASE, reader, status="held")
    assert await store.left_out_for(CASE, reader, status="held") is True
    (listing_sql, listing_args), (flag_sql, flag_args) = conn.calls
    assert flag_args == listing_args
    clauses = listing_sql.split("status = $2", 1)[1].split(" ORDER BY")[0]
    assert clauses.strip().startswith("AND"), listing_sql
    assert f"FILTER (WHERE true{clauses})" in flag_sql
    assert "WHERE investigation_id = $1 AND status = $2" in flag_sql


async def test_left_out_for_is_false_when_the_reader_may_read_every_row() -> None:
    conn = _Conn()
    conn.answer = {"every": 3, "readable": 3}
    store = _store(conn)
    reader = Principal(id="r", clearance="OFFICIAL", org_unit="unit-1")
    assert await store.left_out_for(CASE, reader) is False


# --- the alert store's own question: the borrowed layer ------------------------------------------


@pytest.mark.parametrize(
    ("datasets", "borrowed"),
    [
        (None, "ds-borrowed"),  # no dataset limit: nothing is left out of the read set
        (["ds-1", "ds-borrowed"], "ds-borrowed"),  # the reader reads it
        (["ds-1"], None),  # the case borrows no layer: the case's scope is not the reader's rights
    ],
)
async def test_left_out_on_the_borrowed_layer_costs_no_query_when_nothing_was_refused(
    datasets: list[str] | None, borrowed: str | None
) -> None:
    pool = _PostgresRefusingPool()
    store = AlertStore(pool, None)  # type: ignore[arg-type]
    reader = Principal(id="r", clearance="OFFICIAL", org_unit="unit-1", datasets=datasets)
    assert await store.left_out_on_borrowed_layer(CASE, reader, borrowed) is False
    assert pool.statements == []


async def test_left_out_on_the_borrowed_layer_asks_with_the_scope_of_the_queue() -> None:
    """The question is put over `queue_scope` as `list_queue` puts it (the reader's own alerts and
    their team's, never another's), with the borrowed layer as the one added condition: another
    person's alert on that layer, which the reader could never see, says nothing to them."""
    pool = _PostgresRefusingPool()
    store = AlertStore(pool, None)  # type: ignore[arg-type]
    reader = Principal(id="reader-1", clearance="OFFICIAL", org_unit="unit-1", datasets=["ds-1"])
    stranger = _mine("theirs", "ds-borrowed").model_copy(
        update={"owner_id": "someone-else", "team": "unit-9"}
    )
    pool.put(stranger)
    assert await store.left_out_on_borrowed_layer(CASE, reader, "ds-borrowed") is False
    pool.put(_mine("mine", "ds-borrowed"))
    assert await store.left_out_on_borrowed_layer(CASE, reader, "ds-borrowed") is True
    assert await store.left_out_on_borrowed_layer(CASE, reader, "ds-other") is False


# --- the known floor: the KYC and POLE figures the flag does not yet see ----------------------------
#
# `spec/03_CONDUIT_MIDDLEWARE.md`, the sentence "The flag is a floor, not a ceiling": the KYC and
# POLE figures are counted as the reader, the reader's rights can lower them, and the flag does not
# see it, so a lowered total is recorded `withheld=False` today. These two cases state that gap
# (rule 12). They assert today's answer, deliberately, under a name that says so. **When SE8e
# lands (the counts result gains a `withheld` boolean from the adapter, and the flag becomes one
# `any` over every figure source) these are the tests that flip: change the last assertion to
# `is True`.**

_CLEARED = READER.model_copy(update={"clearance": "SECRET"})


class _CountingGraph:
    """The graph as the adapter answers `type_counts`: the principal's own counts, lower for a
    reader whose clearance is lower. Only the answer differs between readers; nothing in it says
    that a count was lowered (rule 7), as the real port does not."""

    def __init__(self) -> None:
        self.asked_as: list[str] = []

    async def type_counts(self, principal: Principal) -> Any:
        from schemas.explore import TypeCounts

        self.asked_as.append(principal.clearance)
        people = 5 if principal.clearance == "SECRET" else 3
        return TypeCounts(nodes={"Person": people}, edges={"MEMBER_OF": 2})


def _counted_at() -> datetime:
    return datetime(2026, 11, 7, tzinfo=UTC)


async def _pole_report(reader: Principal) -> tuple[Any, bool]:
    from services.api.explore import ExploreService

    from ontology.packs import load_deployment_ontology

    store, graph, analytics, _ = _world(set(), [])
    return await reports.case_report_and_withheld(
        alerts=store, graph=_EmptyGraph(graph), analytics=analytics,  # type: ignore[arg-type]
        held=_Held([]),  # type: ignore[arg-type]
        compute=None,  # type: ignore[arg-type]
        explore=ExploreService(_CountingGraph(), None, now=_counted_at),  # type: ignore[arg-type]
        ontology=load_deployment_ontology(),
        domains=["aml"], investigation_id=CASE, reader=reader, today=TODAY,
    )  # fmt: skip


async def test_a_pole_total_lowered_by_the_readers_rights_is_a_known_floor_until_SE8e() -> None:
    """The real `ExploreService.counts` over a graph whose count the reader's clearance lowers (3
    people for the reader, 5 for a cleared one). The POLE total really is lower; the flag says
    `False`: the known gap (spec 03, "a floor, not a ceiling"). Flips to `True` with SE8e."""
    cleared, cleared_flag = await _pole_report(_CLEARED)
    lowered, flag = await _pole_report(READER)
    person = lambda f: next(c for c in f.pole.classes if c.pole_class.value == "person").total  # noqa: E731
    assert (person(cleared), person(lowered)) == (5, 3), "the figure really was lowered"
    assert cleared_flag is False
    assert flag is False  # SE8e: `is True`


class _KycGraph:
    """Two customers, each verified by a document; the second is visible only to a SECRET reader.
    Answers `list_nodes`, `expand` and `get_node` as the adapter does for the principal given, a
    hidden node being absent from every answer and from none of them by name."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self._nodes = {
            "p-1": SimpleNamespace(
                id="p-1", type="Person", properties={"family_name": "A"}, level=0
            ),
            "p-2": SimpleNamespace(
                id="p-2", type="Person", properties={"family_name": "B"}, level=1
            ),
            "d-1": SimpleNamespace(id="d-1", type="Document", properties={}, level=0),
            "d-2": SimpleNamespace(id="d-2", type="Document", properties={}, level=1),
        }
        self._verified_by = {"p-1": "d-1", "p-2": "d-2"}

    def _seen(self, principal: Principal) -> dict[str, Any]:
        top = 1 if principal.clearance == "SECRET" else 0
        return {k: n for k, n in self._nodes.items() if n.level <= top}

    async def list_nodes(self, entity_type: str, principal: Principal, **kwargs: Any) -> Any:
        found = [n for n in self._seen(principal).values() if n.type == entity_type]
        return SimpleNamespace(nodes=found, next_cursor=None)

    async def get_node(self, node_id: str, principal: Principal, **kwargs: Any) -> Any:
        return self._seen(principal).get(node_id)

    async def expand(self, req: Any, principal: Principal) -> Any:
        seen = self._seen(principal)
        if req.edge_types != ["VERIFIED_BY"]:
            return SimpleNamespace(nodes=[], edges=[])
        if req.direction == "in":  # the holders of these documents
            held = [p for p, d in self._verified_by.items() if d in req.node_ids]
            return SimpleNamespace(nodes=[seen[p] for p in held if p in seen], edges=[])
        docs = [self._verified_by[p] for p in req.node_ids if p in self._verified_by]
        return SimpleNamespace(nodes=[seen[d] for d in docs if d in seen], edges=[])

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


async def _kyc_report(reader: Principal) -> tuple[Any, bool]:
    store, graph, analytics, _ = _world(set(), [])
    return await reports.case_report_and_withheld(
        alerts=store, graph=_KycGraph(graph), analytics=analytics,  # type: ignore[arg-type]
        held=_Held([]),  # type: ignore[arg-type]
        compute=None, explore=None, ontology=None,  # type: ignore[arg-type]
        domains=["fibo"], investigation_id=CASE, reader=reader, today=TODAY,
    )  # fmt: skip


async def test_a_kyc_total_lowered_by_the_readers_rights_is_a_known_floor_until_SE8e() -> None:
    """The real `_kyc_figures` (`_customers`, `assess`) over a graph whose answers the reader's
    clearance lowers: a cleared reader's book holds two customers, this reader's one. The KYC total
    really is lower; the flag says `False`: the known gap (spec 03, "a floor, not a ceiling").
    Flips to `True` with SE8e."""
    cleared, cleared_flag = await _kyc_report(_CLEARED)
    lowered, flag = await _kyc_report(READER)
    assert (cleared.kyc.customers, lowered.kyc.customers) == (2, 1), "the figure really was lowered"
    assert cleared_flag is False
    assert flag is False  # SE8e: `is True`
