"""The screening-list connector: deployment-wide import, versions, subscription by id, what a
dataset is offered, a dataset's own list's rows, and the schedule (`06_DECISIONS.md` ADR-140
Amendment 9 decision 3; Amendment 13). Offline: the store's and the object store's twins, which
refuse what the real ones refuse (`test_list_connector_store.py` runs the Postgres store live).

What a mistake would do, and the case that catches it:
- every refresh of an unchanged list keeping a new version, so a re-screen reads the whole list —
  `test_an_import_is_idempotent_per_version`;
- a changed list overwriting the version elements already name —
  `test_a_changed_list_is_a_new_version_and_the_old_one_stays`;
- a real list kept without its dataset admitted (rule 9), or a refused import leaving anything —
  `test_a_list_that_is_not_synthetic_is_refused_and_nothing_is_kept`;
- a file outside the ingest folder read — `test_a_location_outside_the_ingest_folder_is_refused`;
- a dataset offered a list it does not subscribe to, or another dataset's own list, whatever its
  name or id — `test_a_dataset_is_offered_only_its_own_and_its_subscribed_lists`,
  `test_a_list_another_dataset_owns_is_never_offered`;
- the offered lists and the save gate disagreeing — `test_what_is_offered_is_what_the_gate_reads`;
- a dataset's own list imported for an id its model does not name, or its version replaced —
  `test_a_datasets_own_list_is_imported_as_a_new_version_only_when_it_changes`;
- a schedule's slot run twice, or as someone no longer allowed —
  `test_a_scheduled_slot_runs_once_and_as_someone_still_allowed`.
"""

from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from services.api.list_connector import (
    DeploymentListScheduler,
    InMemoryListRows,
    InMemoryListStore,
    ListConnectorRefused,
    deployment_reference,
    import_list,
    import_own_list,
    offered_lists,
)
from services.ingest.staging_catalogue import staging_rule_violations

from schemas.dataset_model import ReferenceList
from schemas.list_connector import BlankListMapping, DeploymentListInput
from schemas.monitoring import ListSchedule
from schemas.staging import LookupStep

TESTS = Path(__file__).parents[2]
GOLDEN = TESTS / "connectors" / "golden"
FORMATS = TESTS / "knowledge_adapters" / "golden" / "screening_lists"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    shutil.copy(GOLDEN / "blank_client_list.csv", tmp_path / "client.csv")
    shutil.copy(FORMATS / "ofsi_consolidated.csv", tmp_path / "conlist.csv")
    return tmp_path


def _known(*paths: Path) -> set[str]:
    return {_sha(p) for p in paths}


async def _client_list(store: InMemoryListStore, name: str = "Client list") -> str:
    mapping = BlankListMapping.model_validate_json(
        (GOLDEN / "blank_client_list.mapping.json").read_text()
    )
    made = await store.add(
        DeploymentListInput(name=name, template="blank", location="client.csv", mapping=mapping),
        "admin-1",
    )
    return made.id


async def test_an_import_is_idempotent_per_version(root: Path) -> None:
    store, rows = InMemoryListStore(), InMemoryListRows()
    list_id = await _client_list(store)
    known = _known(root / "client.csv")
    first = await import_list(list_id, store=store, rows_kept=rows, root=root, known=known)
    again = await import_list(list_id, store=store, rows_kept=rows, root=root, known=known)
    assert (first.outcome, first.version, first.added) == ("updated", 1, 3)
    assert (again.outcome, again.version) == ("unchanged", 1)
    assert len(rows.files) == 1
    held = await store.get(list_id)
    assert (held.version, held.entries, held.failure) == (1, 3, None)


async def test_a_changed_list_is_a_new_version_and_the_old_one_stays(root: Path) -> None:
    store, rows = InMemoryListStore(), InMemoryListRows()
    list_id = await _client_list(store)
    await import_list(list_id, store=store, rows_kept=rows, root=root,
                      known=_known(root / "client.csv"))  # fmt: skip
    text = (root / "client.csv").read_text().splitlines()
    changed = [text[0], text[1].replace("XA1234567", "XA9999999"), text[3],
               "CL-004,Tamsin Oakhollow,,1990-01-01,XB,,Synthetic regime B,Person"]  # fmt: skip
    (root / "client.csv").write_text("\n".join(changed) + "\n")
    second = await import_list(list_id, store=store, rows_kept=rows, root=root,
                               known=_known(root / "client.csv"))  # fmt: skip
    assert (second.outcome, second.version, second.previous_version) == ("updated", 2, 1)
    assert (second.added, second.changed, second.delisted) == (1, 1, 1)
    record = await store.get(list_id)
    v1 = rows.read(deployment_reference(record, 1))
    v2 = rows.read(deployment_reference(record, 2))
    assert v1 is not None and v2 is not None
    assert {r["ref"] for r in v1} == {"CL-001", "CL-002", "CL-003"}
    assert {r["ref"] for r in v2} == {"CL-001", "CL-003", "CL-004"}


