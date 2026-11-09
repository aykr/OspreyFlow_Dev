"""Admin › Audit's reads and Operations' ageing store on real Postgres (`06_DECISIONS.md` ADR-145
decisions 9 and 10, Amendment 4 decision 11; L2.6). A fresh schema per test, with the real
`InvestigationStore`, `AuditWriter` and engines' history making their own tables.

What a mistake would do, and the case that catches it (each shown red at its real call site,
`process/lanes/admin/L2.6_RED_RECORD.md`):

- the unit filter removed from `AuditSectionReader.stream`'s `WHERE` clause: another unit's case
  entries and its people's entries are listed and counted —
  `test_a_reader_of_one_unit_sees_that_units_entries_alone`;
- a filter ORed with the unit filter (so a filter widens): `test_filters_never_widen_the_read`;
- the rule audit read from the stream, its words unwithheld:
  `test_the_rule_audit_is_never_read_from_the_stream`;
- the dataset filter looking into withheld words, or missing a list of datasets:
  `test_the_dataset_filter_reads_only_words_the_reader_is_shown`;
- a case's entry sent to a holder of `read_audit` who is not the unit's administrator:
  `test_no_case_entry_without_the_safety_net`;
- a system principal's unit (`operator`) read by a real unit of that name, or the writer's unit not
  recorded at all: `test_a_system_unit_is_never_a_real_units`;
- the indexes left unbuilt or invalid: `test_the_indexes_are_built_concurrently_and_valid`; built plainly
  (not `CONCURRENTLY`), so audit writes queue behind the build:
  `test_audit_writes_go_on_while_the_indexes_build`; one left invalid by a crashed build kept:
  `test_an_index_left_invalid_by_a_crashed_build_is_built_again`; another start's build under way
  dropped or waited on: `test_a_start_never_waits_on_or_drops_a_build_under_way`; a start that left
  them never asking again: `test_a_start_that_left_the_indexes_builds_them_once_free`;
- `org_unit` added by an unconditional `ALTER TABLE … ADD COLUMN IF NOT EXISTS`, which takes
  `ACCESS EXCLUSIVE` even when the column is there, so a second Conduit starting waits behind every
  read of `audit_log` (and in one process deadlocks):
  `test_a_second_start_does_not_wait_behind_a_read_of_the_audit`;
- the engines' history truncated at its own read's 200: `test_the_engines_history_pages_with_its_true_total`;
- "once" left to the caller: `test_an_overdue_alert_is_raised_once_by_the_database`.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import asyncpg
import pytest
from services.api import audit as audit_module
from services.api.audit import AuditWriter
from services.api.audit_section import AuditSectionReader, StreamFilters
from services.api.config import PostgresConfig
from services.api.investigations import InvestigationStore
from services.api.model_admin import PostgresModelAdminAudit
from services.api.promotion_ageing import PromotionAgeingStore

from schemas.admin import PromotionOverdueAlert
from schemas.domain import Principal
from schemas.model_admin import ModelAdminEntry
from schemas.rights import ADMIN as FULL
from schemas.rights import Right

_NAMES = [name for name, _ in audit_module._CONCURRENT_INDEXES]

A = Principal(id="adm-a", clearance="SECRET", org_unit="unit-a", roles=["osprey-admin"])
B = Principal(id="adm-b", clearance="SECRET", org_unit="unit-b", roles=["osprey-admin"])
ANA_A = Principal(id="ana-a", clearance="SECRET", org_unit="unit-a", roles=["analyst"])
ANA_B = Principal(id="ana-b", clearance="SECRET", org_unit="unit-b", roles=["analyst"])


@pytest.fixture
async def world() -> AsyncIterator[SimpleNamespace]:
    name = "l26_" + uuid.uuid4().hex[:10]
    base = PostgresConfig.from_env().dsn
    conn = await asyncpg.connect(dsn=base)
    await conn.execute(f'CREATE SCHEMA "{name}"')
    await conn.close()
    dsn = f"{base}?search_path={name}"
    cases = await InvestigationStore.connect(dsn)
    audit = await AuditWriter.connect(dsn)
    await audit.indexes_built()  # built in the background; the index cases read them
    models = await PostgresModelAdminAudit.connect(dsn)
    reader = await AuditSectionReader.connect(dsn)
    ageing = await PromotionAgeingStore.connect(dsn)
    raw = await asyncpg.connect(dsn=dsn)
    case_a = await cases.create(ANA_A, name="Op Kestrel")
    case_b = await cases.create(ANA_B, name="Op Harrier")
    yield SimpleNamespace(cases=cases, audit=audit, models=models, reader=reader, ageing=ageing,
                          raw=raw, case_a=case_a, case_b=case_b, dsn=dsn)  # fmt: skip
    await raw.close()
    for store in (cases, audit, models, reader, ageing):
        await store.close()
    conn = await asyncpg.connect(dsn=base)
    await conn.execute(f'DROP SCHEMA "{name}" CASCADE')
    await conn.close()


async def _record(w: SimpleNamespace, who: Principal, action: str, case: str | None = None,
                  detail: dict[str, object] | None = None) -> None:  # fmt: skip
    await w.audit.record(principal=who, action=action, investigation_id=case,
                         resolved_query=detail or {}, result_cardinality=1)  # fmt: skip


async def _seed(w: SimpleNamespace) -> None:
    await _record(w, ANA_A, "confirm_node", w.case_a.id, {"node_ids": ["n1"]})
    await _record(w, ANA_B, "confirm_node", w.case_b.id, {"node_ids": ["n2"]})
    # Another unit's analyst refused at unit A's case is about unit A's case.
    await _record(w, ANA_B, "access_denied", w.case_a.id)
    # Unit A's administrator acting on unit B's case is about unit B's case: not unit A's to read.
    await _record(w, A, "access_denied", w.case_b.id)
    await _record(w, A, "set_person_roles", None, {"user_id": "ana-a"})
    await _record(w, B, "set_person_roles", None, {"user_id": "ana-b"})
    await _record(w, ANA_A, "probe", "no-such-case")  # a case that does not exist: no unit's
    # An entry written before L2.6 recorded no unit.
    await w.raw.execute(
        "INSERT INTO audit_log (recorded_at, principal_id, action, resolved_query, "
        "result_cardinality) VALUES (now(), 'adm-a', 'set_person_roles', '{}', 1)"
    )


def _seen(rows: list[object]) -> set[tuple[str, str, str | None]]:
    return {(r.principal_id, r.action, r.investigation_id) for r in rows}  # type: ignore[attr-defined]


async def test_a_reader_of_one_unit_sees_that_units_entries_alone(world: SimpleNamespace) -> None:
    await _seed(world)
    rows, total = await world.reader.stream(A, cases=True, rights=FULL, filters=StreamFilters(), offset=0, limit=50)
    assert _seen(rows) == {
        ("ana-a", "confirm_node", world.case_a.id),
        ("ana-b", "access_denied", world.case_a.id),
        ("adm-a", "set_person_roles", None),
    }
    assert total == 3
    assert {r.case_name for r in rows} == {"Op Kestrel", None}
    rows_b, total_b = await world.reader.stream(B, cases=True, rights=FULL, filters=StreamFilters(), offset=0, limit=50)
    assert _seen(rows_b) == {
        ("ana-b", "confirm_node", world.case_b.id),
        ("adm-a", "access_denied", world.case_b.id),
        ("adm-b", "set_person_roles", None),
    }
    assert total_b == 3


async def test_filters_never_widen_the_read(world: SimpleNamespace) -> None:
    await _seed(world)
    for f in (
        StreamFilters(investigation_id=world.case_b.id),
        StreamFilters(who=("adm-b",)),
        StreamFilters(who=("ana-b",), kind="assertions"),
        StreamFilters(dataset_id="ds-b"),
    ):
        rows, total = await world.reader.stream(A, cases=True, rights=FULL, filters=f, offset=0, limit=50)
        assert (rows, total) == ([], 0), f
    rows, total = await world.reader.stream(A, cases=True, rights=FULL, filters=StreamFilters(who=("ana-b",)), offset=0, limit=50)
    assert _seen(rows) == {("ana-b", "access_denied", world.case_a.id)} and total == 1
    rows, _ = await world.reader.stream(A, cases=True, rights=FULL, filters=StreamFilters(kind="people_and_roles"), offset=0, limit=50)
    assert _seen(rows) == {("adm-a", "set_person_roles", None)}
    rows, _ = await world.reader.stream(A, cases=True, rights=FULL, filters=StreamFilters(kind="reads_and_other"), offset=0, limit=50)
    assert _seen(rows) == {("ana-b", "access_denied", world.case_a.id)}
    later = datetime.now(UTC) + timedelta(minutes=1)
    rows, total = await world.reader.stream(A, cases=True, rights=FULL, filters=StreamFilters(since=later), offset=0, limit=50)
    assert (rows, total) == ([], 0)


async def test_the_rule_audit_is_never_read_from_the_stream(world: SimpleNamespace) -> None:
    await _record(world, ANA_A, "rule_fired", world.case_a.id,
                  {"alert_id": "al-1", "words": "Structuring by J. Doe"})  # fmt: skip
    await _record(world, ANA_A, "rule_deployed", world.case_a.id, {"rule_id": "r1"})
    for kind in (None, "reads_and_other", "loads_and_promotions"):
        rows, total = await world.reader.stream(A, cases=True, rights=FULL, filters=StreamFilters(kind=kind), offset=0, limit=50)
        assert (rows, total) == ([], 0), kind


async def test_a_page_and_its_total(world: SimpleNamespace) -> None:
    for i in range(5):
        await _record(world, ANA_A, "confirm_node", world.case_a.id, {"i": i})
    rows, total = await world.reader.stream(A, cases=True, rights=FULL, filters=StreamFilters(), offset=1, limit=2)
    assert total == 5
    assert [r.resolved_query["i"] for r in rows] == [3, 2]  # newest first


async def test_the_engines_history_pages_with_its_true_total(world: SimpleNamespace) -> None:
    t0 = datetime(2026, 11, 8, tzinfo=UTC)
    for i in range(205):
        await world.models.record(ModelAdminEntry(at=t0 + timedelta(seconds=i), by="adm-a",
                                                  action="engine_edited", engine=f"e{i}",
                                                  outcome="done"))  # fmt: skip
    entries, total = await world.reader.model_history(StreamFilters(), offset=200, limit=50)
    assert total == 205 and len(entries) == 5
    assert entries[0].detail == {"engine": "e4", "changes": {}, "outcome": "done"}
    _, by_b = await world.reader.model_history(StreamFilters(who=("adm-b",)), offset=0, limit=50)
    assert by_b == 0


async def test_the_alert_setting_defaults_to_three_and_is_kept(world: SimpleNamespace) -> None:
    assert await world.ageing.alert_after_days() == 3
    await world.ageing.set_alert_after_days(5)
    assert await world.ageing.alert_after_days() == 5


async def test_an_overdue_alert_is_raised_once_by_the_database(world: SimpleNamespace) -> None:
    alert = PromotionOverdueAlert(promotion_id="p1", load_id="load-1", dataset_id="ds-a",
                                  raised_at=datetime.now(UTC), recipients=["eng-1", "adm-a"],
                                  words="Promotion load-1 into Prison records has waited 3 days for review.")  # fmt: skip
    raised = await asyncio.gather(*(world.ageing.raise_once(alert) for _ in range(4)))
    assert sorted(raised) == [False, False, False, True]
    assert [a.load_id for a in await world.ageing.alerts_for("eng-1")] == ["load-1"]
    assert await world.ageing.alerts_for("ana-a") == []


async def test_the_dataset_filter_reads_only_words_the_reader_is_shown(world: SimpleNamespace) -> None:
    await _record(world, A, "set_dataset_egress", None, {"dataset_id": "ds-a", "egress": "none"})
    await _record(world, A, "create_dataset", None, {"dataset_ids": ["ds-x", "ds-a"]})
    await _record(world, A, "set_dataset_egress", None, {"dataset_id": "ds-z"})
    # A read naming the dataset: its words are withheld from everyone, so the filter never looks.
    await _record(world, A, "list_dataset_cases", None, {"dataset_id": "ds-a"})
    rows, total = await world.reader.stream(A, cases=True, rights=FULL,
                                            filters=StreamFilters(dataset_id="ds-a"), offset=0, limit=50)  # fmt: skip
    assert {r.action for r in rows} == {"set_dataset_egress", "create_dataset"} and total == 2
    # A reader shown no dataset's words: the filter answers nothing, so it tells nothing.
    alone = {Right.READ_AUDIT}
    rows, total = await world.reader.stream(A, cases=True, rights=alone,
                                            filters=StreamFilters(dataset_id="ds-a"), offset=0, limit=50)  # fmt: skip
    assert (rows, total) == ([], 0)


async def test_no_case_entry_without_the_safety_net(world: SimpleNamespace) -> None:
    await _seed(world)
    rows, total = await world.reader.stream(A, cases=False, rights=FULL, filters=StreamFilters(),
                                            offset=0, limit=50)  # fmt: skip
    assert _seen(rows) == {("adm-a", "set_person_roles", None)} and total == 1


async def test_a_system_unit_is_never_a_real_units(world: SimpleNamespace) -> None:
    operator = Principal(id="revert-cli", clearance="OFFICIAL", org_unit="operator", roles=[])
    await _record(world, operator, "load_reverted", None, {"load_id": "l1"})
    await _record(world, A, "set_person_roles", None, {"user_id": "ana-a"})
    units = dict(await world.raw.fetch("SELECT action, org_unit FROM audit_log"))
    assert units == {"load_reverted": "system:operator", "set_person_roles": "unit-a"}
    named_so = Principal(id="adm-op", clearance="SECRET", org_unit="operator", roles=["osprey-admin"])
    rows, total = await world.reader.stream(named_so, cases=True, rights=FULL,
                                            filters=StreamFilters(), offset=0, limit=50)  # fmt: skip
    assert (rows, total) == ([], 0)


async def test_the_indexes_are_built_concurrently_and_valid(world: SimpleNamespace) -> None:
    valid = dict(await world.raw.fetch(
        "SELECT c.relname, i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
        "WHERE c.relname = ANY($1::text[]) AND pg_table_is_visible(c.oid)", _NAMES))  # fmt: skip
    assert valid == dict.fromkeys(_NAMES, True)
    # A second start finds them and builds nothing again.
    again = await AuditWriter.connect(world.dsn)
    await again.close()


async def test_a_second_start_does_not_wait_behind_a_read_of_the_audit(world: SimpleNamespace) -> None:
    """A Conduit replica starting while another serves reads (or a second store in the same process,
    as a live run found on 9 November 2026) must not queue for a lock behind them."""
    reading = await asyncpg.connect(dsn=world.dsn)
    held = reading.transaction()
    await held.start()
    try:
        await reading.fetch("SELECT id FROM audit_log LIMIT 1")  # holds ACCESS SHARE until rollback
        again = await asyncio.wait_for(AuditWriter.connect(world.dsn), timeout=10)
        await again.close()
    finally:
        await held.rollback()
        await reading.close()


async def test_an_index_left_invalid_by_a_crashed_build_is_built_again(world: SimpleNamespace) -> None:
    """A `CREATE INDEX CONCURRENTLY` that fails leaves an invalid index of its name behind, which
    `IF NOT EXISTS` would then keep for ever. Made here the way a real failure makes one (a unique
    build over duplicate rows), under the real index's name; the next start drops and rebuilds it."""
    await _record(world, A, "set_person_roles", None, {"user_id": "ana-a"})
    await _record(world, A, "set_person_roles", None, {"user_id": "ana-b"})
    await world.raw.execute("DROP INDEX CONCURRENTLY audit_log_org_unit_idx")
    with pytest.raises(asyncpg.UniqueViolationError):
        await world.raw.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY audit_log_org_unit_idx ON audit_log (action)")
    left = await world.raw.fetchval(
        "SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
        "WHERE c.relname = 'audit_log_org_unit_idx' AND pg_table_is_visible(c.oid)")  # fmt: skip
    assert left is False  # the plant took: an invalid index of the real one's name
    again = await AuditWriter.connect(world.dsn)
    await asyncio.wait_for(again.indexes_built(), 30)
    await again.close()
    valid, unique = await world.raw.fetchrow(
        "SELECT i.indisvalid, i.indisunique FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
        "WHERE c.relname = 'audit_log_org_unit_idx' AND pg_table_is_visible(c.oid)")  # fmt: skip
    assert (valid, unique) == (True, False)


