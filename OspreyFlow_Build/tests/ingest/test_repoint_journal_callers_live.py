"""L2.8c (ADR-109 Amendment 11) against the real stores: the repoint journal's lock and rename
(the L2.8b review's D9 and D10), and every caller that clones or replaces a link an alert can cite
going through the journal, so an alert citing the link each one replaces stays listed for its
readers. The journal's own cases, from L2.8b, are `test_alert_evidence_withheld_live.py`'s.

Each case was shown red by a plant at the real call site; the outputs are kept with the lane's
record (`process/lanes/rules/l2.8c/`)."""

from __future__ import annotations

import asyncio
from typing import Any

import asyncpg
import pytest
from services.api.alerts import RepointLockBusy
from services.api.config import PostgresConfig

from conduit_common.identity import new_id
from schemas.domain import Alert, AlertMode
from tests.ingest import test_typology_rules as _rules_suite
from tests.ingest.test_typology_rules import ANALYST, T0
from tests.services.api.repoint_journal_cleanup import remove_repoint_records  # noqa: F401 - autouse teardown

#: The rules suite's own live stores, as a fixture of this file.
stores = _rules_suite.stores

#: Seconds a case may take before it fails rather than stalls the run.
BOUND = 30


def _alert(case: str, *, node: str | None = None, edges: list[str] | None = None) -> Alert:
    return Alert(id=new_id(), rule_id=f"typology:{new_id()}", owner_id=ANALYST.id, mode=AlertMode.FULL,
                 referent_node_ids=[], edge_ids=edges or [], investigation_id=case, created_at=T0,
                 typology="structuring", words="A finding", severity="medium",
                 alert_node_id=node)  # fmt: skip


async def _record(stores: dict[str, Any]) -> str:
    """An empty record, as `AlertStore.repointing` opens one."""
    record = new_id()
    async with stores["alerts"]._pool.acquire() as conn:
        await conn.execute("INSERT INTO alert_repoint_records (id) VALUES ($1)", record)
    return record


# ---- D10: the lock pool's timeout and its own advisory-key space --------------------------------


async def test_a_settle_that_waits_too_long_for_a_lock_connection_refuses_in_words(
    stores: dict[str, Any],
) -> None:
    """D10. Every lock connection is held elsewhere; a settle waits `lock_wait` for one, then
    refuses in words naming the record and the wait, and the record is left for a later read.
    Red with no timeout on the wait: the settle waited for ever (the case's bound fired)."""
    alerts = stores["alerts"]
    alerts.lock_wait = 0.5
    record = await _record(stores)
    held = [await alerts._lock_pool.acquire() for _ in range(alerts._lock_pool.get_max_size())]
    try:
        with pytest.raises(RepointLockBusy, match=rf"repoint record {record} not settled: no lock "
                                                  r"connection came free within 0\.5 seconds"):  # fmt: skip
            await asyncio.wait_for(alerts._settle_record(None, record, writer=True), BOUND)
    finally:
        for conn in held:
            await alerts._lock_pool.release(conn)
    async with alerts._pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM alert_repoint_records WHERE id = $1", record) == 1


async def test_a_records_lock_is_its_own_whatever_another_store_locks_on_the_same_text(
    stores: dict[str, Any],
) -> None:
    """D10. Another store holds a one-key advisory lock on `hashtext` of the record's own id (as
    `strength_influencers` and `studio_recipes` lock their own text). The record's settle is not
    skipped for it: its writer closes it. Red with the record's lock in the one-key space: the
    settle found the key taken and skipped the record (`None`)."""
    record = await _record(stores)
    other = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        await other.execute("SELECT pg_advisory_lock(hashtext($1))", record)
        settled = await asyncio.wait_for(stores["alerts"]._settle_record(None, record, writer=True), BOUND)
        assert settled == [], "the writer settled its own empty record, not skipped it"
    finally:
        await other.close()


# ---- D9: the rename under the id-ordered lock ---------------------------------------------------


async def test_a_rename_and_a_repoint_of_the_same_alerts_never_deadlock(stores: dict[str, Any]) -> None:
    """D9. Two alerts, `a` before `b` in id order, each naming a node a record renames. Another
    writer (as `apply_repoints` does) has locked `a` and goes on to lock `b`, id order. The rename,
    asked to rename `b`'s node first, takes the rows in id order too, so it waits for `a` holding
    nothing, and the other writer takes `b` at once. Red with the rename outside the id-ordered
    lock: the rename held `b` while waiting for `a`, and Postgres broke the deadlock by killing
    one of the two (`DeadlockDetectedError`)."""
    case = f"case-{new_id()}"
    node_a, node_b = f"node-a-{new_id()}", f"node-b-{new_id()}"
    first, second = _alert(case, node=node_a), _alert(case, node=node_b)
    assert first.id < second.id
    for alert in (first, second):
        await stores["alerts"].save(alert)
    renamed = {node_b: f"{node_b}-r2", node_a: f"{node_a}-r2"}

    other = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        tx = other.transaction()
        await tx.start()
        await other.execute("SET LOCAL lock_timeout = '10s'")
        await other.execute("SELECT id FROM alerts WHERE id = $1 FOR UPDATE", first.id)
        rename = asyncio.create_task(stores["alerts"].rename_alert_nodes(renamed))
        await asyncio.sleep(1.5)  # the rename reaches its wait for `a`
        try:
            await other.execute("SELECT id FROM alerts WHERE id = $1 FOR UPDATE", second.id)
        finally:
            await tx.commit()
        await asyncio.wait_for(rename, BOUND)
    finally:
        await other.close()
    async with stores["alerts"]._pool.acquire() as conn:
        named = dict(await conn.fetch("SELECT id, alert_node_id FROM alerts WHERE id = ANY($1::text[])",
                                      [first.id, second.id]))  # fmt: skip
    assert named == {first.id: renamed[node_a], second.id: renamed[node_b]}
