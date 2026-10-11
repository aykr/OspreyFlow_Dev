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
- the feed and the view disagreeing — the route case reading both for one reader;
- the feed leaving without a record — the route case finding its export-ledger entry;
- a free-text field slipping into the feed — `test_the_feed_carries_no_free_text`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from services.api import reports as reports_module
from services.api.alerts import AlertStore
from services.api.config import PostgresConfig
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
    return await case_report(alerts=stores["alerts"], graph=graph, held=stores["held"],  # type: ignore[arg-type]
                             compute=ComputeRustworkxAdapter(), investigation_id=case,
                             reader=READER, today=TODAY, **kw)  # type: ignore[arg-type]  # fmt: skip


def _without_time(figures: ReportFigures) -> dict[str, object]:
    return figures.model_dump(exclude={"generated_at"})


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
        figures = await _report(stores, graph, case)
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


def test_the_feed_carries_no_free_text() -> None:
    """Figures only (ADR-111 decision 6): every string the feed can carry is a fixed label or a
    date. A new free-text field — an alert's words, a name — fails here until it is justified."""
    allowed = {"label", "typology", "band"}

    def strings(model: type) -> set[str]:
        found: set[str] = set()
        for name, field in model.model_fields.items():  # type: ignore[attr-defined]
            annotation = field.annotation
            inner = getattr(annotation, "__args__", (annotation,))
            for kind in inner:
                if kind is str:
                    found.add(name)
                elif isinstance(kind, type) and hasattr(kind, "model_fields"):
                    found |= strings(kind)
                for sub in getattr(kind, "__args__", ()):
                    if isinstance(sub, type) and hasattr(sub, "model_fields"):
                        found |= strings(sub)
        return found

    assert strings(ReportFigures) <= allowed


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
    return {"Authorization": f"Bearer {sign_token(private_key, default_claims(sub=sub))}"}


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


def test_the_view_and_the_feed_agree_and_the_feed_is_recorded(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    key, _ = keypair
    case = asyncio.run(_case_with_an_alert())
    from services.api.app import app

    with TestClient(app) as client:
        view = client.get(f"/v1/investigations/{case}/reports", headers=_as(key, VIEWER))
        assert view.status_code == 200, view.text
        feed = client.get(f"/v1/investigations/{case}/reports/feed", headers=_as(key, VIEWER))
        assert feed.status_code == 200, feed.text
        strip = lambda body: {k: v for k, v in body.items() if k != "generated_at"}  # noqa: E731
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
