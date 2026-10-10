"""Typology rules on the load path (`spec/06_DECISIONS.md` ADR-109 phase A), against live Postgres
(rules, held rows, alerts, audit), Valkey (finding signatures), MinIO (the engine's staging) and
ArcadeDB (the graph), with the real DuckDB analytics adapter — no fake stands in for a store whose
refusals matter (`CLAUDE.md` rule 15).

What a mistake would do, and the case that catches it:

- a pre-commit hit loaded without its alert, or its alert node written outside the load
  (`test_a_pre_commit_hit_loads_with_its_alert_node_and_queue_row`), and a rule that should not
  fire, firing (`test_a_pre_commit_rule_that_should_not_fire_raises_nothing`);
- a failing pre-commit rule letting rows through unjudged (ruling 1, fail closed)
  (`test_a_failing_pre_commit_rule_holds_its_rows_out_of_the_graph`), and a release that loses a
  held row's provenance (`test_a_released_row_loads_with_its_original_row_number`);
- a rule firing on an event its deployer cannot read, so its alert discloses it (rule 3)
  (`test_a_rule_never_fires_on_events_its_deployer_cannot_read`);
- an alert node readable by someone who cannot read what it references (rule 3)
  (`test_an_alert_node_is_marked_no_lower_than_its_referents`);
- a post-commit rule alerting the same finding twice on an idempotent re-run
  (`test_a_post_commit_rule_alerts_once_per_finding`);
- held rows, rules or audit entries readable outside their case, marking or dataset (rule 4)
  (`test_held_rows_are_read_only_at_or_below_the_readers_marking`,
  `test_a_decision_naming_a_row_the_reviewer_cannot_see_decides_nothing`,
  `test_rules_are_read_only_within_their_case_and_reach`,
  `test_a_rule_audit_entry_naming_a_hidden_node_is_withheld_from_page_and_total`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import duckdb
import pytest
from services.api.alerts import AlertStore
from services.api.audit import AuditWriter
from services.api.config import PostgresConfig, ValkeyConfig
from services.api.held_rows import HeldRowNotFoundError, HeldRowStore
from services.api.rule_evaluation import RuleGate
from services.api.rule_holds import readable_rule_audit, release_held_rows
from services.api.studio_publish import load_with_rules
from services.api.typology_rules import TypologyRuleNotFoundError, TypologyRuleStore
from services.ingest.recipe_loader import load_recipe
from valkey.asyncio import Valkey

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table
from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from ports.analytics import AnalyticsPort
from schemas.domain import (
    Handling,
    HeldRow,
    Principal,
    ProvenanceState,
    RapidMovementParams,
    StructuringParams,
    TypologyRule,
    TypologyRuleInput,
)
from schemas.ingest import Recipe

SCHEME = load_uk_le_scheme()
ONTOLOGY = load_deployment_ontology()
RECIPE = load_recipe(
    __import__("pathlib").Path(__file__).resolve().parents[3]
    / "OspreyFlow_Core/packages/demo_fixtures/ledger_transactions_recipe.yaml"
)
T0 = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)

ANALYST = Principal(id="analyst-rules", clearance="OFFICIAL", org_unit="verify")
SECRET_LOADER = Principal(id="loader-secret", clearance="SECRET", org_unit="verify")


def _row(payer: str, payee: str, amount: float, at: datetime) -> dict[str, str]:
    return {
        "payer_iban": payer,
        "payee_iban": payee,
        "amount": str(amount),
        "at": at.isoformat().replace("+00:00", "Z"),
        "transaction_type": "TRANSFER",
    }


def _deposits(tag: str, count: int = 4) -> list[dict[str, str]]:
    """Sub-threshold deposits from a mule to a hub, six hours apart — structuring."""
    return [
        _row(f"GB{tag}MULE", f"GB{tag}HUB", 9_500, T0 + timedelta(hours=6 * i))
        for i in range(count)
    ]


def _structuring(trigger: str, *, minimum_count: int = 3) -> TypologyRuleInput:
    return TypologyRuleInput(
        name=f"Structuring ({trigger})",
        params=StructuringParams(threshold=10_000, window_days=7, minimum_count=minimum_count),
        trigger=trigger,  # type: ignore[arg-type]
    )


def _marked(recipe: Recipe, classification: str) -> Recipe:
    defaults = recipe.defaults.model_copy(
        update={"handling": {**recipe.defaults.handling, "classification": classification}}
    )
    return recipe.model_copy(update={"defaults": defaults})


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
async def stores() -> AsyncIterator[dict[str, Any]]:
    dsn = PostgresConfig.from_env().dsn
    rules = await TypologyRuleStore.connect(dsn)
    held = await HeldRowStore.connect(dsn, SCHEME)
    alerts = await AlertStore.connect(dsn)
    audit = await AuditWriter.connect(dsn)
    cfg = ValkeyConfig.from_env()
    valkey = Valkey(host=cfg.host, port=cfg.port, db=cfg.db)
    yield {"rules": rules, "held": held, "alerts": alerts, "audit": audit, "valkey": valkey}
    for store in (rules, held, alerts, audit):
        await store.close()
    await valkey.aclose()


@pytest.fixture
def analytics() -> AnalyticsPort:
    con = duckdb.connect(":memory:")
    create_events_table(con)
    return AnalyticsDuckDBAdapter(con, SCHEME)


class _Outage:
    """The analytics store refusing every read — an outage, the dependency's own refusal."""

    async def list_events(self, req: Any, principal: Any) -> Any:
        raise ConnectionError("analytics store unreachable")


