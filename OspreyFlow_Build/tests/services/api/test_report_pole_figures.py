"""The Reports figures follow the case's domain packs (`06_DECISIONS.md` ADR-126 decisions 3, 4, 5
and 7, unit D2), the pure half: which figures a case gets, the POLE classifier, the feed's rows,
and that the POLE counts are the reader's own. The live half (a real ArcadeDB, at the route) is
`test_reports.py`'s.

What a mistake here would do, and the case that catches it:

- `case_report` ignoring the packs would draw a KYC card for a prison case, or hide it for an AML
  one (`test_each_case_gets_the_figures_its_packs_call_for`);
- a case without `fibo` assessing its customers would read every customer for a card it never
  sends (`test_a_case_without_fibo_assesses_no_customer`);
- the POLE figures being a second count, or counted for someone wider than the reader, would put a
  hidden node in a class total
  (`test_the_pole_counts_are_the_readers_own_and_a_hidden_node_is_in_none`);
- a type the ontology does not know vanishing from the figures, `Alert` counted as an Event, or a
  system link counted (`test_the_classifier_*`);
- the feed carrying something other than the card (`test_the_feed_carries_exactly_the_cards_rows`).

The access-control comparison here uses a fake graph that applies the reader's clearance and the
case's datasets as the adapter does; a fake cannot prove the adapter, so the same comparison is
made against ArcadeDB, at the route, in `test_reports.py`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError
from services.api import reports as reports_module
from services.api.explore import ExploreService
from services.api.reports import case_report, feed_rows, pole_figures

from ontology.packs import load_deployment_ontology
from schemas.domain import (
    KycFigures,
    PoleClass,
    PoleClassCount,
    PoleFigures,
    Principal,
    ReportCount,
    ReportFigures,
)
from schemas.explore import TypeCounts

ONTOLOGY = load_deployment_ontology()
TODAY = date(2026, 10, 24)
READER = Principal(id="reader", clearance="OFFICIAL", org_unit="unit-1", datasets=["ds-a"])
COUNTED = datetime(2026, 10, 24, 9, 0, tzinfo=UTC)


class _Graph:
    """Only `type_counts`, which is all `ExploreService.counts` asks of the graph."""

    def __init__(self, counts: TypeCounts) -> None:
        self.counts = counts
        self.asked_as: list[Principal] = []

    async def type_counts(self, principal: Principal) -> TypeCounts:
        self.asked_as.append(principal)
        return self.counts


def _explore(counts: TypeCounts) -> tuple[ExploreService, _Graph]:
    graph = _Graph(counts)
    return ExploreService(graph, None, now=lambda: COUNTED), graph  # type: ignore[arg-type]


PLANTED = TypeCounts(
    nodes={
        "Person": 5, "ThreatActor": 5, "Organisation": 2, "Vehicle": 1, "Event": 0,
        "Alert": 9, "Gone": 4, "Alien": 4,
    },
    edges={
        "MEMBER_OF": 6, "SAME_AS": 2, "NOT_SAME_AS": 1, "ALERTED_ON": 3, "PROPOSED_LINK": 2,
    },
    computed_at=COUNTED,
)  # fmt: skip


# --- the classifier ---------------------------------------------------------------------------


def test_the_classifier_groups_by_class_largest_first_then_by_name_with_no_zero_rows() -> None:
    figures = pole_figures(PLANTED, ONTOLOGY, counted_at=COUNTED)

    assert [c.pole_class for c in figures.classes] == [
        PoleClass.PERSON,
        PoleClass.OBJECT,
        PoleClass.LOCATION,
        PoleClass.EVENT,
        PoleClass.ORGANISATION,
    ], "always five, in this order"
    by_class = {c.pole_class: c for c in figures.classes}
    person = by_class[PoleClass.PERSON]
    assert person.total == 10
    assert [(t.entity_type, t.count) for t in person.types] == [("Person", 5), ("ThreatActor", 5)]
    assert by_class[PoleClass.OBJECT].total == 1
    assert [t.entity_type for t in by_class[PoleClass.OBJECT].types] == ["Vehicle"]
    assert by_class[PoleClass.ORGANISATION].total == 2
    assert (by_class[PoleClass.LOCATION].total, by_class[PoleClass.LOCATION].types) == (0, [])
    assert figures.counted_at == COUNTED


def test_the_classifier_leaves_alert_out_of_event_and_of_every_figure() -> None:
    figures = pole_figures(PLANTED, ONTOLOGY, counted_at=COUNTED)

    event = next(c for c in figures.classes if c.pole_class is PoleClass.EVENT)
    assert event.total == 0 and event.types == []
    everywhere = [t.entity_type for c in figures.classes for t in c.types]
    assert "Alert" not in everywhere
    assert "Alert" not in [t.entity_type for t in figures.other]


def test_the_classifier_puts_a_type_the_ontology_does_not_know_under_other() -> None:
    figures = pole_figures(PLANTED, ONTOLOGY, counted_at=COUNTED)

    assert [(t.entity_type, t.count) for t in figures.other] == [("Alien", 4), ("Gone", 4)]
    assert sum(c.total for c in figures.classes) + sum(t.count for t in figures.other) == 21, (
        "every node but the Alerts is in the figures, so none vanishes"
    )


def test_the_classifier_counts_links_that_are_not_system_and_those_it_does_not_know() -> None:
    figures = pole_figures(PLANTED, ONTOLOGY, counted_at=COUNTED)

    assert figures.links == 6 + 2, "MEMBER_OF and a pending proposal's type; not SAME_AS & co."


def test_the_classifier_of_an_empty_case_is_five_empty_classes() -> None:
    figures = pole_figures(TypeCounts(), ONTOLOGY, counted_at=COUNTED)

    assert [c.total for c in figures.classes] == [0, 0, 0, 0, 0]
    assert figures.other == [] and figures.links == 0


def test_a_class_is_typed_so_a_sixth_cannot_be_written() -> None:
    PoleClassCount(pole_class=PoleClass.PERSON, total=0, types=[])
    with pytest.raises(ValidationError):
        PoleClassCount(pole_class="vehicle", total=0, types=[])  # type: ignore[arg-type]


# --- which figures a case gets ----------------------------------------------------------------


class _Spy:
    def __init__(self) -> None:
        self.kyc_reads = 0

    async def kyc(self, *args: object, **kwargs: object) -> KycFigures:
        self.kyc_reads += 1
        return KycFigures(customers=2, verified=1, unverified=1, by_band=[])


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> _Spy:
    spy = _Spy()

    async def _no_alerts(*args: object, **kwargs: object) -> list[object]:
        return []

    monkeypatch.setattr(reports_module, "queue", _no_alerts)
    monkeypatch.setattr(reports_module, "_kyc_figures", spy.kyc)
    return spy


async def _report(
    domains: Sequence[str], explore: ExploreService, reader: Principal = READER
) -> ReportFigures:
    return await case_report(
        alerts=None,  # type: ignore[arg-type]
        graph=None,  # type: ignore[arg-type]
        held=None,  # type: ignore[arg-type]
        compute=None,  # type: ignore[arg-type]
        investigation_id="case-1",
        reader=reader,
        today=TODAY,
        domains=domains,
        ontology=ONTOLOGY,
        explore=explore,
    )


@pytest.mark.parametrize(
    ("domains", "has_kyc", "has_pole"),
    [
        ([], False, True),
        (["fibo"], True, False),
        (["niem"], False, True),
        (["stix"], False, True),
        (["fibo", "niem"], True, True),
        (["fibo", "stix"], True, True),
        (["fibo", "niem", "stix"], True, True),
    ],
)
async def test_each_case_gets_the_figures_its_packs_call_for(
    spy: _Spy, domains: list[str], has_kyc: bool, has_pole: bool
) -> None:
    """The plant is `case_report` ignoring the packs: any one of these rows then fails."""
    explore, _ = _explore(PLANTED)

    figures = await _report(domains, explore)

    assert (figures.kyc is not None, figures.pole is not None) == (has_kyc, has_pole)


async def test_a_case_without_fibo_assesses_no_customer(spy: _Spy) -> None:
    for domains in ([], ["niem"], ["stix"], ["niem", "stix"]):
        await _report(domains, _explore(PLANTED)[0])
    assert spy.kyc_reads == 0

    await _report(["fibo"], _explore(PLANTED)[0])
    assert spy.kyc_reads == 1


async def test_a_pure_aml_case_reads_no_pole_counts_at_all(spy: _Spy) -> None:
    explore, graph = _explore(PLANTED)

    await _report(["fibo"], explore)

    assert graph.asked_as == [], "the card is not sent, so nothing is counted for it"


async def test_a_case_that_assesses_no_customer_is_not_held_to_the_customer_bound(
    monkeypatch: pytest.MonkeyPatch, spy: _Spy
) -> None:
    """ADR-111 decision 4's bound applies only when `kyc` is computed (ADR-126 decision 3)."""

    async def _too_many(*args: object, **kwargs: object) -> KycFigures:
        raise AssertionError("customers were read for a case with no fibo")

    monkeypatch.setattr(reports_module, "_kyc_figures", _too_many)

    figures = await _report(["niem"], _explore(PLANTED)[0])

    assert figures.kyc is None and figures.pole is not None


