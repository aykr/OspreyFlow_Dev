"""*Promotions overdue* (`06_DECISIONS.md` ADR-145 Amendment 4 decision 11, R7) raised by admin's own
job in the Conduit's real lifespan (Amendment 6): `promotion_ageing.PromotionSweep`, ticking every
`OSPREY_PROMOTION_SWEEP_SECONDS`, reading whatever source `app.state.waiting_promotions` holds.

Real: the app's lifespan and its task, the Postgres stores (the alert raised once by the database,
the setting, a dataset's home case and its Authors' grants), `_promotion_recipients`. Stood in:
the promotion source (case's L3.4 has not recorded promotions yet; the stand-in is the seam's
Protocol) and the identity provider's list of people, which the test stack has no provider for.

What a mistake would do, and the case that fails: the job never started, or started on the source
the Conduit held at start-up rather than the one on `app.state` at each tick (no alert); the
proposer, an Author without `review_promotions`, or another unit's administrator alerted; an alert
before N days. Not this test's: the alert raised on every tick, which the table's primary key
refuses and which `test_promotion_ageing.py::test_the_alert_fires_once` (A2) and the store test's
U5 catch. Each run leaves its own dataset, home case, grants and alert rows on the stack, named by
its run so a second run never meets them.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from fastapi.testclient import TestClient
from services.api.config import PostgresConfig
from services.api.investigations import AccessLevel, InvestigationStore
from services.api.promotion_ageing import PendingPromotion

from schemas.admin import PersonAccount
from schemas.domain import Principal

PROPOSER = Principal(id="sw-prop", clearance="SECRET", org_unit="unit-sw", roles=["analyst"])


@pytest.fixture
def api_env(jwks_url: str) -> Iterator[None]:
    keys = ("OIDC_JWKS_URL", "OIDC_ALGORITHMS", "ARCADEDB_DATABASE", "OSPREY_PROMOTION_SWEEP_SECONDS")
    previous = {k: os.environ.get(k) for k in keys}
    os.environ.update({"OIDC_JWKS_URL": jwks_url, "OIDC_ALGORITHMS": "RS256",
                       "ARCADEDB_DATABASE": "ospreyflow", "OSPREY_PROMOTION_SWEEP_SECONDS": "0.5"})  # fmt: skip
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class _Source:
    """The seam's Protocol, as L3.4 will fill it: one promotion past N days, one not yet."""

    recorded = True

    def __init__(self, dataset_id: str, tag: str) -> None:
        now = datetime.now(UTC)
        self.items = [
            PendingPromotion(promotion_id=f"{tag}-old", load_id=f"{tag}-load-1",
                             dataset_id=dataset_id, dataset_name=f"Synthetic custody {tag}",
                             dataset_unit="unit-sw", proposed_by=PROPOSER.id,
                             proposed_at=now - timedelta(days=3, minutes=5)),
            PendingPromotion(promotion_id=f"{tag}-new", load_id=f"{tag}-load-2",
                             dataset_id=dataset_id, dataset_name=f"Synthetic custody {tag}",
                             dataset_unit="unit-sw", proposed_by=PROPOSER.id,
                             proposed_at=now - timedelta(days=1)),
        ]  # fmt: skip

    async def waiting_for_review(self, reader: Principal) -> list[PendingPromotion]:
        return []

    async def all_waiting(self) -> list[PendingPromotion]:
        return list(self.items)


def _person(pid: str, roles: list[str], unit: str = "unit-sw") -> PersonAccount:
    return PersonAccount(id=pid, username=pid, name=pid, enabled=True, roles=roles,
                         clearance="SECRET", org_unit=unit)  # fmt: skip


class _People:
    async def list_people(self) -> list[PersonAccount]:
        return [
            _person(PROPOSER.id, ["analyst", "right:review_promotions"]),  # never alerted
            _person("sw-rev", ["analyst", "right:review_promotions"]),  # an Author who reviews
            _person("sw-auth", ["analyst"]),  # an Author who may not review
            _person("sw-adm", ["osprey-admin"]),  # the unit's administrator
            _person("sw-adm-9", ["osprey-admin"], unit="unit-other"),  # another unit's
        ]

    async def aclose(self) -> None:
        return None