def _gate(
    stores: dict[str, Any],
    graph: Any,
    analytics: Any,
    rules: list[TypologyRule],
    case: str,
    *,
    loader: Principal = ANALYST,
    owners: dict[str, Principal] | None = None,
    fail_closed: bool = True,
) -> RuleGate:
    known = {ANALYST.id: ANALYST, SECRET_LOADER.id: SECRET_LOADER, **(owners or {})}

    async def principal_for_owner(owner_id: str) -> Principal | None:
        return known.get(owner_id)

    return RuleGate(
        rules=rules,
        investigation_id=case,
        graph=graph,
        analytics=analytics,
        scheme=SCHEME,
        alert_store=stores["alerts"],
        audit=stores["audit"],
        valkey=stores["valkey"],
        principal_for_owner=principal_for_owner,
        loader=loader,
        held_store=stores["held"],
        fail_closed=fail_closed,
    )


async def _load(
    graph: Any,
    analytics: AnalyticsPort,
    gate: RuleGate,
    rows: list[dict[str, str]],
    *,
    recipe: Recipe = RECIPE,
    loader: Principal = ANALYST,
    load_id: str | None = None,
) -> Any:
    load_id = load_id or new_id()
    report, events, _held = await load_with_rules(
        recipe,
        rows,
        loader,
        graph=graph,
        ontology=ONTOLOGY,
        load_id=load_id,
        investigation_scope=gate.investigation_id,
        source="transactions.csv",
        rules=gate,
    )
    if events:
        await analytics.load_events(events)
    report.rule_notes.extend(await gate.post_commit(events, load_id=load_id))
    return report


async def _case_alerts(stores: dict[str, Any], owner: Principal, case: str) -> list[Any]:
    return [a for a in await stores["alerts"].list_authorized(owner) if a.investigation_id == case]


# --- pre-commit -------------------------------------------------------------


