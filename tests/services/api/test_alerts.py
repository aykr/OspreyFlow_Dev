"""`services/api/alerts.py` — `06_DECISIONS.md` ADR-038/039. Real Postgres (the
alert store, the audit log) and real ArcadeDB (the referent recheck) — access control and
"revoked access" are exactly the class of claim a fake cannot stand in for.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import asyncpg
import pytest
from services.api.alerts import (
    AlertNotFoundError,
    AlertStore,
    disclosure_policy_from_value,
    evidence_available,
    record_match,
)
from services.api.audit import AuditWriter
from services.api.config import PostgresConfig

from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Handling, NodeWrite, Principal, Provenance, ProvenanceState, SourceRef

OWNER = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
OTHER_ANALYST = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-1")


@pytest.fixture
async def alert_store():
    s = await AlertStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


@pytest.fixture
async def audit():
    w = await AuditWriter.connect(PostgresConfig.from_env().dsn)
    yield w
    await w.close()


def _node_write(*, owning_unit: str, classification: str = "OFFICIAL") -> NodeWrite:
    now = datetime.now(UTC)
    return NodeWrite(
        id=new_id(),
        type="Person",
        properties={
            "family_name": "Alertfixture",
            "given_names": "A",
            "date_of_birth": "1990-01-01",
        },
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="fixture", locator="test", excerpt_hash="")],
            first_seen=now,
        ),
        handling=Handling(
            classification=classification,
            handling_code="P",
            originator=owning_unit,
            owning_unit=owning_unit,
        ),
        created_by="test",
        created_at=now,
    )


# --- disclosure_policy_from_value — pure, unit-tested directly -----------------------------------


def test_hotlist_policy_defaults_to_strict_when_deployment_config_is_unset() -> None:
    """`06_DECISIONS.md` ADR-038's own named test: an unset, empty or unrecognised configuration
    value all behave as `strict` — checked as three separate cases, not one representative one."""
    assert disclosure_policy_from_value(None) == "strict"
    assert disclosure_policy_from_value("") == "strict"
    assert disclosure_policy_from_value("not-a-real-mode") == "strict"
    assert disclosure_policy_from_value("Notify") == "strict"  # case-sensitive, not guessed at
    assert disclosure_policy_from_value("notify") == "notify"


# --- record_match / evidence_available — real Postgres + real ArcadeDB ---------------------------


async def test_a_visible_match_writes_a_full_alert_with_its_referent(alert_store, audit) -> None:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes([_node_write(owning_unit=OWNER.org_unit)], tx)
        await graph.commit_transaction(tx)

        alert = await record_match(
            graph=graph,
            alert_store=alert_store,
            audit=audit,
            recipient=OWNER,
            rule_id="rule-1",
            matched_identifier="+44-fixture",
            triggering_node_ids=[node_id],
            policy="strict",
        )
        assert alert is not None
        assert alert.mode.value == "full"
        assert alert.referent_node_ids == [node_id]
        assert await evidence_available(alert, OWNER, graph) is True


async def test_alert_evidence_is_unreadable_after_referent_access_is_revoked(
    alert_store, audit
) -> None:
    """`06_DECISIONS.md` ADR-039's own named test: write an alert referencing a node visible to
    the owner; revoke that access (a handling change — the only way a node's own handling changes
    in this system is `supersede_node`, `01_DOMAIN_MODEL.md` §2.4); read the alert's evidence
    again; assert it is no longer available."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes([_node_write(owning_unit=OWNER.org_unit)], tx)
        await graph.commit_transaction(tx)

        alert = await record_match(
            graph=graph,
            alert_store=alert_store,
            audit=audit,
            recipient=OWNER,
            rule_id="rule-1",
            matched_identifier="+44-fixture",
            triggering_node_ids=[node_id],
            policy="strict",
        )
        assert alert is not None
        assert await evidence_available(alert, OWNER, graph) is True

        # Revoke: supersede the node with a replacement OWNER can no longer see — a different
        # owning_unit AND a classification above OWNER's own clearance, so no path back for them.
        tx = await graph.begin_transaction()
        await graph.supersede_node(
            node_id, _node_write(owning_unit="unit-2", classification="SECRET"), tx
        )
        await graph.commit_transaction(tx)

        assert await evidence_available(alert, OWNER, graph) is False