# --- the POLE counts are the reader's own -----------------------------------------------------

_RANK = {"OFFICIAL": 1, "SECRET": 2}


class _FilteringGraph:
    """A graph that answers `type_counts` as the adapter does: a node counts when its marking is
    within the principal's clearance and it is in one of the principal's datasets (`None` is all),
    a link when it, and both ends, count."""

    def __init__(self) -> None:
        self.nodes: dict[str, tuple[str, str, str]] = {}  # id -> (type, marking, dataset)
        self.links: list[tuple[str, str, str, str, str]] = []  # type, src, dst, marking, dataset

    def node(
        self, node_id: str, node_type: str, *, marking: str = "OFFICIAL", dataset: str
    ) -> None:
        self.nodes[node_id] = (node_type, marking, dataset)

    def link(self, link_type: str, src: str, dst: str, *, marking: str = "OFFICIAL",
             dataset: str) -> None:  # fmt: skip
        self.links.append((link_type, src, dst, marking, dataset))

    def _sees(self, principal: Principal, marking: str, dataset: str) -> bool:
        within = _RANK[marking] <= _RANK[principal.clearance]
        return within and (principal.datasets is None or dataset in principal.datasets)

    async def type_counts(self, principal: Principal) -> TypeCounts:
        visible = {i for i, (_, m, d) in self.nodes.items() if self._sees(principal, m, d)}
        nodes: dict[str, int] = {}
        for i in visible:
            nodes[self.nodes[i][0]] = nodes.get(self.nodes[i][0], 0) + 1
        edges: dict[str, int] = {}
        for link_type, src, dst, marking, dataset in self.links:
            if self._sees(principal, marking, dataset) and src in visible and dst in visible:
                edges[link_type] = edges.get(link_type, 0) + 1
        return TypeCounts(nodes=nodes, edges=edges)


