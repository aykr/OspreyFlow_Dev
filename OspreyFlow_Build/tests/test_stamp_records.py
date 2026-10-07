"""`scripts.stamp_datasets.place_records` against real Postgres (ADR-099 Amendment 3 part (e)):
what a deployment held before the amendment is placed in a dataset where its case is recorded, and
counted, never guessed, where it is not.

What a mistake here would do, and the case that catches it: a proposal or an alert left in no
dataset would be offered or shown in every case of its owner (`test_a_proposal_and_an_alert_take_
their_cases_dataset`); one placed in a dataset its case does not read would vanish from the case
that made it (the same test, against the case's first dataset); a record with no case placed by a
guess would land in the wrong dataset (`test_what_records_no_case_is_counted_not_guessed`); a dry
run that writes, or a second run that moves anything (the last two)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import asyncpg
import pytest
from scripts.stamp_datasets import place_records
from services.api.alerts import AlertStore
from services.api.config import PostgresConfig
from services.api.datasets import Dataset, PostgresDatasetStore
from services.api.hotlists import HotlistStore
from services.api.link_type_store import LinkTypeProposalStore
from services.api.link_types import LinkTypeProposal
from services.api.monitors import MonitorStore
from services.api.pattern_store import PatternStore
from services.api.studio_recipes import StudioRecipeStore

from conduit_common.identity import new_id
from schemas.domain import Alert, AlertMode, PatternQuery, Principal

NOW = datetime(2026, 10, 1, tzinfo=UTC)


@pytest.fixture
async def setup():  # type: ignore[no-untyped-def]
    dsn = PostgresConfig.from_env().dsn
    stores = [
        await PostgresDatasetStore.connect(dsn),
        await LinkTypeProposalStore.connect(dsn),
        await AlertStore.connect(dsn),
        await PatternStore.connect(dsn),
        await HotlistStore.connect(dsn),
        await MonitorStore.connect(dsn),
        await StudioRecipeStore.connect(dsn),
    ]
    unit = f"unit-{new_id()}"
    owner = Principal(id=f"analyst-{new_id()}", clearance="OFFICIAL", org_unit=unit)
    datasets, proposals, alerts, patterns, hotlists = stores[:5]
    for dataset_id in ("fixture-corp", "enron"):
        await datasets.register(
            Dataset(
                id=f"{dataset_id}-{unit}",
                name=dataset_id,
                owning_unit=unit,
                created_at=NOW,
                created_by="t",
            )
        )
    case = new_id()
    await datasets.set_for_case(case, [f"fixture-corp-{unit}", f"enron-{unit}"], owner)
    proposal = LinkTypeProposal(
        id=new_id(),
        name="KNOWN_TO",
        from_types=["Person"],
        to_types=["Person"],
        directed=False,
        investigation_id=case,
        owning_unit=unit,
        proposed_by=owner.id,
        proposed_at=NOW,
        reason="x",
    )
    await proposals.create(proposal)
    alert = Alert(
        id=new_id(),
        rule_id="hotlist:h",
        owner_id=owner.id,
        mode=AlertMode.FULL,
        referent_node_ids=["n"],
        investigation_id=case,
        created_at=NOW,
    )
    await alerts.save(alert)
    pattern = await patterns.save(
        owner, pattern_id=None, name="p", definition=PatternQuery(nodes=[], edges=[])
    )
    hotlist = await hotlists.create(owner, identifier="+44", review_date=date(2027, 1, 1))
    conn = await asyncpg.connect(dsn)
    yield conn, unit, proposal, alert, pattern, hotlist
    await conn.close()
    for store in stores:
        await store.close()


async def _dataset(conn, table: str, key: str, value: str) -> str | None:  # type: ignore[no-untyped-def]
    return await conn.fetchval(f"SELECT dataset_id FROM {table} WHERE {key} = $1 LIMIT 1", value)


async def test_a_proposal_and_an_alert_take_their_cases_dataset(setup) -> None:  # type: ignore[no-untyped-def]
    conn, unit, proposal, alert, _, _ = setup
    report = await place_records(conn, write=True, say=lambda _: None)
    assert await _dataset(conn, "link_type_proposals", "id", proposal.id) == f"fixture-corp-{unit}"
    assert await _dataset(conn, "alerts", "id", alert.id) == f"fixture-corp-{unit}"
    assert report.placed["link_type_proposals"] >= 1 and report.placed["alerts"] >= 1


async def test_what_records_no_case_is_counted_not_guessed(setup) -> None:  # type: ignore[no-untyped-def]
    conn, _, _, _, pattern, hotlist = setup
    report = await place_records(conn, write=True, say=lambda _: None)
    assert await _dataset(conn, "saved_patterns", "pattern_id", pattern.pattern_id) is None
    assert await _dataset(conn, "hotlists", "id", hotlist.id) is None
    assert report.unplaced["saved_patterns"] >= 1 and report.unplaced["hotlists"] >= 1


async def test_a_dry_run_writes_nothing(setup) -> None:  # type: ignore[no-untyped-def]
    conn, _, proposal, _, _, _ = setup
    report = await place_records(conn, write=False, say=lambda _: None)
    assert report.placed["link_type_proposals"] >= 1
    assert await _dataset(conn, "link_type_proposals", "id", proposal.id) is None


async def test_running_it_again_moves_nothing(setup) -> None:  # type: ignore[no-untyped-def]
    conn, unit, proposal, _, _, _ = setup
    await place_records(conn, write=True, say=lambda _: None)
    await place_records(conn, write=True, say=lambda _: None)
    assert await _dataset(conn, "link_type_proposals", "id", proposal.id) == f"fixture-corp-{unit}"