async def test_revoked_alert_remains_listed_as_unavailable_not_removed(alert_store, audit) -> None:
    """Addition 2 to `06_DECISIONS.md` ADR-039: the alert's own row stays visible, marked
    unavailable via `evidence_available`, rather than vanishing from the owner's own store —
    `get_authorized`/`list_authorized` must still return it after the referent is revoked."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes([_node_write(owning_unit=OWNER.org_unit)], tx)
        await graph.commit_transaction(tx)

        alert = await record_match(
            graph=graph,
            alert_store=alert_store,
            audit=audit,
            recipient=OWNER,
            rule_id="rule-1",
            matched_identifier="+44-fixture",
            triggering_node_ids=[node_id],
            policy="strict",
        )
        assert alert is not None

        tx = await graph.begin_transaction()
        await graph.supersede_node(
            node_id, _node_write(owning_unit="unit-2", classification="SECRET"), tx
        )
        await graph.commit_transaction(tx)

        # The row itself: not gone, not raising — a direct read still succeeds.
        reread = await alert_store.get_authorized(alert.id, OWNER)
        assert reread.id == alert.id
        assert await evidence_available(reread, OWNER, graph) is False

        listed = await alert_store.list_authorized(OWNER)
        assert any(a.id == alert.id for a in listed)


async def test_a_suppressed_strict_match_writes_no_alert_row(alert_store, audit) -> None:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes(
            [_node_write(owning_unit="unit-2", classification="SECRET")], tx
        )
        await graph.commit_transaction(tx)

        alert = await record_match(
            graph=graph,
            alert_store=alert_store,
            audit=audit,
            recipient=OWNER,
            rule_id="rule-1",
            matched_identifier="+44-fixture",
            triggering_node_ids=[node_id],
            policy="strict",
        )
        assert alert is None


async def test_notify_mode_alert_contains_no_referent_its_recipient_cannot_read(
    alert_store, audit
) -> None:
    """`06_DECISIONS.md` ADR-038's own named test, written against the alert as it would be
    serialised to the client (`.model_dump()`), not against an internal Python object — the same
    instruction the task gives for exactly this test, because a check against an attribute that
    happens to be empty today does not catch a future evidence panel reconstructing content a
    different way."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes(
            [_node_write(owning_unit="unit-2", classification="SECRET")], tx
        )
        await graph.commit_transaction(tx)

        alert = await record_match(
            graph=graph,
            alert_store=alert_store,
            audit=audit,
            recipient=OWNER,
            rule_id="rule-1",
            matched_identifier="+44-do-not-leak",
            triggering_node_ids=[node_id],
            policy="notify",
        )
        assert alert is not None

        serialised = alert.model_dump(mode="json")
        assert serialised["referent_node_ids"] == []
        assert node_id not in str(serialised)
        assert "+44-do-not-leak" not in str(serialised)

        # And the same check again after a fresh read back through the store — not merely the
        # in-memory object `record_match` happened to return.
        reread = await alert_store.get_authorized(alert.id, OWNER)
        reread_serialised = reread.model_dump(mode="json")
        assert reread_serialised["referent_node_ids"] == []
        assert node_id not in str(reread_serialised)
        assert "+44-do-not-leak" not in str(reread_serialised)


async def test_suppressed_and_notify_matches_both_write_an_audit_record_with_principal_and_mode(
    alert_store, audit
) -> None:
    """`06_DECISIONS.md` ADR-038's own named test: both modes are audited, not only `notify` —
    without this a customer's security function cannot be shown what the system did on their
    behalf in the mode that produces no visible alert at all."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    pool = await asyncpg.create_pool(dsn=PostgresConfig.from_env().dsn)
    try:
        async with arcadedb_adapter(ontology, scheme) as graph:
            tx = await graph.begin_transaction()
            (node_id,) = await graph.upsert_nodes(
                [_node_write(owning_unit="unit-2", classification="SECRET")], tx
            )
            await graph.commit_transaction(tx)

            for mode in ("strict", "notify"):
                identifier = f"+44-audit-{mode}"
                await record_match(
                    graph=graph,
                    alert_store=alert_store,
                    audit=audit,
                    recipient=OWNER,
                    rule_id="rule-1",
                    matched_identifier=identifier,
                    triggering_node_ids=[node_id],
                    policy=mode,  # type: ignore[arg-type]
                )
                async with pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT principal_id, resolved_query FROM audit_log "
                        "WHERE principal_id = $1 AND resolved_query->>'identifier' = $2",
                        OWNER.id,
                        identifier,
                    )
                assert row is not None, f"no audit record written for mode={mode}"
                assert row["principal_id"] == OWNER.id
                resolved = json.loads(row["resolved_query"])
                assert resolved["identifier"] == identifier
                assert resolved["mode"] == mode
    finally:
        await pool.close()


# --- AlertStore.get_authorized — existence-leak discipline, in-query from the start -------------


async def test_a_missing_alert_id_raises_not_found(alert_store) -> None:
    with pytest.raises(AlertNotFoundError):
        await alert_store.get_authorized("no-such-alert", OWNER)


async def test_an_alert_owned_by_a_different_analyst_is_not_found_not_forbidden(
    alert_store, audit
) -> None:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes([_node_write(owning_unit=OWNER.org_unit)], tx)
        await graph.commit_transaction(tx)

        alert = await record_match(
            graph=graph,
            alert_store=alert_store,
            audit=audit,
            recipient=OWNER,
            rule_id="rule-1",
            matched_identifier="+44-fixture",
            triggering_node_ids=[node_id],
            policy="strict",
        )
        assert alert is not None
        with pytest.raises(AlertNotFoundError):
            await alert_store.get_authorized(alert.id, OTHER_ANALYST)


async def test_list_never_returns_another_analysts_alert(alert_store, audit) -> None:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes([_node_write(owning_unit=OWNER.org_unit)], tx)
        await graph.commit_transaction(tx)

        await record_match(
            graph=graph,
            alert_store=alert_store,
            audit=audit,
            recipient=OWNER,
            rule_id="rule-1",
            matched_identifier="+44-fixture",
            triggering_node_ids=[node_id],
            policy="strict",
        )
        listed = await alert_store.list_authorized(OTHER_ANALYST)
        assert listed == [] or all(a.owner_id != OWNER.id for a in listed)