def _world(*, with_hidden: bool) -> _FilteringGraph:
    graph = _FilteringGraph()
    graph.node("p1", "Person", dataset="ds-a")
    graph.node("p2", "Person", dataset="ds-a")
    graph.node("o1", "Organisation", dataset="ds-a")
    graph.link("MEMBER_OF", "p1", "o1", dataset="ds-a")
    graph.link("ASSOCIATE_OF", "p1", "p2", dataset="ds-a")
    if with_hidden:
        graph.node("secret", "Person", marking="SECRET", dataset="ds-a")
        graph.node("elsewhere", "Person", dataset="ds-other")
        graph.link("MEMBER_OF", "p2", "secret", dataset="ds-a")
        graph.link("ASSOCIATE_OF", "p1", "p2", marking="SECRET", dataset="ds-a")
    return graph


async def _pole_as(graph: _FilteringGraph, reader: Principal) -> PoleFigures:
    explore = ExploreService(graph, None, now=lambda: COUNTED)  # type: ignore[arg-type]
    figures = await _report([], explore, reader)
    return figures.pole  # type: ignore[return-value]


async def test_the_pole_counts_are_the_readers_own_and_a_hidden_node_is_in_none(
    spy: _Spy,
) -> None:
    """Four things the reader cannot have: a node over their clearance, a node in another dataset,
    a readable link to the hidden node, and a hidden link between two readable nodes. The figures
    must equal those of the same case without them. The plant is the figures counted for a widened
    principal (`clearance` SECRET, `datasets=None`)."""
    plain = await _pole_as(_world(with_hidden=False), READER)
    with_hidden = await _pole_as(_world(with_hidden=True), READER)

    assert with_hidden == plain
    person = next(c for c in plain.classes if c.pole_class is PoleClass.PERSON)
    assert person.total == 2 and plain.links == 2, "a non-empty comparison, not two empties"