async def test_audit_writes_go_on_while_the_indexes_build(world: SimpleNamespace) -> None:
    """The invariant the concurrent build exists for. An audit write left open holds `ROW EXCLUSIVE`
    on `audit_log`; a plain `CREATE INDEX` waits for it holding a queued `SHARE`, and every later
    audit write queues behind that, so every route is refused until the open one ends. A concurrent
    build waits for it too, but under `SHARE UPDATE EXCLUSIVE`, which a write does not wait for."""
    for name, _ in audit_module._CONCURRENT_INDEXES:
        await world.raw.execute(f"DROP INDEX CONCURRENTLY {name}")
    held = await asyncpg.connect(dsn=world.dsn)
    builder = await asyncpg.connect(dsn=world.dsn)
    later = await asyncpg.connect(dsn=world.dsn)
    building: asyncio.Task[None] | None = None
    try:
        open_write = held.transaction()
        await open_write.start()
        await held.execute(
            "INSERT INTO audit_log (recorded_at, principal_id, action, resolved_query, "
            "result_cardinality) VALUES (now(), 'ana-a', 'probe', '{}', 1)")  # fmt: skip
        building = asyncio.create_task(audit_module.build_indexes(builder))
        pid = builder.get_server_pid()
        for _ in range(200):  # until the build is waiting on the open write
            if await world.raw.fetchval(
                "SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = $1", pid):  # fmt: skip
                break
            await asyncio.sleep(0.05)
        else:
            raise AssertionError("the build never waited on the open write")
        await later.execute("SET lock_timeout = '2s'")
        await later.execute(
            "INSERT INTO audit_log (recorded_at, principal_id, action, resolved_query, "
            "result_cardinality) VALUES (now(), 'ana-b', 'probe', '{}', 1)")  # fmt: skip
        await open_write.commit()
        await asyncio.wait_for(building, 30)
    finally:
        if building is not None and not building.done():
            building.cancel()
        for conn in (held, builder, later):
            await conn.close()
    valid = dict(await world.raw.fetch(
        "SELECT c.relname, i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
        "WHERE c.relname = ANY($1::text[]) AND pg_table_is_visible(c.oid)", _NAMES))  # fmt: skip
    assert valid == dict.fromkeys(_NAMES, True)


