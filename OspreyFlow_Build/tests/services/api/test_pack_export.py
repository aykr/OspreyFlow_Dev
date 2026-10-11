"""Exporting a published report pack (`06_DECISIONS.md` ADR-113 decision 6, through ADR-045/047):
the exporter's own access is checked again now, item by item; what they may not see is withheld and
counted under the manifest policy, never named; an exporter who may see nothing is refused and
nothing is recorded; an item needing its originator consulted needs a justification and a
reference; every allowed export is in the export ledger as `report_pack`. The ledger is the real one,
in Postgres; the rest are `test_packs.py`'s fakes.

What a mistake would do, and the case that catches it:
- an export above the exporter's handling — `test_an_exporter_who_may_see_no_item_is_refused_and_nothing_is_recorded`;
- the manifest carrying a withheld item, or the ledger missing the export —
  `test_the_manifest_names_only_what_the_exporter_may_see_and_the_ledger_records_it`;
- a withheld count printed when the deployment says omit — `test_under_omit_the_manifest_carries_no_withheld_count`;
- the originator's consent skipped — `test_an_item_needing_its_originator_needs_a_justification_and_a_reference`;
- exporting by a Reports Viewer or at Viewer — `test_exporting_needs_the_export_right_and_editor`;
- a withdrawn publication exported — `test_a_pack_with_no_live_publication_has_nothing_to_export`;
- the exporter or publisher printed as an account id when the directory names them (ADR-106) —
  `test_the_manifest_names_only_what_the_exporter_may_see_and_the_ledger_records_it`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from schemas.domain import Principal
from services.api.app import app, get_config, get_export_ledger
from services.api.config import PostgresConfig
from services.api.export import ExportLedgerEntry, ExportLedgerStore

from tests.services.api.test_packs import (
    CASE,
    CLEARED_READER,
    EDITOR,
    LEVELS,
    LOW_EDITOR,
    NO_LEVEL,
    READER,
    VIEWER,
    World,
    _add,
    _handling,
    _new_pack,
    _publish,
    world,  # noqa: F401 — `exporting` below wraps it
)

COMPLIANCE = Principal(id="compliance", clearance="SECRET", org_unit="unit-9", roles=["osprey-admin"])


async def _ledger() -> AsyncIterator[ExportLedgerStore]:
    store = await ExportLedgerStore.connect(PostgresConfig.from_env().dsn)
    try:
        yield store
    finally:
        await store.close()


@pytest.fixture
def exporting(world: World) -> Iterator[World]:  # noqa: F811 — the imported fixture, requested
    policy = SimpleNamespace(export_manifest_policy="disclose")
    app.dependency_overrides.update({get_export_ledger: _ledger, get_config: lambda: policy})
    world.policy = policy  # type: ignore[attr-defined]
    yield world


def _entries_since(since: datetime, who: str) -> list[ExportLedgerEntry]:
    import asyncio

    async def read() -> list[ExportLedgerEntry]:
        store = await ExportLedgerStore.connect(PostgresConfig.from_env().dsn)
        try:
            return [e for e in await store.list_all(COMPLIANCE) if e.exported_at >= since and e.principal_id == who]
        finally:
            await store.close()

    return asyncio.run(read())


def _export(w: World, pack: str, who: Principal, **body: Any) -> Any:
    return w.as_(who).post(f"{CASE}/packs/{pack}/export", json=body)


def test_an_exporter_who_may_see_no_item_is_refused_and_nothing_is_recorded(exporting: World) -> None:
    w = exporting
    since = datetime.now(UTC)
    pack = _new_pack(w)
    _add(w, pack, kind="note", text="secret", classification="SECRET")
    _publish(w, pack)
    refused = _export(w, pack, LOW_EDITOR)
    assert refused.status_code == 403 and refused.json()["error"] == "export_refused", refused.text
    assert "secret" not in refused.text
    assert _entries_since(since, LOW_EDITOR.id) == [], "nothing left the building, nothing recorded"


def test_the_manifest_names_only_what_the_exporter_may_see_and_the_ledger_records_it(exporting: World) -> None:
    w = exporting
    since = datetime.now(UTC)
    pack = _new_pack(w)
    official = _add(w, pack, kind="note", text="official", classification="OFFICIAL")
    secret = _add(w, pack, kind="note", text="secret", classification="SECRET")
    _add(w, pack, kind="note", text="sensitive", classification="OFFICIAL-SENSITIVE")
    _publish(w, pack)
    response = _export(w, pack, LOW_EDITOR)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [i["id"] for i in body["items"]] == [official["id"]] and secret["id"] not in response.text
    assert body["withheld"] == 2 and body["version"] == 1
    assert body["mark"]["handling_level"] == "OFFICIAL" and body["mark"]["pack_id"] == pack
    (entry,) = _entries_since(since, LOW_EDITOR.id)
    assert (entry.artefact_kind, entry.item_count, entry.withheld_count, entry.handling_level) == (
        "report_pack", 1, 2, "OFFICIAL")  # fmt: skip
    assert body["ledger_entry_id"] == entry.id
    assert (body["mark"]["exported_by_name"], body["published_by_name"]) == (None, "Edith Editor")
    whole = _export(w, pack, EDITOR).json()
    assert whole["withheld"] == 0 and whole["mark"]["handling_level"] == "SECRET"
    assert (whole["mark"]["exported_by"], whole["mark"]["exported_by_name"]) == ("ed", "Edith Editor")


def test_under_omit_the_manifest_carries_no_withheld_count(exporting: World) -> None:
    w = exporting
    w.policy.export_manifest_policy = "omit"  # type: ignore[attr-defined]
    pack = _new_pack(w)
    _add(w, pack, kind="note", text="official", classification="OFFICIAL")
    _add(w, pack, kind="note", text="secret", classification="SECRET")
    _publish(w, pack)
    body = _export(w, pack, LOW_EDITOR).json()
    assert body["withheld"] is None and body["policy"] == "omit"


def test_an_item_needing_its_originator_needs_a_justification_and_a_reference(exporting: World) -> None:
    w = exporting
    since = datetime.now(UTC)
    pack = _new_pack(w)
    w.graph.add("n-s2", _handling().model_copy(update={"sanitisation_code": "S2"}), "Harbour Street")
    _add(w, pack, kind="entity", node_id="n-s2", caption="The meeting place")
    _publish(w, pack)
    blocked = _export(w, pack, EDITOR)
    assert blocked.status_code == 422 and blocked.json()["error"] == "override_required", blocked.text
    assert [b["id"] for b in blocked.json()["blocked"]] == ["n-s2"]
    assert _export(w, pack, EDITOR, justification="Cleared by the owner").status_code == 422
    allowed = _export(w, pack, EDITOR, justification="Cleared by the owner", originator_reference="ORIG-12")
    assert allowed.status_code == 200, allowed.text
    (entry,) = _entries_since(since, EDITOR.id)
    assert entry.justification_given and entry.originator_reference_given


def test_exporting_needs_the_export_right_and_editor(exporting: World) -> None:
    w = exporting
    pack = _new_pack(w)
    _add(w, pack, kind="note", text="n", classification="OFFICIAL")
    _publish(w, pack)
    assert _export(w, pack, READER).status_code == 403, "a Reports Viewer reads, never exports"
    assert _export(w, pack, CLEARED_READER).status_code == 403
    assert _export(w, pack, VIEWER).status_code == 403, "the export right, but only Viewer"
    exporter_without_level = NO_LEVEL.model_copy(update={"roles": ["analyst"]})
    assert exporter_without_level.id not in LEVELS
    assert _export(w, pack, exporter_without_level).status_code == 404


def test_a_pack_with_no_live_publication_has_nothing_to_export(exporting: World) -> None:
    w = exporting
    pack = _new_pack(w)
    _add(w, pack, kind="note", text="n", classification="OFFICIAL")
    assert _export(w, pack, EDITOR).status_code == 404, "a draft is not exported"
    _publish(w, pack)
    w.as_(EDITOR).post(f"{CASE}/packs/{pack}/versions/1/withdraw", json={"reason": "wrong"})
    assert _export(w, pack, EDITOR).status_code == 404, "nor is a withdrawn publication"