async def test_the_fake_graph_does_show_a_widened_reader_the_hidden_things(spy: _Spy) -> None:
    """Shown able to fail: counted for a wider principal the same world differs, so the equality
    above is the reader's own scope at work and not an accident of the fixture."""
    wide = READER.model_copy(update={"clearance": "SECRET", "datasets": None})

    plain = await _pole_as(_world(with_hidden=True), READER)
    widened = await _world(with_hidden=True).type_counts(wide)

    assert widened.nodes["Person"] == 4 and plain.links == 2 and widened.edges["ASSOCIATE_OF"] == 2


async def test_the_pole_counts_come_from_the_explore_service_as_the_reader(spy: _Spy) -> None:
    explore, graph = _explore(PLANTED)

    await _report([], explore)

    assert graph.asked_as == [READER]


# --- the feed ---------------------------------------------------------------------------------


def _figures(*, kyc: bool, pole: bool) -> ReportFigures:
    return ReportFigures(
        period_weeks=12,
        as_of=TODAY,
        generated_at=COUNTED,
        alerts_total=0,
        kyc=KycFigures(
            customers=2, verified=1, unverified=1, by_band=[ReportCount(label="low", value=2)]
        )
        if kyc
        else None,
        pole=pole_figures(PLANTED, ONTOLOGY, counted_at=COUNTED) if pole else None,
    )


def test_the_feed_carries_exactly_the_cards_rows() -> None:
    figures = _figures(kyc=False, pole=True)
    assert figures.pole is not None

    rows = [r for r in feed_rows(figures) if r[0].startswith("pole")]

    expected: list[tuple[str, str, str, str, int]] = []
    for c in figures.pole.classes:
        expected.append(("pole", c.pole_class.value, "", "", c.total))
        expected += [
            ("pole_type", f"{c.pole_class.value}:{t.entity_type}", "", "", t.count) for t in c.types
        ]
    expected += [
        ("pole_other", f"other:{t.entity_type}", "", "", t.count) for t in figures.pole.other
    ]
    expected.append(("pole_links", "links", "", "", figures.pole.links))
    assert rows == expected
    assert ("pole", "person", "", "", 10) in rows
    assert ("pole_type", "person:Person", "", "", 5) in rows
    assert ("pole_other", "other:Alien", "", "", 4) in rows
    assert ("pole_links", "links", "", "", 8) in rows


def test_the_feed_leaves_typology_empty_on_every_pole_row() -> None:
    """A BI user filtering typologies must never meet an entity type."""
    rows = [r for r in feed_rows(_figures(kyc=True, pole=True)) if r[0].startswith("pole")]

    assert rows and all(r[2] == "" and r[3] == "" for r in rows)


def test_a_case_with_a_kyc_card_carries_kyc_rows_and_one_without_carries_none() -> None:
    with_kyc = feed_rows(_figures(kyc=True, pole=False))
    without = feed_rows(_figures(kyc=False, pole=True))

    assert {r[0] for r in with_kyc} >= {"kyc", "kyc_band"}
    assert not [r for r in with_kyc if r[0].startswith("pole")]
    assert not [r for r in without if r[0].startswith("kyc")]


def test_a_pole_type_row_is_labelled_by_a_closed_class_and_a_type_name_only() -> None:
    figures = ReportFigures(
        period_weeks=12, as_of=TODAY, generated_at=COUNTED, alerts_total=0,
        pole=pole_figures(TypeCounts(nodes={"Person": 1}), ONTOLOGY, counted_at=COUNTED),
    )  # fmt: skip

    labels = [r[1] for r in feed_rows(figures) if r[0] == "pole_type"]

    assert labels == ["person:Person"]