async def test_a_list_that_is_not_synthetic_is_refused_and_nothing_is_kept(root: Path) -> None:
    store, rows = InMemoryListStore(), InMemoryListRows()
    list_id = await _client_list(store)
    refused = await import_list(list_id, store=store, rows_kept=rows, root=root, known=set())
    assert refused.outcome == "refused" and "rule 9" in refused.words
    assert rows.files == {}
    held = await store.get(list_id)
    assert held.version == 0 and held.failure == refused.words
    ok = await import_list(list_id, store=store, rows_kept=rows, root=root,
                           known=_known(root / "client.csv"))  # fmt: skip
    assert ok.outcome == "updated" and (await store.get(list_id)).failure is None


async def test_a_real_list_of_an_unconfirmed_licence_is_refused_even_when_admitted(
    root: Path, tmp_path: Path
) -> None:
    from services.api.list_connector import admit_list

    exceptions = tmp_path / "exceptions.yaml"
    exceptions.write_text(
        "exceptions:\n  - dataset: un_list\n    approved_uses: [local_development]\n"
        "    added_by: owner\n    added_date: '2026-11-08'\n    device: test-device\n"
        "    justification: a test of the gate\n    decision_record: ADR-140\n"
    )
    with pytest.raises(ListConnectorRefused, match="licence is not confirmed"):
        admit_list({"main": b"<x/>"}, template="un_consolidated", dataset="un_list",
                   use="local_development", known=set(), exceptions_path=exceptions)  # fmt: skip


async def test_a_location_outside_the_ingest_folder_is_refused(root: Path) -> None:
    store, rows = InMemoryListStore(), InMemoryListRows()
    made = await store.add(
        DeploymentListInput(name="Escape", template="ofsi_consolidated", location="../x.csv"),
        "admin-1",
    )
    refused = await import_list(made.id, store=store, rows_kept=rows, root=root, known=set())
    assert refused.outcome == "refused" and "outside the ingest folder" in refused.words


async def test_a_format_list_imports_through_its_template(root: Path) -> None:
    store, rows = InMemoryListStore(), InMemoryListRows()
    made = await store.add(
        DeploymentListInput(name="OFSI", template="ofsi_consolidated", location="conlist.csv"),
        "admin-1",
    )
    done = await import_list(made.id, store=store, rows_kept=rows, root=root,
                             known=_known(root / "conlist.csv"))  # fmt: skip
    assert done.outcome == "updated" and done.added == 3


async def _two_lists(root: Path) -> tuple[InMemoryListStore, str, str]:
    store, rows = InMemoryListStore(), InMemoryListRows()
    one = await _client_list(store, "Client list")
    two = await _client_list(store, "Second list")
    known = _known(root / "client.csv")
    for list_id in (one, two):
        await import_list(list_id, store=store, rows_kept=rows, root=root, known=known)
    return store, one, two


OWN_A = ReferenceList(id="rl-a", dataset_id="ds-a", name="establishments", kind="reference",
                      key_column="estab_id", version=1)  # fmt: skip
OWN_B = ReferenceList(id="rl-b", dataset_id="ds-b", name="numbers", kind="reference",
                      key_column="number", version=1)  # fmt: skip


async def test_a_dataset_is_offered_only_its_own_and_its_subscribed_lists(root: Path) -> None:
    store, one, two = await _two_lists(root)
    assert [o.id for o in await offered_lists("ds-a", store=store, own=[OWN_A])] == ["rl-a"]
    await store.subscribe("ds-a", one, "author-1")
    offered = await offered_lists("ds-a", store=store, own=[OWN_A])
    assert [(o.id, o.deployment_wide) for o in offered] == [("rl-a", False), (one, True)]
    assert two not in {o.id for o in offered}
    assert [o.id for o in await offered_lists("ds-b", store=store, own=[OWN_B])] == ["rl-b"]


async def test_a_list_another_dataset_owns_is_never_offered(root: Path) -> None:
    store, _one, _two = await _two_lists(root)
    # Even handed in as "own", and whatever its kind: its own record says it is ds-b's.
    offered = await offered_lists("ds-a", store=store, own=[OWN_A, OWN_B])
    assert OWN_B.id not in {o.id for o in offered}
    screening_of_b = OWN_B.model_copy(update={"id": "rl-b2", "kind": "screening"})
    offered = await offered_lists("ds-a", store=store, own=[OWN_A, screening_of_b])
    assert "rl-b2" not in {o.id for o in offered}


async def test_a_subscription_to_a_list_that_does_not_exist_is_refused(root: Path) -> None:
    from services.api.list_connector import ListNotFound

    store, _one, _two = await _two_lists(root)
    with pytest.raises(ListNotFound):
        await store.subscribe("ds-a", "no-such-list", "author-1")