async def test_a_pre_commit_hit_loads_with_its_alert_node_and_queue_row(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    case = f"case-{new_id()}"
    rule = await stores["rules"].create(ANALYST, case, _structuring("pre_commit"))
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        report = await _load(graph, analytics, _gate(stores, graph, analytics, [rule], case),
                             _deposits("A"))  # fmt: skip

        assert report.edges_created == 1 and report.rows_held == 0
        assert any("raised 1 alert" in n for n in report.rule_notes)
        (alert,) = await _case_alerts(stores, ANALYST, case)
        assert (alert.typology, alert.trigger) == ("structuring", "pre_commit")
        assert len(alert.event_ids) == 4 and len(alert.referent_node_ids) == 2
        assert alert.alert_node_id is not None

        node = await graph.get_node(alert.alert_node_id, ANALYST)
        assert node is not None and node.type == "Alert"
        assert node.provenance.state is ProvenanceState.INFERRED
        assert node.provenance.extracted_by == f"rule:{rule.id}"
        # The node was written by this load: it carries the load's id, so reverting the load
        # reverts the alert with it.
        neighbours = await graph.expand(
            __import__("schemas.domain", fromlist=["ExpandRequest"]).ExpandRequest(
                node_ids=[alert.alert_node_id], edge_types=["ALERTED_ON"], limit=10
            ),
            ANALYST,
        )
        assert {n.id for n in neighbours.nodes} >= set(alert.referent_node_ids)


async def test_a_pre_commit_rule_that_should_not_fire_raises_nothing(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    case = f"case-{new_id()}"
    rule = await stores["rules"].create(ANALYST, case, _structuring("pre_commit", minimum_count=5))
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        report = await _load(graph, analytics, _gate(stores, graph, analytics, [rule], case),
                             _deposits("B"))  # fmt: skip
        assert report.edges_created == 1 and report.rows_held == 0
        assert await _case_alerts(stores, ANALYST, case) == []


async def test_a_failing_pre_commit_rule_holds_its_rows_out_of_the_graph(
    stores: dict[str, Any],
) -> None:
    case = f"case-{new_id()}"
    rule = await stores["rules"].create(ANALYST, case, _structuring("pre_commit"))
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        gate = _gate(stores, graph, _Outage(), [rule], case)
        report = await _load(graph, _Outage(), gate, _deposits("C"))  # type: ignore[arg-type]

        assert report.rows_held == 4
        assert report.edges_created == 0 and report.nodes_created == 0, "nothing judged, loaded"
        assert any("held for review" in n for n in report.rule_notes)
        held = await stores["held"].list_authorized(case, ANALYST)
        assert sorted(h.row_index for h in held) == [0, 1, 2, 3]
        assert all(h.rule_id == rule.id and "failed" in h.reason for h in held)
        assert held[0].row["payer_iban"] == "GBCMULE"


async def test_a_released_row_loads_with_its_original_row_number(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    case = f"case-{new_id()}"
    rule = await stores["rules"].create(ANALYST, case, _structuring("pre_commit"))
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        rows = [_row("GBDX", "GBDY", 500, T0), *_deposits("D", 2)]
        await _load(graph, _Outage(), _gate(stores, graph, _Outage(), [rule], case), rows)  # type: ignore[arg-type]
        held = await stores["held"].list_authorized(case, ANALYST)
        later = [h for h in held if h.row_index == 2]

        report = await release_held_rows(
            later, RECIPE, ANALYST, graph=graph, ontology=ONTOLOGY, analytics=analytics,
            media=None, rules=_gate(stores, graph, analytics, [rule], case, fail_closed=False),
            load_id=new_id(),
        )  # fmt: skip
        assert report.edges_created == 1 and report.rows_held == 0
        (edge_id,) = report.touched_edge_ids
        events = await analytics.list_events(
            __import__("schemas.analytics", fromlist=["EventListRequest"]).EventListRequest(
                filter=__import__("schemas.analytics", fromlist=["EventFilter"]).EventFilter(
                    investigation_scope=case, edge_ids=[edge_id]
                )
            ),
            ANALYST,
        )
        assert [e.properties["source_rows"] for e in events.events] == [[2]]


async def test_a_rule_never_fires_on_events_its_deployer_cannot_read(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    case = f"case-{new_id()}"
    rule = await stores["rules"].create(ANALYST, case, _structuring("pre_commit"))
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        gate = _gate(stores, graph, analytics, [rule], case, loader=SECRET_LOADER)
        report = await _load(graph, analytics, gate, _deposits("E"),
                             recipe=_marked(RECIPE, "SECRET"), loader=SECRET_LOADER)  # fmt: skip
        assert report.edges_created == 1
        assert await _case_alerts(stores, ANALYST, case) == []
        assert await _case_alerts(stores, SECRET_LOADER, case) == []


async def test_an_alert_node_is_marked_no_lower_than_its_referents(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    case = f"case-{new_id()}"
    rule = await stores["rules"].create(SECRET_LOADER, case, _structuring("pre_commit"))
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        gate = _gate(stores, graph, analytics, [rule], case, loader=SECRET_LOADER)
        await _load(graph, analytics, gate, _deposits("F"),
                    recipe=_marked(RECIPE, "SECRET"), loader=SECRET_LOADER)  # fmt: skip
        (alert,) = await _case_alerts(stores, SECRET_LOADER, case)
        assert alert.alert_node_id is not None
        node = await graph.get_node(alert.alert_node_id, SECRET_LOADER)
        assert node is not None and node.handling.classification == "SECRET"
        assert await graph.get_node(alert.alert_node_id, ANALYST) is None


# --- post-commit ------------------------------------------------------------


async def test_a_post_commit_rule_alerts_once_per_finding(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    case = f"case-{new_id()}"
    rule = await stores["rules"].create(
        ANALYST,
        case,
        TypologyRuleInput(
            name="Pass-through",
            params=RapidMovementParams(within_hours=24, keep_fraction=0.8),
            trigger="post_commit",
        ),
    )
    rows = [
        _row("GBGPAYER", "GBGCONDUIT", 50_000, T0),
        _row("GBGCONDUIT", "GBGOFFSHORE", 48_000, T0 + timedelta(hours=3)),
    ]
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        first = await _load(graph, analytics, _gate(stores, graph, analytics, [rule], case), rows)
        assert any("raised 1 alert" in n for n in first.rule_notes)
        (alert,) = await _case_alerts(stores, ANALYST, case)
        assert (alert.typology, alert.trigger) == ("rapid_movement", "post_commit")
        assert alert.alert_node_id is not None

        # The same export again: the dedupe key makes the load idempotent, and the finding is
        # the one already alerted.
        await _load(graph, analytics, _gate(stores, graph, analytics, [rule], case), rows)
        assert len(await _case_alerts(stores, ANALYST, case)) == 1


# --- reads and their access (rule 4) ----------------------------------------


def _held(case: str, classification: str, code: str = "P", unit: str = "verify") -> HeldRow:
    return HeldRow(
        id=new_id(), investigation_id=case, recipe_id="r", recipe_version=1, load_id="l",
        source="s", row_index=0, row={"a": "1"}, rule_id="rule", reason="test",
        handling=Handling(classification=classification, handling_code=code, originator=unit,
                          owning_unit=unit),
        held_at=datetime.now(UTC),
    )  # fmt: skip


async def test_held_rows_are_read_only_at_or_below_the_readers_marking(
    stores: dict[str, Any],
) -> None:
    case = f"case-{new_id()}"
    official, secret, restricted = (
        _held(case, "OFFICIAL"),
        _held(case, "SECRET"),
        _held(case, "OFFICIAL", code="R", unit="other-unit"),
    )
    await stores["held"].hold([official, secret, restricted])

    assert [h.id for h in await stores["held"].list_authorized(case, ANALYST)] == [official.id]
    assert {h.id for h in await stores["held"].list_authorized(case, SECRET_LOADER)} == {
        official.id,
        secret.id,
    }
    with pytest.raises(HeldRowNotFoundError):
        await stores["held"].get_authorized(secret.id, case, ANALYST)
    with pytest.raises(HeldRowNotFoundError):
        await stores["held"].get_authorized(official.id, "another-case", ANALYST)
    receiver = ANALYST.model_copy(update={"org_unit": "other-unit", "receivable_handling_codes": ["R"]})
    assert restricted.id in {h.id for h in await stores["held"].list_authorized(case, receiver)}


async def test_a_decision_naming_a_row_the_reviewer_cannot_see_decides_nothing(
    stores: dict[str, Any],
) -> None:
    case = f"case-{new_id()}"
    official, secret = _held(case, "OFFICIAL"), _held(case, "SECRET")
    await stores["held"].hold([official, secret])
    with pytest.raises(HeldRowNotFoundError):
        await stores["held"].decide_for_reader(
            [official.id, secret.id], case, ANALYST, status="rejected", reason="no"
        )
    (still,) = await stores["held"].list_authorized(case, ANALYST)
    assert still.id == official.id and still.status == "held"


async def test_rules_are_read_only_within_their_case_and_reach(stores: dict[str, Any]) -> None:
    case = f"case-{new_id()}"
    in_set = ANALYST.model_copy(update={"datasets": ["ds-1"]})
    rule = await stores["rules"].create(in_set, case, _structuring("post_commit"))
    assert rule.dataset_id == "ds-1"
    assert [r.id for r in await stores["rules"].list_for_case(case, in_set)] == [rule.id]
    assert await stores["rules"].list_for_case("another-case", in_set) == []
    elsewhere = ANALYST.model_copy(update={"datasets": ["ds-2"]})
    assert await stores["rules"].list_for_case(case, elsewhere) == []
    with pytest.raises(TypologyRuleNotFoundError):
        await stores["rules"].retire(rule.id, case, elsewhere)
    retired = await stores["rules"].retire(rule.id, case, in_set)
    assert retired.status == "retired"
    assert await stores["rules"].list_active_for_case(case) == []
    with pytest.raises(TypologyRuleNotFoundError):
        await stores["rules"].retire(rule.id, case, in_set)


async def test_a_rule_audit_entry_naming_a_hidden_node_is_withheld_from_page_and_total(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    case = f"case-{new_id()}"
    open_rule = await stores["rules"].create(ANALYST, case, _structuring("pre_commit"))
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await _load(graph, analytics, _gate(stores, graph, analytics, [open_rule], case),
                    _deposits("H"))  # fmt: skip
        secret_rule = await stores["rules"].create(SECRET_LOADER, case, _structuring("pre_commit"))
        await _load(graph, analytics,
                    _gate(stores, graph, analytics, [secret_rule], case, loader=SECRET_LOADER),
                    _deposits("J"), recipe=_marked(RECIPE, "SECRET"),
                    loader=SECRET_LOADER)  # fmt: skip

        seen_by_secret = await readable_rule_audit(stores["audit"], graph, case, SECRET_LOADER)
        seen_by_official = await readable_rule_audit(stores["audit"], graph, case, ANALYST)
        fired = [e for e in seen_by_secret.entries if e.action == "rule_fired"]
        assert len(fired) == 2
        assert [e.detail["rule_id"] for e in seen_by_official.entries
                if e.action == "rule_fired"] == [open_rule.id]  # fmt: skip
        assert seen_by_official.total == seen_by_secret.total - 1


async def test_an_alert_on_official_flows_into_a_secret_account_is_secret(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """The flows are OFFICIAL, one account they touch is SECRET: the alert must be SECRET, or an
    OFFICIAL reader learns through it that the SECRET account exists (rule 3)."""
    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        quiet = _gate(stores, graph, analytics, [], case, loader=SECRET_LOADER)
        await _load(graph, analytics, quiet, [_row("GBKHUB", "GBKELSEWHERE", 10, T0 - timedelta(days=30))],
                    recipe=_marked(RECIPE, "SECRET"), loader=SECRET_LOADER)  # fmt: skip
        rule = await stores["rules"].create(SECRET_LOADER, case, _structuring("pre_commit"))
        rows = [_row("GBKMULE", "GBKHUB", 9_500, T0 + timedelta(hours=6 * i)) for i in range(4)]
        await _load(graph, analytics,
                    _gate(stores, graph, analytics, [rule], case, loader=SECRET_LOADER), rows,
                    loader=SECRET_LOADER)  # fmt: skip
        (alert,) = await _case_alerts(stores, SECRET_LOADER, case)
        assert alert.alert_node_id is not None
        node = await graph.get_node(alert.alert_node_id, SECRET_LOADER)
        assert node is not None and node.handling.classification == "SECRET"
        assert await graph.get_node(alert.alert_node_id, ANALYST) is None