# --- the five classes are a rule of the model -------------------------------------------------


def _classes(*order: PoleClass) -> list[PoleClassCount]:
    return [PoleClassCount(pole_class=c, total=0, types=[]) for c in order]


_FIVE = (
    PoleClass.PERSON,
    PoleClass.OBJECT,
    PoleClass.LOCATION,
    PoleClass.EVENT,
    PoleClass.ORGANISATION,
)


def test_the_pole_figures_are_exactly_the_five_classes_in_order() -> None:
    PoleFigures(classes=_classes(*_FIVE), other=[], links=0, counted_at=COUNTED)

    with pytest.raises(ValidationError, match="five"):
        PoleFigures(classes=_classes(*_FIVE[:4]), other=[], links=0, counted_at=COUNTED)
    with pytest.raises(ValidationError, match="five"):
        PoleFigures(classes=[], other=[], links=0, counted_at=COUNTED)
    with pytest.raises(ValidationError, match="five"):
        PoleFigures(
            classes=_classes(*_FIVE, PoleClass.PERSON), other=[], links=0, counted_at=COUNTED
        )


def test_the_pole_figures_refuse_the_classes_in_another_order() -> None:
    swapped = (_FIVE[1], _FIVE[0], *_FIVE[2:])

    with pytest.raises(ValidationError, match="order"):
        PoleFigures(classes=_classes(*swapped), other=[], links=0, counted_at=COUNTED)


# --- when the counts were taken ---------------------------------------------------------------


class _UndatedThenDated:
    """An explore whose first answer says nothing of when it was counted (a kept entry from before
    the stamp existed); asked for a fresh count, it answers with the time."""

    def __init__(self, *, fresh_is_dated: bool = True) -> None:
        self.asked: list[bool] = []
        self.fresh_is_dated = fresh_is_dated

    async def counts(self, principal: Principal, *, fresh: bool = False) -> TypeCounts:
        self.asked.append(fresh)
        dated = fresh and self.fresh_is_dated
        return PLANTED.model_copy(update={"computed_at": COUNTED if dated else None})


async def test_counts_without_a_date_are_recounted_and_never_stamped_now(spy: _Spy) -> None:
    explore = _UndatedThenDated()

    figures = await _report([], explore)  # type: ignore[arg-type]

    assert explore.asked == [False, True], "a missing date is a cache miss: recount, bypassing"
    assert figures.pole is not None and figures.pole.counted_at == COUNTED
    assert figures.pole.counted_at != figures.generated_at


async def test_counts_that_stay_undated_are_refused_rather_than_stamped_now(spy: _Spy) -> None:
    explore = _UndatedThenDated(fresh_is_dated=False)

    with pytest.raises(RuntimeError, match="computed_at"):
        await _report([], explore)  # type: ignore[arg-type]


class _Kept:
    def __init__(self, held: dict[str, object] | None) -> None:
        self.held = held
        self.put_with: list[object] = []

    async def get(self, signature: str, principal: Principal) -> object | None:
        return self.held

    async def put(self, signature: str, principal: Principal, result: object) -> None:
        self.put_with.append(result)

    async def invalidate_prefix(self) -> None:
        return None


async def test_a_kept_entry_without_a_date_is_a_miss_in_the_explore_service() -> None:
    cache = _Kept({"nodes": {"Person": 1}, "edges": {}})
    graph = _Graph(PLANTED)
    explore = ExploreService(graph, cache, now=lambda: COUNTED)  # type: ignore[arg-type]

    counts = await explore.counts(READER)

    assert graph.asked_as == [READER] and counts.computed_at == COUNTED
    assert len(cache.put_with) == 1


async def test_a_fresh_count_bypasses_a_dated_kept_entry_and_replaces_it() -> None:
    kept = PLANTED.model_dump(mode="json")
    cache = _Kept(kept)
    graph = _Graph(TypeCounts(nodes={"Person": 9}, computed_at=COUNTED))
    explore = ExploreService(graph, cache, now=lambda: COUNTED)  # type: ignore[arg-type]

    assert (await explore.counts(READER)).nodes == PLANTED.nodes, "served from what was kept"
    assert graph.asked_as == []
    assert (await explore.counts(READER, fresh=True)).nodes == {"Person": 9}
    assert graph.asked_as == [READER] and len(cache.put_with) == 1