async def _home_case() -> str:
    cases = await InvestigationStore.connect(PostgresConfig.from_env().dsn)
    try:
        case = await cases.create(PROPOSER, name="Synthetic custody home")
        for who in ("sw-rev", "sw-auth"):
            await cases.set_grant(case.id, who, AccessLevel.AUTHOR, by=PROPOSER)
        return case.id
    finally:
        await cases.close()


async def _home(dataset_id: str, case_id: str) -> int | None:
    """The dataset's home case, on a connection of the test's own (the app's pools belong to the
    app's event loop), with N pinned to 3; returns the shared setting it replaced."""
    from services.api.datasets import PostgresDatasetStore  # makes `home_cases`, as the Conduit does
    from services.api.promotion_ageing import PromotionAgeingStore

    for store_type in (PostgresDatasetStore, PromotionAgeingStore):
        store = await store_type.connect(PostgresConfig.from_env().dsn)  # type: ignore[attr-defined]
        await store.close()
    conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        await conn.execute(
            "INSERT INTO datasets (id, name, owning_unit, created_at, created_by) "
            "VALUES ($1, $1, 'unit-sw', now(), $2)", dataset_id, PROPOSER.id)  # fmt: skip
        await conn.execute(
            "INSERT INTO home_cases (dataset_id, investigation_id, made_at, made_by) "
            "VALUES ($1, $2, now(), $3)", dataset_id, case_id, PROPOSER.id)  # fmt: skip
        before = await conn.fetchval(
            "SELECT value::text FROM operations_settings WHERE key = 'promotion_alert_after_days'")
        await conn.execute(
            "INSERT INTO operations_settings (key, value) VALUES ('promotion_alert_after_days', '3') "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value")  # fmt: skip
        return int(before) if before is not None else None
    finally:
        await conn.close()


async def _restore(days: int | None) -> None:
    conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        if days is None:
            await conn.execute(
                "DELETE FROM operations_settings WHERE key = 'promotion_alert_after_days'")
        else:
            await conn.execute(
                "UPDATE operations_settings SET value = $1::jsonb "
                "WHERE key = 'promotion_alert_after_days'", str(days))  # fmt: skip
    finally:
        await conn.close()


async def _alerts(tag: str) -> list[asyncpg.Record]:
    conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        return await conn.fetch(
            "SELECT promotion_id, recipients::text AS recipients, words "
            "FROM promotion_overdue_alerts WHERE promotion_id LIKE $1", f"{tag}-%")  # fmt: skip
    finally:
        await conn.close()


async def _tidy(tag: str, dataset_id: str, case_id: str) -> None:
    """Removes what the test wrote to the shared stack, whatever it did (L2.7's review): its alerts,
    the dataset's home case and the dataset, and the home case with every row naming it."""
    conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        await conn.execute("DELETE FROM promotion_overdue_alerts WHERE promotion_id LIKE $1",
                           f"{tag}-%")  # fmt: skip
        await conn.execute("DELETE FROM home_cases WHERE dataset_id = $1", dataset_id)
        naming = await conn.fetch(
            "SELECT table_name FROM information_schema.columns WHERE table_schema = current_schema() "
            "AND column_name = 'investigation_id' AND table_name <> 'investigations'"
        )
        for row in naming:
            await conn.execute(
                f'DELETE FROM "{row["table_name"]}" WHERE investigation_id = $1', case_id
            )
        await conn.execute("DELETE FROM investigations WHERE id = $1", case_id)
        await conn.execute("DELETE FROM datasets WHERE id = $1", dataset_id)
    finally:
        await conn.close()


def test_the_lifespans_own_sweep_raises_r7s_alert_once_at_n_days(api_env: None) -> None:
    tag = "sw" + uuid.uuid4().hex[:8]
    dataset_id = f"ds-{tag}"
    case_id = asyncio.run(_home_case())
    days_before = asyncio.run(_home(dataset_id, case_id))
    from services.api.app import app

    with TestClient(app):
        held, source_held = app.state.identity_admin, app.state.waiting_promotions
        app.state.identity_admin = _People()
        try:
            # Set after start-up, as L3.4 will: the job asks `app.state` at every tick.
            app.state.waiting_promotions = _Source(dataset_id, tag)
            deadline = time.monotonic() + 20
            rows: list[asyncpg.Record] = []
            while time.monotonic() < deadline and not rows:
                time.sleep(0.5)
                rows = asyncio.run(_alerts(tag))
            time.sleep(2)  # several more ticks
            rows = asyncio.run(_alerts(tag))
        finally:
            app.state.identity_admin = held
            app.state.waiting_promotions = source_held
            asyncio.run(_restore(days_before))
            asyncio.run(_tidy(tag, dataset_id, case_id))
    assert [r["promotion_id"] for r in rows] == [f"{tag}-old"]  # once, and only the one at N days
    [row] = rows
    assert sorted(__import__("json").loads(row["recipients"])) == ["sw-adm", "sw-rev"]
    assert row["words"] == (
        f"Promotion {tag}-load-1 into Synthetic custody {tag} has waited 3 days for review.")


async def _record_promotions(dataset_id: str, tag: str) -> None:
    """Two promotions waiting in L3.4's own record (`promotion_store.PostgresPromotionStore`), one
    past N days and one not, as a board's promotion under *Second person reviews* writes them."""
    from services.api.promotion_store import PostgresPromotionStore, PromotionRecord

    store = await PostgresPromotionStore.connect(PostgresConfig.from_env().dsn)
    now = datetime.now(UTC)
    try:
        for suffix, load, age in (("old", 1, timedelta(days=3, minutes=5)),
                                  ("new", 2, timedelta(days=1))):  # fmt: skip
            await store.add(PromotionRecord(
                id=f"{tag}-{suffix}", load_id=f"{tag}-load-{load}", trigger="analyst_promotion",
                case_id=f"case-{tag}", board_id=f"board-{tag}", dataset_id=dataset_id,
                layer_id=f"layer-{tag}", proposed_by=PROPOSER.id, proposed_at=now - age,
                status="awaiting_review", marking="OFFICIAL", unit="unit-sw",
            ))  # fmt: skip
    finally:
        await store.close()


async def _forget(tag: str) -> None:
    """What the real-store case wrote, removed (the promotions and their alert)."""
    conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        await conn.execute("DELETE FROM promotions WHERE id LIKE $1", f"{tag}-%")
        await conn.execute("DELETE FROM promotion_overdue_alerts WHERE promotion_id LIKE $1",
                           f"{tag}-%")  # fmt: skip
    finally:
        await conn.close()


def test_the_lifespans_own_seam_over_the_real_promotion_record_raises_the_alert(
    api_env: None,
) -> None:
    """The same sweep with nothing stood in for the source: the lifespan's own
    `app.state.waiting_promotions` (`app.waiting_promotions_seam`, L3.4) over promotions written
    to the real `promotions` table. Red with `NoPromotionsYet()` still in the lifespan (no
    alert)."""
    tag = "swr" + uuid.uuid4().hex[:8]
    dataset_id = f"ds-{tag}"
    case_id = asyncio.run(_home_case())
    days_before = asyncio.run(_home(dataset_id, case_id))
    from services.api.app import app

    try:
        with TestClient(app):
            held = app.state.identity_admin
            app.state.identity_admin = _People()
            try:
                asyncio.run(_record_promotions(dataset_id, tag))
                deadline = time.monotonic() + 20
                rows: list[asyncpg.Record] = []
                while time.monotonic() < deadline and not rows:
                    time.sleep(0.5)
                    rows = asyncio.run(_alerts(tag))
                time.sleep(2)
                rows = asyncio.run(_alerts(tag))
            finally:
                app.state.identity_admin = held
    finally:
        asyncio.run(_forget(tag))
        asyncio.run(_restore(days_before))
    assert [r["promotion_id"] for r in rows] == [f"{tag}-old"]
    [row] = rows
    assert sorted(__import__("json").loads(row["recipients"])) == ["sw-adm", "sw-rev"]
    assert row["words"] == (
        f"Promotion {tag}-load-1 into {dataset_id} has waited 3 days for review.")