_INDEX_OID = "SELECT c.oid FROM pg_class c WHERE c.relname = $1 AND pg_table_is_visible(c.oid)"


async def _waiting_on_a_lock(world: SimpleNamespace, conn: asyncpg.Connection) -> None:
    pid = conn.get_server_pid()
    for _ in range(200):
        if await world.raw.fetchval(
            "SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = $1", pid):  # fmt: skip
            return
        await asyncio.sleep(0.05)
    raise AssertionError("the build never waited on the open write")


async def _audit_insert(conn: asyncpg.Connection, who: str) -> None:
    await conn.execute(
        "INSERT INTO audit_log (recorded_at, principal_id, action, resolved_query, "
        "result_cardinality) VALUES (now(), $1, 'probe', '{}', 1)", who)  # fmt: skip


async def test_a_start_never_waits_on_or_drops_a_build_under_way(world: SimpleNamespace) -> None:
    """A real concurrent build under way (another start's, held up by an open audit write): its
    index reads invalid exactly as a crashed one does. A second start must neither drop it nor
    take any lock on `audit_log` behind it (a `CREATE INDEX IF NOT EXISTS` takes `SHARE` before it
    reads the name, and every audit write would queue behind that), so it returns at once, a write
    after it goes through, and the build finishes as the first start's."""
    await world.raw.execute("DROP INDEX CONCURRENTLY audit_log_org_unit_idx")
    held = await asyncpg.connect(dsn=world.dsn)
    builder = await asyncpg.connect(dsn=world.dsn)
    later = await asyncpg.connect(dsn=world.dsn)
    building: asyncio.Task[bool] | None = None
    second: AuditWriter | None = None
    try:
        open_write = held.transaction()
        await open_write.start()
        await _audit_insert(held, "ana-a")
        building = asyncio.create_task(audit_module.build_indexes(builder))
        await _waiting_on_a_lock(world, builder)
        under_way = await world.raw.fetchval(_INDEX_OID, "audit_log_org_unit_idx")
        second = await asyncio.wait_for(AuditWriter.connect(world.dsn, index_retry_seconds=0.2), 5)
        await later.execute("SET lock_timeout = '2s'")
        await _audit_insert(later, "ana-b")
        await open_write.commit()
        assert await asyncio.wait_for(building, 30) is True
        assert second._index_retry is not None  # it left them to the builder, and asks again
        await asyncio.wait_for(second._index_retry, 5)  # and stops once they are built
    finally:
        if building is not None and not building.done():
            building.cancel()
        if second is not None:
            await second.close()
        for conn in (held, builder, later):
            await conn.close()
    assert await world.raw.fetchval(audit_module._INDEX_STATE_SQL, "audit_log_org_unit_idx") is True
    # The very index that was under way, not one dropped and built again by the second start.
    assert await world.raw.fetchval(_INDEX_OID, "audit_log_org_unit_idx") == under_way


