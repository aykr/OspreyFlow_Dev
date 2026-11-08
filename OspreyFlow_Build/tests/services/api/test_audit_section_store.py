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
    models = await PostgresModelAdminAudit.connect(dsn)
    reader = await AuditSectionReader.connect(dsn)
    ageing = await PromotionAgeingStore.connect(dsn)
    raw = await asyncpg.connect(dsn=dsn)
    case_a = await cases.create(ANA_A, name="Op Kestrel")
    case_b = await cases.create(ANA_B, name="Op Harrier")
    yield SimpleNamespace(cases=cases, audit=audit, models=models, reader=reader, ageing=ageing,
                          raw=raw, case_a=case_a, case_b=case_b)  # fmt: skip
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
        StreamFilters(who="adm-b"),
        StreamFilters(who="ana-b", kind="assertions"),
        StreamFilters(dataset_id="ds-b"),
    ):
        rows, total = await world.reader.stream(A, cases=True, rights=FULL, filters=f, offset=0, limit=50)
        assert (rows, total) == ([], 0), f
    rows, total = await world.reader.stream(A, cases=True, rights=FULL, filters=StreamFilters(who="ana-b"), offset=0, limit=50)
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
    _, by_b = await world.reader.model_history(StreamFilters(who="adm-b"), offset=0, limit=50)
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
