"""The KYC gate as rules (`spec/06_DECISIONS.md` ADR-109 phase F), against live Postgres (rules,
alerts, audit, the screening list), Valkey, MinIO and ArcadeDB with Operation Ledger built in it —
the onboarding of Halcyon Marine Ltd, 80% owned by the Cyprus trust whose owners are PETROV (60%)
and NAIR (40%): PETROV holds 0.6 × 0.8 = 48% of the applicant, NAIR 0.4 × 0.8 = 32%.

What a mistake would do, and the case that catches it (each rule's fires case beside its refuses
case, rule 15):

- an applicant whose beneficial owner is listed, onboarded without an alert — the addendum's own
  demo (`test_an_applicant_owned_through_a_trust_by_a_listed_person_is_stopped_at_the_gate`), and
  an owner below the threshold screened as if a beneficial owner
  (`test_an_owner_below_the_threshold_is_not_screened`);
- a screening hit written asserted, or as a merge (rules 5 and 6) — the hit is a scored, inferred
  `SAME_AS` to the listed party (the same case);
- a phone already used by several customers missed (`test_a_shared_phone_is_flagged_at_the_count`);
- a customer verified only by an expired document onboarded unflagged
  (`test_an_expired_document_verifies_no_one`), and a valid one flagged (`…_a_valid_document_…`);
- a customer the rule's deployer cannot read, judged and disclosed (rule 3)
  (`test_a_customer_the_deployer_cannot_read_is_not_judged`);
- the gate working before commit only (`test_the_gate_runs_after_commit_too`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pytest
import yaml
from scripts.load_screening_list import parse_list
from services.api.alerts import AlertStore
from services.api.audit import AuditWriter
from services.api.config import PostgresConfig, ValkeyConfig
from services.api.held_rows import HeldRowStore
from services.api.rule_evaluation import RuleGate
from services.api.screening import ScreeningListStore
from services.api.studio_publish import load_with_rules
from services.api.typology_rules import TypologyRuleStore
from services.ingest.recipe_loader import load_recipe
from valkey.asyncio import Valkey

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table
from adapters.compute_rustworkx.adapter import ComputeRustworkxAdapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_edge_id, new_id, new_node_id
from demo_fixtures.ledger import build_ledger_graph
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.domain import (
    DocumentVerificationParams,
    EdgeWrite,
    Handling,
    KycScreeningParams,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SharedAttributesParams,
    SourceRef,
    TypologyRuleInput,
)

SCHEME = load_uk_le_scheme()
ONTOLOGY = load_deployment_ontology()
CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"
RECIPE = load_recipe(CORE / "packages/demo_fixtures/ledger_onboarding_recipe.yaml")
SYNTHETIC_LIST = CORE / "packages/demo_fixtures/screening_list_synthetic.yaml"
OFFICER = Principal(id="kyc-officer", clearance="OFFICIAL", org_unit="verify")
SECRET_LOADER = Principal(id="kyc-secret-loader", clearance="SECRET", org_unit="verify")
SHARED_PHONE = "447700900777"


def _application(name: str, **overrides: str) -> dict[str, str]:
    row = {
        "company_name": name, "country": "CY", "industry": "Ship management",
        "owner_company": "Aegean Fiduciary Trust", "owner_percent": "80",
        "phone": "", "document_title": "", "document_kind": "", "document_expires": "",
    }  # fmt: skip
    row.update(overrides)
    return row


@pytest.fixture
async def stores() -> AsyncIterator[dict[str, Any]]:
    dsn = PostgresConfig.from_env().dsn
    made = {
        "rules": await TypologyRuleStore.connect(dsn),
        "held": await HeldRowStore.connect(dsn, SCHEME),
        "alerts": await AlertStore.connect(dsn),
        "audit": await AuditWriter.connect(dsn),
        "screening": await ScreeningListStore.connect(dsn),
    }
    list_name, entries = parse_list(yaml.safe_load(SYNTHETIC_LIST.read_text()), use="local_development")
    await made["screening"].replace_list(list_name, entries)
    cfg = ValkeyConfig.from_env()
    made["valkey"] = Valkey(host=cfg.host, port=cfg.port, db=cfg.db)
    yield made
    for key in ("rules", "held", "alerts", "audit", "screening"):
        await made[key].close()
    await made["valkey"].aclose()


def _gate(stores: dict[str, Any], graph: Any, rules: list[Any], case: str, loader: Principal = OFFICER) -> RuleGate:
    con = duckdb.connect(":memory:")
    create_events_table(con)
    known = {OFFICER.id: OFFICER, SECRET_LOADER.id: SECRET_LOADER}

    async def principal_for_owner(owner_id: str) -> Principal | None:
        return known.get(owner_id)

    return RuleGate(
        rules=rules, investigation_id=case, graph=graph, analytics=AnalyticsDuckDBAdapter(con, SCHEME),
        scheme=SCHEME, alert_store=stores["alerts"], audit=stores["audit"], valkey=stores["valkey"],
        principal_for_owner=principal_for_owner, loader=loader, held_store=stores["held"],
        screening=stores["screening"], compute=ComputeRustworkxAdapter(),
    )  # fmt: skip


async def _onboard(graph: Any, gate: RuleGate, rows: list[dict[str, str]], *, loader: Principal = OFFICER,
                   recipe: Any = RECIPE) -> Any:  # fmt: skip
    load_id = new_id()
    report, events, _ = await load_with_rules(
        recipe, rows, loader, graph=graph, ontology=ONTOLOGY, load_id=load_id,
        investigation_scope=gate.investigation_id, source="applications.csv", rules=gate,
    )  # fmt: skip
    report.rule_notes.extend(await gate.post_commit(events, load_id=load_id, written=gate.last_written))
    return report


async def _alerts(stores: dict[str, Any], case: str, who: Principal = OFFICER) -> list[Any]:
    return [a for a in await stores["alerts"].list_authorized(who) if a.investigation_id == case]


def _rule(params: Any, trigger: str = "pre_commit") -> TypologyRuleInput:
    return TypologyRuleInput(name=params.typology, params=params, trigger=trigger)  # type: ignore[arg-type]


async def test_an_applicant_owned_through_a_trust_by_a_listed_person_is_stopped_at_the_gate(
    stores: dict[str, Any],
) -> None:
    case = f"case-{new_id()}"
    rule = await stores["rules"].create(OFFICER, case, _rule(KycScreeningParams()))
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await build_ledger_graph(graph=graph, ontology=ONTOLOGY, principal=OFFICER)
        report = await _onboard(graph, _gate(stores, graph, [rule], case), [_application("Halcyon Marine Ltd")])
        assert report.nodes_created >= 1 and report.rows_held == 0, "the applicant loads, with its alerts"
        alerts = await _alerts(stores, case)
        words = sorted(a.words for a in alerts)
        assert len(alerts) == 2, words
        assert any("ultimately owned 48% by Elena Petrov" in w and "PETROVA, Elena" in w for w in words)
        assert any("ultimately owned 32% by Priya Nair" in w and "politically exposed" in w for w in words)
        petrov_alert = next(a for a in alerts if "Petrov" in (a.words or ""))
        same_as = [e for e in await graph.edges_among(petrov_alert.referent_node_ids, OFFICER)
                   if e.type == "SAME_AS"]  # fmt: skip
        assert len(same_as) == 1
        assert same_as[0].provenance.state is ProvenanceState.INFERRED
        assert same_as[0].properties["score"] >= 0.9
        listed = await graph.get_node(same_as[0].target, OFFICER)
        assert listed is not None and listed.properties["listing"] == "sanction"


async def test_an_owner_below_the_threshold_is_not_screened(stores: dict[str, Any]) -> None:
    case = f"case-{new_id()}"
    rule = await stores["rules"].create(OFFICER, case, _rule(KycScreeningParams(owner_threshold=50)))
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await build_ledger_graph(graph=graph, ontology=ONTOLOGY, principal=OFFICER)
        await _onboard(graph, _gate(stores, graph, [rule], case), [_application("Halcyon Marine Ltd")])
        assert await _alerts(stores, case) == []


async def _customers_sharing(graph: Any, count: int) -> None:
    now = datetime.now(UTC)
    prov = Provenance(state=ProvenanceState.ASSERTED, first_seen=now,
                      sources=[SourceRef(document_id="t", locator="r", excerpt_hash="")])  # fmt: skip
    handling = Handling(classification="OFFICIAL", handling_code="P", originator="unit-fincrime", owning_unit="verify")
    phone = NodeWrite(id=new_node_id(), type="Endpoint", properties={"value_normalised": SHARED_PHONE,
                      "endpoint_kind": "msisdn"}, provenance=prov, handling=handling, created_by="t", created_at=now)  # fmt: skip
    people = [NodeWrite(id=new_node_id(), type="Person", properties={"family_name": f"Sharer{i}"},
                        provenance=prov, handling=handling, created_by="t", created_at=now) for i in range(count)]  # fmt: skip
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([phone, *people], tx)
    await graph.upsert_edges([EdgeWrite(id=new_edge_id(), type="USES", source=p.id, target=phone.id,
                                        provenance=prov, handling=handling, created_by="t", created_at=now)
                              for p in people], tx)  # fmt: skip
    await graph.commit_transaction(tx)


async def test_a_shared_phone_is_flagged_at_the_count(stores: dict[str, Any]) -> None:
    """Three customers already use the phone. The first applicant makes a fourth user: at a
    threshold of four others it is not flagged (three others). The second applicant then finds four
    others, the first applicant among them, and is flagged at the same threshold."""
    case = f"case-{new_id()}"
    rule = await stores["rules"].create(OFFICER, case, _rule(SharedAttributesParams(min_others=4)))
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await build_ledger_graph(graph=graph, ontology=ONTOLOGY, principal=OFFICER)
        await _customers_sharing(graph, 3)
        await _onboard(graph, _gate(stores, graph, [rule], case),
                       [_application("Seaborne Atlas Ltd", phone=SHARED_PHONE)])  # fmt: skip
        assert await _alerts(stores, case) == []
        await _onboard(graph, _gate(stores, graph, [rule], case),
                       [_application("Halcyon Marine Ltd", phone=SHARED_PHONE)])  # fmt: skip
        (alert,) = await _alerts(stores, case)
        assert alert.typology == "shared_attributes"
        assert "already used by 4 other customer(s)" in (alert.words or "")
        assert "Seaborne Atlas Ltd" in (alert.words or "")


async def test_an_expired_document_verifies_no_one(stores: dict[str, Any]) -> None:
    case = f"case-{new_id()}"
    rule = await stores["rules"].create(OFFICER, case, _rule(DocumentVerificationParams()))
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await build_ledger_graph(graph=graph, ontology=ONTOLOGY, principal=OFFICER)
        await _onboard(graph, _gate(stores, graph, [rule], case), [_application(
            "Halcyon Marine Ltd", document_title="Certificate of incorporation",
            document_kind="certificate_of_incorporation", document_expires="2025-01-31")])  # fmt: skip
        (alert,) = await _alerts(stores, case)
        assert "no valid verifying document: certificate of incorporation expired on 2025-01-31" in (alert.words or "")


async def test_a_valid_document_raises_nothing(stores: dict[str, Any]) -> None:
    case = f"case-{new_id()}"
    rule = await stores["rules"].create(OFFICER, case, _rule(DocumentVerificationParams()))
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await build_ledger_graph(graph=graph, ontology=ONTOLOGY, principal=OFFICER)
        await _onboard(graph, _gate(stores, graph, [rule], case), [_application(
            "Halcyon Marine Ltd", document_title="Certificate of incorporation",
            document_kind="certificate_of_incorporation", document_expires="2099-12-31")])  # fmt: skip
        assert await _alerts(stores, case) == []


async def test_a_customer_the_deployer_cannot_read_is_not_judged(stores: dict[str, Any]) -> None:
    case = f"case-{new_id()}"
    rule = await stores["rules"].create(OFFICER, case, _rule(DocumentVerificationParams()))
    defaults = RECIPE.defaults.model_copy(update={"handling": {**RECIPE.defaults.handling, "classification": "SECRET"}})
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await _onboard(graph, _gate(stores, graph, [rule], case, loader=SECRET_LOADER),
                       [_application("Secret Holdings Ltd", owner_company="")],
                       loader=SECRET_LOADER, recipe=RECIPE.model_copy(update={"defaults": defaults}))  # fmt: skip
        assert await _alerts(stores, case) == []
        assert await _alerts(stores, case, SECRET_LOADER) == []


async def test_the_gate_runs_after_commit_too(stores: dict[str, Any]) -> None:
    case = f"case-{new_id()}"
    rule = await stores["rules"].create(OFFICER, case, _rule(DocumentVerificationParams(), "post_commit"))
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await _onboard(graph, _gate(stores, graph, [rule], case), [_application("Halcyon Marine Ltd", owner_company="")])
        (alert,) = await _alerts(stores, case)
        assert alert.trigger == "post_commit" and "none on record" in (alert.words or "")


# --- the KYC status and baseline risk, computed at read ------------------------

from datetime import date  # noqa: E402

from services.api.kyc import assess  # noqa: E402


async def test_the_status_and_risk_are_computed_from_what_the_reader_sees(
    stores: dict[str, Any],
) -> None:
    """Halcyon onboarded with an expired certificate, a phone three others use, registered in
    Cyprus in ship management, owned through the trust by two listed people: unverified, and every
    factor named. Nothing is stored: the same read tomorrow could differ, and that is the point."""
    case = f"case-{new_id()}"
    rule = await stores["rules"].create(OFFICER, case, _rule(KycScreeningParams()))
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await build_ledger_graph(graph=graph, ontology=ONTOLOGY, principal=OFFICER)
        await _customers_sharing(graph, 3)
        await _onboard(graph, _gate(stores, graph, [rule], case), [_application(
            "Halcyon Marine Ltd", phone=SHARED_PHONE, document_title="Certificate of incorporation",
            document_kind="certificate_of_incorporation", document_expires="2025-01-31")])  # fmt: skip
        halcyon = await graph.find_node("Organisation", "name", "Halcyon Marine Ltd", OFFICER)
        assert halcyon is not None
        status = await assess(graph, ComputeRustworkxAdapter(), halcyon.id, OFFICER, today=date(2026, 10, 10))
        assert status.status == "unverified"
        assert [d.state for d in status.documents] == ["expired"]
        factors = sorted(f.factor for f in status.factors)
        assert factors == ["country_medium", "industry_medium", "owner_listed", "owner_listed",
                           "shared_attribute", "unverified"]  # fmt: skip
        assert status.risk_band == "high" and status.risk_score == 15 + 10 + 40 + 40 + 20 + 25

        # Before the certificate lapsed it verified Halcyon: the status is the date's, not stored.
        earlier = await assess(graph, ComputeRustworkxAdapter(), halcyon.id, OFFICER, today=date(2025, 1, 1))
        assert earlier.status == "verified"


async def test_a_document_the_reader_cannot_see_verifies_no_one_for_them(stores: dict[str, Any]) -> None:
    """A SECRET certificate verifies the customer for a SECRET reader; an OFFICIAL reader sees no
    document at all and reads the customer unverified — the graph they can see supports nothing
    more (rule 3), and nothing tells them a hidden document exists."""
    now = datetime.now(UTC)
    prov = Provenance(state=ProvenanceState.ASSERTED, first_seen=now,
                      sources=[SourceRef(document_id="t", locator="r", excerpt_hash="")])  # fmt: skip
    official = Handling(classification="OFFICIAL", handling_code="P", originator="verify", owning_unit="verify")
    secret = official.model_copy(update={"classification": "SECRET"})
    company = NodeWrite(id=new_node_id(), type="Organisation", properties={"name": "Quiet Ltd"},
                        provenance=prov, handling=official, created_by="t", created_at=now)  # fmt: skip
    certificate = NodeWrite(id=new_node_id(), type="Document", properties={
        "title": "Certificate", "document_kind": "certificate_of_incorporation", "expires_on": "2099-01-01"},
        provenance=prov, handling=secret, created_by="t", created_at=now)  # fmt: skip
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        tx = await graph.begin_transaction()
        await graph.upsert_nodes([company, certificate], tx)
        await graph.upsert_edges([EdgeWrite(id=new_edge_id(), type="VERIFIED_BY", source=company.id,
                                            target=certificate.id, provenance=prov, handling=secret,
                                            created_by="t", created_at=now)], tx)  # fmt: skip
        await graph.commit_transaction(tx)
        cleared = await assess(graph, ComputeRustworkxAdapter(), company.id, SECRET_LOADER, today=date(2026, 10, 10))
        seen = await assess(graph, ComputeRustworkxAdapter(), company.id, OFFICER, today=date(2026, 10, 10))
        assert (cleared.status, len(cleared.documents)) == ("verified", 1)
        assert (seen.status, seen.documents) == ("unverified", [])


# --- the daily sweep for lapsing documents (ruling 7) ----------------------------

from services.api.kyc_expiries import KycExpiryStore  # noqa: E402
from services.api.kyc_sweep import sweep  # noqa: E402


async def _swept(stores: dict[str, Any], graph: Any, expiries: KycExpiryStore, day: date) -> Any:
    known = {OFFICER.id: OFFICER}

    async def principal_for_owner(owner_id: str) -> Principal | None:
        return known.get(owner_id)

    return await sweep(
        day=day, expiries=expiries, rules=stores["rules"], graph=graph, scheme=SCHEME,
        alert_store=stores["alerts"], audit=stores["audit"], valkey=stores["valkey"],
        principal_for_owner=principal_for_owner, sweeper=OFFICER,
    )  # fmt: skip


async def test_a_document_that_lapses_is_caught_by_the_daily_sweep_once(stores: dict[str, Any]) -> None:
    """Valid when loaded (no alert then); the day after it lapses the sweep raises a review; a
    second sweep raises nothing more. A customer with a second, valid document is not raised."""
    await stores["valkey"].delete("kyc:sweep:last")
    expiries = await KycExpiryStore.connect(PostgresConfig.from_env().dsn)
    case = f"case-{new_id()}"
    rule = await stores["rules"].create(OFFICER, case, _rule(DocumentVerificationParams()))
    try:
        async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
            gate = _gate(stores, graph, [rule], case)
            gate.expiries = expiries
            lapsing = "2026-10-12"
            await _onboard(graph, gate, [
                _application("Halcyon Marine Ltd", owner_company="", document_title="Passport",
                             document_kind="passport", document_expires=lapsing),
                _application("Steady Freight Ltd", owner_company="", document_title="Register extract",
                             document_kind="register_extract", document_expires=lapsing),
            ])  # fmt: skip
            # Steady Freight also holds a document valid long after.
            steady = await graph.find_node("Organisation", "name", "Steady Freight Ltd", OFFICER)
            assert steady is not None
            await _onboard(graph, gate, [_application("Steady Freight Ltd", owner_company="",
                           document_title="Certificate", document_kind="certificate_of_incorporation",
                           document_expires="2099-01-01")])  # fmt: skip
            assert await _alerts(stores, case) == [], "both verified when loaded"

            before = await _swept(stores, graph, expiries, date(2026, 10, 12))
            assert before.alerts == 0, "not lapsed until after the 12th"
            after = await _swept(stores, graph, expiries, date(2026, 10, 13))
            assert after.alerts == 1
            (alert,) = await _alerts(stores, case)
            assert "Halcyon Marine Ltd is no longer verified: passport expired on 2026-10-12" in (alert.words or "")
            again = await _swept(stores, graph, expiries, date(2026, 10, 14))
            assert again.alerts == 0 and len(await _alerts(stores, case)) == 1
    finally:
        await expiries.close()
        await stores["valkey"].delete("kyc:sweep:last")


async def test_the_gate_the_routes_build_carries_what_the_kyc_and_pattern_rules_read() -> None:
    """Every case above builds its `RuleGate` by hand, so none could see the run and release routes'
    own factory drop the screening list: found live, 11 October 2026 — the onboarding pipeline's
    every row held, "this deployment has no screening list store", in a deployment that has one."""
    from services.api.app import _rule_gate

    class OneRule:
        async def list_active_for_case(self, _case: str) -> list[object]:
            return [object()]

    screening, compute, expiries, patterns = object(), object(), object(), object()
    gate = await _rule_gate(
        "case", loader=OFFICER, graph=object(), analytics=object(), scheme=SCHEME,
        typology_rules=OneRule(), held_rows=object(), alerts_store=object(), audit=object(),
        valkey=object(), principal_resolver=object(), screening=screening, compute=compute,
        expiries=expiries, patterns=patterns,
    )  # type: ignore[arg-type]  # fmt: skip
    assert gate is not None
    assert (gate.screening, gate.compute, gate.expiries, gate.patterns) == (screening, compute, expiries, patterns)