async def test_a_start_that_left_the_indexes_builds_them_once_free(world: SimpleNamespace) -> None:
    """A start that could not take the build's lock serves without its indexes only until the
    lock is free: it asks again and builds them itself, with no restart."""
    await world.raw.execute("DROP INDEX CONCURRENTLY audit_log_org_unit_idx")
    other = await asyncpg.connect(dsn=world.dsn)
    second: AuditWriter | None = None
    try:
        await other.execute(f"SELECT pg_advisory_lock({audit_module._INDEX_LOCK_SQL})")
        second = await asyncio.wait_for(AuditWriter.connect(world.dsn, index_retry_seconds=0.2), 5)
        assert await world.raw.fetchval(audit_module._INDEX_STATE_SQL, "audit_log_org_unit_idx") is None
        await other.execute(f"SELECT pg_advisory_unlock({audit_module._INDEX_LOCK_SQL})")
        assert second._index_retry is not None
        await asyncio.wait_for(second._index_retry, 5)
    finally:
        if second is not None:
            await second.close()
        await other.close()
    assert await world.raw.fetchval(audit_module._INDEX_STATE_SQL, "audit_log_org_unit_idx") is True


async def test_units_are_recorded_from_this_deployments_own_date(world: SimpleNamespace) -> None:
    """Written once when the column is added at a start (now); a deployment that already had it
    takes its earliest entry recording a unit; a later start changes neither."""
    added = await world.reader.units_from()
    assert added is not None and abs((datetime.now(UTC) - added).total_seconds()) < 120
    await world.raw.execute("DELETE FROM audit_log_units_from")
    early = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)
    await world.raw.execute(
        "INSERT INTO audit_log (recorded_at, principal_id, action, resolved_query, "
        "result_cardinality, org_unit) VALUES ($1, 'adm-a', 'probe', '{}', 1, 'unit-a')", early)  # fmt: skip
    again = await AuditWriter.connect(world.dsn)
    await again.close()
    assert await world.reader.units_from() == early
    later = await AuditWriter.connect(world.dsn)
    await later.close()
    assert await world.reader.units_from() == early