# --- the routes pass the case's packs, the ontology and the kept counts -----------------------

VIEWER = Principal(id="viv", clearance="OFFICIAL", org_unit="unit-1", roles=["reports_viewer"])


class _Cases:
    def __init__(self, domains: list[str]) -> None:
        from services.api.investigations import Investigation

        self.case = Investigation(
            id="inv-1",
            name="Case",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by="alice",
            owning_unit="unit-1",
            domains=domains,  # type: ignore[arg-type]
        )

    async def get_authorized(self, investigation_id: str, principal: Principal, *, need: object):  # type: ignore[no-untyped-def]
        return self.case

    async def effective_level(self, investigation_id: str, principal: Principal):  # type: ignore[no-untyped-def]
        from services.api.investigations import AccessLevel

        return AccessLevel.VIEWER


class _Sink:
    async def record(self, *args: object, **kwargs: object) -> None:
        return None


@pytest.fixture
def client(spy: _Spy):  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient
    from services.api.app import (
        app,
        get_alerts_store,
        get_audit,
        get_compute,
        get_explore,
        get_export_ledger,
        get_graph,
        get_held_rows,
        get_investigations,
        get_ontology,
        get_principal,
    )

    def build(domains: list[str]) -> tuple[TestClient, _Graph]:
        explore, graph = _explore(PLANTED)
        app.dependency_overrides[get_investigations] = lambda: _Cases(domains)
        app.dependency_overrides[get_principal] = lambda: VIEWER
        app.dependency_overrides[get_alerts_store] = lambda: object()
        app.dependency_overrides[get_audit] = lambda: _Sink()
        app.dependency_overrides[get_export_ledger] = lambda: _Sink()
        app.dependency_overrides[get_graph] = lambda: object()
        app.dependency_overrides[get_held_rows] = lambda: object()
        app.dependency_overrides[get_compute] = lambda: object()
        app.dependency_overrides[get_ontology] = lambda: ONTOLOGY
        app.dependency_overrides[get_explore] = lambda: explore
        return TestClient(app, raise_server_exceptions=True), graph

    yield build
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("domains", "has_kyc", "has_pole"),
    [([], False, True), (["fibo"], True, False), (["fibo", "niem"], True, True)],
)
def test_the_view_and_the_feed_follow_the_cases_packs_at_the_route(
    client: Any,
    domains: list[str],
    has_kyc: bool,
    has_pole: bool,
) -> None:
    """The plant is a route that hands `case_report` no packs of the case (`domains=[]` always)."""
    api, _ = client(domains)

    view = api.get("/v1/investigations/inv-1/reports")
    feed = api.get("/v1/investigations/inv-1/reports/feed?format=csv")

    assert view.status_code == 200, view.text
    assert (view.json()["kyc"] is not None, view.json()["pole"] is not None) == (has_kyc, has_pole)
    sections = {line.split(",")[0] for line in feed.text.splitlines()[1:]}
    assert ("kyc" in sections, "pole" in sections) == (has_kyc, has_pole)


def test_a_reports_viewer_reads_the_pole_figures_without_the_investigate_right(client: Any) -> None:
    """ADR-126 decision 5: the roles ADR-112 gave Reports hold no `INVESTIGATE`, so they cannot
    read Explore's counts, and read these figures all the same."""
    api, _ = client([])

    assert api.get("/v1/investigations/inv-1/explore/counts").status_code == 403
    view = api.get("/v1/investigations/inv-1/reports")
    assert view.status_code == 200 and view.json()["pole"]["links"] == 8


def test_a_case_with_a_pole_card_reads_the_counts_as_the_reader_at_the_route(client: Any) -> None:
    api, graph = client(["niem"])

    api.get("/v1/investigations/inv-1/reports")

    assert [p.id for p in graph.asked_as] == ["viv"] and graph.asked_as[0].clearance == "OFFICIAL"
