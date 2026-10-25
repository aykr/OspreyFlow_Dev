"""The export manifest says whether the case holds material the exporter may not view, and never how
much (ADR-124 decision 9; ADR-045).

`ExportManifest.withheld` is the exporter's standing sentence for the case: `True` or `False` under
`disclose`, never `None`; absent (`None`) under `omit`. It is computed as `DeltaSnapshot.withheld`
is (`WorkingSetService.withheld_for`, from the counted access index), on handling alone: a hidden
node's datasets play no part. The real routes and the real stores are `test_export_routes.py` and
`test_export.py`; this file runs `submit_export` over the working-set fakes, with no connection.
"""

from __future__ import annotations

from typing import Any

import pytest
from services.api.export import ExportItem, ExportRequest, submit_export
from services.api.working_set.service import WorkingSetService

from ontology.handling import load_uk_le_scheme
from schemas.domain import Handling, Principal, Subgraph

from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore
from .working_set.test_visible_link import node

SCHEME = load_uk_le_scheme()
CASE = "inv-1"
OFFICIAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
SECRET = Principal(id="analyst-2", clearance="SECRET", org_unit="unit-1")


class _Ledger:
    def __init__(self) -> None:
        self.entries: list[Any] = []

    async def record(self, entry: Any) -> None:
        self.entries.append(entry)


class _NoJudgements:
    """`submit_export` is given no judgement ids here, so nothing reads the store."""


def _request() -> ExportRequest:
    return ExportRequest(
        artefact_kind="subgraph",
        items=[
            ExportItem(
                id="pub",
                kind="node",
                handling=Handling(
                    classification="OFFICIAL",
                    handling_code="P",
                    originator="unit-1",
                    owning_unit="unit-1",
                ),
            )
        ],
        resolution_threshold=0.5,
    )


async def _export(
    store: FakeWorkingSetStore, reader: Principal, policy: str = "disclose"
) -> tuple[Any, _Ledger]:
    ledger = _Ledger()
    result = await submit_export(
        investigation_id=CASE,
        request=_request(),
        principal=reader,
        graph=FakeGraphPort(Subgraph(nodes=[], edges=[])),  # type: ignore[arg-type]
        scheme=SCHEME,
        judgements=_NoJudgements(),  # type: ignore[arg-type]
        ledger=ledger,  # type: ignore[arg-type]
        working_set=WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), store, SCHEME),
        manifest_policy=policy,  # type: ignore[arg-type]
    )
    return result, ledger


async def _store(*nodes: Any) -> FakeWorkingSetStore:
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, list(nodes))
    return store


async def test_a_reader_below_a_stored_items_marking_is_told_and_a_cleared_reader_is_not() -> None:
    """Violation caught: no flag, so an artefact reads as complete to a recipient when the case
    holds more than the exporter may view. True below the marking, false for a cleared reader."""
    store = await _store(node("pub"), node("sec", "SECRET"))
    below, _ = await _export(store, OFFICIAL)
    cleared, _ = await _export(store, SECRET)
    assert below.manifest.withheld is True
    assert cleared.manifest.withheld is False


async def test_an_empty_case_says_false_not_none() -> None:
    result, _ = await _export(await _store(), OFFICIAL)
    assert result.manifest.withheld is False


async def test_the_flag_is_equal_whatever_datasets_the_hidden_material_is_in() -> None:
    """Violation caught (ADR-099; rule 3): the judgement folded the datasets in, so the manifest
    would tell an exporter whether the hidden material sits in their own datasets: a signal about
    where it is. Two cases that differ only in the datasets of the hidden node give one answer, and
    it is true in both, as the node is hidden by its handling."""
    in_mine = await _store(
        node("pub"), node("sec", "SECRET").model_copy(update={"datasets": ["a"]})
    )
    elsewhere = await _store(
        node("pub"), node("sec", "SECRET").model_copy(update={"datasets": ["b"]})
    )
    reader = OFFICIAL.model_copy(update={"datasets": ["a"]})
    first, _ = await _export(in_mine, reader)
    second, _ = await _export(elsewhere, reader)
    assert first.manifest.withheld is True
    assert second.manifest.withheld is True


async def test_readable_material_in_another_dataset_is_not_withheld() -> None:
    """The other half: a readable node outside the reader's datasets is outside the case's world,
    not withheld from it (ADR-099), so the flag is false."""
    store = await _store(node("pub").model_copy(update={"datasets": ["b"]}))
    reader = OFFICIAL.model_copy(update={"datasets": ["a"]})
    result, _ = await _export(store, reader)
    assert result.manifest.withheld is False


@pytest.mark.parametrize("held_back", [True, False])
async def test_under_omit_the_manifest_has_no_flag_but_the_ledger_still_does(
    held_back: bool,
) -> None:
    """Under `omit` the artefact's manifest carries nothing (`None`); the ledger entry records the
    yes or no either way (ADR-045: audited in both modes), and a yes or no only."""
    store = await _store(node("pub"), *([node("sec", "SECRET")] if held_back else []))
    result, ledger = await _export(store, OFFICIAL, policy="omit")
    assert result.manifest.withheld is None
    (entry,) = ledger.entries
    assert entry.withheld is held_back


async def test_under_disclose_the_flag_is_never_none() -> None:
    for held in ([], [node("sec", "SECRET")]):
        result, ledger = await _export(await _store(node("pub"), *held), OFFICIAL)
        assert isinstance(result.manifest.withheld, bool)
        assert ledger.entries[0].withheld is result.manifest.withheld


async def test_the_manifest_and_the_ledger_hold_no_count() -> None:
    """Violation caught (decision 9): a count kept anywhere. Neither model has a field that holds
    one, and the serialised forms carry no `withheld_count`."""
    store = await _store(node("pub"), node("sec", "SECRET"))
    result, ledger = await _export(store, OFFICIAL)
    assert "withheld_count" not in result.manifest.model_dump()
    assert "withheld_count" not in ledger.entries[0].model_dump()
    assert set(result.manifest.model_dump()) == {"policy", "withheld"}