async def test_a_start_returns_before_its_own_build(world: SimpleNamespace) -> None:
    """Item 9: a start never builds inside its start. With an audit write left open (which a
    concurrent build waits for) and an index missing, it returns at once; the build finishes in the
    background once the write ends."""
    await world.raw.execute("DROP INDEX CONCURRENTLY audit_log_org_unit_idx")
    held = await asyncpg.connect(dsn=world.dsn)
    writer: AuditWriter | None = None
    try:
        open_write = held.transaction()
        await open_write.start()
        await _audit_insert(held, "ana-a")
        writer = await asyncio.wait_for(AuditWriter.connect(world.dsn), 5)
        await open_write.commit()
        await asyncio.wait_for(writer.indexes_built(), 30)
    finally:
        if writer is not None:
            await writer.close()
        await held.close()
    assert await world.raw.fetchval(audit_module._INDEX_STATE_SQL, "audit_log_org_unit_idx") is True


async def test_the_build_survives_any_failure_and_close_still_closes(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item 8: an `InterfaceError` mid-build (asyncpg's "connection is closed", which is no
    `PostgresError`, unlike `ConnectionDoesNotExistError`) is logged and tried again; and a build that only ever fails never stops `close` closing the pool."""
    await world.raw.execute("DROP INDEX CONCURRENTLY audit_log_org_unit_idx")
    real = audit_module.build_indexes
    calls: list[int] = []

    async def lost_once(conn: asyncpg.Connection) -> bool:
        calls.append(1)
        if len(calls) == 1:
            raise asyncpg.InterfaceError("cannot perform operation: connection is closed")
        return await real(conn)

    monkeypatch.setattr(audit_module, "build_indexes", lost_once)
    writer = await AuditWriter.connect(world.dsn, index_retry_seconds=0.1)
    await asyncio.wait_for(writer.indexes_built(), 30)
    await writer.close()
    assert len(calls) == 2
    assert await world.raw.fetchval(audit_module._INDEX_STATE_SQL, "audit_log_org_unit_idx") is True

    async def always_fails(conn: asyncpg.Connection) -> bool:
        raise RuntimeError("planted")

    await world.raw.execute("DROP INDEX CONCURRENTLY audit_log_org_unit_idx")
    monkeypatch.setattr(audit_module, "build_indexes", always_fails)
    failing = await AuditWriter.connect(world.dsn, index_retry_seconds=0.05)
    await asyncio.sleep(0.2)
    await failing.close()  # raises nothing
    assert failing._pool.is_closing()
