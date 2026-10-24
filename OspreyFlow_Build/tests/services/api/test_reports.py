"""The Reports view's figures (`06_DECISIONS.md` ADR-111): one computation for the Glass's Reports
view and the dashboards' feed, every figure counted as its reader. Real Postgres (alerts, held rows)
and real ArcadeDB (the all-or-nothing referent check, the KYC assessment) — a fake cannot stand in
for "a hidden alert is in no figure".

What a mistake would do, and the case that catches it:
- a hidden alert counted in a total or a bucket, telling the reader it exists (rule 3, the
  "histogram bucket" clause) — `test_a_hidden_alert_changes_no_figure`, the same report with and
  without it, equal;
- held rows shown to a Viewer, who may not read them — `test_held_figures_are_for_editors_only`;
- a report silently cut at its bound (rule 2) — `test_a_report_past_its_bound_says_so`;
- the POLE figures counting something the reader cannot read, or something outside the case's
  datasets, or a link to or between such things (rule 3) —
  `test_the_pole_figures_count_nothing_the_reader_cannot_read_at_the_route`, the same figures for
  a case with those things and one without;
- the feed and the view disagreeing — the route case reading both for one reader;
- the feed leaving without a record — the route case finding its export-ledger entry;
- a free-text field slipping into the feed — `test_the_feed_carries_no_free_text`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from services.api import reports as reports_module
from services.api.alerts import AlertStore
from services.api.config import PostgresConfig
from services.api.datasets import Dataset, PostgresDatasetStore
from services.api.explore import ExploreService
from services.api.held_rows import HeldRowStore
from services.api.investigations import AccessLevel, InvestigationStore
from services.api.reports import ReportLimitExceededError, case_report

from adapters.compute_rustworkx.adapter import ComputeRustworkxAdapter
from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_edge_id, new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from ontology.packs import load_deployment_ontology
from schemas.domain import (
    Alert,
    AlertMode,
    EdgeWrite,
    Handling,
    HeldRow,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    ReportFigures,
    SourceRef,
)
from tests.conftest import default_claims, sign_token
from tests.services.api.case_dataset import dataset_for, give_case_its_dataset

SCHEME = load_uk_le_scheme()
ONTOLOGY = load_deployment_ontology()
DATASET = f"reports-{new_id()}"
READER = Principal(id="reports-reader", clearance="OFFICIAL", org_unit="unit-1", datasets=[DATASET])
TODAY = date.today()


def _handling(classification: str = "OFFICIAL") -> Handling:
    return Handling(classification=classification, handling_code="P", originator="unit-1",
                    owning_unit="unit-1")  # fmt: skip


def _provenance() -> Provenance:
    return Provenance(state=ProvenanceState.ASSERTED, first_seen=datetime.now(UTC),
                      sources=[SourceRef(document_id="fixture", locator="t", excerpt_hash="")])  # fmt: skip


def _node(node_type: str, props: dict[str, object], *, classification: str = "OFFICIAL",
          dataset: str = DATASET) -> NodeWrite:  # fmt: skip
    return NodeWrite(id=new_id(), type=node_type, properties=props, provenance=_provenance(),
                     handling=_handling(classification), created_by="test",
                     created_at=datetime.now(UTC), datasets=[dataset])  # fmt: skip


def _alert(case: str, node_ids: list[str], typology: str, *, dataset: str = DATASET, days_ago: int = 0,
           status: str = "open", disposition: str | None = None) -> Alert:  # fmt: skip
    return Alert(
        id=new_id(), rule_id=f"typology:{new_id()}", owner_id="deployer", mode=AlertMode.FULL,
        referent_node_ids=node_ids, investigation_id=case, dataset_id=dataset,
        created_at=datetime.now(UTC) - timedelta(days=days_ago), typology=typology, words="w",
        status=status, disposition=disposition,  # type: ignore[arg-type]
    )  # fmt: skip


@pytest.fixture
async def stores() -> Iterator[dict[str, object]]:
    dsn = PostgresConfig.from_env().dsn
    made = {"alerts": await AlertStore.connect(dsn), "held": await HeldRowStore.connect(dsn, SCHEME)}
    yield made  # type: ignore[misc]
    for store in made.values():
        await store.close()  # type: ignore[attr-defined]


async def _write(graph: object, nodes: list[NodeWrite], edges: list[EdgeWrite] = ()) -> list[str]:  # type: ignore[assignment]
    tx = await graph.begin_transaction()  # type: ignore[attr-defined]
    ids = await graph.upsert_nodes(nodes, tx)  # type: ignore[attr-defined]
    if edges:
        await graph.upsert_edges(list(edges), tx)  # type: ignore[attr-defined]
    await graph.commit_transaction(tx)  # type: ignore[attr-defined]
    return list(ids)


async def _report(stores: dict[str, object], graph: object, case: str, **kw: object) -> ReportFigures:
    # ADR-126: a case's packs choose its figures; a case of none (POLE) unless the test says so.
    kw.setdefault("domains", [])
    return await case_report(alerts=stores["alerts"], graph=graph, held=stores["held"],  # type: ignore[arg-type]
                             compute=ComputeRustworkxAdapter(), investigation_id=case,
                             reader=READER, today=TODAY, ontology=ONTOLOGY,
                             explore=ExploreService(graph, None),  # type: ignore[arg-type]
                             **kw)  # type: ignore[arg-type]  # fmt: skip


def _without_time(figures: ReportFigures) -> dict[str, object]:
    return figures.model_dump(exclude={"generated_at": True, "pole": {"counted_at"}})


async def test_a_report_counts_the_alerts_by_typology_age_and_outcome(stores: dict[str, object]) -> None:
    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        a, b = await _write(graph, [_node("Person", {"family_name": "A"}), _node("Person", {"family_name": "B"})])
        for alert in (_alert(case, [a], "structuring"), _alert(case, [b], "rapid_movement", days_ago=10),
                      _alert(case, [a, b], "structuring", days_ago=3, status="closed",
                             disposition="true_positive")):  # fmt: skip
            await stores["alerts"].save(alert)  # type: ignore[attr-defined]
        figures = await _report(stores, graph, case)
    assert figures.alerts_total == 3
    by_typology = {o.typology: o for o in figures.outcomes}
    assert (by_typology["structuring"].open, by_typology["structuring"].true_positive) == (1, 1)
    assert by_typology["rapid_movement"].open == 1
    assert {c.label: c.value for c in figures.open_by_age} == {
        "under a day": 1, "1 to 7 days": 0, "7 to 30 days": 1, "over 30 days": 0}  # fmt: skip
    assert sum(w.count for w in figures.alerts_by_week) == 3


async def test_a_hidden_alert_changes_no_figure(stores: dict[str, object]) -> None:
    """The plant: two cases identical but for one alert on a node the reader cannot see. Their
    reports must be equal — in every total, outcome and age bucket (rule 3)."""
    seen, hidden_case = f"case-{new_id()}", f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        a, secret = await _write(graph, [_node("Person", {"family_name": "A"}),
                                         _node("Person", {"family_name": "S"}, classification="SECRET")])  # fmt: skip
        for case in (seen, hidden_case):
            await stores["alerts"].save(_alert(case, [a], "structuring"))  # type: ignore[attr-defined]
        await stores["alerts"].save(_alert(hidden_case, [a, secret], "circular_flow"))  # type: ignore[attr-defined]
        assert _without_time(await _report(stores, graph, seen)) == _without_time(
            await _report(stores, graph, hidden_case))


async def test_held_figures_are_for_editors_only(stores: dict[str, object]) -> None:
    case = f"case-{new_id()}"
    for classification in ("OFFICIAL", "SECRET"):
        await stores["held"].hold([HeldRow(  # type: ignore[attr-defined]
            id=new_id(), investigation_id=case, recipe_id="r", recipe_version=1, load_id="l", source="s",
            row_index=0, row={"a": "1"}, rule_id="rule", reason="test", handling=_handling(classification),
            held_at=datetime.now(UTC), dataset_id=DATASET)])  # fmt: skip
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        viewer = await _report(stores, graph, case, show_held=False)
        editor = await _report(stores, graph, case, show_held=True)
    assert viewer.held is None
    assert editor.held is not None and (editor.held.held, editor.held.released) == (1, 0), "SECRET row not counted"


async def test_the_kyc_book_is_assessed_as_the_reader(stores: dict[str, object]) -> None:
    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        good, lapsed, valid_doc, old_doc = await _write(graph, [
            _node("Organisation", {"name": "Steady Freight Ltd"}),
            _node("Organisation", {"name": "Halcyon Marine Ltd", "country": "CY"}),
            _node("Document", {"title": "Cert", "document_kind": "certificate_of_incorporation",
                               "expires_on": "2099-01-01"}),
            _node("Document", {"title": "Cert", "document_kind": "certificate_of_incorporation",
                               "expires_on": "2025-01-31"}),
        ])  # fmt: skip
        edges = [EdgeWrite(id=new_edge_id(), type="VERIFIED_BY", source=s, target=t, provenance=_provenance(),
                           handling=_handling(), created_by="test", created_at=datetime.now(UTC),
                           datasets=[DATASET]) for s, t in ((good, valid_doc), (lapsed, old_doc))]  # fmt: skip
        await _write(graph, [], edges)
        figures = await _report(stores, graph, case, domains=["fibo"])  # ADR-126: a `[fibo]` case
    assert figures.kyc is not None and figures.pole is None
    assert (figures.kyc.customers, figures.kyc.verified, figures.kyc.unverified) == (2, 1, 1)
    assert sum(b.value for b in figures.kyc.by_band) == 2


async def test_a_report_past_its_bound_says_so(stores: dict[str, object], monkeypatch: pytest.MonkeyPatch) -> None:
    case = f"case-{new_id()}"
    monkeypatch.setattr(reports_module, "ALERT_BOUND", 1)
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        (a,) = await _write(graph, [_node("Person", {"family_name": "A"})])
        for _ in range(2):
            await stores["alerts"].save(_alert(case, [a], "structuring"))  # type: ignore[attr-defined]
        with pytest.raises(ReportLimitExceededError) as refused:
            await _report(stores, graph, case)
    assert (refused.value.detail.cap_kind, refused.value.detail.cap, refused.value.detail.would_be) == ("alerts", 1, 2)


#: ADR-126 decision 7. Each name here is justified: the feed leaves the Glass, so a string field is
#: a possible leak and is listed one by one.
#: - `label`, `typology`, `band`: fixed labels (ADR-111).
#: - `entity_type`: an ontology type name, closed and declared by the deployment, never an entity's
#:   own text (a stored type the ontology does not know is a type name too, never a property).
#: - `pole_class`: the closed POLE class, typed `PoleClass`, so no free string can be written.
FEED_STRING_ALLOWLIST = {"label", "typology", "band", "entity_type", "pole_class"}


def _string_fields(model: type) -> set[str]:
    """Every field of `model`, and of the models inside it, that is a string or a closed string
    set (an enum), by name."""
    import enum

    found: set[str] = set()
    for name, field in model.model_fields.items():  # type: ignore[attr-defined]
        annotation = field.annotation
        inner = getattr(annotation, "__args__", (annotation,))
        for kind in inner:
            if kind is str or (isinstance(kind, type) and issubclass(kind, enum.StrEnum)):
                found.add(name)
            elif isinstance(kind, type) and hasattr(kind, "model_fields"):
                found |= _string_fields(kind)
            for sub in getattr(kind, "__args__", ()):
                if isinstance(sub, type) and hasattr(sub, "model_fields"):
                    found |= _string_fields(sub)
    return found


def test_the_feed_carries_no_free_text() -> None:
    """Figures only (ADR-111 decision 6): every string the feed can carry is a fixed label, a closed
    ontology name or a date. A new free-text field — an alert's words, a name — fails here until it
    is justified."""
    assert _string_fields(ReportFigures) <= FEED_STRING_ALLOWLIST


def test_the_free_text_gate_fails_for_any_other_new_string_field() -> None:
    """Shown able to fail, in the shape the gate meets: a new string field on a model inside the
    report (a pole type that carried a name), and one on the report itself."""
    from pydantic import BaseModel

    from schemas.domain import PoleFigures

    class _Named(PoleFigures):
        note: str = ""

    class _WithName(ReportFigures):
        pole: _Named | None = None  # type: ignore[assignment]

    class _Reported(ReportFigures):
        analyst: str = ""

    assert _string_fields(_WithName) - FEED_STRING_ALLOWLIST == {"note"}
    assert _string_fields(_Reported) - FEED_STRING_ALLOWLIST == {"analyst"}
    assert issubclass(_Reported, BaseModel)
    assert {"entity_type", "pole_class"} <= _string_fields(ReportFigures), (
        "the gate sees the new fields, so the allowlist entries are what lets them through"
    )


# --- the routes ---------------------------------------------------------------------------------

AUTHOR = Principal(id="reports-author", clearance="OFFICIAL", org_unit="unit-1")
VIEWER = "reports-viewer"
OUTSIDER = "reports-outsider"


@pytest.fixture
def api_env(jwks_url: str) -> Iterator[None]:
    import os

    previous = {k: os.environ.get(k) for k in ("OIDC_JWKS_URL", "OIDC_ALGORITHMS", "ARCADEDB_DATABASE")}
    os.environ.update(OIDC_JWKS_URL=jwks_url, OIDC_ALGORITHMS="RS256", ARCADEDB_DATABASE="ospreyflow")
    try:
        yield
    finally:
        for key, value in previous.items():
            os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)


def _as(private_key: rsa.RSAPrivateKey, sub: str) -> dict[str, str]:
    # ADR-112: the feed is the Reports Viewer's right; the case Viewer here holds that role.
    claims = default_claims(sub=sub, roles=["reports_viewer"])
    return {"Authorization": f"Bearer {sign_token(private_key, claims)}"}


async def _case_with_an_alert() -> str:
    store = await InvestigationStore.connect(PostgresConfig.from_env().dsn)
    alerts = await AlertStore.connect(PostgresConfig.from_env().dsn)
    try:
        case = await store.create(AUTHOR, name="Reports case")
        await give_case_its_dataset(case.id, AUTHOR)
        await store.set_grant(case.id, VIEWER, AccessLevel.VIEWER, by=AUTHOR)
        # The running app's own database, never `arcadedb_adapter`'s separate one.
        client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
        try:
            graph = GraphArcadeDBAdapter(client, SCHEME)
            await graph.apply_schema(load_default_ontology())
            (a,) = await _write(graph, [_node("Person", {"family_name": "A"}, dataset=dataset_for(AUTHOR))])
        finally:
            await client.aclose()
        await alerts.save(_alert(case.id, [a], "structuring", dataset=dataset_for(AUTHOR)))
        return case.id
    finally:
        await store.close()
        await alerts.close()


@contextmanager
def _app_client() -> Iterator[TestClient]:
    """The real app, driven as `test_the_view_and_the_feed_agree...` always has, with the `explore`
    prefix cleared before the first read and again when the test ends, on the app's own loop (its
    Valkey connection is made there; `asyncio.run` would use it from a second loop).

    The key of a kept count holds the principal and no store or database, which is right for one
    store per deployment. These tests share one Valkey across databases, so a count left here is
    served to whichever file's case asks next (seen: `test_explore_routes.py` run after this file,
    7 failed). Every route test in this file goes through this."""
    from services.api.app import app

    with TestClient(app) as client:
        assert client.portal is not None
        client.portal.call(app.state.explore_cache.invalidate_prefix)
        try:
            yield client
        finally:
            client.portal.call(app.state.explore_cache.invalidate_prefix)


def test_the_view_and_the_feed_agree_and_the_feed_is_recorded(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    key, _ = keypair
    case = asyncio.run(_case_with_an_alert())

    with _app_client() as client:
        view = client.get(f"/v1/investigations/{case}/reports", headers=_as(key, VIEWER))
        assert view.status_code == 200, view.text
        feed = client.get(f"/v1/investigations/{case}/reports/feed", headers=_as(key, VIEWER))
        assert feed.status_code == 200, feed.text
        def strip(body: dict[str, object]) -> dict[str, object]:
            pole = body.get("pole")
            return {
                **{k: v for k, v in body.items() if k not in ("generated_at", "pole")},
                "pole": None
                if pole is None
                else {k: v for k, v in pole.items() if k != "counted_at"},  # type: ignore[attr-defined]
            }

        assert strip(view.json()) == strip(feed.json())
        assert view.json()["alerts_total"] == 1 and view.json()["held"] is None, "a Viewer sees no held rows"
        csv = client.get(f"/v1/investigations/{case}/reports/feed?format=csv", headers=_as(key, VIEWER))
        assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
        assert csv.text.splitlines()[0] == "section,label,typology,week_start,value"
        assert client.get(f"/v1/investigations/{case}/reports", headers=_as(key, OUTSIDER)).status_code == 404

        ledger = client.get("/v1/exports", headers={"Authorization": f"Bearer {sign_token(key, default_claims(sub='compliance-1', roles=['compliance']))}"})  # fmt: skip
        assert ledger.status_code == 200, ledger.text
        feeds = [e for e in ledger.json()["entries"] if e["investigation_id"] == case]
        assert [(e["artefact_kind"], e["principal_id"]) for e in feeds] == [("report_feed", VIEWER)] * 2, \
            "each feed read, JSON and CSV, is in the export ledger; the view is not"


# --- ADR-126: the POLE figures are the reader's own, at the route ------------------------------


async def _register_dataset(dataset_id: str) -> None:
    store = await PostgresDatasetStore.connect(PostgresConfig.from_env().dsn)
    try:
        await store.add(
            Dataset(
                id=dataset_id,
                name=f"Pole figures {dataset_id}",
                owning_unit="unit-1",
                created_at=datetime.now(UTC),
                created_by="test",
            )
        )
    finally:
        await store.close()


#: The POLE fixture's nodes by key, and its links as (type, source, target, marking, hidden).
#: One table, read by the fixture and by
#: `test_the_pole_fixtures_links_are_ones_the_ontology_permits`, so a link the composed ontology
#: refuses is found without a live run. A hidden pair is never a visible pair, so no store that
#: merges same-pair links can fold a SECRET link into a readable one.
POLE_NODE_TYPES = {"p1": "Person", "p2": "Person", "org": "Organisation", "secret": "Person"}
POLE_LINKS: list[tuple[str, str, str, str, bool]] = [
    ("MEMBER_OF", "p1", "org", "OFFICIAL", False),
    ("ASSOCIATE_OF", "p1", "p2", "OFFICIAL", False),
    # A readable link to the hidden node.
    ("ASSOCIATE_OF", "p2", "secret", "OFFICIAL", True),
    # A hidden link between two readable nodes.
    ("MEMBER_OF", "p2", "org", "SECRET", True),
]


def test_the_pole_fixtures_links_are_ones_the_ontology_permits() -> None:
    """The live fixture once wrote `MEMBER_OF` from a Person to a Person, which the composed
    ontology refuses (it runs Person to Organisation), and failed only when run live. Every link
    of the fixture, hidden or not, is checked here against the same composed ontology."""
    ends = {e.name: (e.from_types, e.to_types) for e in ONTOLOGY.edge_types}
    for kind, source, target, _marking, _hidden in POLE_LINKS:
        from_types, to_types = ends[kind]
        assert POLE_NODE_TYPES[source] in from_types, (kind, source)
        assert POLE_NODE_TYPES[target] in to_types, (kind, target)
    assert sum(1 for *_, hidden in POLE_LINKS if not hidden) == 2
    assert {POLE_NODE_TYPES[k] for k in ("p1", "p2", "org")} == {"Person", "Organisation"}


async def _pole_case(dataset_id: str, *, with_hidden: bool, other_dataset: str) -> str:
    """A POLE case (`domains=[]`) reading `dataset_id`, holding two people, an organisation and two
    links the viewer can read (`POLE_LINKS`). With `with_hidden`, also the four things the viewer
    must not be able to count: a SECRET person, a person in a dataset the case does not read, a
    readable link to the SECRET person, and a SECRET link between two readable people."""
    await _register_dataset(dataset_id)
    store = await InvestigationStore.connect(PostgresConfig.from_env().dsn)
    try:
        case = await store.create(AUTHOR, name=f"Pole figures {dataset_id}", domains=[])
        await store.set_grant(case.id, VIEWER, AccessLevel.VIEWER, by=AUTHOR)
        datasets = await PostgresDatasetStore.connect(PostgresConfig.from_env().dsn)
        try:
            await datasets.set_for_case(case.id, [dataset_id], AUTHOR)
        finally:
            await datasets.close()
    finally:
        await store.close()
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    try:
        graph = GraphArcadeDBAdapter(client, SCHEME)
        await graph.apply_schema(load_default_ontology())
        p1, p2, org = await _write(graph, [
            _node("Person", {"family_name": "A"}, dataset=dataset_id),
            _node("Person", {"family_name": "B"}, dataset=dataset_id),
            _node("Organisation", {"name": "Steady Freight Ltd"}, dataset=dataset_id),
        ])  # fmt: skip

        def link(kind: str, a: str, b: str, *, marking: str = "OFFICIAL") -> EdgeWrite:
            return EdgeWrite(
                id=new_edge_id(),
                type=kind,
                source=a,
                target=b,
                provenance=_provenance(),
                handling=_handling(marking),
                created_by="test",
                created_at=datetime.now(UTC),
                datasets=[dataset_id],
            )

        nodes: list[NodeWrite] = []
        ids = {"p1": p1, "p2": p2, "org": org}
        if with_hidden:
            secret = _node("Person", {"family_name": "S"}, classification="SECRET",
                           dataset=dataset_id)  # fmt: skip
            nodes = [secret, _node("Person", {"family_name": "Elsewhere"}, dataset=other_dataset)]
            ids["secret"] = secret.id
        edges = [
            link(kind, ids[source], ids[target], marking=marking)
            for kind, source, target, marking, hidden in POLE_LINKS
            if with_hidden or not hidden
        ]
        await _write(graph, nodes, edges)
    finally:
        await client.aclose()
    return case.id


def test_the_pole_figures_count_nothing_the_reader_cannot_read_at_the_route(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    """Rule 3 and 4, at the route (so `scope_to_case` is exercised). Two POLE cases, the same for
    the viewer but for four things in one: a node over the viewer's clearance, a node outside the
    case's datasets, a readable link to the hidden node, and a hidden link between two readable
    nodes. Their POLE figures, and the feed's POLE rows, must be equal, and not empty.

    **Written before the first read**, and the `explore` cache prefix is cleared in the test, so a
    kept count can never make this green. The plant is the figures counted for a widened principal
    (higher clearance, `datasets=None`) in `case_report`'s `explore.counts(...)` call."""
    key, _ = keypair
    suffix = new_id()
    other = f"pole-other-{suffix}"

    async def build() -> tuple[str, str]:
        await _register_dataset(other)
        plain = await _pole_case(f"pole-plain-{suffix}", with_hidden=False, other_dataset=other)
        hidden = await _pole_case(f"pole-hidden-{suffix}", with_hidden=True, other_dataset=other)
        return plain, hidden

    plain, hidden = asyncio.run(build())

    def pole_rows(csv_text: str) -> list[str]:
        return [line for line in csv_text.splitlines() if line.startswith("pole")]

    with _app_client() as client:
        seen: dict[str, tuple[dict[str, object], list[str]]] = {}
        for name, case in (("plain", plain), ("hidden", hidden)):
            view = client.get(f"/v1/investigations/{case}/reports", headers=_as(key, VIEWER))
            assert view.status_code == 200, view.text
            feed = client.get(
                f"/v1/investigations/{case}/reports/feed?format=csv", headers=_as(key, VIEWER)
            )
            assert feed.status_code == 200, feed.text
            body = view.json()
            assert body["kyc"] is None, "a case of no packs has no KYC card"
            pole = {k: v for k, v in body["pole"].items() if k != "counted_at"}
            seen[name] = (pole, pole_rows(feed.text))

    plain_pole, plain_rows = seen["plain"]
    hidden_pole, hidden_rows = seen["hidden"]
    classes: list[dict[str, Any]] = plain_pole["classes"]  # type: ignore[assignment]
    people = next(c for c in classes if c["pole_class"] == "person")
    assert people["total"] == 2 and plain_pole["links"] == 2, "a non-empty comparison"
    assert hidden_pole == plain_pole, "a hidden node or link is in a figure"
    assert plain_rows and hidden_rows == plain_rows, "the feed carries the same rows"