async def test_what_is_offered_is_what_the_gate_reads(root: Path) -> None:
    store, one, two = await _two_lists(root)
    await store.subscribe("ds-a", one, "author-1")
    every = [OWN_A, OWN_B, *[deployment_reference(r) for r in await store.lists()]]
    offered = {o.name for o in await offered_lists("ds-a", store=store, own=[OWN_A, OWN_B])}
    for name in ("establishments", "numbers", "Client list", "Second list"):
        step = LookupStep(id="look", kind="lookup", input="src", list=name, on="k",
                          add=[{"column": "x"}])  # type: ignore[arg-type,call-arg]  # fmt: skip
        gate = staging_rule_violations([step], sources=["src"], lists=every, dataset_id="ds-a",
                                       subscribed=await store.subscribed("ds-a"))  # fmt: skip
        assert (name in offered) == (not gate), name


async def test_a_datasets_own_list_is_imported_as_a_new_version_only_when_it_changes() -> None:
    rows = InMemoryListRows()
    body = b"estab_id,estab_name\nE1,HMP Synthetic One\nE2,HMP Synthetic Two\n"
    with pytest.raises(ListConnectorRefused, match="names no list"):
        import_own_list("ds-a", "rl-a", body, rows_kept=rows, named=[], name="establishments",
                        key_column="estab_id")  # fmt: skip
    with pytest.raises(ListConnectorRefused, match="first import"):
        import_own_list("ds-a", "rl-a", body, rows_kept=rows, named=["rl-a"])
    first, outcome = import_own_list("ds-a", "rl-a", body, rows_kept=rows, named=["rl-a"],
                                     name="establishments", key_column="estab_id")  # fmt: skip
    assert (first.version, outcome) == (1, "updated")
    same, outcome = import_own_list("ds-a", "rl-a", body, rows_kept=rows, named=["rl-a"])
    assert (same.version, outcome) == (1, "unchanged")
    more = body + b"E3,HMP Synthetic Three\n"
    second, outcome = import_own_list("ds-a", "rl-a", more, rows_kept=rows, named=["rl-a"])
    assert (second.version, second.name, second.key_column, outcome) == (
        2, "establishments", "estab_id", "updated")  # fmt: skip
    assert len(rows.read(first) or []) == 2 and len(rows.read(second) or []) == 3
    assert [r.id for r in rows.kept("ds-b")] == []
    with pytest.raises(ListConnectorRefused, match="key"):
        import_own_list("ds-a", "rl-a", b"estab_id,n\nE1,a\nE1,b\n", rows_kept=rows,
                        named=["rl-a"])  # fmt: skip


async def test_a_scheduled_slot_runs_once_and_as_someone_still_allowed(root: Path) -> None:
    store, rows = InMemoryListStore(), InMemoryListRows()
    list_id = await _client_list(store)
    set_at = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    await store.set_schedule(list_id, ListSchedule(every="daily", hour=5), "admin-1", set_at)
    claims: set[str] = set()

    async def claim(key: str) -> bool:
        if key in claims:
            return False
        claims.add(key)
        return True

    allowed: dict[str, str | None] = {"admin-1": None}

    async def may_run(owner: str) -> str | None:
        return allowed[owner]

    async def run(lid: str, owner: str) -> object:
        assert owner == "admin-1"
        return await import_list(lid, store=store, rows_kept=rows, root=root, trigger="schedule",
                                 known=_known(root / "client.csv"))  # fmt: skip

    scheduler = DeploymentListScheduler(store, claim, may_run, run)  # type: ignore[arg-type]
    later = set_at + timedelta(days=3)
    stale = (await store.scheduled())[0]  # what a second replica read before the first marked
    await scheduler.tick(later)
    await scheduler.tick(later)
    assert scheduler.seen == [list_id]
    claims.clear()  # its claim expired, or never reached Valkey: the slot's mark still holds
    await scheduler._consider(stale, later)
    assert scheduler.seen == [list_id]
    assert [i.trigger for i in await store.imports(list_id)] == ["schedule"]
    allowed["admin-1"] = "they no longer hold load_screening_lists"
    await scheduler.tick(later + timedelta(days=1))
    latest = (await store.imports(list_id))[0]
    assert latest.outcome == "refused" and "no longer hold" in latest.words
    assert scheduler.seen == [list_id]
    words = (await store.get(list_id)).schedule_words
    assert words and "05:00" in words


# --- the lane review of L1.6 ----------------------------------------------------------------------


async def test_a_list_given_a_schedule_after_its_first_import_still_imports_its_changes(
    root: Path,
) -> None:
    """Review item 3: the schedule was part of the version's record, so a scheduled list's next
    changed import read its previous version as "another list's" and crashed."""
    store, rows = InMemoryListStore(), InMemoryListRows()
    list_id = await _client_list(store)
    await import_list(list_id, store=store, rows_kept=rows, root=root,
                      known=_known(root / "client.csv"))  # fmt: skip
    await store.set_schedule(list_id, ListSchedule(every="daily", hour=5), "admin-1",
                             datetime(2026, 11, 8, tzinfo=UTC))  # fmt: skip
    (root / "client.csv").write_text((root / "client.csv").read_text().replace("XB", "XC"))
    done = await import_list(list_id, store=store, rows_kept=rows, root=root,
                             known=_known(root / "client.csv"))  # fmt: skip
    assert (done.outcome, done.version, done.changed) == ("updated", 2, 1)


async def test_a_version_file_left_by_an_import_that_never_applied_is_stepped_over(
    root: Path,
) -> None:
    """Review item 16: a process that died between keeping v2's file and applying it left the
    list at v1 for ever, every later import refused as "already kept with other rows". v2's rows
    were never live, so the next import keeps v3 and leaves the orphan untouched."""
    store, rows = InMemoryListStore(), InMemoryListRows()
    list_id = await _client_list(store)
    known = _known(root / "client.csv")
    await import_list(list_id, store=store, rows_kept=rows, root=root, known=known)
    record = await store.get(list_id)
    rows.write(deployment_reference(record, 2), [{**SAMPLE_ROW, "ref": "ORPHAN"}])
    (root / "client.csv").write_text((root / "client.csv").read_text().replace("XB", "XC"))
    done = await import_list(list_id, store=store, rows_kept=rows, root=root,
                             known=_known(root / "client.csv"))  # fmt: skip
    assert (done.outcome, done.version, done.previous_version) == ("updated", 3, 1)
    assert rows.read(deployment_reference(record, 2)) == [
        dict(SAMPLE_ROW, ref="ORPHAN", aliases=None, date_of_birth=None)
    ]


SAMPLE_ROW: dict[str, object] = {
    "ref": "X", "primary_name": "Someone", "aliases": "", "date_of_birth": " ",
    "nationality": "XA", "identifiers": None, "programme": None, "listing": "sanction",
    "entity_type": "Person",
}  # fmt: skip


async def test_an_own_list_with_blank_cells_is_unchanged_when_imported_again() -> None:
    """Review item 7: the real keeper reads a blank cell back as empty (None), the CSV gives "",
    so the digests differed and every re-import of an unchanged list kept a new version. The twin
    now keeps cells as the real keeper does; `test_list_rows_parquet_live.py` runs the real one."""
    rows = InMemoryListRows()
    body = b"estab_id,estab_name,region\nE1,HMP Synthetic One,\nE2,HMP Synthetic Two, \n"
    first, _ = import_own_list("ds-a", "rl-a", body, rows_kept=rows, named=["rl-a"],
                               name="establishments", key_column="estab_id")  # fmt: skip
    again, outcome = import_own_list("ds-a", "rl-a", body, rows_kept=rows, named=["rl-a"])
    assert (again.version, outcome) == (first.version, "unchanged")
    assert (rows.read(first) or [])[0]["region"] is None


async def test_a_name_two_readable_lists_share_is_offered_as_neither(root: Path) -> None:
    """Review item 15: the gate refuses a Lookup of a name two readable lists share; offering one
    of them would offer what the gate then refuses."""
    store, one, _two = await _two_lists(root)
    await store.subscribe("ds-a", one, "author-1")
    own_same_name = OWN_A.model_copy(update={"name": "Client list"})
    offered = await offered_lists("ds-a", store=store, own=[own_same_name])
    assert "Client list" not in {o.name for o in offered}


async def test_an_own_list_past_the_row_or_byte_cap_is_refused_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The orchestrator's second review (item 15): a dataset's own list is held to the same caps as
    a connector's read, refused whole and in words (rule 2)."""
    from services.ingest.connectors import reads

    rows = InMemoryListRows()
    body = b"estab_id,name\n" + b"".join(f"E{n},HMP {n}\n".encode() for n in range(10))
    monkeypatch.setattr(reads, "MAX_ROWS", 5)
    with pytest.raises(ListConnectorRefused, match="rows"):
        import_own_list("ds-a", "rl-a", body, rows_kept=rows, named=["rl-a"], name="e",
                        key_column="estab_id")  # fmt: skip
    monkeypatch.setattr(reads, "MAX_ROWS", 500_000)
    monkeypatch.setattr(reads, "MAX_BYTES", 40)
    with pytest.raises(ListConnectorRefused, match="bytes"):
        import_own_list("ds-a", "rl-a", body, rows_kept=rows, named=["rl-a"], name="e",
                        key_column="estab_id")  # fmt: skip
    assert rows.files == {}
